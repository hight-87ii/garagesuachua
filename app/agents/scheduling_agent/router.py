"""Scheduling & Reception agent: lich hen + tiep nhan.

Chuc nang:
- Kiem tra khung gio trong (get_available_slots).
- Goi y ky thuat vien phu hop (suggest_technicians).
- Phat hien trung lich / qua tai (detect_schedule_conflicts).
- Tao lich NHAO de khach xac nhan (create_appointment_draft, status Pending).
- Chuyen lich hen thanh phieu sua chua (convert_appointment_to_order, idempotent).

An toan:
- Lich AI tao CHI o trang thai Pending; AI khong tu xac nhan.
- KHONG dat lich khi khung gio da kin hoac KTV da ban dung khung do
  (create_appointment_draft tra {"blocked": True}).
- Xac minh truong truc tiep tu client: data.time phai thuoc WORK_SLOTS,
  data.preferred_technician_id phai la KTV hop le (=> 400), chan ngay nghi.
- create_appointment_draft dung BOOKING_LOCK: 2 request dong thoi khong the
  cung dat vao 1 khung chi con 1 cho.
- Chuyen lich chi khi co yeu cau ro (appointment_id tuong minh hoac y dinh
  trong cau + ma #id); khach chi thao tac tren lich cua chinh minh.
- Moi cau tra loi kem SAFETY_SCHEDULING.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import re
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import Appointment, User, Vehicle
from app.agents.base import call_gemini_safe, sanitize_llm_text, sanitize_llm_history
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call
from app.agents.common import (
    SAFETY_RULES_SCHEDULING, SAFETY_SCHEDULING,
    WEATHER_KEYS, SLOT_KEYS, SCHEDULE_TECH_KEYS, CONVERT_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import ScheduleIn

router = APIRouter(prefix="/agent/scheduling", tags=["Scheduling Agent"])

STAFF_ROLES = ("technician", "manager", "admin")
_APPT_ID_RE = re.compile(r"#\s*(\d{1,7})")


def _db_user(db: Session, user: dict) -> User | None:
    return db.query(User).filter(User.username == user.get("sub")).first()


def _resolve_vehicle(db: Session, user: dict, db_user: User, data: ScheduleIn):
    """Xe dang xet: vehicle_id tuong minh (khach: phai so huu) hoac bien so
    trong cau. Tra Vehicle hoac None."""
    role = user.get("role")
    if data.vehicle_id is not None:
        q = db.query(Vehicle).filter(Vehicle.id == data.vehicle_id)
        if role not in STAFF_ROLES:
            q = q.filter(Vehicle.user_id == db_user.id)
        car = q.first()
        if car is None:
            raise HTTPException(status_code=403,
                                detail="Xe này không thuộc tài khoản của bạn.")
        return car
    if role in STAFF_ROLES:
        return T.find_vehicle_by_plate(db, data.message)
    return T.find_vehicle_by_plate(db, data.message, db_user.id)


def _parse_appt_id(data: ScheduleIn) -> int | None:
    if data.appointment_id is not None:
        return data.appointment_id
    m = _APPT_ID_RE.search(data.message or "")
    return int(m.group(1)) if m else None


@router.post("/chat", dependencies=[
    Depends(require_roles([Role.CUSTOMER, Role.TECHNICIAN, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def scheduling_chat(data: ScheduleIn, db: Session = Depends(get_db),
                          user: dict = Depends(get_current_user)):
    question = sanitize_llm_text(data.message).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")
    db_user = _db_user(db, user)
    if not db_user:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản.")

    role = user.get("role") or "customer"
    uid = db_user.id
    low = question.lower()

    # Xac minh truong truyen TRUC TIEP tu client (giao dien) — khong tin du lieu tho.
    if data.time and not T.is_valid_slot(data.time):
        raise HTTPException(status_code=400, detail=(
            f"Khung giờ '{data.time}' không hợp lệ. Chọn: " + ", ".join(T.WORK_SLOTS) + "."))
    if data.preferred_technician_id is not None \
            and not T.is_valid_technician(db, data.preferred_technician_id):
        raise HTTPException(
            status_code=400,
            detail="Kỹ thuật viên không tồn tại hoặc không phải kỹ thuật viên.")

    date_str = data.date or T.parse_vi_date(question)
    time_str = data.time or T.parse_time(question)
    car = _resolve_vehicle(db, user, db_user, data)
    off_reason = T.day_off_reason(date_str) if date_str else None

    booking = T.wants_booking(question)
    wants_slots = any(k in low for k in SLOT_KEYS) or booking
    wants_tech = any(k in low for k in SCHEDULE_TECH_KEYS) or booking or wants_slots

    out: dict = {"date": date_str, "time": time_str}
    if off_reason:
        out["closed"] = off_reason
    ctx = []

    # 1. Khung gio trong
    slots = T.get_available_slots(db, date_str) if date_str else None
    if slots is not None and not off_reason:
        out["available_slots"] = slots

    # 2. KTV goi y
    techs = T.suggest_technicians(db, date_str, time_str)
    out["technicians"] = techs

    # 3. Trung lich / qua tai
    conflicts = T.detect_schedule_conflicts(
        db, date_str, time_str,
        technician_id=data.preferred_technician_id,
        vehicle_id=car.id if car else None)
    out["conflicts"] = conflicts

    if car:
        out["vehicle"] = {"id": car.id, "plate": car.license_plate,
                          "make": car.make, "model": car.model}

    if date_str:
        ctx.append(f"NGÀY HẸN: {date_str}" + (f", GIỜ: {time_str}" if time_str else ""))
    if off_reason:
        ctx.append("NGÀY NGHỈ: " + off_reason + " Không nhận lịch ngày này.")
    if slots is not None and wants_slots and not off_reason:
        ctx.append("KHUNG GIỜ TRỐNG: " + (", ".join(slots["free"]) or "(hết chỗ)")
                   + " | ĐÃ KÍN: " + (", ".join(slots["busy"]) or "(không)"))
    if wants_tech and techs:
        ctx.append("KTV GỢI Ý: " + "; ".join(
            f"{t['name']} (đang {t['in_progress']} xe"
            + (", bận khung này" if t["busy_at_slot"] else ", rảnh khung này") + ")"
            for t in techs))
    if conflicts.get("has_conflict"):
        # Luon neu ro trung lich/qua tai khi co, du nguoi dung khong hoi truc tiep.
        ctx.append("CẢNH BÁO XUNG ĐỘT: " + "; ".join(conflicts["reasons"]))
    if car:
        ctx.append(f"XE ĐANG XÉT: {car.make} {car.model} (biển {car.license_plate})")

    # 4. Tao lich NHAP (khach xac nhan) — CHAN khi khung kin / KTV ban khung do.
    draft, needs = None, []
    blocked_reasons = []
    if booking:
        v = car
        if v is None:
            own = T.get_my_vehicles(db, uid)
            v = own[0] if len(own) == 1 else None
        if v is None:
            needs.append("xe (nêu biển số, VD: 30E-222.33)")
        if not date_str:
            needs.append("ngày hẹn (VD: ngày mai, thứ 2, 15/10)")
        if v is not None and date_str and not needs and off_reason:
            # Ngay xuong nghi -> khong tao lich, bao ro ly do.
            blocked_reasons = [off_reason]
        elif v is not None and date_str and not needs:
            # Khach chi dat cho xe cua minh; nhan vien dat ho chu xe.
            owner_id = v.user_id if role in STAFF_ROLES else uid
            try:
                draft = T.create_appointment_draft(
                    db, owner_id, v.id, date_str, time_str,
                    symptoms=question,
                    preferred_technician_id=data.preferred_technician_id)
            except ValueError as e:
                needs.append(str(e))
                draft = None
            if draft and draft.get("blocked"):
                blocked_reasons = draft.get("reasons") or ["Khung giờ đã kín."]
                draft = None
            elif draft:
                out["draft"] = draft
                when = (f" giờ {draft['time']}" if draft["time"] else " (chưa chốt giờ)")
                if draft.get("duplicate"):
                    ctx.append(
                        "LỊCH ĐÃ TỒN TẠI #{}: xe {} ngày {}{} (Pending, CHƯA xác nhận) — "
                        "KHÔNG tạo trùng. Hãy xác nhận lịch này hoặc chọn giờ khác.".format(
                            draft["id"], draft["plate"], draft["date"], when))
                else:
                    ctx.append(
                        "ĐÃ TẠO LỊCH NHÁP #{}: xe {} ngày {}{} (trạng thái Pending, CHƯA xác nhận). "
                        "Hãy yêu cầu khách/nhân viên xác nhận.".format(
                            draft["id"], draft["plate"], draft["date"], when))
    if blocked_reasons:
        out["blocked"] = blocked_reasons
        is_closed = off_reason in blocked_reasons
        out["needs"] = ["ngày khác"] if is_closed else ["khung giờ khác hoặc kỹ thuật viên khác"]
        if is_closed:
            ctx.append("KHÔNG THỂ ĐẶT LỊCH: " + "; ".join(blocked_reasons)
                       + " Hãy đề nghị khách chọn NGÀY KHÁC.")
        else:
            ctx.append("KHÔNG THỂ ĐẶT LỊCH: " + "; ".join(blocked_reasons)
                       + " Hãy mời chọn khung giờ trống khác (xem KHUNG GIỜ TRỐNG) "
                       "hoặc KTV khác — KHÔNG tạo lịch vào chỗ đã kín.")
    elif needs and not draft:
        out["needs"] = needs
        ctx.append("CÒN THIẾU: " + ", ".join(needs) + ". Hãy hỏi lại ngắn gọn.")

    # 5. Chuyen lich hen thanh phieu sua chua
    appt_id = _parse_appt_id(data)
    wants_convert = any(k in low for k in CONVERT_KEYS) or data.appointment_id is not None
    if wants_convert and appt_id:
        convert_error = None
        try:
            appt = db.query(Appointment).filter(Appointment.id == appt_id).first()
            if not appt:
                convert_error = "Không tìm thấy lịch hẹn."
            elif role not in STAFF_ROLES and appt.user_id != uid:
                raise HTTPException(
                    status_code=403,
                    detail="Lịch hẹn này không thuộc tài khoản của bạn.")
            else:
                order = T.convert_appointment_to_order(
                    db, appt_id, technician_id=data.preferred_technician_id)
                out["order"] = order
                ctx.append(
                    "ĐÃ CHUYỂN THÀNH PHIẾU SỬA CHỮA #{} (từ lịch #{}): xe {}, "
                    "trạng thái {}, KTV {}.".format(
                        order["id"], order["appointment_id"], order["plate"],
                        order["status"], order["technician_id"] or "(chưa phân công)"))
        except ValueError as e:
            convert_error = str(e)
        if convert_error:
            out["convert_error"] = convert_error
            ctx.append("KHÔNG THỂ CHUYỂN LỊCH: " + convert_error)
    elif wants_convert and not appt_id:
        needs.append("mã lịch hẹn (#id) để chuyển thành phiếu")
        out["needs"] = needs
        ctx.append("CÒN THIẾU: mã lịch hẹn (#id) để chuyển thành phiếu sửa chữa.")

    # Prompt gon: Cai hoi -> NGAY -> KHUNG GIO -> KTV -> XUNG DOT -> XE
    # -> KET QUA (nhap/phieu) -> RAG -> THOI TIET -> SAFETY cuoi.
    rag = T.search_knowledge(question)
    weather = T.get_weather_context(db)
    weather_txt = weather if any(k in low for k in WEATHER_KEYS) else ""
    name = user.get("name") or db_user.full_name or "bạn"

    system_prompt = (
        f"Bạn là AI Lịch hẹn & Tiếp nhận của garage ThreeH Workshop, hỗ trợ {name} "
        f"({role}) ngắn gọn, đúng dữ liệu.\n"
        f"Câu hỏi: {question}\n"
        + (chr(10).join(ctx) + "\n" if ctx else "")
        + (f"TÀI LIỆU NỘI BỘ:\n{rag}\n" if rag else "")
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + SAFETY_RULES_SCHEDULING
    )

    started = time.perf_counter()
    result = call_gemini_safe(
        message=system_prompt, context_msg="Ho tro lich hen va tiep nhan garage",
        history=sanitize_llm_history(data.history))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="scheduling", user_id=uid,
                       vehicle_id=car.id if car else None,
                       prompt_len=len(system_prompt), ok=False,
                       latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="scheduling", user_id=uid,
                   vehicle_id=car.id if car else None,
                   prompt_len=len(system_prompt), ok=True, latency_ms=latency_ms)

    out["message"] = result["message"] + SAFETY_SCHEDULING
    out["question"] = question
    return out
