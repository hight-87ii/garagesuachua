from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json as _json
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import User, Vehicle
from app.agents.base import (
    call_gemini_safe, extract_plate_mention, sanitize_llm_text,
    sanitize_llm_history,
)
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call
from app.services import gemini_service as _gemini_service
from app.agents.common import (
    suggest_services, estimate_range,
    SAFETY_RULES_CUSTOMER, SAFETY_CUSTOMER,
    WEATHER_KEYS, PRICE_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import ChatIn

router = APIRouter(prefix="/agent/customer", tags=["Customer Agent"])


def _db_user_id(db: Session, user: dict) -> int | None:
    u = db.query(User).filter(User.username == user.get("sub")).first()
    return u.id if u else None


async def _prepare_customer_chat(db: Session, user: dict, data: ChatIn):
    """Build prompt + metadata chung cho /chat (JSON) va /chat/stream (NDJSON).
    Tra (question, system_prompt, history, out, car, uid)."""
    question = sanitize_llm_text(data.message).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")
    uid = _db_user_id(db, user)
    if not uid:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản.")

    ctx_blocks, out = [], {}
    low = question.lower()

    # 1. Xe của tôi + lịch sử (ưu tiên vehicle_id tường minh, rồi biển số trong câu)
    cars = T.get_my_vehicles(db, uid)
    cars_d = [T.vehicle_to_dict(v) for v in cars]
    out["vehicles"] = cars_d
    car = None
    if data.vehicle_id is not None:
        car = db.query(Vehicle).filter(
            Vehicle.id == data.vehicle_id, Vehicle.user_id == uid).first()
        if car is None:
            raise HTTPException(status_code=403, detail="Xe này không thuộc tài khoản của bạn.")
    if car is None:
        car = T.find_vehicle_by_plate(db, question, uid)
    plate_mention = extract_plate_mention(question)
    if car is None and plate_mention:
        # Nêu biển số lạ: báo rõ không thuộc tài khoản, không đoán bừa xe khác
        ctx_blocks.append(
            f"Khách nhắc tới biển số {plate_mention} nhưng xe này KHÔNG thuộc tài khoản. "
            "Hãy nói rõ điều đó và hỏi lại (VD: nhờ kiểm tra biển số hoặc chọn trong danh sách xe của khách).")
    elif car is None and len(cars) == 1 and any(
            k in low for k in ["xe của tôi", "xe toi", "lịch sử", "lich su", "bảo dưỡng", "bao duong"]):
        car = db.query(Vehicle).filter_by(user_id=uid).first()
    if car:
        hist = T.get_vehicle_history(db, car.id)
        out["vehicle"] = {"id": car.id, "plate": car.license_plate,
                          "make": car.make, "model": car.model}
        out["history"] = hist
        lines = [f"- #{h['id']} [{h['status']}] {h['created']}: {h['symptoms']} (công {h['labor']:,}đ)"
                 for h in hist]
        ctx_blocks.append("XE ĐANG XÉT: {} {} {} (biển {})\nLỊCH SỬ SỬA CHỮA:\n{}".format(
            car.make, car.model, car.id, car.license_plate,
            "\n".join(lines) if lines else "(chưa có)"))

    # 2. Hóa đơn của tôi
    if any(k in low for k in ["hóa đơn", "hoa don", "thanh toán", "thanh toan", "công nợ", "cong no", "tiền", "tien"]):
        invs = T.get_my_invoices(db, uid)
        out["invoices"] = invs
        ctx_blocks.append("HÓA ĐƠN CỦA KHÁCH:\n" + ("\n".join(
            f"- HD-{i['id']} ({i['plate']}, {i['created']}): {i['total']:,}đ — {i['status']}"
            for i in invs) if invs else "(chưa có hóa đơn)"))

    # 3. Lịch hẹn của tôi + ý định đặt lịch
    booking = T.wants_booking(question)
    if booking or any(k in low for k in ["lịch hẹn", "lich hen", "lịch", "lich", "hẹn", "hen"]):
        appts = T.get_my_appointments(db, uid)
        out["appointments"] = appts
        ctx_blocks.append("LỊCH HẸN HIỆN CÓ:\n" + ("\n".join(
            f"- #{a['id']} {a['date']} {a['time'] or ''} ({a['plate']}) — {a['status']}"
            for a in appts) if appts else "(chưa có lịch hẹn)"))
    draft, needs, blocked = None, [], []
    if booking:
        v = car or (db.query(Vehicle).filter_by(user_id=uid).first() if len(cars) == 1 else None)
        d = T.parse_vi_date(question)
        t = T.parse_time(question)
        if v is None:
            needs.append("xe (nêu biển số, VD: 30E-222.33)")
        if d is None:
            needs.append("ngày hẹn (VD: ngày mai, thứ 2, 15/10)")
        if not needs:
            try:
                draft = T.create_appointment_draft(
                    db, uid, v.id, d, t, symptoms=question)
            except ValueError as e:
                # Loi nghiep vu (ngay nghi / gio ngoai khung / KTV sai) -> chan;
                # loi thieu/ngay qua khu -> hoi lai.
                msg = str(e)
                if any(k in msg for k in ("nghỉ", "Khung giờ", "Kỹ thuật viên")):
                    blocked.append(msg)
                else:
                    needs.append(msg)
                draft = None
            if draft and draft.get("blocked"):
                # Chan dat lich vao khung da kin / KTV da ban (1 nguon: tools).
                blocked = draft.get("reasons") or ["Khung giờ đã kín."]
                draft = None
            elif draft:
                out["draft"] = draft
                when = (f" giờ {draft['time']}" if draft["time"] else " (chưa chốt giờ)")
                if draft.get("duplicate"):
                    ctx_blocks.append(
                        "LỊCH ĐÃ TỒN TẠI #{}: xe {} ngày {}{} (Pending, chưa xác nhận) — "
                        "KHÔNG tạo trùng. Dặn khách vào Đặt lịch hẹn để xem lại/xác nhận.".format(
                            draft["id"], draft["plate"], draft["date"], when))
                else:
                    ctx_blocks.append(
                        "ĐÃ TẠO LỊCH NHÁP #{}: xe {} ngày {}{} (trạng thái Pending, CHƯA xác nhận). "
                        "Dặn khách vào Đặt lịch hẹn để xem lại/xác nhận.".format(
                            draft["id"], draft["plate"], draft["date"], when))
        if blocked:
            out["blocked"] = blocked
            closed = any("nghỉ" in b for b in blocked)
            out["needs"] = ["ngày khác"] if closed else ["khung giờ khác"]
            if closed:
                ctx_blocks.append("KHÔNG THỂ ĐẶT LỊCH: " + "; ".join(blocked)
                                  + " Hãy mời khách chọn NGÀY KHÁC.")
            else:
                ctx_blocks.append("KHÔNG THỂ ĐẶT LỊCH: " + "; ".join(blocked)
                                  + " Hãy mời khách chọn khung giờ khác — KHÔNG tạo lịch "
                                  "vào chỗ đã kín.")
        elif needs and not draft:
            out["needs"] = needs
            ctx_blocks.append("Khách muốn đặt lịch nhưng còn thiếu: " + ", ".join(needs)
                              + ". Hãy hỏi lại đúng các thông tin còn thiếu, ngắn gọn.")

    # 4. Dịch vụ gợi ý + ước tính (luôn tính từ DB cho out;
    # prompt gon: catalog chi kem khi khach hoi gia).
    services = suggest_services(db, question)
    out["suggestions"] = services
    out["estimate"] = estimate_range(services)
    catalog = "\n".join(
        f"- {s['name']} ({s['category'] or 'chung'}): {s['price']:,}đ"
        f"{' (khuyến mãi)' if s['promo'] else ''}" for s in services
    ) if services else "(chưa khớp dịch vụ nào)"
    rag = T.search_knowledge(question)
    weather = T.get_weather_context(db)
    name = user.get("name") or "bạn"

    # Prompt gon + thu tu co dinh: Cau hoi -> XE -> LICH SU -> RAG -> DANH MUC
    # (chi khi hoi gia) -> THOI TIET (chi khi lien quan) -> SAFETY cuoi.
    weather_txt = weather if any(k in low for k in WEATHER_KEYS) else ""
    catalog_txt = catalog if any(k in low for k in PRICE_KEYS) else "(bỏ qua danh mục)"
    cars_txt = (chr(10).join(
        f"- {c['plate']} · {c['make']} {c['model']} (ODO {c['odo'] or '—'})"
        for c in cars_d) if cars_d else "(chưa có xe)")

    system_prompt = (
        f"Bạn là Customer Service AI của garage ThreeH Workshop, tư vấn cho khách hàng {name} thân thiện, ngắn gọn.\n"
        f"Câu hỏi: {question}\n"
        f"XE:\n{cars_txt}\n"
        f"LỊCH SỬ:\n{chr(10).join(ctx_blocks) if ctx_blocks else '(chưa có ngữ cảnh)'}\n"
        + (f"TÀI LIỆU NỘI BỘ:\n{rag}\n" if rag else "")
        + f"DANH MỤC (chỉ khi hỏi giá): {catalog_txt}\n"
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + SAFETY_RULES_CUSTOMER
    )

    history = sanitize_llm_history(data.history)
    out["question"] = question
    return question, system_prompt, history, out, car, uid


@router.post("/chat", dependencies=[
    Depends(require_roles([Role.CUSTOMER, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def customer_support(data: ChatIn, db: Session = Depends(get_db),
                           user: dict = Depends(get_current_user)):
    question, system_prompt, history, out, car, uid = await _prepare_customer_chat(
        db, user, data)

    started = time.perf_counter()
    result = call_gemini_safe(message=system_prompt, context_msg="Ho tro khach hang garage",
                            history=history)
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="customer", user_id=uid,
                       vehicle_id=car.id if car else None,
                       prompt_len=len(system_prompt), ok=False,
                       latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="customer", user_id=uid,
                   vehicle_id=car.id if car else None,
                   prompt_len=len(system_prompt), ok=True,
                   latency_ms=latency_ms)
    out["message"] = result["message"] + SAFETY_CUSTOMER
    return out


@router.post("/chat/stream", dependencies=[
    Depends(require_roles([Role.CUSTOMER, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def customer_support_stream(data: ChatIn, db: Session = Depends(get_db),
                                  user: dict = Depends(get_current_user)):
    """Stream NDJSON cho UI (ai_assistant + chatbox): 1 event meta (JSON cau truc:
    suggestions/estimate/draft/needs/...) roi cac event delta (text chay dan),
    ket thuc bang done. Dung chung _prepare_customer_chat + call_gemini_safe
    stream nen chi 1 lan goi Gemini, khong fork logic."""
    question, system_prompt, history, out, car, uid = await _prepare_customer_chat(
        db, user, data)
    if _gemini_service.client is None:
        raise HTTPException(status_code=503, detail=_gemini_service.NO_KEY_MSG)

    started = time.perf_counter()

    def gen():
        ok = True
        try:
            yield _json.dumps({"type": "meta", "data": out},
                              ensure_ascii=False, default=str) + "\n"
            for chunk in call_gemini_safe(
                    message=system_prompt, context_msg="Ho tro khach hang garage",
                    history=history, stream=True):
                yield _json.dumps({"type": "delta", "text": chunk},
                                  ensure_ascii=False) + "\n"
            yield _json.dumps({"type": "delta", "text": SAFETY_CUSTOMER},
                              ensure_ascii=False) + "\n"
            yield _json.dumps({"type": "done"}, ensure_ascii=False) + "\n"
        except Exception:
            ok = False
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            log_agent_call(agent="customer", user_id=uid,
                           vehicle_id=car.id if car else None,
                           prompt_len=len(system_prompt), ok=ok,
                           latency_ms=latency_ms,
                           error=None if ok else "stream")

    return StreamingResponse(gen(), media_type="application/x-ndjson")
