"""Tools DB cho AI agents (P6-05).

- get_my_vehicles(user_id), get_vehicle_history(vehicle_id)
- search_services: dich vu Active theo ten (LIKE), gia that tu DB.
  (Goi y phu tung dung 1 ham duy nhat common.suggest_parts.)
- find_vehicle_by_plate: uy thac base.detect_vehicle (1 logic duy nhat),
  chi them pham vi query DB + loc user_id.
- search_knowledge: wrap search_knowledge_base.
- create_appointment_draft: chi tao lich hen NHAP (Appointment, Pending) —
  KHONG tao phieu sua chua; phieu chi sinh ra khi xac nhan (convert). Tu choi
  (blocked) khi khung gio da kin / KTV da ban (booking_conflicts); xac minh
  ngay nghi / gio ngoai khung / KTV khong hop le (booking_input_errors); va
  khoa BOOKING_LOCK chong dat trung khi 2 request dong thoi.
- Manager tools (tach tu dashboard main.py, 1 nguon duy nhat):
  get_manager_kpis, get_pending_appointments, get_low_stock_parts,
  get_technician_performance, get_revenue_summary, get_quotes_waiting.
- Scheduling tools (lich hen + tiep nhan):
  get_available_slots, suggest_technicians, detect_schedule_conflicts,
  convert_appointment_to_order (xac nhan lich -> tao phieu + chuyen Confirmed;
  create_appointment_draft o tren duoc mo rong de nhan preferred_technician_id).
- Inventory tools (kho phu tung, CHI DOC — khong tu xuat kho):
  get_part_stock, search_stock, get_stock_alerts, predict_restock_demand.
- Billing tools (bao gia & hoa don, CHI DOC — khong tu thanh toan):
  compute_amounts (cong thuc dung chung), compute_order_quote, draft_invoice,
  check_quote_abnormal, get_receivables, get_active_promotions.
- Maintenance tools (cham soc & nhac bao duong, CHI DOC — khong tu dat lich):
  analyze_vehicle_profile, predict_maintenance, maintenance_recommendations.
"""
import math
import re
import threading
import unicodedata
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import User, Vehicle, Appointment, RepairOrder, Invoice
from app.models.models import ServiceCatalog, SparePart, RepairOrderPart
from app.models.models import Promotion
from app.services.rag_service import search_knowledge_base
from app.services.weather_service import get_today_weather_context
from app.agents.base import detect_vehicle
from app.core.schedule_config import (
    WORK_SLOTS, is_valid_slot, day_off_reason,
)

# Khoa tuan tu hoa buoc "kiem tra roi tao" lich hen: chan 2 request dong thoi
# cung dat vao 1 khung chi con 1 cho (single-process; uvicorn 1 worker).
BOOKING_LOCK = threading.Lock()

VI_DAYS = {"thứ 2": 0, "thu 2": 0, "thứ 3": 1, "thu 3": 1, "thứ 4": 2,
           "thu 4": 2, "thứ 5": 3, "thu 5": 3, "thứ 6": 4, "thu 6": 4,
           "thứ 7": 5, "thu 7": 5, "chủ nhật": 6, "chu nhat": 6}


# ---------- Vehicle & history (tra object/dict, khong raise) ----------

def get_my_vehicles(db: Session, user_id: int) -> list:
    """Tra Vehicle objects cua user. Loi -> []."""
    try:
        return db.query(Vehicle).filter(Vehicle.user_id == user_id).all()
    except Exception:
        return []


def vehicle_to_dict(v) -> dict:
    return {"id": v.id, "plate": v.license_plate, "make": v.make,
            "model": v.model, "year": v.manufacture_year,
            "odo": v.current_odo} if v is not None else {}


def get_vehicle_history(db: Session, vehicle_id: int, limit: int = 5,
                        status: str | None = "Completed") -> list:
    """Lich su RepairOrder moi nhat + linh kien da thay. Loi -> [].
    status="Completed" (mac dinh, giu hanh vi cu); status=None -> moi trang thai
    (technical agent can nhin ca don dang sua)."""
    try:
        q = db.query(RepairOrder).filter(RepairOrder.vehicle_id == vehicle_id)
        if status is not None:
            q = q.filter(RepairOrder.status == status)
        orders = q.order_by(RepairOrder.created_at.desc()).limit(limit).all()
    except Exception:
        return []
    out = []
    for o in orders:
        try:
            parts = [f"{p.part.name} (x{p.quantity})" for p in o.used_parts if p.part]
        except Exception:
            parts = []
        out.append({
            "id": o.id, "status": o.status,
            "symptoms": o.symptoms,
            "inspection": o.inspection_result,
            "labor": o.estimated_cost or 0,
            "parts": parts,
            "rating": o.service_rating,
            "created": o.created_at.strftime("%d/%m/%Y") if o.created_at else None,
            "completed": o.completed_at.strftime("%d/%m/%Y") if o.completed_at else None,
        })
    return out


def get_my_invoices(db: Session, user_id: int, limit: int = 5) -> list:
    try:
        rows = db.query(Invoice).join(RepairOrder).join(Vehicle).filter(
            Vehicle.user_id == user_id
        ).order_by(Invoice.created_at.desc()).limit(limit).all()
    except Exception:
        return []
    return [{"id": i.id, "total": i.total_amount, "status": i.status,
             "plate": i.repair_order.vehicle.license_plate if i.repair_order and i.repair_order.vehicle else None,
             "created": i.created_at.strftime("%d/%m/%Y") if i.created_at else None}
            for i in rows]


def get_my_appointments(db: Session, user_id: int, limit: int = 5) -> list:
    try:
        rows = db.query(Appointment).filter(
            Appointment.user_id == user_id
        ).order_by(Appointment.appointment_date.desc()).limit(limit).all()
    except Exception:
        return []
    return [{"id": a.id, "date": a.appointment_date, "time": a.appointment_time,
             "type": a.appointment_type, "status": a.status,
             "plate": a.vehicle.license_plate if a.vehicle else None}
            for a in rows]


def find_vehicle_by_plate(db: Session, text: str, user_id: int | None = None):
    """Tim xe theo bien so trong cau. Uy thac base.detect_vehicle (1 logic
    duy nhat, substring tolerant); ham nay chi them pham vi query DB.
    Neu user_id cho truoc, chi xe cua nguoi do. Loi -> None."""
    try:
        q = db.query(Vehicle)
        if user_id is not None:
            q = q.filter(Vehicle.user_id == user_id)
        return detect_vehicle(text, q.all())
    except Exception:
        return None


# ---------- Parts & services lookup (LIKE, gia that, khong raise) ----------

def search_services(db: Session, q: str, limit: int = 5) -> list:
    """Tim dich vu Active theo ten (LIKE). Loi -> []."""
    try:
        rows = db.query(ServiceCatalog).filter(
            ServiceCatalog.name.like(f"%{q}%"),
            ServiceCatalog.status == "Active",
        ).limit(limit).all()
    except Exception:
        return []
    return [{"id": s.id, "service_code": s.service_code, "name": s.name,
             "base_price": s.base_price or 0} for s in rows]


# ---------- Knowledge & weather (wrap an toan) ----------

def search_knowledge(query: str) -> str:
    """Wrap search_knowledge_base. Rong/loi -> '' (RAG-off fallback)."""
    try:
        return search_knowledge_base(query) or ""
    except Exception:
        return ""


def get_weather_context(db: Session) -> str:
    """Wrap get_today_weather_context. Loi -> ''."""
    try:
        return get_today_weather_context(db) or ""
    except Exception:
        return ""


# ---------- Booking draft ----------

def parse_vi_date(text: str, ref: datetime | None = None):
    """Parse ngay tieng Viet don gian -> 'YYYY-MM-DD' hoac None."""
    ref = ref or datetime.now()
    t = (text or "").lower()
    if "ngày mai" in t or "ngay mai" in t:
        return (ref + timedelta(days=1)).strftime("%Y-%m-%d")
    if "ngày mốt" in t or "ngay mot" in t:
        return (ref + timedelta(days=2)).strftime("%Y-%m-%d")
    if "hôm nay" in t or "hom nay" in t:
        return ref.strftime("%Y-%m-%d")
    for name, wd in VI_DAYS.items():
        if name in t:
            delta = (wd - ref.weekday()) % 7 or 7
            return (ref + timedelta(days=delta)).strftime("%Y-%m-%d")
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = ref.year if not y else (2000 + int(y) if len(y) == 2 else int(y))
        try:
            dt = datetime(year, mo, d)
        except ValueError:
            return None
        if dt.date() < ref.date() and not y:
            try:
                dt = datetime(year + 1, mo, d)
            except ValueError:
                return None
        return dt.strftime("%Y-%m-%d")
    return None


def parse_time(text: str):
    # Quét mọi ứng viên, bỏ qua số ngoài giờ hành chính (VD: số trong biển số xe).
    # Hiểu buổi tiếng Việt: sáng/am, chiều/tối/đêm/pm.
    for m in re.finditer(r"\b(\d{1,2})(?:\s*(?::|h|giờ|gio)\s*(\d{1,2})?)?\s*"
                         r"(am|pm|sáng|sang|trưa|trua|chiều|chieu|tối|toi|đêm|dem)?\b",
                         (text or "").lower(), re.IGNORECASE):
        h, mi, ap = int(m.group(1)), m.group(2), (m.group(3) or "").lower()
        mi = int(mi) if mi else 0
        if ap in ("pm", "chiều", "chieu", "tối", "toi", "đêm", "dem") and h < 12:
            h += 12
        if ap in ("am", "sáng", "sang") and h == 12:
            h = 0
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            continue
        # Giờ xưởng: 08:00-17:00
        if h < 8 or h > 17:
            continue
        return f"{h:02d}:{mi:02d}"
    return None


def wants_booking(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ["đặt lịch", "dat lich", "đặt hẹn", "dat hen",
                                "book lịch", "book lich", "hẹn lịch", "hen lich"])


def is_valid_technician(db: Session, technician_id: int | None) -> bool:
    """True neu None (khong chi dinh) hoac la KTV dang hoat dong. Loi -> False."""
    if technician_id is None:
        return True
    try:
        return db.query(User).filter(
            User.id == technician_id, User.role == "technician",
            User.is_active != 0).first() is not None
    except Exception:
        return False


def booking_input_errors(db: Session, date_str: str | None, time_str: str | None,
                         technician_id: int | None = None) -> list:
    """Liet ke loi dau vao dat lich (ngay nghi / gio ngoai khung / KTV sai).
    Rong = hop le. Khong raise (de router tra 400 ro rang)."""
    errors = []
    off = day_off_reason(date_str)
    if off:
        errors.append(off)
    if not is_valid_slot(time_str):
        errors.append("Khung giờ không hợp lệ (chọn: " + ", ".join(WORK_SLOTS) + ").")
    if not is_valid_technician(db, technician_id):
        errors.append("Kỹ thuật viên không tồn tại hoặc không phải kỹ thuật viên.")
    return errors


def create_appointment_draft(db: Session, user_id: int, vehicle_id: int,
                             date_str: str, time_str: str | None,
                             symptoms: str, appt_type: str = "Repair",
                             preferred_technician_id: int | None = None) -> dict:
    """Tao lich hen NHAP (Appointment, Pending). KHONG tao phieu sua chua va
    khong tu xac nhan — phieu chi duoc sinh khi xac nhan qua
    convert_appointment_to_order. preferred_technician_id (tuy chon) do
    scheduling agent goi y, luu vao lich hen.

    Tra ve {"blocked": True, "reasons": [...]} (khong tao gi) neu khung gio da
    kin hoac KTV da ban dung khung do; {"duplicate": True} neu trung lich cua xe.
    Raise ValueError khi dau vao sai (ngay qua khu/ngay nghi/gio ngoai khung/
    KTV khong hop le).
    """
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == vehicle_id, Vehicle.user_id == user_id).first()
    if not vehicle:
        raise ValueError("Xe không thuộc tài khoản của bạn.")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("Ngày hẹn không hợp lệ (cần YYYY-MM-DD).")
    if d < datetime.now().date():
        raise ValueError("Ngày hẹn phải từ hôm nay trở đi.")
    # Xac minh dau vao: ngay nghi, gio ngoai khung, KTV khong hop le.
    errors = booking_input_errors(db, date_str, time_str, preferred_technician_id)
    if errors:
        raise ValueError(" ".join(errors))
    # Khoa tuan tu: kiem tra trung/kin + tao nam trong 1 vung critical duy nhat
    # -> 2 request dong thoi khong the cung dat vao 1 cho cuoi cung.
    with BOOKING_LOCK:
        # Chong trung: da co lich Pending/Confirmed cung xe + ngay -> tra ve lich do
        dup = db.query(Appointment).filter(
            Appointment.user_id == user_id, Appointment.vehicle_id == vehicle_id,
            Appointment.appointment_date == date_str,
            Appointment.status.in_(["Pending", "Confirmed"])).first()
        if dup:
            return {"id": dup.id, "duplicate": True, "date": dup.appointment_date,
                    "time": dup.appointment_time, "plate": vehicle.license_plate,
                    "technician_id": dup.preferred_technician_id}
        # CHAN khi khung gio da kin / KTV da ban dung khung do (1 nguon duy nhat).
        blocks = booking_conflicts(db, date_str, time_str, preferred_technician_id)
        if blocks:
            return {"id": None, "duplicate": False, "blocked": True, "reasons": blocks,
                    "date": date_str, "time": time_str, "plate": vehicle.license_plate,
                    "technician_id": preferred_technician_id}
        appt = Appointment(user_id=user_id, vehicle_id=vehicle_id,
                           appointment_date=date_str, appointment_time=time_str,
                           appointment_type=appt_type,
                           symptoms=(symptoms or "").strip() or "Khách đặt qua AI",
                           status="Pending",
                           preferred_technician_id=preferred_technician_id)
        db.add(appt)
        db.commit()
    return {"id": appt.id, "duplicate": False, "date": date_str,
            "time": time_str, "plate": vehicle.license_plate,
            "technician_id": preferred_technician_id}


# ---------- Scheduling & reception tools (P8: lich hen + tiep nhan) ----------

# Gio lam viec cua xuong: lay tu app.core.schedule_config (1 nguon duy nhat,
# khop UI dat lich). `WORK_SLOTS` da duoc import o dau file.
ACTIVE_APPT_STATUSES = ("Pending", "Confirmed")


def _active_technician_count(db: Session) -> int:
    """So KTV dang hoat dong = suc chua moi khung gio (toi thieu 1)."""
    try:
        n = db.query(User).filter(User.role == "technician",
                                  User.is_active != 0).count()
    except Exception:
        n = 0
    return max(1, n)


def get_available_slots(db: Session, date_str: str,
                        technician_id: int | None = None) -> dict:
    """Khung gio trong cua 1 ngay. Suc chua = so KTV dang hoat dong (hoac 1
    neu loc theo 1 KTV). Loi -> free rong. Khong raise."""
    out = {"date": date_str, "slots": [], "free": [], "busy": []}
    if not date_str:
        return out
    try:
        capacity = 1 if technician_id is not None else _active_technician_count(db)
        q = db.query(Appointment).filter(
            Appointment.appointment_date == date_str,
            Appointment.status.in_(list(ACTIVE_APPT_STATUSES)))
        if technician_id is not None:
            q = q.filter(Appointment.preferred_technician_id == technician_id)
        counts: dict = {}
        for a in q.all():
            key = a.appointment_time or ""
            counts[key] = counts.get(key, 0) + 1
        for s in WORK_SLOTS:
            booked = counts.get(s, 0)
            free = booked < capacity
            out["slots"].append({"time": s, "booked": booked,
                                 "capacity": capacity, "free": free})
            (out["free"] if free else out["busy"]).append(s)
    except Exception:
        pass
    return out


def suggest_technicians(db: Session, date_str: str | None = None,
                        time_str: str | None = None, limit: int = 3) -> list:
    """Goi y KTV phu hop: uu tien KTV ranh khung gio, tai don thap.
    Loi -> []. Khong raise."""
    try:
        techs = db.query(User).filter(User.role == "technician",
                                      User.is_active != 0).all()
    except Exception:
        return []
    out = []
    for t in techs:
        try:
            in_prog = db.query(RepairOrder).filter(
                RepairOrder.technician_id == t.id,
                RepairOrder.status == "In Progress").count()
            pending = db.query(RepairOrder).filter(
                RepairOrder.technician_id == t.id,
                RepairOrder.status == "Pending").count()
            busy_at_slot = False
            if date_str and time_str:
                busy_at_slot = db.query(Appointment).filter(
                    Appointment.preferred_technician_id == t.id,
                    Appointment.appointment_date == date_str,
                    Appointment.appointment_time == time_str,
                    Appointment.status.in_(list(ACTIVE_APPT_STATUSES))
                ).first() is not None
        except Exception:
            in_prog = pending = 0
            busy_at_slot = False
        out.append({"id": t.id, "name": t.full_name, "in_progress": in_prog,
                    "pending": pending, "busy_at_slot": busy_at_slot})
    out.sort(key=lambda r: (r["busy_at_slot"], r["in_progress"], r["pending"]))
    return out[:limit]


def detect_schedule_conflicts(db: Session, date_str: str | None = None,
                              time_str: str | None = None,
                              technician_id: int | None = None,
                              vehicle_id: int | None = None) -> dict:
    """Phat hien trung lich / qua tai cho (ngay, [gio], KTV, xe).

    Tra ve co cau truc de ben goi tu quyet dinh chan dat lich:
    overload (khung kin), technician_busy, vehicle_busy (trung xe), reasons.
    Loi -> khong co xung dot. Khong raise."""
    out = {"has_conflict": False, "overload": False,
           "technician_busy": False, "vehicle_busy": False,
           "reasons": [], "load": 0, "capacity": 0}
    if not date_str:
        return out
    try:
        capacity = _active_technician_count(db)
        q = db.query(Appointment).filter(
            Appointment.appointment_date == date_str,
            Appointment.status.in_(list(ACTIVE_APPT_STATUSES)))
        if time_str:
            q = q.filter(Appointment.appointment_time == time_str)
        rows = q.all()
        out["load"] = len(rows)
        out["capacity"] = capacity
        # Qua tai chi tinh khi biet khung gio (capacity la suc chua MOI khung,
        # so sanh voi tong ca ngay se sai).
        if time_str and len(rows) >= capacity:
            out["overload"] = True
            out["reasons"].append(
                f"Khung {time_str} đã kín ({len(rows)}/{capacity} chỗ).")
        if technician_id is not None:
            for a in rows:
                if a.preferred_technician_id == technician_id:
                    out["technician_busy"] = True
                    out["reasons"].append(
                        f"KTV đã có lịch #{a.id} lúc {a.appointment_time or '(chưa chốt giờ)'}.")
                    break
        if vehicle_id is not None:
            for a in rows:
                if a.vehicle_id == vehicle_id:
                    out["vehicle_busy"] = True
                    out["reasons"].append(f"Xe đã có lịch #{a.id} trong ngày.")
                    break
        out["has_conflict"] = out["overload"] or out["technician_busy"] or out["vehicle_busy"]
    except Exception:
        pass
    return out


def booking_conflicts(db: Session, date_str: str | None, time_str: str | None,
                      technician_id: int | None = None) -> list:
    """Ly do CHAN dat lich cho (ngay, [gio], KTV). Rong = dat duoc.

    Chi chan khi chac chan: khung gio da kin, hoac KTV da ban DUNG khung gio do.
    (Khi chua co gio thi khong the ket luan kin -> de nguoi dung chot gio.)
    Trung xe cung ngay do create_appointment_draft xu ly rieng (duplicate).
    Loi -> []. Khong raise."""
    if not date_str:
        return []
    c = detect_schedule_conflicts(db, date_str, time_str, technician_id=technician_id)
    reasons = []
    if c.get("overload"):
        reasons.append(f"Khung {time_str} đã kín ({c['load']}/{c['capacity']} chỗ).")
    if time_str and technician_id is not None and c.get("technician_busy"):
        reasons.append(f"Kỹ thuật viên đã bận khung {time_str}.")
    return reasons


def convert_appointment_to_order(db: Session, appointment_id: int,
                                 technician_id: int | None = None) -> dict:
    """Xac nhan lich hen -> tao phieu sua chua + chuyen lich sang Confirmed.

    Day la buoc XAC NHAN cua luong lich NHAP: create_appointment_draft chi tao
    Appointment, con phieu sua chua chi sinh ra o day.
    Idempotent: da co phieu -> tra lai, khong tao trung; nhung VAN chot lich
    (Pending -> Confirmed) neu truoc do bi bo sot (du lieu cu / dat qua web).
    Loi nghiep vu -> ValueError (router bat)."""
    appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appt:
        raise ValueError("Không tìm thấy lịch hẹn.")
    if appt.status == "Cancelled":
        raise ValueError("Lịch hẹn đã hủy, không thể chuyển thành phiếu.")
    existing = db.query(RepairOrder).filter(
        RepairOrder.appointment_id == appointment_id).first()
    if existing:
        if appt.status == "Pending":
            appt.status = "Confirmed"
            db.commit()
        return {"id": existing.id, "appointment_id": appt.id, "created": False,
                "status": existing.status, "appointment_status": appt.status,
                "technician_id": existing.technician_id,
                "plate": appt.vehicle.license_plate if appt.vehicle else None}
    tech_id = technician_id if technician_id is not None else appt.preferred_technician_id
    ro = RepairOrder(vehicle_id=appt.vehicle_id, technician_id=tech_id,
                     appointment_id=appt.id,
                     order_type=appt.appointment_type or "Repair",
                     symptoms=appt.symptoms, ai_diagnosis=appt.ai_diagnosis,
                     status="Pending")
    db.add(ro)
    if appt.status == "Pending":
        appt.status = "Confirmed"
    db.commit()
    return {"id": ro.id, "appointment_id": appt.id, "created": True,
            "status": ro.status, "appointment_status": appt.status,
            "technician_id": ro.technician_id,
            "plate": appt.vehicle.license_plate if appt.vehicle else None}


# ---------- Manager tools (tach tu dashboard main.py, khong raise) ----------

def get_manager_kpis(db: Session) -> dict:
    """KPI van hanh: don theo trang thai + tiep nhan cho + lich hen cho.
    Loi -> dict rong so 0."""
    out = {"orders": {"Pending": 0, "In Progress": 0, "Completed": 0},
           "pending_receptions": 0, "appointments_pending": 0}
    try:
        for st in out["orders"]:
            out["orders"][st] = db.query(RepairOrder).filter(
                RepairOrder.status == st).count()
        out["pending_receptions"] = db.query(RepairOrder).filter(
            RepairOrder.status == "Pending",
            RepairOrder.reception_datetime.is_(None)).count()
        out["appointments_pending"] = db.query(Appointment).filter(
            Appointment.status == "Pending").count()
    except Exception:
        pass
    return out


def get_pending_appointments(db: Session, limit: int = 5) -> list:
    """Lich hen Pending sap toi (date asc). Loi -> []."""
    try:
        rows = db.query(Appointment).filter(
            Appointment.status == "Pending"
        ).order_by(Appointment.appointment_date.asc()).limit(limit).all()
    except Exception:
        return []
    return [{"id": a.id, "date": a.appointment_date, "time": a.appointment_time,
             "status": a.status,
             "plate": a.vehicle.license_plate if a.vehicle else None,
             "customer": a.user.full_name if a.user else None,
             "symptoms": a.symptoms} for a in rows]


def get_low_stock_parts(db: Session, limit: int = 5) -> list:
    """Phu tung sap het (cung cong thuc trang Kho main.py:
    stock <= min_stock or 5). Loi -> []."""
    try:
        rows = [p for p in db.query(SparePart).all()
                if (p.stock_quantity or 0) <= (p.min_stock or 5)]
    except Exception:
        return []
    rows.sort(key=lambda p: (p.stock_quantity or 0))
    return [{"name": p.name, "part_number": p.part_number,
             "stock": p.stock_quantity or 0, "min": p.min_stock}
            for p in rows[:limit]]


def get_technician_performance(db: Session) -> list:
    """Tai don moi KTV (all-time; ban period-aware nam o trang overview).
    Loi -> []."""
    try:
        techs = db.query(User).filter(User.role == "technician").all()
    except Exception:
        return []
    out = []
    for t in techs:
        try:
            q = db.query(RepairOrder).filter(RepairOrder.technician_id == t.id)
            total = q.count()
            completed = q.filter(RepairOrder.status == "Completed").count()
            in_prog = q.filter(RepairOrder.status == "In Progress").count()
            pending = q.filter(RepairOrder.status == "Pending").count()
        except Exception:
            total = completed = in_prog = pending = 0
        out.append({"name": t.full_name, "total": total, "completed": completed,
                    "in_progress": in_prog, "pending": pending})
    out.sort(key=lambda r: (-r["completed"], -r["total"]))
    return out


def get_revenue_summary(db: Session) -> dict:
    """Tong doanh thu + cong no Unpaid tu Invoice. Loi -> so 0."""
    out = {"total": 0, "paid_amount": 0, "unpaid_count": 0, "unpaid_amount": 0}
    try:
        invs = db.query(Invoice).all()
    except Exception:
        return out
    out["total"] = sum(i.total_amount or 0 for i in invs)
    out["paid_amount"] = sum(i.total_amount or 0 for i in invs if i.status == "Paid")
    unpaid = [i for i in invs if i.status == "Unpaid"]
    out["unpaid_count"] = len(unpaid)
    out["unpaid_amount"] = sum(i.total_amount or 0 for i in unpaid)
    return out


def get_quotes_waiting(db: Session, limit: int = 5) -> list:
    """Bao gia cho khach duyet (customer_approval Pending + co estimated_cost,
    don chua xong). Loi -> []."""
    try:
        rows = db.query(RepairOrder).filter(
            RepairOrder.customer_approval == "Pending",
            RepairOrder.estimated_cost.isnot(None),
            RepairOrder.status.in_(["Pending", "In Progress"])
        ).order_by(RepairOrder.created_at.desc()).limit(limit).all()
    except Exception:
        return []
    return [{"id": o.id, "status": o.status,
             "estimated_cost": o.estimated_cost or 0,
             "plate": o.vehicle.license_plate if o.vehicle else None}
            for o in rows]


# ---------- Inventory tools (kho phu tung, CHI DOC, khong xuat kho) ----------

LEAD_DAYS = 7            # Thoi gian cho hang ve (ngay)
COVER_TARGET_DAYS = 21   # Muc tieu ton du tru (ngay)


def _part_dict(p) -> dict:
    return {"id": p.id, "part_number": p.part_number, "name": p.name,
            "other_name": p.other_name, "category": p.category, "brand": p.brand,
            "stock": p.stock_quantity or 0, "min": p.min_stock or 0,
            "max": p.max_stock or 0,
            "price": p.price or 0, "purchase_price": p.purchase_price or 0,
            "status": p.status,
            "low": (p.stock_quantity or 0) <= (p.min_stock or 5),
            "out": (p.stock_quantity or 0) <= 0}


def get_part_stock(db: Session, query: str = "", limit: int = 10) -> list:
    """Tra ton kho theo ten/ma/loai/hang (LIKE). query rong -> uu tien hang
    ton thap truoc. Loi -> []. CHI DOC."""
    try:
        q = db.query(SparePart)
        key = (query or "").strip()
        if key:
            like = f"%{key}%"
            q = q.filter(
                SparePart.name.like(like) | SparePart.part_number.like(like)
                | SparePart.other_name.like(like) | SparePart.category.like(like)
                | SparePart.brand.like(like))
            rows = q.order_by(SparePart.name).limit(limit).all()
        else:
            rows = q.all()
            rows.sort(key=lambda p: (p.stock_quantity or 0))
            rows = rows[:limit]
    except Exception:
        return []
    return [_part_dict(p) for p in rows]


def search_stock(db: Session, text: str, limit: int = 8) -> list:
    """Tim ton kho theo token trong cau (KHONG loc con hang — de kiem tra hang
    het). Loi -> []. CHI DOC."""
    try:
        parts = db.query(SparePart).all()
    except Exception:
        return []
    keys = set(re.findall(r"[a-zA-ZÀ-ỹ0-9]+", (text or "").lower()))
    if not keys:
        return []
    scored = []
    for p in parts:
        hay = set(re.findall(r"[a-zA-ZÀ-ỹ0-9]+", " ".join(
            [p.name or "", p.part_number or "", p.other_name or "",
             p.category or "", p.brand or ""]).lower()))
        scored.append((len(keys & hay), p))
    scored.sort(key=lambda t: (-t[0], t[1].stock_quantity or 0))
    out = []
    for score, p in scored:
        if score <= 0:
            break
        out.append(_part_dict(p))
        if len(out) >= limit:
            break
    return out


def get_stock_alerts(db: Session, limit: int = 5) -> dict:
    """Canh bao phu tung sap het / da het. Loi -> rong. CHI DOC."""
    out = {"total": 0, "low": [], "out": []}
    try:
        parts = db.query(SparePart).all()
    except Exception:
        return out
    out["total"] = len(parts)
    low = [p for p in parts if 0 < (p.stock_quantity or 0) <= (p.min_stock or 5)]
    oos = [p for p in parts if (p.stock_quantity or 0) <= 0]
    low.sort(key=lambda p: (p.stock_quantity or 0))
    oos.sort(key=lambda p: (p.stock_quantity or 0))
    out["low"] = [_part_dict(p) for p in low[:limit]]
    out["out"] = [_part_dict(p) for p in oos[:limit]]
    return out


def predict_restock_demand(db: Session, days: int = 30, limit: int = 5) -> list:
    """Du doan nhu cau nhap hang tu tieu thu N ngay (RepairOrderPart) + ton kho.
    Tra list [.., cover_days, suggested_order, urgency out/low/watch]. CHI DOC."""
    days = max(1, int(days or 30))
    since = datetime.now() - timedelta(days=days)
    try:
        rows = db.query(RepairOrderPart).join(RepairOrder).filter(
            RepairOrder.created_at >= since).all()
    except Exception:
        rows = []
    usage: dict = {}
    for r in rows:
        usage[r.part_id] = usage.get(r.part_id, 0) + (r.quantity or 0)
    try:
        parts = db.query(SparePart).all()
    except Exception:
        return []
    items = []
    for p in parts:
        used = usage.get(p.id, 0)
        stock = p.stock_quantity or 0
        mn = p.min_stock or 5
        avg = used / days
        cover = (stock / avg) if avg > 0 else None
        reorder_point = max(mn, math.ceil(avg * LEAD_DAYS))
        target = max(p.max_stock or 0, mn * 3, math.ceil(avg * COVER_TARGET_DAYS))
        suggested = max(0, target - stock)
        if stock <= 0:
            urgency = "out"
        elif stock <= reorder_point:
            urgency = "low"
        elif cover is not None and cover < LEAD_DAYS:
            urgency = "watch"
        else:
            continue
        items.append({"id": p.id, "part_number": p.part_number, "name": p.name,
                      "stock": stock, "min": mn, "used": used,
                      "avg_per_day": round(avg, 2),
                      "cover_days": round(cover, 1) if cover is not None else None,
                      "suggested_order": suggested, "urgency": urgency})
    rank = {"out": 0, "low": 1, "watch": 2}
    items.sort(key=lambda r: (rank[r["urgency"]],
                              r["cover_days"] if r["cover_days"] is not None else 1e9,
                              r["stock"]))
    return items[:limit]


# ---------- Billing tools (bao gia & hoa don, CHI DOC, khong tu thanh toan) ----

VAT_RATE = 0.1                 # VAT mac dinh (mau technician.generate_invoice)
ABNORMAL_DISCOUNT_PCT = 50.0   # Giam gia > 50% -> bat thuong
ABNORMAL_DEVIATION = 3.0       # Lech > 3x trung binh -> bat thuong
OVERDUE_DAYS = 30              # Cong no qua han (ngay)


def _r(x) -> float:
    return round(float(x or 0), 2)


def compute_amounts(labor: float, parts_total: float,
                    vat_rate: float = VAT_RATE, discount: float = 0.0) -> dict:
    """Cong thuc hoa don DUNG CHUNG (mau technician.generate_invoice):
    subtotal = cong + phu tung; vat = subtotal*vat_rate; total = subtotal+vat-discount.
    discount KHONG vuot subtotal. Khong raise."""
    labor = max(0.0, float(labor or 0))
    parts_total = max(0.0, float(parts_total or 0))
    subtotal = labor + parts_total
    vat_amount = subtotal * float(vat_rate or 0)
    discount = max(0.0, min(float(discount or 0), subtotal))
    total = subtotal + vat_amount - discount
    return {"labor": _r(labor), "parts_total": _r(parts_total),
            "subtotal": _r(subtotal), "vat_rate": float(vat_rate or 0),
            "vat_amount": _r(vat_amount), "discount": _r(discount),
            "total": _r(total)}


def order_parts_breakdown(db: Session, order) -> list:
    """Dong phu tung da dung tren phieu. Loi -> []. CHI DOC."""
    try:
        rows = order.used_parts or []
    except Exception:
        return []
    out = []
    for rp in rows:
        try:
            p = rp.part
            out.append({"part_id": rp.part_id,
                        "part_number": p.part_number if p else None,
                        "name": p.name if p else None,
                        "quantity": rp.quantity or 0,
                        "unit_price": rp.unit_price or 0,
                        "line_total": (rp.quantity or 0) * (rp.unit_price or 0)})
        except Exception:
            continue
    return out


def compute_order_quote(db: Session, order_id: int, discount_percent: float = 0.0,
                        vat_rate: float = VAT_RATE, labor: float | None = None) -> dict:
    """Bao gia 1 phieu: cong + phu tung + VAT + giam gia. Loi -> ValueError."""
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        raise ValueError("Không tìm thấy phiếu sửa chữa.")
    items = order_parts_breakdown(db, order)
    parts_total = sum(i["line_total"] for i in items)
    labor_cost = float(order.estimated_cost or 0) if labor is None else float(labor or 0)
    discount = (labor_cost + parts_total) * (float(discount_percent or 0) / 100.0)
    amounts = compute_amounts(labor_cost, parts_total, vat_rate, discount)
    return {"order_id": order.id,
            "plate": order.vehicle.license_plate if order.vehicle else None,
            "status": order.status, "items": items,
            "discount_percent": float(discount_percent or 0), **amounts}


def draft_invoice(db: Session, order_id: int, discount_percent: float = 0.0,
                  vat_rate: float = VAT_RATE) -> dict:
    """Sinh BAN NHAP hoa don (khong ghi DB, khong tu xuat/thanh toan)."""
    quote = compute_order_quote(db, order_id, discount_percent, vat_rate)
    return {"draft": True, "kind": "HoaDon",
            "note": "Bản nháp — chưa xuất hóa đơn, cần người có quyền xác nhận.",
            **quote}


def check_quote_abnormal(db: Session, order_id: int,
                         quote: dict | None = None,
                         technician_id: int | None = None) -> dict:
    """Kiem tra bao gia bat thuong. Loi -> khong ket luan. CHI DOC.

    technician_id != None -> muc trung binh chi tinh tren hoa don cua KTV do
    (tranh lo so lieu toan garage). None -> toan garage (Manager/Admin).
    """
    out = {"abnormal": False, "reasons": []}
    try:
        q = quote or compute_order_quote(db, order_id)
    except ValueError:
        return out
    total = q.get("total", 0)
    if total <= 0:
        out["reasons"].append("Tổng tiền ≤ 0.")
    if (q.get("labor") or 0) <= 0 and (q.get("parts_total") or 0) > 0:
        out["reasons"].append("Có phụ tùng nhưng chưa có tiền công.")
    if (q.get("discount_percent") or 0) > ABNORMAL_DISCOUNT_PCT:
        out["reasons"].append(
            f"Giảm giá {q['discount_percent']}% vượt ngưỡng {ABNORMAL_DISCOUNT_PCT}%.")
    # Lech xa trung binh hoa don da xuat (chi khi du mau)
    try:
        tq = db.query(Invoice).filter(Invoice.total_amount.isnot(None))
        if technician_id is not None:
            tq = tq.join(RepairOrder, Invoice.repair_order_id == RepairOrder.id).filter(
                RepairOrder.technician_id == technician_id)
        totals = [float(i.total_amount or 0) for i in tq.all()]
    except Exception:
        totals = []
    if len(totals) >= 5:
        avg = sum(totals) / len(totals)
        if avg > 0 and (total > avg * ABNORMAL_DEVIATION
                        or total < avg / ABNORMAL_DEVIATION):
            out["reasons"].append(
                f"Tổng tiền {_r(total):,.0f} lệch xa mức trung bình {_r(avg):,.0f}.")
    out["abnormal"] = bool(out["reasons"])
    return out


def get_receivables(db: Session, limit: int = 10,
                    technician_id: int | None = None) -> dict:
    """Theo doi cong no: hoa don Unpaid + tuoi no (aging). Loi -> rong. CHI DOC.

    technician_id != None -> CHI tinh cong no tren phieu do KTV nay phu trach
    (khong lo du lieu toan garage). None -> toan garage (Manager/Admin).
    """
    out = {"unpaid_count": 0, "unpaid_amount": 0.0, "overdue_count": 0,
           "overdue_amount": 0.0, "aging": {"0_7": 0.0, "8_30": 0.0, "31_plus": 0.0},
           "items": [], "scope": "technician" if technician_id is not None else "garage"}
    try:
        q = db.query(Invoice).filter(Invoice.status == "Unpaid")
        if technician_id is not None:
            q = q.join(RepairOrder, Invoice.repair_order_id == RepairOrder.id).filter(
                RepairOrder.technician_id == technician_id)
        rows = q.order_by(Invoice.created_at.asc()).all()
    except Exception:
        return out
    now = datetime.now()
    items = []
    for i in rows:
        amt = float(i.total_amount or 0)
        days = (now - i.created_at).days if i.created_at else 0
        overdue = days >= OVERDUE_DAYS
        out["unpaid_count"] += 1
        out["unpaid_amount"] += amt
        if overdue:
            out["overdue_count"] += 1
            out["overdue_amount"] += amt
        if days <= 7:
            out["aging"]["0_7"] += amt
        elif days <= 30:
            out["aging"]["8_30"] += amt
        else:
            out["aging"]["31_plus"] += amt
        items.append({"invoice_id": i.id, "order_id": i.repair_order_id,
                      "total": _r(amt), "days": days, "overdue": overdue,
                      "plate": (i.repair_order.vehicle.license_plate
                                if i.repair_order and i.repair_order.vehicle else None)})
    for k in ("unpaid_amount", "overdue_amount"):
        out[k] = _r(out[k])
    for k in out["aging"]:
        out["aging"][k] = _r(out["aging"][k])
    out["items"] = sorted(items, key=lambda r: (-r["days"], -r["total"]))[:limit]
    return out


def get_active_promotions(db: Session, limit: int = 5) -> list:
    """Khuyen mai DANG ap dung: status == "Active" VA hom nay nam trong
    [start_date, end_date] (bo qua neu thieu/khong doc duoc moc). Loi -> []. CHI DOC."""
    try:
        rows = db.query(Promotion).filter(
            Promotion.status == "Active").order_by(Promotion.id.desc()).all()
    except Exception:
        return []
    today = datetime.now().date()
    out = []
    for p in rows:
        start = _parse_date_any(p.start_date)
        end = _parse_date_any(p.end_date)
        if start is not None and start > today:
            continue  # chua toi ngay bat dau
        if end is not None and end < today:
            continue  # da het han
        out.append({"id": p.id, "title": p.title,
                    "discount_percent": p.discount_percent or 0,
                    "start": p.start_date, "end": p.end_date})
        if len(out) >= limit:
            break
    return out


# ---------- Maintenance tools (cham soc & nhac bao duong, CHI DOC) ----------

# Ke hoach bao duong dinh ky (km/thang) + tu khoa nhan dien lan lam gan nhat.
MAINTENANCE_PLAN = [
    {"code": "oil", "label": "Thay dầu động cơ", "interval_km": 5000,
     "interval_months": 6,
     "keywords": ("dau may", "nhot", "loc dau", "thay dau", "oil")},
    {"code": "filter_air", "label": "Thay lọc gió động cơ", "interval_km": 15000,
     "interval_months": 12,
     "keywords": ("loc gio", "gio dong co", "air filter")},
    {"code": "tire", "label": "Đảo/kiểm tra lốp, cân bằng", "interval_km": 10000,
     "interval_months": 12,
     "keywords": ("lop", "vo xe", "can bang", "tire")},
    {"code": "brake", "label": "Kiểm tra/thay má phanh", "interval_km": 20000,
     "interval_months": 12,
     "keywords": ("phanh", "ma phanh", "brake")},
    {"code": "coolant", "label": "Kiểm tra nước làm mát", "interval_km": 20000,
     "interval_months": 24,
     "keywords": ("nuoc lam mat", "coolant", "ket nuoc")},
    {"code": "battery", "label": "Kiểm tra/thay ắc quy", "interval_km": 40000,
     "interval_months": 30,
     "keywords": ("ac quy", "binh dien", "battery")},
]

_STATUS_RANK = {"overdue": 0, "due_soon": 1, "ok": 2}


def _fold(text: str) -> str:
    """Bo dau tieng Viet + lowercase de so khop tu khoa on dinh."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.replace("đ", "d")


def _parse_date_any(value):
    """Chuoi 'YYYY-MM-DD'/'DD/MM/YYYY' hoac datetime -> datetime.date; loi -> None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _maintenance_time_base(v) -> tuple:
    """Moc goc theo THOI GIAN khi chua co lich su bao duong: (nguon, date).
    Uu tien ngay mua / ngay dang ky xe. KHONG dung nam san xuat (tranh bao qua
    han hang loat cho xe cu thieu lich su). Khong co -> (None, None)."""
    for src in ("purchase_date", "registration_date"):
        d = _parse_date_any(getattr(v, src, None))
        if d:
            return src, d
    return None, None


def analyze_vehicle_profile(db: Session, vehicle_id: int) -> dict:
    """Ho so xe: ODO, thong tin, lich su sua chua, phu tung thay nhieu.
    Loi -> dict rong. CHI DOC."""
    out = {"vehicle": {}, "history": [], "total_orders": 0,
           "last_service_date": None, "top_parts_replaced": []}
    try:
        v = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    except Exception:
        return out
    if not v:
        return out
    out["vehicle"] = {"id": v.id, "plate": v.license_plate, "make": v.make,
                      "model": v.model, "year": v.manufacture_year,
                      "odo": v.current_odo or 0, "usage": v.usage_type,
                      "warranty": v.warranty_status}
    hist = get_vehicle_history(db, vehicle_id, limit=5, status=None)
    out["history"] = hist
    # total_orders phai la TONG so phieu (hist chi lay toi da 5 phieu de hien thi).
    try:
        out["total_orders"] = db.query(RepairOrder).filter(
            RepairOrder.vehicle_id == vehicle_id).count()
    except Exception:
        out["total_orders"] = len(hist)
    if hist:
        out["last_service_date"] = hist[0].get("completed") or hist[0].get("created")
    counts: dict = {}
    try:
        orders = db.query(RepairOrder).filter(
            RepairOrder.vehicle_id == vehicle_id).all()
        for o in orders:
            for rp in o.used_parts:
                if rp.part:
                    counts[rp.part.name] = counts.get(rp.part.name, 0) + (rp.quantity or 0)
    except Exception:
        pass
    out["top_parts_replaced"] = [{"name": k, "quantity": n} for k, n in
                                 sorted(counts.items(), key=lambda x: -x[1])[:5]]
    return out


def predict_maintenance(db: Session, vehicle_id: int) -> dict:
    """Du doan moc bao duong theo ODO **HOAC** thoi gian:
    - km: ODO hien tai vs ODO lan lam gan nhat + interval_km.
    - thoi gian: so thang tu lan lam gan nhat + interval_months (neu chua co
      lich su thi lay moc mua/ngay dang ky xe neu biet).
    Den han neu MOT trong hai vuot nguong. Loi -> items rong. CHI DOC."""
    out = {"vehicle_id": vehicle_id, "plate": None, "odo": 0, "items": [],
           "overdue_count": 0, "due_soon_count": 0}
    try:
        v = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    except Exception:
        return out
    if not v:
        return out
    odo = v.current_odo or 0
    out["plate"] = v.license_plate
    out["odo"] = odo
    today = datetime.now().date()
    v_ref_src, v_ref_date = _maintenance_time_base(v)
    try:
        orders = db.query(RepairOrder).filter(
            RepairOrder.vehicle_id == vehicle_id,
            RepairOrder.status == "Completed").order_by(
            RepairOrder.created_at.desc()).all()
    except Exception:
        orders = []
    # (blob tu khoa, odo tai lan do, ngay, id) — moi nhat truoc
    history = []
    for o in orders:
        try:
            parts = " ".join((rp.part.name or "") for rp in o.used_parts if rp.part)
        except Exception:
            parts = ""
        blob = _fold(" ".join([o.symptoms or "", o.inspection_result or "",
                               o.order_type or "", parts]))
        date_ref = o.completed_at or o.created_at
        history.append((blob, o.final_odo or o.current_odo or 0, date_ref, o.id))
    items = []
    for plan in MAINTENANCE_PLAN:
        last = None
        last_date = None
        for blob, odo_ref, date_ref, oid in history:
            if any(k in blob for k in plan["keywords"]):
                last_date = date_ref.date() if date_ref else None
                last = {"order_id": oid, "odo": odo_ref,
                        "date": date_ref.strftime("%d/%m/%Y") if date_ref else None}
                break
        # --- Den han theo KM ---
        base_odo = last["odo"] if last else 0
        interval_km = plan["interval_km"]
        km_since = max(0, odo - base_odo)
        km_remaining = max(0, base_odo + interval_km - odo)
        if odo >= base_odo + interval_km:
            km_status = "overdue"
        elif km_since >= int(interval_km * 0.8):
            km_status = "due_soon"
        else:
            km_status = "ok"
        # --- Den han theo THOI GIAN (interval_months) ---
        interval_months = plan["interval_months"]
        if last is not None:
            base_date, base_src = last_date, "last_service"
        else:
            base_date, base_src = v_ref_date, v_ref_src
        months_since = months_remaining = None
        time_status = "ok"
        if base_date is not None and interval_months:
            months_since = round((today - base_date).days / 30.44, 1)
            months_remaining = round(max(0.0, interval_months - months_since), 1)
            if months_since >= interval_months:
                time_status = "overdue"
            elif months_since >= interval_months * 0.8:
                time_status = "due_soon"
        # --- Gop: qua han neu MOT trong hai qua han; worst-of ---
        status = km_status if _STATUS_RANK[km_status] <= _STATUS_RANK[time_status] \
            else time_status
        due_by = [n for n, st in (("km", km_status), ("time", time_status))
                  if st != "ok"]
        items.append({"code": plan["code"], "label": plan["label"],
                      "interval_km": interval_km,
                      "interval_months": interval_months,
                      "last_service": last, "km_since": km_since,
                      "km_remaining": km_remaining, "km_status": km_status,
                      "months_since": months_since,
                      "months_remaining": months_remaining,
                      "time_status": time_status,
                      "time_base": ({"source": base_src,
                                     "date": base_date.strftime("%d/%m/%Y")}
                                    if base_date is not None else None),
                      "due_by": due_by, "status": status})
    items.sort(key=lambda r: (_STATUS_RANK[r["status"]], r["km_remaining"]))
    out["items"] = items
    out["overdue_count"] = sum(1 for i in items if i["status"] == "overdue")
    out["due_soon_count"] = sum(1 for i in items if i["status"] == "due_soon")
    return out


def _match_service(db: Session, text: str):
    """Dich vu Active khop token voi text (score>0 moi tra). Loi -> None."""
    try:
        services = db.query(ServiceCatalog).filter(
            ServiceCatalog.status == "Active").all()
    except Exception:
        return None
    keys = set(re.findall(r"[a-z0-9]+", _fold(text)))
    best, best_score = None, 0
    for s in services:
        hay = set(re.findall(r"[a-z0-9]+", _fold(
            f"{s.name} {s.category or ''} {s.description or ''}")))
        score = len(keys & hay)
        if score > best_score:
            best, best_score = s, score
    if best is None:
        return None
    price = best.promo_price if best.promo_price else (best.base_price or 0)
    return {"id": best.id, "name": best.name, "price": price,
            "promo": bool(best.promo_price)}


def maintenance_recommendations(db: Session, vehicle_id: int, limit: int = 5) -> list:
    """Khuyen nghi ca nhan hoa cho xe: hang muc due/overdue + dich vu khop gia.
    Ly do neu ro den han theo km va/hoac thoi gian. Loi -> []. CHI DOC."""
    plan = predict_maintenance(db, vehicle_id)
    out = []
    for it in plan.get("items", []):
        if it["status"] == "ok":
            continue
        reason = ("Quá hạn" if it["status"] == "overdue" else "Sắp tới hạn")
        bits = []
        if it.get("km_status") != "ok":
            bits.append(f"{it['km_since']:,} km")
        if it.get("time_status") != "ok" and it.get("months_since") is not None:
            bits.append(f"{it['months_since']:.0f} tháng")
        if bits:
            reason += " (" + " / ".join(bits)
            if it["last_service"] and it["last_service"].get("date"):
                reason += f", lần trước {it['last_service']['date']}"
            reason += ")"
        elif it["last_service"] and it["last_service"].get("date"):
            reason += f" (lần trước {it['last_service']['date']})"
        else:
            reason += " (chưa có lịch sử)"
        out.append({"code": it["code"], "label": it["label"],
                    "status": it["status"], "reason": reason,
                    "km_since": it["km_since"], "km_remaining": it["km_remaining"],
                    "months_since": it.get("months_since"),
                    "months_remaining": it.get("months_remaining"),
                    "due_by": it.get("due_by", []),
                    "service": _match_service(db, it["label"])})
        if len(out) >= limit:
            break
    return out
