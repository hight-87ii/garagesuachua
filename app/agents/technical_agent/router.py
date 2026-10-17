from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import User
from app.agents.base import call_gemini_safe, sanitize_llm_text, sanitize_llm_history
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call, mask_sensitive_id
from app.agents.common import (
    suggest_parts, suggest_services, estimate_range,
    SAFETY_RULES_TECHNICAL, SAFETY_TECHNICAL,
    WEATHER_KEYS, PRICE_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import DiagnoseIn

router = APIRouter(prefix="/agent/technical", tags=["Technical Agent"])

logger = logging.getLogger("threeh.agents")


def _db_user_id(db: Session, user: dict) -> int | None:
    u = db.query(User).filter(User.username == user.get("sub")).first()
    return u.id if u else None


@router.post("/diagnose", dependencies=[
    Depends(require_roles([Role.TECHNICIAN, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def diagnose_vehicle(data: DiagnoseIn, db: Session = Depends(get_db),
                           user: dict = Depends(get_current_user)):
    symptom = sanitize_llm_text(data.symptom).strip()
    if not symptom:
        raise HTTPException(status_code=400, detail="Thiếu triệu chứng xe.")
    uid = _db_user_id(db, user)

    out = {}

    # 1. Xe theo biển số + TOÀN BỘ lịch sử RepairOrder (mọi trạng thái)
    # Ưu tiên license_plate tường minh, fallback parse biển số trong symptom.
    # Chuan hoa: upper().strip(), giu - . de detect_vehicle tu normalize.
    car = None
    plate = (data.license_plate or "").strip().upper() or None
    if plate:
        car = T.find_vehicle_by_plate(db, plate)
    if car is None:
        car = T.find_vehicle_by_plate(db, symptom)
    if car:
        # Audit: KTV duoc xem moi xe (khong gioi han user) -> log mask/hash, không lộ biển số thô.
        logger.info("technical diagnose user_id=%s vehicle_id=%s plate_ref=%s",
                    uid, car.id, mask_sensitive_id(car.license_plate))
        hist = T.get_vehicle_history(db, car.id, limit=5, status=None)
        out["vehicle"] = {"id": car.id, "plate": car.license_plate,
                          "make": car.make, "model": car.model,
                          "odo": car.current_odo}
        out["history"] = hist
        lines = [f"- #{h['id']} [{h['status']}] {h['created']}: {h['symptoms']} "
                 f"| xử lý: {h['inspection'] or '—'} (công {h['labor']:,}đ) | sao: {h['rating'] or '—'}"
                 for h in hist]
        xe_txt = "{} {} (biển {}, ODO {})".format(
            car.make, car.model, car.license_plate, car.current_odo or "—")
        history_txt = (
            "XE ĐANG XÉT: {} {} {} (biển {}, ODO {})\nTOÀN BỘ LỊCH SỬ REPAIRORDER:\n{}".format(
                car.make, car.model, car.id, car.license_plate,
                car.current_odo or "—",
                "\n".join(lines) if lines else "(chưa có lịch sử)"))
    else:
        xe_txt = "(chưa xác định được xe)"
        history_txt = ("(Không xác định được biển số trong mô tả — phân tích chung, "
                       "không gắn với lịch sử xe cụ thể.)")

    # 2. Phụ tùng còn hàng + dịch vụ Active (luôn tính từ DB cho out;
    # prompt gon: danh muc chi kem khi hoi gia).
    parts = suggest_parts(db, symptom)
    services = suggest_services(db, symptom)
    out["parts"] = parts
    out["services"] = services
    out["estimate"] = estimate_range(parts + [s for s in services])
    parts_all = "\n".join(
        f"- {p['name']} (mã {p['part_number'] or '—'}, {p['brand'] or 'không rõ hãng'}): "
        f"{p['price']:,}đ, tồn {p['stock']}"
        for p in parts) if parts else "(không khớp phụ tùng còn hàng)"
    svc_all = "\n".join(
        f"- {s['name']}: {s['price']:,}đ" for s in services
    ) if services else "(không khớp dịch vụ)"

    weather = T.get_weather_context(db)
    rag = T.search_knowledge(symptom)
    slow = symptom.lower()
    parts_txt = parts_all if any(k in slow for k in PRICE_KEYS) else "(bỏ qua danh mục)"
    svc_txt = svc_all if any(k in slow for k in PRICE_KEYS) else "(bỏ qua danh mục)"
    weather_txt = weather if any(k in slow for k in WEATHER_KEYS) else ""

    # Prompt gon + thu tu co dinh: Trieu chung -> XE -> LICH SU -> RAG ->
    # DANH MUC (chi khi hoi gia) -> THOI TIET (chi khi lien quan) ->
    # YEU CAU -> SAFETY_RULES_TECHNICAL dong cuoi (nguyen van).
    prompt = (
        f"Bạn là AI Cố vấn Kỹ thuật tại garage ThreeH Workshop, hỗ trợ thợ {user.get('name') or ''}.\n"
        "Hãy chú ý xem thời tiết (ngập nước, nắng gắt, độ ẩm cao) có thể là nguyên nhân gây triệu chứng không.\n"
        f"Triệu chứng: {symptom}\n"
        f"XE: {xe_txt}\n"
        f"LỊCH SỬ:\n{history_txt}\n"
        + (f"TÀI LIỆU NỘI BỘ LIÊN QUAN:\n{rag}\n" if rag else "")
        + "DANH MỤC (chỉ khi hỏi giá):\n"
        + "LINH KIỆN CÒN HÀNG TRONG KHO (giá thật, VNĐ):\n"
        + f"{parts_txt}\n"
        + "DỊCH VỤ ĐANG KINH DOANH LIÊN QUAN (giá thật, VNĐ):\n"
        + f"{svc_txt}\n"
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + "YÊU CẦU TRẢ LỜI: xếp hạng các khả năng theo xác suất, mỗi khả năng kèm CÁCH KIỂM CHỨNG cụ thể, rồi đề xuất linh kiện/dịch vụ phù hợp từ danh mục trên kèm báo giá SƠ BỘ (ghi rõ chưa gồm công thợ và VAT).\n"
        + SAFETY_RULES_TECHNICAL
    )

    started = time.perf_counter()
    result = call_gemini_safe(message=prompt, context_msg="Ho tro ky thuat vien chan doan",
                            history=sanitize_llm_history(data.history))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="technical", user_id=uid,
                       vehicle_id=car.id if car else None,
                       prompt_len=len(prompt), ok=False,
                       latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="technical", user_id=uid,
                   vehicle_id=car.id if car else None,
                   prompt_len=len(prompt), ok=True,
                   latency_ms=latency_ms)
    out["message"] = result["message"] + SAFETY_TECHNICAL
    out["symptom"] = symptom
    return out
