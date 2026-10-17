from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.database import get_db
from app.models.models import User, RepairOrder, Invoice, SparePart, Vehicle, Appointment
from app.routers.auth import get_current_user_from_cookie

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def check_auth(request: Request, db: Session, allowed_roles: list = ["manager"]):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None
    if user.get("role") not in allowed_roles and user.get("role") != "admin":
        return None
    return user

@router.get("/manager/overview", response_class=HTMLResponse)
async def manager_overview(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    from datetime import datetime, date, timedelta
    from dateutil.relativedelta import relativedelta
    today = date.today()
    today_str = today.strftime("%d/%m/%Y")
    today_ymd = today.strftime("%Y-%m-%d")

    period = request.query_params.get("period", "day")
    months = int(request.query_params.get("months", "3"))
    
    if period == "day":
        start_date = today
        period_label = "Hôm nay"
    elif period == "week":
        start_date = today - timedelta(days=6)
        period_label = "7 ngày qua"
    elif period == "month":
        start_date = today.replace(day=1)
        period_label = "Tháng này"
    elif period == "custom":
        start_date = today - relativedelta(months=months)
        period_label = f"{months} tháng gần nhất"
    else:
        start_date = today
        period_label = "Hôm nay"

    period_start_str = start_date.strftime("%d/%m/%Y")

    # Query all, then filter in memory
    from app.services.appointment_sweep import auto_cancel_noshow
    auto_cancel_noshow(db)
    all_orders = db.query(RepairOrder).order_by(RepairOrder.id.desc()).all()
    all_invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
    from app.models.models import Appointment
    all_appointments = db.query(Appointment).order_by(Appointment.appointment_date.asc()).all()

    # Filter based on period
    orders = [o for o in all_orders if o.created_at and o.created_at.date() >= start_date]
    invoices = [i for i in all_invoices if i.created_at and i.created_at.date() >= start_date]
    
    def parse_apt_date(d_str):
        if not d_str: return None
        try: return datetime.strptime(d_str, "%Y-%m-%d").date()
        except: return None

    appointments = [a for a in all_appointments if parse_apt_date(a.appointment_date) and parse_apt_date(a.appointment_date) >= start_date]

    # 1. KPI
    today_appointments = [a for a in all_appointments if a.appointment_date and a.appointment_date.startswith(today_ymd)]
    
    period_revenue = sum((inv.total_amount or 0) for inv in invoices)
    
    kpi = {
        "received": len([o for o in orders if o.status == 'Pending']),
        "in_progress": len([o for o in orders if o.status == 'In Progress']),
        "completed_today": len([o for o in orders if o.status == 'Completed']),
        "appointments_today": len(appointments),
        "revenue_today": period_revenue,
        "pending_issues": len([a for a in appointments if a.status == 'Pending'])
    }
    
    # 2. Workshop Status (real-time, not period-filtered)
    status = {
        "pending": len([o for o in all_orders if o.status == 'Pending']),
        "checking": 0,
        "repairing": len([o for o in all_orders if o.status == 'In Progress']),
        "waiting_parts": 0,
        "completed": len([o for o in all_orders if o.status == 'Completed']),
        "handed_over": len([o for o in all_orders if getattr(o, 'handover_datetime', None)])
    }
    
    # 3. Technician Performance — period-aware, rich metrics
    from app.models.models import User
    techs = db.query(User).filter(User.role == 'technician').order_by(User.full_name).all()

    # Build invoice lookup: repair_order_id -> invoice total
    invoice_by_order = {inv.repair_order_id: (inv.total_amount or 0) for inv in all_invoices}

    tech_perf = []
    for t in techs:
        tech_orders = [o for o in orders if o.technician_id == t.id]
        completed = [o for o in tech_orders if o.status == 'Completed']
        in_prog   = [o for o in tech_orders if o.status == 'In Progress']
        pending   = [o for o in tech_orders if o.status == 'Pending']
        total     = len(tech_orders)

        # Revenue: sum invoices of completed orders in period
        revenue = sum(invoice_by_order.get(o.id, 0) for o in completed)

        # Completion rate
        completion_rate = round(len(completed) / total * 100) if total > 0 else 0

        # Average days to complete
        durations = []
        for o in completed:
            if o.completed_at and o.created_at:
                delta = (o.completed_at - o.created_at).total_seconds() / 86400
                if delta >= 0:
                    durations.append(delta)
        avg_days = round(sum(durations) / len(durations), 1) if durations else None

        # Rating average for completed orders with ratings
        ratings = [o.service_rating for o in completed if o.service_rating]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

        tech_perf.append({
            "id": t.id,
            "name": t.full_name,
            "total": total,
            "in_progress": len(in_prog),
            "completed": len(completed),
            "pending": len(pending),
            "revenue": revenue,
            "completion_rate": completion_rate,
            "avg_days": avg_days,
            "avg_rating": avg_rating,
            # Keep old key for backward compat
            "completed_today": len(completed),
        })

    # Sort by completed desc, then revenue desc
    tech_perf.sort(key=lambda x: (-x["completed"], -x["revenue"]))

    # ── Chart data ──────────────────────────────────────────────────────────
    # A) Revenue time-series: group invoices by day within the period
    from collections import defaultdict
    import json as _json

    rev_by_day: dict = defaultdict(float)
    orders_by_day: dict = defaultdict(int)

    # Determine step: day-by-day for ≤31 days, month-by-month for longer
    total_days = (today - start_date).days + 1
    use_monthly = total_days > 45

    if use_monthly:
        # Group by YYYY-MM
        for inv in invoices:
            if inv.created_at:
                key = inv.created_at.strftime("%Y-%m")
                rev_by_day[key] += (inv.total_amount or 0)
        for o in orders:
            if o.created_at:
                key = o.created_at.strftime("%Y-%m")
                orders_by_day[key] += 1
        # Build sorted label list
        cur = start_date.replace(day=1)
        chart_labels = []
        while cur <= today:
            chart_labels.append(cur.strftime("%Y-%m"))
            cur = (cur + relativedelta(months=1)).replace(day=1)
        chart_rev_values = [round(rev_by_day.get(l, 0) / 1_000_000, 2) for l in chart_labels]
        chart_order_values = [orders_by_day.get(l, 0) for l in chart_labels]
        chart_label_display = [l[5:] + "/" + l[:4] for l in chart_labels]  # MM/YYYY
    else:
        # Day-by-day
        for inv in invoices:
            if inv.created_at:
                key = inv.created_at.strftime("%Y-%m-%d")
                rev_by_day[key] += (inv.total_amount or 0)
        for o in orders:
            if o.created_at:
                key = o.created_at.strftime("%Y-%m-%d")
                orders_by_day[key] += 1
        chart_labels = []
        cur_d = start_date
        while cur_d <= today:
            chart_labels.append(cur_d.strftime("%Y-%m-%d"))
            cur_d += timedelta(days=1)
        chart_rev_values = [round(rev_by_day.get(l, 0) / 1_000_000, 2) for l in chart_labels]
        chart_order_values = [orders_by_day.get(l, 0) for l in chart_labels]
        chart_label_display = [l[8:] + "/" + l[5:7] for l in chart_labels]  # DD/MM

    chart_revenue = {
        "labels": _json.dumps(chart_label_display),
        "revenue": _json.dumps(chart_rev_values),
        "orders": _json.dumps(chart_order_values),
    }

    # B) Order status distribution (real-time snapshot)
    chart_status = {
        "labels": _json.dumps(["Chờ tiếp nhận", "Đang sửa", "Hoàn thành", "Đã bàn giao"]),
        "values": _json.dumps([
            status["pending"],
            status["repairing"],
            status["completed"],
            status["handed_over"],
        ]),
    }

    # C) Tech performance bar chart (period)
    tp_names  = [t["name"].split()[-1] for t in tech_perf]   # short name (last word)
    tp_done   = [t["completed"] for t in tech_perf]
    tp_prog   = [t["in_progress"] for t in tech_perf]
    tp_rev_m  = [round(t["revenue"] / 1_000_000, 2) for t in tech_perf]
    chart_tech = {
        "labels":    _json.dumps(tp_names),
        "completed": _json.dumps(tp_done),
        "in_prog":   _json.dumps(tp_prog),
        "revenue":   _json.dumps(tp_rev_m),
    }
    # ────────────────────────────────────────────────────────────────────────

    # 4. Kho phụ tùng + khách hàng
    all_parts = db.query(SparePart).all()
    low_stock_parts = [p for p in all_parts if (p.stock_quantity or 0) <= (p.min_stock or 5)]
    out_of_stock = [p for p in all_parts if (p.stock_quantity or 0) <= 0]
    lowest_parts = sorted(all_parts, key=lambda p: (p.stock_quantity or 0))[:4]
    customer_count = db.query(User).filter(User.role == 'customer').count()
    vehicle_count = db.query(Vehicle).count()
    technicians = db.query(User).filter(User.role == 'technician', User.is_active != 0).order_by(User.full_name).all()
    from app.core.agent_monitor import read_agent_daily_stats
    agent_stats = read_agent_daily_stats(days=14)

    return templates.TemplateResponse(request=request, name="manager_overview.html", context={
        "user": user, "orders": orders, "invoices": invoices, "appointments": appointments,
        "kpi": kpi, "status_counts": status, "today_appointments": today_appointments[:5],
        "tech_perf": tech_perf, "today_str": today_str,
        "current_period": period, "custom_months": months, "period_label": period_label,
        "period_start_str": period_start_str,
        "parts_total": len(all_parts), "low_stock_parts": low_stock_parts,
        "out_of_stock": out_of_stock, "lowest_parts": lowest_parts,
        "customer_count": customer_count, "vehicle_count": vehicle_count,
        "technicians": technicians,
        "parts": sorted(all_parts, key=lambda p: (p.name or "")),
        "chart_revenue": chart_revenue,
        "chart_status": chart_status,
        "chart_tech": chart_tech,
        "agent_stats": agent_stats,
    })

@router.post("/manager/create-invoice")
async def create_invoice(
    request: Request,
    order_id: int = Form(...),
    total_amount: float = Form(...),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    # Tạo hóa đơn cho order
    existing_inv = db.query(Invoice).filter(Invoice.repair_order_id == order_id).first()
    if not existing_inv:
        new_inv = Invoice(repair_order_id=order_id, total_amount=total_amount)
        db.add(new_inv)
        db.commit()
        
    return RedirectResponse("/manager/overview", status_code=302)

@router.post("/manager/pay-invoice")
async def pay_invoice(
    request: Request,
    invoice_id: int = Form(...),
    payment_method: str = Form("Tiền mặt"),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if inv:
        inv.status = "Paid"
        inv.payment_method = payment_method
        db.commit()
        
    return RedirectResponse("/manager/overview", status_code=302)

# --- QUẢN LÝ TÀI KHOẢN ---

# Vai trò mà từng người được GÁN MỚI:
# - Quản lý (manager): chỉ được tạo/tăng cấp lên Khách hàng.
# - Chỉ admin mới được tạo/tăng cấp lên Kỹ thuật viên, Quản lý, Admin.
MANAGER_ASSIGNABLE_ROLES = {"customer"}
ADMIN_ASSIGNABLE_ROLES = {"customer", "technician", "manager", "admin"}

def _assignable_roles(manager_user: dict) -> set:
    if manager_user.get("role") == "admin":
        return ADMIN_ASSIGNABLE_ROLES
    return MANAGER_ASSIGNABLE_ROLES

def _can_manager_edit(manager_user: dict, target: User, new_role: str) -> bool:
    is_admin = manager_user.get("role") == "admin"
    # Không được sửa tài khoản admin (trừ chính admin).
    if target.role == "admin" and not is_admin:
        return False
    # Không cho tự đổi role của chính mình (chống tự hạ/tự nâng quyền).
    if target.username == manager_user.get("sub") and new_role != target.role:
        return False
    # Đổi sang vai trò mới thì vai đó phải nằm trong quyền được gán.
    if new_role != target.role and new_role not in _assignable_roles(manager_user):
        return False
    return True

@router.get("/manager/users", response_class=HTMLResponse)
async def manager_users(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    # Lấy danh sách tài khoản (Trừ tài khoản manager đang đăng nhập)
    users = db.query(User).filter(User.username != user["sub"]).all()
    
    return templates.TemplateResponse(request=request, name="manager_users.html", context={
        "user": user, "users": users
    })

@router.post("/manager/users/update")
async def update_user(
    request: Request,
    user_id: int = Form(...),
    full_name: str = Form(...),
    phone: str = Form(None),
    email: str = Form(None),
    address: str = Form(None),
    role: str = Form(...),
    password: str = Form(None),
    db: Session = Depends(get_db)
):
    manager_user = check_auth(request, db, ["manager"])
    if not manager_user:
        return RedirectResponse("/login")

    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        if not _can_manager_edit(manager_user, db_user, role):
            return RedirectResponse("/manager/users?error=forbidden_role", status_code=302)
        db_user.full_name = full_name
        db_user.phone = phone
        db_user.email = email
        db_user.address = address
        db_user.role = role
        
        # Nhập vào form thì hash mới lưu
        if password:
            from app.routers.auth import get_password_hash
            db_user.password_hash = get_password_hash(password)
            
        db.commit()
        
    return RedirectResponse("/manager/users?success=1", status_code=302)

@router.post("/manager/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(None),
    email: str = Form(None),
    role: str = Form(...),
    db: Session = Depends(get_db)
):
    manager_user = check_auth(request, db, ["manager"])
    if not manager_user:
        return RedirectResponse("/login")
        
    # Kiểm tra xem username đã tồn tại chưa
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return RedirectResponse("/manager/users?error=username_exists", status_code=302)

    if role not in _assignable_roles(manager_user):
        return RedirectResponse("/manager/users?error=forbidden_role", status_code=302)

    from app.routers.auth import get_password_hash
    
    new_user = User(
        username=username,
        password_hash=get_password_hash(password),
        full_name=full_name,
        phone=phone,
        email=email,
        role=role
    )
    db.add(new_user)
    db.commit()

    return RedirectResponse("/manager/users?success=1", status_code=302)

LEAVE_REASONS = {"Nghi viec": "Đã nghỉ việc", "Di hoc nang cao": "Đi học nâng cao",
                 "Trai nghiem": "Trải nghiệm bên ngoài", "Khac": "Lý do khác"}

@router.post("/manager/users/toggle-active")
async def toggle_user_active(
    request: Request,
    user_id: int = Form(...),
    action: str = Form(...),  # 'lock' | 'unlock'
    leave_reason: str = Form(""),
    leave_date: str = Form(""),
    db: Session = Depends(get_db)
):
    """Khóa / mở lại tài khoản (nghỉ việc, đi học, trải nghiệm... rồi quay lại)."""
    manager_user = check_auth(request, db, ["manager"])
    if not manager_user:
        return RedirectResponse("/login")

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        return RedirectResponse("/manager/users", status_code=302)
    # Không tự khóa chính mình; không khóa admin (trừ chính admin).
    if db_user.username == manager_user.get("sub"):
        return RedirectResponse("/manager/users?error=forbidden_role", status_code=302)
    if db_user.role == "admin" and manager_user.get("role") != "admin":
        return RedirectResponse("/manager/users?error=forbidden_role", status_code=302)

    if action == "lock":
        db_user.is_active = 0
        db_user.leave_reason = leave_reason or "Khac"
        db_user.leave_date = (leave_date or "").strip() or datetime.now().strftime("%Y-%m-%d")
        db_user.return_date = None
    elif action == "unlock":
        db_user.is_active = 1
        db_user.return_date = datetime.now().strftime("%Y-%m-%d")
    db.commit()
    return RedirectResponse("/manager/users?success=1", status_code=302)

# --- QUẢN LÝ TÀI LIỆU GARA CHO AI ---

from app.models.models import GarageDocument

@router.get("/manager/documents", response_class=HTMLResponse)
async def manager_documents(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    documents = db.query(GarageDocument).order_by(GarageDocument.id.desc()).all()
    
    return templates.TemplateResponse(request=request, name="manager_documents.html", context={
        "user": user, "documents": documents
    })

@router.post("/manager/documents/upload")
async def upload_document(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    document_type: str = Form("report"),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    uploader = db.query(User).filter(User.username == user["sub"]).first()
    uploader_id = uploader.id if uploader else None

    from ingest_knowledge import normalize_doc_type
    new_doc = GarageDocument(
        title=title,
        content=content,
        document_type=normalize_doc_type(document_type),
        uploaded_by=uploader_id
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # DB la source of truth: nap that vao VectorDB; loi -> giu is_ingested=0
    # de bam "Nap lai" (POST /manager/documents/{id}/reingest), khong vo request.
    try:
        from ingest_knowledge import ingest_db_document
        ingest_db_document(new_doc.id)
    except Exception as e:
        new_doc.is_ingested = 0
        db.commit()
        print(f"Ingest that bai, giu is_ingested=0 de ingest lai sau: {e}")

    return RedirectResponse("/manager/documents?success=1", status_code=302)


@router.post("/manager/documents/{doc_id}/reingest")
async def reingest_document(request: Request, doc_id: int, db: Session = Depends(get_db)):
    """Nap lai 1 doc 'Cho ingest' vao VectorDB (nut o badge manager_documents)."""
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")

    doc = db.query(GarageDocument).filter(GarageDocument.id == doc_id).first()
    if not doc:
        return RedirectResponse("/manager/documents?notfound=1", status_code=302)
    try:
        from ingest_knowledge import ingest_db_document
        ingest_db_document(doc_id)
    except Exception as e:
        print(f"Reingest #{doc_id} loi: {e}")
        return RedirectResponse("/manager/documents?reingest_failed=1", status_code=302)
    return RedirectResponse("/manager/documents?reingested=1", status_code=302)

# --- QUẢN LÝ KHUYẾN MÃI ---

from app.models.models import Promotion

@router.get("/manager/promotions", response_class=HTMLResponse)
async def manager_promotions(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    promotions = db.query(Promotion).order_by(Promotion.id.desc()).all()
    
    return templates.TemplateResponse(request=request, name="manager_promotions.html", context={
        "user": user, "promotions": promotions
    })

@router.post("/manager/promotions/create")
async def create_promotion(
    request: Request,
    title: str = Form(...),
    description: str = Form(None),
    discount_percent: float = Form(0.0),
    start_date: str = Form(None),
    end_date: str = Form(None),
    status: str = Form("Active"),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    new_promo = Promotion(
        title=title,
        description=description,
        discount_percent=discount_percent,
        start_date=start_date,
        end_date=end_date,
        status=status
    )
    db.add(new_promo)
    db.commit()
    
    return RedirectResponse("/manager/promotions?success=1", status_code=302)

@router.post("/manager/promotions/update")
async def update_promotion(
    request: Request,
    promotion_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    discount_percent: float = Form(0.0),
    start_date: str = Form(None),
    end_date: str = Form(None),
    status: str = Form("Active"),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["manager"])
    if not user:
        return RedirectResponse("/login")
        
    db_promo = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if db_promo:
        db_promo.title = title
        db_promo.description = description
        db_promo.discount_percent = discount_percent
        db_promo.start_date = start_date
        db_promo.end_date = end_date
        db_promo.status = status
        
        db.commit()
        
    return RedirectResponse("/manager/promotions?success=1", status_code=302)
@router.get("/manager/technician/{tech_id}/{mode}", response_class=HTMLResponse)
async def manager_technician_view_edit(request: Request, tech_id: int, mode: str, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager", "admin"])
    if not user:
        return RedirectResponse("/login")
        
    tech = db.query(User).filter(User.id == tech_id).first()
    if not tech:
        return RedirectResponse("/our-team")

    is_view_mode = (mode == "view")

    # Số liệu thật: việc hoàn thành, điểm TB, việc đang mở
    done_orders = db.query(RepairOrder).filter(
        RepairOrder.technician_id == tech.id, RepairOrder.status == "Completed"
    ).order_by(RepairOrder.completed_at.desc()).all()
    rated = [o.service_rating for o in done_orders if o.service_rating]
    avg = round(sum(rated) / len(rated), 1) if rated else None
    open_orders = db.query(RepairOrder).filter(
        RepairOrder.technician_id == tech.id,
        RepairOrder.status.in_(["Pending", "In Progress"])
    ).order_by(RepairOrder.created_at.desc()).all()
    dist = {s: 0 for s in (5, 4, 3, 2, 1)}
    for r in rated:
        dist[int(r)] = dist.get(int(r), 0) + 1
    reviews = [o for o in done_orders if o.service_rating][:3]
    stats = {"done": len(done_orders), "avg": avg, "nrate": len(rated),
             "open": len(open_orders), "dist": dist}

    return templates.TemplateResponse(request=request, name="manager_edit_tech.html", context={
        "user": user,
        "db_user": tech,
        "is_view_mode": is_view_mode,
        "stats": stats,
        "open_orders": open_orders,
        "reviews": reviews
    })

@router.post("/manager/technician/{tech_id}/update")
async def manager_technician_update(
    request: Request, 
    tech_id: int,
    db: Session = Depends(get_db),
    full_name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    # EmployeeProfile fields
    dob_year: str = Form(""),
    gender: str = Form(""),
    avatar_url: str = Form(""),
    work_area: str = Form(""),
    job_title: str = Form(""),
    garage_name: str = Form(""),
    years_of_experience: str = Form(""),
    hire_date: str = Form(""),
    past_roles: str = Form(""),
    technical_skills: List[str] = Form([]),
    education_school: str = Form(""),
    education_degree: str = Form(""),
    trade_certificates: List[str] = Form([]),
    brand_certificates: str = Form(""),
    safety_certificates: str = Form(""),
    past_garages: str = Form(""),
    vehicle_types: List[str] = Form([]),
    key_projects: str = Form(""),
    zalo_link: str = Form(""),
    facebook_link: str = Form(""),
    linkedin_link: str = Form(""),
    garage_address: str = Form(""),
    customer_rating_score: str = Form(""),
    feedback_summary: str = Form(""),
    social_profiles: str = Form(""),
    tutorial_videos: str = Form(""),
    tech_posts: str = Form(""),
    community_participation: str = Form(""),
    address: str = Form(""),
):
    user = check_auth(request, db, ["manager", "admin"])
    if not user:
        return RedirectResponse("/login")
        
    tech = db.query(User).filter(User.id == tech_id).first()
    if not tech:
        return RedirectResponse("/our-team")
        
    # Update base info
    tech.full_name = full_name
    tech.phone = phone
    tech.email = email
    tech.address = address or None
    
    if password:
        from app.routers.auth import get_password_hash
        tech.password_hash = get_password_hash(password)
        
    # Update profile
    from app.models.models import EmployeeProfile
    profile = db.query(EmployeeProfile).filter(EmployeeProfile.user_id == tech.id).first()
    if not profile:
        profile = EmployeeProfile(user_id=tech.id)
        db.add(profile)
        
    profile.dob_year = int(dob_year) if dob_year.isdigit() else None
    profile.gender = gender
    profile.avatar_url = avatar_url
    profile.work_area = work_area
    profile.job_title = job_title
    profile.garage_name = garage_name
    profile.years_of_experience = int(years_of_experience) if years_of_experience.isdigit() else None
    profile.hire_date = hire_date
    profile.past_roles = past_roles
    profile.technical_skills = ", ".join([s for s in technical_skills if s]) or None
    profile.education_school = education_school
    profile.education_degree = education_degree
    profile.trade_certificates = ", ".join([s for s in trade_certificates if s]) or None
    profile.brand_certificates = brand_certificates
    profile.safety_certificates = safety_certificates
    profile.past_garages = past_garages
    profile.vehicle_types = ", ".join([s for s in vehicle_types if s]) or None
    profile.key_projects = key_projects
    profile.zalo_link = zalo_link
    profile.facebook_link = facebook_link
    profile.linkedin_link = linkedin_link
    profile.garage_address = garage_address
    try:
        profile.customer_rating_score = float(customer_rating_score) if customer_rating_score.strip() else None
    except ValueError:
        pass
    profile.feedback_summary = feedback_summary or None
    profile.social_profiles = social_profiles or None
    profile.tutorial_videos = tutorial_videos or None
    profile.tech_posts = tech_posts or None
    profile.community_participation = community_participation or None
    
    db.commit()
    
    return RedirectResponse(f"/manager/technician/{tech.id}/edit?success=1", status_code=302)
