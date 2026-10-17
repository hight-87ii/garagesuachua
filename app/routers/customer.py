from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os

from app.database import get_db
from app.models.models import User, Vehicle, Appointment, RepairOrder, Invoice, EmployeeProfile, ServiceCatalog, RepairOrderPart
from app.routers.auth import get_current_user_from_cookie
from app.services.ai_service import analyze_vehicle_symptoms
from app.services.appointment_sweep import auto_cancel_noshow

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def check_auth(request: Request, db: Session, allowed_roles: list = ["customer"]):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None
    if user.get("role") not in allowed_roles and user.get("role") != "admin":
        return None
    return user

# --- QUẢN LÝ XE ---

@router.get("/my-vehicles", response_class=HTMLResponse)
async def my_vehicles(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer", "manager", "technician"])
    if not user:
        return RedirectResponse("/login")
    
    # Lấy DB user id
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    vehicles = db.query(Vehicle).filter(Vehicle.user_id == db_user.id).all()
    
    return templates.TemplateResponse(request=request, name="vehicles.html", context={"user": user, "vehicles": vehicles})

@router.post("/my-vehicles/add")
async def add_vehicle(
    request: Request,
    license_plate: str = Form(...),
    make: str = Form(...),
    model: str = Form(...),
    manufacture_year: int = Form(None),
    version: str = Form(None),
    color: str = Form(None),
    fuel_type: str = Form(None),
    vin: str = Form(None),
    engine_number: str = Form(None),
    current_odo: int = Form(None),
    registration_date: str = Form(None),
    purchase_date: str = Form(None),
    usage_type: str = Form(None),
    warranty_status: str = Form(None),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
        
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    new_vehicle = Vehicle(
        license_plate=license_plate, make=make, model=model, user_id=db_user.id,
        manufacture_year=manufacture_year, version=version, color=color,
        fuel_type=fuel_type, vin=vin, engine_number=engine_number,
        current_odo=current_odo, registration_date=registration_date,
        purchase_date=purchase_date, usage_type=usage_type, warranty_status=warranty_status
    )
    try:
        db.add(new_vehicle)
        db.commit()
    except Exception as e:
        db.rollback() # Bỏ qua lỗi duplicate biển số
        
    return RedirectResponse("/my-vehicles", status_code=302)

@router.post("/my-vehicles/update-odo")
async def update_odo(
    request: Request,
    vehicle_id: int = Form(...),
    new_odo: int = Form(...),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
        
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.user_id == db_user.id).first()
    
    if vehicle and new_odo >= (vehicle.current_odo or 0):
        vehicle.current_odo = new_odo
        db.commit()
        
    return RedirectResponse("/my-vehicles", status_code=302)

# --- ĐỘI NGŨ KỸ THUẬT VIÊN ---

@router.get("/our-team", response_class=HTMLResponse)
async def our_team(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)

    # Chỉ thợ đang làm việc mới hiện cho khách chọn/xem
    technicians = db.query(User).filter(
        User.role == "technician", User.is_active != 0).all()

    # Số liệu thật cho từng thợ: việc hoàn thành + điểm đánh giá trung bình
    tech_stats = {}
    for t in technicians:
        done_q = db.query(RepairOrder).filter(
            RepairOrder.technician_id == t.id, RepairOrder.status == "Completed")
        done_n = done_q.count()
        rated = [o.service_rating for o in done_q.all() if o.service_rating]
        avg = round(sum(rated) / len(rated), 1) if rated else None
        open_n = db.query(RepairOrder).filter(
            RepairOrder.technician_id == t.id,
            RepairOrder.status.in_(["Pending", "In Progress"])).count()
        tech_stats[t.id] = {"done": done_n, "avg": avg, "nrate": len(rated), "open": open_n}

    return templates.TemplateResponse(request=request, name="our_team.html", context={
        "user": user, "technicians": technicians, "tech_stats": tech_stats
    })

@router.get("/our-team/{tech_id}", response_class=HTMLResponse)
async def tech_public_profile(request: Request, tech_id: int, db: Session = Depends(get_db)):
    """Khách hàng xem chi tiết hồ sơ công khai của kỹ thuật viên."""
    user = get_current_user_from_cookie(request, db)

    tech = db.query(User).filter(User.id == tech_id, User.role == "technician").first()
    if not tech or getattr(tech, "is_active", 1) == 0:
        return RedirectResponse("/our-team")

    done_orders = db.query(RepairOrder).filter(
        RepairOrder.technician_id == tech.id, RepairOrder.status == "Completed"
    ).order_by(RepairOrder.completed_at.desc()).all()
    rated = [o.service_rating for o in done_orders if o.service_rating]
    avg = round(sum(rated) / len(rated), 1) if rated else None
    open_n = db.query(RepairOrder).filter(
        RepairOrder.technician_id == tech.id,
        RepairOrder.status.in_(["Pending", "In Progress"])).count()
    # Đánh giá gần nhất có điểm (ẩn tên khách — chỉ hiện xe đã làm + thời gian)
    reviews = [o for o in done_orders if o.service_rating][:3]

    stats = {"done": len(done_orders), "avg": avg, "nrate": len(rated), "open": open_n}
    return templates.TemplateResponse(request=request, name="tech_detail.html", context={
        "user": user, "tech": tech, "ep": tech.employee_profile,
        "stats": stats, "reviews": reviews
    })

# --- ĐẶT LỊCH HẸN & AI ---

@router.get("/my-appointments", response_class=HTMLResponse)
async def my_appointments(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
        
    db_user = db.query(User).filter(User.username == user["sub"]).first()

    # Tự động hủy lịch quá hẹn 24h không tới + xóa lịch đã hủy quá 1 ngày
    auto_n = auto_cancel_noshow(db)
    _purge_old_cancelled(db)

    vehicles = db.query(Vehicle).filter(Vehicle.user_id == db_user.id).all()
    appointments = db.query(Appointment).filter(Appointment.user_id == db_user.id).order_by(Appointment.id.desc()).all()
    technicians = db.query(User).filter(
        User.role == "technician", User.is_active != 0).all()
    services = db.query(ServiceCatalog).filter(ServiceCatalog.status == "Active").all()
    
    return templates.TemplateResponse(request=request, name="appointments.html", context={
        "user": user, "vehicles": vehicles, "appointments": appointments,
        "technicians": technicians, "services": services,
        "booked": request.query_params.get("booked") == "1",
        "cancelled": request.query_params.get("cancelled") == "1",
        "auto_cancelled": auto_n,
        "error": request.query_params.get("error"),
        "today": datetime.utcnow().strftime("%Y-%m-%d"),
    })

# Khung giờ khách có thể chọn (1 nguồn duy nhất: app.core.schedule_config).
from app.core.schedule_config import WORK_SLOTS as TIME_SLOTS

@router.post("/my-appointments/book")
async def book_appointment(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
        
    form_data = await request.form()
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    
    # --- Validate cơ bản ---
    vehicle_id_raw = form_data.get("vehicle_id")
    appointment_date = (form_data.get("appointment_date") or "").strip()
    appointment_time = (form_data.get("appointment_time") or "").strip()
    appointment_type = form_data.get("appointment_type", "Repair")
    
    def error_redirect(msg: str):
        from urllib.parse import quote
        return RedirectResponse(f"/my-appointments?error={quote(msg)}", status_code=302)
    
    if not vehicle_id_raw:
        return error_redirect("Bạn chưa chọn xe. Vui lòng chọn xe cần đặt lịch.")
    
    vehicle = db.query(Vehicle).filter(
        Vehicle.id == int(vehicle_id_raw),
        Vehicle.user_id == db_user.id
    ).first()
    if not vehicle:
        return error_redirect("Xe không tồn tại hoặc không thuộc tài khoản của bạn.")
    
    if not appointment_date:
        return error_redirect("Bạn chưa chọn ngày hẹn.")
    
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if appointment_date < today_str:
        return error_redirect("Ngày hẹn không được ở quá khứ. Vui lòng chọn ngày từ hôm nay trở đi.")
    
    if appointment_time and appointment_time not in TIME_SLOTS:
        return error_redirect("Khung giờ không hợp lệ. Vui lòng chọn lại.")
    
    preferred_technician_id = form_data.get("preferred_technician_id")
    preferred_technician_id = int(preferred_technician_id) if preferred_technician_id else None

    # Xác minh chặt: KTV phải tồn tại & đúng vai trò; chặn ngày xưởng nghỉ.
    from app.agents.tools import (
        booking_conflicts, is_valid_technician, BOOKING_LOCK,
    )
    from app.core.schedule_config import day_off_reason
    if not is_valid_technician(db, preferred_technician_id):
        return error_redirect("Kỹ thuật viên không hợp lệ. Vui lòng chọn lại.")
    off = day_off_reason(appointment_date)
    if off:
        return error_redirect(off + " Vui lòng chọn ngày khác.")

    symptoms = ""
    ai_result = None
    
    if appointment_type == "CarWash":
        # Get selected services
        service_ids = form_data.getlist("service_ids")
        if not service_ids:
            # Fallback if no service selected
            symptoms = "Yêu cầu dịch vụ Rửa xe / Chăm sóc xe"
        else:
            selected_services = db.query(ServiceCatalog).filter(ServiceCatalog.id.in_(service_ids)).all()
            service_names = [s.name for s in selected_services]
            symptoms = "Yêu cầu dịch vụ: " + ", ".join(service_names)
    else:
        symptoms = (form_data.get("symptoms") or "").strip()
        if not symptoms:
            return error_redirect("Bạn mô tả tình trạng lỗi để garage tiếp nhận nhé!")
        # Gọi AI chỉ khi là sửa chữa
        ai_result = analyze_vehicle_symptoms(symptoms)
    
    # Khóa tuần tự + kiểm tra kín chỗ rồi mới tạo: 2 request đồng thời không
    # thể cùng đặt vào 1 khung chỉ còn 1 chỗ (dùng chung luật với AI agents).
    with BOOKING_LOCK:
        blocks = booking_conflicts(db, appointment_date, appointment_time or None,
                                   preferred_technician_id)
        if blocks:
            return error_redirect("Không thể đặt: " + " ".join(blocks)
                                  + " Vui lòng chọn khung giờ hoặc kỹ thuật viên khác.")

        new_app = Appointment(
            user_id=db_user.id,
            vehicle_id=vehicle.id,
            appointment_date=appointment_date,
            appointment_time=appointment_time or None,
            appointment_type=appointment_type,
            symptoms=symptoms,
            ai_diagnosis=ai_result,
            status="Pending",
            preferred_technician_id=preferred_technician_id
        )
        db.add(new_app)
        db.flush() # Lấy id lịch hẹn để liên kết phiếu sửa chữa

        new_ro = RepairOrder(
            vehicle_id=vehicle.id,
            technician_id=preferred_technician_id,
            appointment_id=new_app.id,
            order_type=appointment_type,
            symptoms=symptoms,
            status="Pending"
        )
        db.add(new_ro)
        db.commit()

    return RedirectResponse("/my-appointments?booked=1", status_code=302)

@router.post("/my-appointments/{appointment_id}/cancel")
async def cancel_appointment(request: Request, appointment_id: int, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
    
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    appt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.user_id == db_user.id
    ).first()
    
    # Chỉ cho phép hủy lịch còn Pending hoặc Confirmed
    if appt and appt.status in ("Pending", "Confirmed"):
        appt.status = "Cancelled"
        appt.cancelled_at = datetime.utcnow()
        db.commit()

    return RedirectResponse("/my-appointments?cancelled=1", status_code=302)

# --- CHI TIẾT CÔNG VIỆC SỬA CHỮA (KHÁCH HÀNG) ---

@router.get("/my-repairs/{order_id}", response_class=HTMLResponse)
async def my_repair_detail(request: Request, order_id: int, db: Session = Depends(get_db)):
    """Khách hàng xem chi tiết công việc sửa chữa: thông tin công việc + thông tin kỹ thuật."""
    user = check_auth(request, db, ["customer", "manager", "technician"])
    if not user:
        return RedirectResponse("/login")

    db_user = db.query(User).filter(User.username == user["sub"]).first()
    order = db.query(RepairOrder).join(Vehicle).filter(
        RepairOrder.id == order_id,
        Vehicle.user_id == db_user.id
    ).first()
    if not order:
        return RedirectResponse("/my-appointments")

    # --- Định dạng chuỗi datetime (các cột reception/handover là String) ---
    def _fmt_dt(v):
        if not v:
            return None
        s = str(v)
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(s, fmt).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                continue
        return s

    # --- Timeline 5 bước (ưu tiên trạng thái đơn trước) ---
    if order.handover_datetime:
        active_idx = 5          # hoàn thành + bàn giao xong → tất cả done
    elif order.status == "Completed":
        active_idx = 4          # đã xong, chờ bàn giao
    elif not order.reception_datetime:
        active_idx = 0          # chưa tiếp nhận xe
    elif order.estimated_cost is None or order.customer_approval == "Pending":
        active_idx = 1          # đang kiểm tra / chờ duyệt báo giá
    else:  # In Progress hoặc đã duyệt, chờ bắt đầu
        active_idx = 2

    if order.status == "Completed":
        repair_note = "Đã sửa xong"
    elif order.status == "In Progress":
        repair_note = "Đang thực hiện"
    elif order.customer_approval == "Approved":
        repair_note = "Chờ garage bắt đầu"
    else:
        repair_note = None

    step_defs = [
        ("Tiếp nhận xe", _fmt_dt(order.reception_datetime)),
        ("Kiểm tra & báo giá",
         f"Đã báo giá {order.estimated_cost:,} đ".replace(",", ".") if order.estimated_cost
         else ("Chưa phát sinh báo giá" if order.status == "Completed" else "Đang kiểm tra hiện trạng")),
        ("Sửa chữa", repair_note),
        ("Hoàn thành", order.completed_at.strftime("%d/%m/%Y %H:%M") if order.completed_at else None),
        ("Bàn giao xe", _fmt_dt(order.handover_datetime)),
    ]
    steps = []
    for idx, (label, note) in enumerate(step_defs):
        state = "done" if idx < active_idx else ("active" if idx == active_idx else "pending")
        steps.append({"label": label, "note": note, "state": state})

    # --- Chi phí ---
    labor_cost = order.estimated_cost or 0
    parts_total = sum(p.quantity * p.unit_price for p in order.used_parts)

    # --- Video (7 ngày) & ảnh nghiệm thu ---
    video_available = False
    video_expires_at = None
    video_url = None
    if order.repair_video_path and order.completed_at:
        video_expires_at = order.completed_at + timedelta(days=7)
        existing_video = _repair_video_file(order.repair_video_path)
        if datetime.utcnow() <= video_expires_at and existing_video:
            video_available = True
            video_url = f"/repairs/{order.id}/video"

    completion_images = [s.strip() for s in (order.completion_images or "").split(",") if s.strip()]
    appointment = db.query(Appointment).filter(Appointment.id == order.appointment_id).first() if order.appointment_id else None

    # Danh sách hiển thị an toàn (các trường đều Optional)
    def _split(v):
        return [s.strip() for s in (v or "").split(",") if s.strip()]

    technical = {
        "reception_datetime": _fmt_dt(order.reception_datetime),
        "deliverer_name": order.deliverer_name,
        "fuel_level": order.fuel_level,
        "current_odo": order.current_odo,
        "symptom_severity": order.symptom_severity,
        "abnormal_sounds": order.abnormal_sounds,
        "warning_lights": _split(order.warning_lights),
        "exterior_scratches": _split(order.exterior_scratches),
        "key_count": order.key_count,
        "personal_belongings": _split(order.personal_belongings),
    }

    return templates.TemplateResponse(request=request, name="my_repair_detail.html", context={
        "user": user,
        "order": order,
        "vehicle": order.vehicle,
        "appointment": appointment,
        "steps": steps,
        "labor_cost": labor_cost,
        "parts_total": parts_total,
        "handover_fmt": _fmt_dt(order.handover_datetime),
        "technical": technical,
        "completion_images": completion_images,
        "video_available": video_available,
        "video_url": video_url,
        "video_expires_at": video_expires_at,
    })

CANCELLED_RETENTION_DAYS = 1

def _purge_old_cancelled(db: Session) -> int:
    """Xóa lịch hẹn đã hủy quá 1 ngày.

    Kèm theo: phiếu sửa chữa được tạo từ lịch đó nhưng chưa làm gì
    (vẫn Pending, chưa tiếp nhận, chưa có hóa đơn) cũng bị xóa để
    tránh rác. Phiếu đã tiếp nhận / đang sửa / hoàn thành và hóa đơn
    đã xuất được giữ lại làm hồ sơ.
    """
    cutoff = datetime.utcnow() - timedelta(days=CANCELLED_RETENTION_DAYS)
    old = db.query(Appointment).filter(
        Appointment.status == "Cancelled",
        Appointment.cancelled_at.isnot(None),
        Appointment.cancelled_at <= cutoff,
    ).all()
    for appt in old:
        linked = db.query(RepairOrder).filter(
            RepairOrder.appointment_id == appt.id,
            RepairOrder.status == "Pending",
            RepairOrder.reception_datetime.is_(None),
        ).all()
        for order in linked:
            if order.invoice:
                continue
            db.query(RepairOrderPart).filter(
                RepairOrderPart.repair_order_id == order.id
            ).delete()
            db.delete(order)
        db.delete(appt)
    if old:
        db.commit()
    return len(old)

# --- HÓA ĐƠN ---

@router.get("/my-invoices", response_class=HTMLResponse)
async def my_invoices(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
        
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    
    # Lấy tất cả hóa đơn của các xe thuộc sở hữu người dùng này
    vehicles = db.query(Vehicle).filter(Vehicle.user_id == db_user.id).all()
    vehicle_ids = [v.id for v in vehicles]
    
    invoices = db.query(Invoice).join(RepairOrder).filter(RepairOrder.vehicle_id.in_(vehicle_ids)).order_by(Invoice.id.desc()).all()
    
    # --- Tổng hợp KPI cho 4 thẻ đầu trang ---
    now = datetime.utcnow()
    kpi = {
        "total_count": len(invoices),
        "total_spent": sum(i.total_amount or 0 for i in invoices),
        "total_unpaid": sum(i.total_amount or 0 for i in invoices if i.status == "Unpaid"),
        "month_total": sum(
            i.total_amount or 0 for i in invoices
            if i.created_at and i.created_at.year == now.year and i.created_at.month == now.month
        ),
    }
    
    # --- Chuẩn bị dữ liệu hiển thị (tóm tắt dịch vụ + nhóm theo tháng) ---
    groups = {}
    for inv in invoices:
        order = inv.repair_order
        vehicle = order.vehicle
        parts_count = len(order.used_parts)
        
        if order.order_type == "CarWash":
            summary = "Dịch vụ rửa xe / chăm sóc xe"
        elif order.inspection_result:
            summary = order.inspection_result
        else:
            summary = order.symptoms or "Sửa chữa, bảo dưỡng"
        if parts_count:
            summary += f" · {parts_count} phụ tùng thay thế"
        
        month_key = inv.created_at.strftime("%m/%Y") if inv.created_at else "Khác"
        groups.setdefault(month_key, []).append({
            "inv": inv,
            "vehicle": vehicle,
            "summary": summary,
            "search": f"HD-{inv.id:04d} {vehicle.license_plate if vehicle else ''} {summary}".lower(),
        })
    
    return templates.TemplateResponse(request=request, name="my_invoices.html", context={
        "user": user, "invoices": invoices, "groups": groups, "kpi": kpi, "vehicles": vehicles
    })

def _repair_video_file(path: str | None) -> str | None:
    if not path:
        return None
    rel = path.lstrip("/")
    candidates = [os.path.join("app", rel), rel]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None

def _get_owned_invoice(db: Session, db_user: User, invoice_id: int) -> Invoice | None:
    """Lấy hóa đơn và kiểm tra xe thuộc sở hữu khách hàng (chống truy cập IDOR)."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice or not invoice.repair_order or not invoice.repair_order.vehicle:
        return None
    if invoice.repair_order.vehicle.user_id != db_user.id:
        return None
    return invoice

@router.get("/my-invoices/{invoice_id}", response_class=HTMLResponse)
async def my_invoice_detail(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
    
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    invoice = _get_owned_invoice(db, db_user, invoice_id)
    if not invoice:
        return RedirectResponse("/my-invoices")
    
    order = invoice.repair_order
    
    # --- Timeline tiến trình sửa chữa ---
    if order.status == "Pending":
        active_idx = 1        # đang ở bước kiểm tra & báo giá
    elif order.status == "In Progress":
        active_idx = 2        # đang sửa
    elif order.handover_datetime:
        active_idx = 5        # hoàn thành + bàn giao xong
    else:
        active_idx = 4        # hoàn thành, chờ bàn giao
    
    step_defs = [
        ("Tiếp nhận xe", order.created_at.strftime("%d/%m/%Y %H:%M") if order.created_at else None),
        ("Kiểm tra & báo giá", f"Khách { 'đã duyệt' if order.customer_approval == 'Approved' else ('đã từ chối' if order.customer_approval == 'Rejected' else 'chờ duyệt báo giá') }"),
        ("Sửa chữa", None),
        ("Hoàn thành", order.completed_at.strftime("%d/%m/%Y %H:%M") if order.completed_at else None),
        ("Bàn giao xe", order.handover_datetime or None),
    ]
    steps = []
    for idx, (label, note) in enumerate(step_defs):
        state = "done" if idx < active_idx else ("active" if idx == active_idx else "pending")
        steps.append({"label": label, "note": note, "state": state})
    
    labor_cost = order.estimated_cost or 0
    parts_total = sum(p.quantity * p.unit_price for p in order.used_parts)

    # --- Video camera xe đang sửa: lưu 7 ngày kể từ khi sửa xong ---
    video_available = False
    video_expires_at = None
    video_url = None
    if order.repair_video_path and order.completed_at:
        video_expires_at = order.completed_at + timedelta(days=7)
        existing_video = _repair_video_file(order.repair_video_path)
        if datetime.utcnow() <= video_expires_at and existing_video:
            video_available = True
            video_url = f"/repairs/{order.id}/video"
        elif datetime.utcnow() > video_expires_at:
            # Hết hạn: xóa file để giải phóng dung lượng, giữ biên bản chữ
            try:
                if existing_video:
                    os.remove(existing_video)
            except OSError:
                pass
            order.repair_video_path = None
            db.commit()

    completion_images = [s.strip() for s in (order.completion_images or "").split(",") if s.strip()]

    return templates.TemplateResponse(request=request, name="my_invoice_detail.html", context={
        "user": user,
        "invoice": invoice,
        "order": order,
        "steps": steps,
        "labor_cost": labor_cost,
        "parts_total": parts_total,
        "payment_methods": ["Tiền mặt", "Chuyển khoản", "Ví điện tử", "Thẻ ngân hàng"],
        "video_available": video_available,
        "video_url": video_url,
        "video_expires_at": video_expires_at,
        "completion_images": completion_images,
    })

@router.post("/my-invoices/{invoice_id}/pay")
async def confirm_invoice_payment(
    request: Request,
    invoice_id: int,
    payment_method: str = Form(...),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")
    
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    invoice = _get_owned_invoice(db, db_user, invoice_id)
    if not invoice:
        return RedirectResponse("/my-invoices")
    
    if invoice.status == "Unpaid":
        invoice.status = "Paid"
        invoice.payment_method = payment_method
        db.commit()
    
    return RedirectResponse(f"/my-invoices/{invoice_id}", status_code=302)

@router.get("/my-invoices/{invoice_id}/print", response_class=HTMLResponse)
async def print_my_invoice(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["customer"])
    if not user:
        return RedirectResponse("/login")

    db_user = db.query(User).filter(User.username == user["sub"]).first()
    invoice = _get_owned_invoice(db, db_user, invoice_id)
    if not invoice:
        return RedirectResponse("/my-invoices")

    return templates.TemplateResponse(request, "invoice_print.html", {
        "invoice": invoice,
        "user": user,
    })

@router.get("/repairs/{order_id}/video")
async def watch_repair_video(request: Request, order_id: int, db: Session = Depends(get_db)):
    """Chủ xe xem video xe đang sửa. Video chỉ tồn tại 7 ngày từ khi sửa xong."""
    user = check_auth(request, db, ["customer", "technician", "manager"])
    if not user:
        return RedirectResponse("/login")

    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order or not order.repair_video_path or not order.completed_at:
        raise HTTPException(status_code=404, detail="Không tìm thấy video.")

    if user.get("role") == "customer":
        db_user = db.query(User).filter(User.username == user["sub"]).first()
        if not order.vehicle or order.vehicle.user_id != db_user.id:
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem video này.")

    expires_at = order.completed_at + timedelta(days=7)
    if datetime.utcnow() > expires_at:
        raise HTTPException(status_code=410, detail="Video đã hết hạn lưu trữ 7 ngày.")

    file_path = _repair_video_file(order.repair_video_path)
    if not file_path:
        raise HTTPException(status_code=404, detail="File video không còn tồn tại.")

    return FileResponse(file_path, media_type="video/mp4", filename=f"repair-{order.id}.mp4")

@router.post("/my-appointments/approve")
async def approve_quote(
    request: Request,
    order_id: int = Form(...),
    action: str = Form(...), # 'approve' or 'reject'
    next: str = Form(""),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["customer"])
    if not user: return RedirectResponse("/login")
    
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    order = db.query(RepairOrder).join(Vehicle).filter(RepairOrder.id == order_id, Vehicle.user_id == db_user.id).first()
    
    if order:
        if action == "approve":
            order.customer_approval = "Approved"
        else:
            order.customer_approval = "Rejected"
            order.status = "Completed" # Từ chối báo giá coi như hủy/xong
        db.commit()
    # Quay lại trang chi tiết công việc nếu được chỉ định (an toàn: chỉ chấp nhận path nội bộ)
    if next.startswith("/my-repairs/"):
        return RedirectResponse(next, status_code=302)
    return RedirectResponse("/my-appointments", status_code=302)

@router.post("/my-appointments/rate")
async def rate_service(
    request: Request,
    order_id: int = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["customer"])
    if not user: return RedirectResponse("/login")
    
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    order = db.query(RepairOrder).join(Vehicle).filter(RepairOrder.id == order_id, Vehicle.user_id == db_user.id).first()
    
    if order and order.status == "Completed":
        order.service_rating = rating
        db.commit()
    return RedirectResponse("/my-appointments", status_code=302)
