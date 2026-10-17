"""Maintenance agent: cham soc & nhac bao duong (CHI DOC, khong tu dat lich).

Chuc nang:
- Phan tich ODO + lich su sua chua (tools.analyze_vehicle_profile).
- Du doan moc bao duong (tools.predict_maintenance): theo KM **hoac** THOI GIAN
  (interval_months ke tu lan lam gan nhat / ngay mua).
- Nhac thay dau/lop/phanh/ac quy... (tools.maintenance_recommendations).
- Ca nhan hoa khuyen nghi cho tung xe.

Nguyen tac:
- Router khong ghi DB: khong tao lich hen/phieu sua chua.
- Khach chi xem duoc xe cua minh (anti-IDOR). Moi reply kem SAFETY_MAINTENANCE.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import User, Vehicle
from app.agents.base import call_gemini_safe, sanitize_llm_text, sanitize_llm_history
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call
from app.agents.common import (
    SAFETY_RULES_MAINTENANCE, SAFETY_MAINTENANCE, WEATHER_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import MaintenanceIn

router = APIRouter(prefix="/agent/maintenance", tags=["Maintenance Agent"])

STAFF_ROLES = ("technician", "manager", "admin")


def _db_user(db: Session, user: dict) -> User | None:
    return db.query(User).filter(User.username == user.get("sub")).first()


def _resolve_vehicle(db: Session, user: dict, db_user: User, data: MaintenanceIn):
    role = user.get("role")
    if data.vehicle_id is not None:
        q = db.query(Vehicle).filter(Vehicle.id == data.vehicle_id)
        if role not in STAFF_ROLES:
            q = q.filter(Vehicle.user_id == db_user.id)
        car = q.first()
        if car is None:
            raise HTTPException(
                status_code=403 if role not in STAFF_ROLES else 404,
                detail="Xe này không thuộc tài khoản của bạn."
                if role not in STAFF_ROLES else "Không tìm thấy xe.")
        return car
    if role in STAFF_ROLES:
        return T.find_vehicle_by_plate(db, data.message)
    car = T.find_vehicle_by_plate(db, data.message, db_user.id)
    if car is None:
        own = T.get_my_vehicles(db, db_user.id)
        if len(own) == 1:
            car = own[0]
    return car


@router.post("/chat", dependencies=[
    Depends(require_roles([Role.CUSTOMER, Role.TECHNICIAN, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def maintenance_chat(data: MaintenanceIn, db: Session = Depends(get_db),
                           user: dict = Depends(get_current_user)):
    question = sanitize_llm_text(data.message).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")
    db_user = _db_user(db, user)
    if not db_user:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản.")
    uid = db_user.id
    low = question.lower()

    car = _resolve_vehicle(db, user, db_user, data)
    out: dict = {}
    ctx = []

    if car is None:
        out["needs"] = ["xe (nêu biển số, VD: 30E-222.33)"]
        ctx.append("CÒN THIẾU: xe (nêu biển số). Hãy hỏi lại ngắn gọn.")
    else:
        profile = T.analyze_vehicle_profile(db, car.id)
        plan = T.predict_maintenance(db, car.id)
        recs = T.maintenance_recommendations(db, car.id)
        out["profile"] = profile
        out["plan"] = plan
        out["recommendations"] = recs

        v = profile["vehicle"]
        ctx.append("XE ĐANG XÉT: {} {} {} (biển {}) — ODO {} km.".format(
            v.get("make") or "?", v.get("model") or "?", v.get("year") or "?",
            v.get("plate"), v.get("odo")))
        if profile["history"]:
            ctx.append("LỊCH SỬ SỬA CHỮA:\n" + "\n".join(
                f"- #{h['id']} [{h['status']}] {h['created']}: {h['symptoms']}"
                for h in profile["history"]))
        else:
            ctx.append("LỊCH SỬ SỬA CHỮA: (chưa có)")
        ctx.append("TỔNG SỐ PHIẾU: {}.".format(profile.get("total_orders", 0)))

        def _remain_txt(it):
            txt = "{:,} km".format(it["km_remaining"])
            if it.get("months_remaining") is not None:
                txt += " / {:.1f} tháng".format(it["months_remaining"])
            return txt

        ctx.append("MỐC BẢO DƯỠNG (ODO {:,} km): ".format(v.get("odo") or 0) + "; ".join(
            "{}: {} (còn {})".format(
                it["label"],
                {"overdue": "QUÁ HẠN", "due_soon": "sắp tới hạn",
                 "ok": "còn tốt"}[it["status"]],
                _remain_txt(it))
            for it in plan["items"]))
        if recs:
            ctx.append("KHUYẾN NGHỊ: " + "; ".join(
                "{}{}{}".format(
                    r["label"], f" — {r['reason']}",
                    f" (dịch vụ: {r['service']['name']} {r['service']['price']:,}đ)"
                    if r["service"] else "")
                for r in recs))

    rag = T.search_knowledge(question)
    weather = T.get_weather_context(db)
    weather_txt = weather if any(k in low for k in WEATHER_KEYS) else ""
    name = user.get("name") or db_user.full_name or "bạn"

    system_prompt = (
        f"Bạn là AI Chăm sóc & Nhắc bảo dưỡng của garage ThreeH Workshop, hỗ trợ {name} "
        f"ngắn gọn, cá nhân hóa theo xe. KHÔNG tự đặt lịch — chỉ nhắc và gợi ý.\n"
        f"Câu hỏi: {question}\n"
        + (chr(10).join(ctx) + "\n" if ctx else "")
        + (f"TÀI LIỆU NỘI BỘ:\n{rag}\n" if rag else "")
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + SAFETY_RULES_MAINTENANCE
    )

    started = time.perf_counter()
    result = call_gemini_safe(
        message=system_prompt, context_msg="Ho tro cham soc va nhac bao duong",
        history=sanitize_llm_history(data.history))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="maintenance", user_id=uid,
                       vehicle_id=car.id if car else None,
                       prompt_len=len(system_prompt), ok=False,
                       latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="maintenance", user_id=uid,
                   vehicle_id=car.id if car else None,
                   prompt_len=len(system_prompt), ok=True, latency_ms=latency_ms)

    out["message"] = result["message"] + SAFETY_MAINTENANCE
    out["question"] = question
    return out
