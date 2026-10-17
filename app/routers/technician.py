from typing import List
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
import shutil
import time
from datetime import datetime

from app.database import get_db
from app.models.models import User, RepairOrder, Vehicle, Invoice, RepairOrderPart, SparePart
from app.routers.auth import get_current_user_from_cookie

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def check_auth(request: Request, db: Session, allowed_roles: list = ["technician"]):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return None
    if user.get("role") not in allowed_roles and user.get("role") != "admin":
        return None
    return user

@router.get("/tech/dashboard", response_class=HTMLResponse)
async def tech_dashboard(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["technician", "manager"])
    if not user:
        return RedirectResponse("/login")
        
    search_date = request.query_params.get("date", "")

    # Quét hủy lịch quá hẹn 24h không tới (để bảng việc không kẹt phiếu ma)
    from app.services.appointment_sweep import auto_cancel_noshow
    auto_cancel_noshow(db)

    # Lấy danh sách phiếu sửa chữa kèm theo xe
    query = db.query(RepairOrder)
    
    if search_date:
        # Filter by created_at containing the date (e.g. '2026-10-08')
        from sqlalchemy import func
        query = query.filter(func.date(RepairOrder.created_at) == search_date)
        
    orders = query.order_by(RepairOrder.id.desc()).all()
    from app.models.models import SparePart
    parts = db.query(SparePart).all()
    technicians = db.query(User).filter(
        User.role.in_(["technician", "admin"]), User.is_active != 0
    ).order_by(User.full_name).all()
    
    return templates.TemplateResponse(request=request, name="tech_dashboard.html", context={
        "user": user, "orders": orders, "parts": parts, "technicians": technicians, "search_date": search_date
    })

@router.post("/tech/reception")
async def tech_reception(
    request: Request,
    order_id: int = Form(...),
    reception_datetime: str = Form(...),
    deliverer_name: str = Form(...),
    fuel_level: str = Form(""),
    current_odo: str = Form(""),
    symptom_severity: str = Form(""),
    abnormal_sounds: str = Form(""),
    key_count: int = Form(0),
    customer_phone: str = Form(""),
    customer_email: str = Form(""),
    customer_address: str = Form(""),
    exterior_scratches: List[str] = Form([]),
    warning_lights: List[str] = Form([]),
    personal_belongings: List[str] = Form([]),
    vehicle_images: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    exterior_scratches_list = exterior_scratches
    warning_lights_list = warning_lights
    personal_belongings_list = personal_belongings
    
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if order:
        order.reception_datetime = reception_datetime
        order.deliverer_name = deliverer_name
        order.fuel_level = fuel_level
        order.symptom_severity = symptom_severity
        order.abnormal_sounds = abnormal_sounds
        order.key_count = key_count
        
        order.exterior_scratches = ", ".join(exterior_scratches_list) if exterior_scratches_list else ""
        order.warning_lights = ", ".join(warning_lights_list) if warning_lights_list else ""
        order.personal_belongings = ", ".join(personal_belongings_list) if personal_belongings_list else ""

        # Thông tin khách hàng phải luôn đầy đủ sau tiếp nhận
        owner = order.vehicle.owner if order.vehicle else None
        if owner:
            phone = (customer_phone or "").strip()
            if phone:
                owner.phone = phone
            email = (customer_email or "").strip()
            if email:
                owner.email = email
            address = (customer_address or "").strip()
            if address:
                owner.address = address
        
        if current_odo and current_odo.isdigit():
            odo_val = int(current_odo)
            order.current_odo = odo_val
            if order.vehicle and odo_val > (order.vehicle.current_odo or 0):
                order.vehicle.current_odo = odo_val
                
        if vehicle_images and vehicle_images.filename:
            upload_dir = "app/static/uploads/vehicles"
            os.makedirs(upload_dir, exist_ok=True)
            _, ext = os.path.splitext(vehicle_images.filename)
            ext = ext.lower()[:5]
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            safe_name = f"{order.id}_{int(time.time())}{ext}"
            filepath = os.path.join(upload_dir, safe_name)
            written = 0
            with open(filepath, "wb") as f:
                while True:
                    chunk = (await vehicle_images.read(1024 * 1024)) if hasattr(vehicle_images, "read") else b""
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > 5 * 1024 * 1024:
                        break
                    f.write(chunk)
            if written == 0 or written > 5 * 1024 * 1024:
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            else:
                order.vehicle_images = f"/static/uploads/vehicles/{safe_name}"
                
        db_user = db.query(User).filter(User.username == user["sub"]).first()
        if user["role"] == "technician":
            order.technician_id = db_user.id
            
        db.commit()
    return RedirectResponse("/tech/dashboard", status_code=303)

@router.get("/tech/print-reception/{order_id}", response_class=HTMLResponse)
async def print_reception_ticket(
    request: Request,
    order_id: int,
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order:
        return RedirectResponse("/tech/dashboard")
        
    return templates.TemplateResponse(request=request, name="reception_ticket.html", context={
        "user": user, "order": order
    })

@router.post("/tech/quote")
async def repair_quote(
    request: Request,
    order_id: int = Form(...),
    inspection_result: str = Form(...),
    estimated_cost: int = Form(...),
    technician_id: str = Form(""),
    repair_started_at: str = Form(""),
    repair_notes: str = Form(""),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if order:
        order.inspection_result = inspection_result
        order.estimated_cost = estimated_cost
        # Báo giá KHÔNG tự duyệt: giữ Pending để khách xem chi tiết và đồng ý/từ chối
        # (kể cả khi khách không có mặt tại xưởng). Chỉ khi khách duyệt mới được vào sửa.
        order.customer_approval = "Pending"
        if order.status != "Pending":
            order.status = "Pending"

        db_user = db.query(User).filter(User.username == user["sub"]).first()
        if user["role"] == "technician" and db_user:
            order.technician_id = db_user.id
        elif user["role"] in ["manager", "admin"] and technician_id.isdigit():
            selected_technician = db.query(User).filter(
                User.id == int(technician_id),
                User.role.in_(["technician", "admin"])
            ).first()
            if selected_technician:
                order.technician_id = selected_technician.id

        if repair_started_at:
            try:
                order.repair_started_at = datetime.fromisoformat(repair_started_at)
            except ValueError:
                order.repair_started_at = datetime.now()
        else:
            order.repair_started_at = datetime.now()
        order.repair_notes = repair_notes.strip() or None
        db.commit()
    return RedirectResponse("/tech/dashboard", status_code=303)

@router.post("/tech/update-status")
async def update_status(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")

    form = await request.form()
    try:
        order_id = int(form.get("order_id"))
    except (TypeError, ValueError):
        return RedirectResponse("/tech/dashboard")
    status = (form.get("status") or "").strip()
    handover_datetime = form.get("handover_datetime") or None

    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if order and status:
        # Chốt cửa: chưa được khách duyệt thì không cho vào sửa (kể cả thợ/quản lý bấm tay)
        if status == "In Progress" and order.customer_approval != "Approved":
            return RedirectResponse("/tech/dashboard", status_code=303)

        order.status = status
        db_user = db.query(User).filter(User.username == user["sub"]).first()
        if user["role"] == "technician":
            order.technician_id = db_user.id

        if status == "In Progress":
            technician_id_raw = (form.get("technician_id") or "").strip()
            if user["role"] in ["manager", "admin"] and technician_id_raw.isdigit():
                selected_technician = db.query(User).filter(
                    User.id == int(technician_id_raw),
                    User.role.in_(["technician", "admin"])
                ).first()
                if selected_technician:
                    order.technician_id = selected_technician.id

            started_at_raw = (form.get("repair_started_at") or "").strip()
            if started_at_raw:
                try:
                    order.repair_started_at = datetime.fromisoformat(started_at_raw)
                except ValueError:
                    order.repair_started_at = order.repair_started_at or datetime.now()
            elif not order.repair_started_at:
                order.repair_started_at = datetime.now()

            repair_notes = (form.get("repair_notes") or "").strip()
            if repair_notes:
                order.repair_notes = repair_notes

        if status == "Completed":
            order.completed_at = datetime.utcnow()
            order.handover_datetime = handover_datetime

            # --- Biên bản nghiệm thu ngay sau khi sửa xong ---
            final_odo_raw = (form.get("final_odo") or "").strip()
            if final_odo_raw.isdigit():
                final_odo = int(final_odo_raw)
                base_odo = order.current_odo or (order.vehicle.current_odo if order.vehicle else 0) or 0
                if final_odo >= base_odo:
                    order.final_odo = final_odo
                    if order.vehicle and final_odo > (order.vehicle.current_odo or 0):
                        order.vehicle.current_odo = final_odo
            completion_notes = (form.get("completion_notes") or "").strip()
            if completion_notes:
                order.completion_notes = completion_notes

            # Ảnh nghiệm thu (nhiều ảnh, giới hạn dung lượng để chống đầy ổ đĩa)
            upload_dir = "app/static/uploads/repairs"
            os.makedirs(upload_dir, exist_ok=True)
            MAX_IMAGE_BYTES = 5 * 1024 * 1024
            MAX_IMAGES_PER_ORDER = 5
            MAX_VIDEO_BYTES = 100 * 1024 * 1024

            def _save_limited(upload, dest: str, max_bytes: int) -> bool:
                written = 0
                with open(dest, "wb") as buffer:
                    while True:
                        chunk = upload.file.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes:
                            break
                        buffer.write(chunk)
                if written > max_bytes or written == 0:
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    return False
                return True

            saved_images = []
            images = form.getlist("completion_images") if hasattr(form, "getlist") else []
            existing_count = len([s for s in (order.completion_images or "").split(",") if s.strip()])
            for img in images:
                if existing_count + len(saved_images) >= MAX_IMAGES_PER_ORDER:
                    break
                filename = getattr(img, "filename", None)
                if filename:
                    ext = os.path.splitext(filename)[1].lower()[:5] or ".jpg"
                    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                        continue
                    safe_name = f"{order.id}_{int(time.time())}_{len(saved_images)}{ext}"
                    dest = os.path.join(upload_dir, safe_name)
                    if _save_limited(img, dest, MAX_IMAGE_BYTES):
                        saved_images.append(f"/static/uploads/repairs/{safe_name}")
            if saved_images:
                existing = [s for s in (order.completion_images or "").split(",") if s.strip()]
                order.completion_images = ",".join(existing + saved_images)

            # Video camera quay xe đang sửa / nghiệm thu (tối đa 100MB)
            video = form.get("repair_video")
            video_filename = getattr(video, "filename", None) if video else None
            if video_filename:
                ext = os.path.splitext(video_filename)[1].lower()[:5] or ".mp4"
                if ext in (".mp4", ".mov", ".webm"):
                    safe_name = f"{order.id}_{int(time.time())}_repair{ext}"
                    dest = os.path.join(upload_dir, safe_name)
                    if _save_limited(video, dest, MAX_VIDEO_BYTES):
                        order.repair_video_path = f"/static/uploads/repairs/{safe_name}"
                        order.repair_video_uploaded_at = datetime.utcnow()

        db.commit()

    return RedirectResponse("/tech/dashboard", status_code=302)

@router.post("/tech/update-repair-details")
async def update_repair_details(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["technician", "manager"])
    if not user:
        return RedirectResponse("/login")

    form = await request.form()
    try:
        order_id = int(form.get("order_id"))
    except (TypeError, ValueError):
        return RedirectResponse("/tech/dashboard", status_code=303)

    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if order and order.status in ("Pending", "In Progress"):
        if user["role"] in ["manager", "admin"]:
            technician_id_raw = (form.get("technician_id") or "").strip()
            if technician_id_raw.isdigit():
                selected_technician = db.query(User).filter(
                    User.id == int(technician_id_raw),
                    User.role.in_(["technician", "admin"])
                ).first()
                if selected_technician:
                    order.technician_id = selected_technician.id

        started_at_raw = (form.get("repair_started_at") or "").strip()
        if started_at_raw:
            try:
                order.repair_started_at = datetime.fromisoformat(started_at_raw)
            except ValueError:
                pass
        order.repair_notes = (form.get("repair_notes") or "").strip() or None
        # Phát sinh lúc đang sửa: được sửa kết quả kiểm tra + tiền công
        inspection_raw = (form.get("inspection_result") or "").strip()
        if inspection_raw:
            order.inspection_result = inspection_raw
        cost_raw = (form.get("estimated_cost") or "").strip()
        if cost_raw:
            try:
                new_cost = int(float(cost_raw))
                if new_cost >= 0:
                    order.estimated_cost = new_cost
            except ValueError:
                pass
        db.commit()

    return RedirectResponse("/tech/dashboard", status_code=303)

@router.post("/tech/order/remove-part")
async def remove_part_from_order(
    request: Request,
    db: Session = Depends(get_db)
):
    """Gỡ 1 dòng linh kiện khỏi phiếu đang sửa (chưa xuất hóa đơn): hoàn lại tồn kho."""
    user = check_auth(request, db, ["technician", "manager"])
    if not user:
        return RedirectResponse("/login")
    form = await request.form()
    try:
        rop_id = int(form.get("rop_id"))
    except (TypeError, ValueError):
        return RedirectResponse("/tech/dashboard", status_code=303)
    rop = db.query(RepairOrderPart).filter(RepairOrderPart.id == rop_id).first()
    if rop:
        order = db.query(RepairOrder).filter(RepairOrder.id == rop.repair_order_id).first()
        if order and order.status in ("Pending", "In Progress") and not order.invoice:
            part = db.query(SparePart).filter(SparePart.id == rop.part_id).first()
            if part:
                part.stock_quantity = (part.stock_quantity or 0) + (rop.quantity or 0)
            db.delete(rop)
            db.commit()
    return RedirectResponse("/tech/dashboard", status_code=303)

@router.post("/tech/create-direct-order")
async def create_direct_order(
    request: Request,
    customer_phone: str = Form(...),
    license_plate: str = Form(...),
    symptoms: str = Form(...),
    customer_name: str = Form(None),
    make: str = Form(None),
    model: str = Form(None),
    db: Session = Depends(get_db)
):
    tech_user = check_auth(request, db, ["technician", "manager"])
    if not tech_user: return RedirectResponse("/login")
    
    # 1. Tìm hoặc tạo User khách hàng bằng SĐT
    from app.routers.auth import get_password_hash
    customer = db.query(User).filter(User.username == customer_phone).first()
    if not customer:
        customer = db.query(User).filter(User.phone == customer_phone).first()
        
    if not customer:
        customer = User(
            username=customer_phone,
            password_hash=get_password_hash("123456"),
            full_name=customer_name or "Khách hàng",
            phone=customer_phone,
            role="customer"
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        
    # 2. Tìm hoặc tạo Xe
    vehicle = db.query(Vehicle).filter(Vehicle.license_plate == license_plate).first()
    if not vehicle:
        vehicle = Vehicle(
            license_plate=license_plate,
            make=make or "Chưa rõ",
            model=model or "Chưa rõ",
            user_id=customer.id
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        
    # 3. Phân tích AI
    from app.services.ai_service import analyze_vehicle_symptoms
    ai_result = analyze_vehicle_symptoms(symptoms)
    
    # 4. Tạo Phiếu sửa chữa (RepairOrder)
    new_ro = RepairOrder(
        vehicle_id=vehicle.id,
        symptoms=symptoms,
        ai_diagnosis=ai_result,
        status="Pending"
    )
    db.add(new_ro)
    db.commit()
    
    return RedirectResponse("/tech/dashboard", status_code=302)

# --- QUẢN LÝ PHỤ TÙNG & HÓA ĐƠN ---

from app.models.models import SparePart, RepairOrderPart, Invoice

@router.get("/tech/parts", response_class=HTMLResponse)
async def tech_parts(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    parts = db.query(SparePart).order_by(SparePart.name).all()
    return templates.TemplateResponse(request=request, name="tech_parts.html", context={"user": user, "parts": parts})

@router.post("/tech/parts/add")
async def add_part(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user: return RedirectResponse("/login")
    
    form_data = await request.form()
    
    image = form_data.get("image")
    image_url = None
    part_number = form_data.get("part_number", "")
    
    if image and hasattr(image, "filename") and image.filename:
        os.makedirs("app/static/uploads/parts", exist_ok=True)
        ext = image.filename.split(".")[-1]
        filename = f"{int(time.time())}_{part_number}.{ext}"
        filepath = f"app/static/uploads/parts/{filename}"
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/static/uploads/parts/{filename}"
    
    new_part = SparePart(
        part_number=part_number,
        name=form_data.get("name"),
        other_name=form_data.get("other_name"),
        category=form_data.get("category"),
        part_type=form_data.get("part_type"),
        image_url=image_url,
        description=form_data.get("description"),
        # Kỹ thuật
        oem_code=form_data.get("oem_code"),
        manufacturer_code=form_data.get("manufacturer_code"),
        brand=form_data.get("brand"),
        origin=form_data.get("origin"),
        dimensions=form_data.get("dimensions"),
        unit=form_data.get("unit"),
        weight=form_data.get("weight"),
        shelf_life=form_data.get("shelf_life"),
        # Tương thích
        compatible_make=form_data.get("compatible_make"),
        compatible_model=form_data.get("compatible_model"),
        compatible_year=form_data.get("compatible_year"),
        compatible_version=form_data.get("compatible_version"),
        compatible_engine=form_data.get("compatible_engine"),
        compatible_fuel=form_data.get("compatible_fuel"),
        # Kho
        warehouse=form_data.get("warehouse"),
        shelf_location=form_data.get("shelf_location"),
        stock_quantity=int(form_data.get("stock_quantity") or 0),
        min_stock=int(form_data.get("min_stock") or 0),
        max_stock=int(form_data.get("max_stock") or 0),
        status=form_data.get("status") or "Đang kinh doanh",
        # Giá nhập
        supplier=form_data.get("supplier"),
        supplier_code=form_data.get("supplier_code"),
        purchase_price=int(form_data.get("purchase_price") or 0),
        price=int(form_data.get("price") or 0),
        vat_rate=form_data.get("vat_rate"),
        first_import_date=form_data.get("first_import_date"),
        # Bảo hành
        has_warranty=form_data.get("has_warranty"),
        warranty_period=form_data.get("warranty_period"),
        warranty_conditions=form_data.get("warranty_conditions"),
        warranty_notes=form_data.get("warranty_notes"),
        # Mã vạch
        barcode=form_data.get("barcode"),
        qrcode=form_data.get("qrcode"),
        serial_number=form_data.get("serial_number"),
        # Lịch sử
        created_by=user.get("full_name") or user.get("sub"),
        created_at=datetime.utcnow()
    )
    db.add(new_part)
    db.commit()
    return RedirectResponse("/tech/parts", status_code=302)

@router.post("/tech/parts/update")
async def update_part(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user: return RedirectResponse("/login")
    
    form_data = await request.form()
    part_id = int(form_data.get("part_id"))
    
    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if part:
        part.part_number = form_data.get("part_number", part.part_number)
        part.name = form_data.get("name", part.name)
        part.other_name = form_data.get("other_name")
        part.category = form_data.get("category")
        part.part_type = form_data.get("part_type")
        part.description = form_data.get("description")
        
        # Kỹ thuật
        part.oem_code = form_data.get("oem_code")
        part.manufacturer_code = form_data.get("manufacturer_code")
        part.brand = form_data.get("brand")
        part.origin = form_data.get("origin")
        part.dimensions = form_data.get("dimensions")
        part.unit = form_data.get("unit")
        part.weight = form_data.get("weight")
        part.shelf_life = form_data.get("shelf_life")
        
        # Tương thích
        part.compatible_make = form_data.get("compatible_make")
        part.compatible_model = form_data.get("compatible_model")
        part.compatible_year = form_data.get("compatible_year")
        part.compatible_version = form_data.get("compatible_version")
        part.compatible_engine = form_data.get("compatible_engine")
        part.compatible_fuel = form_data.get("compatible_fuel")
        
        # Kho
        part.warehouse = form_data.get("warehouse")
        part.shelf_location = form_data.get("shelf_location")
        part.stock_quantity = int(form_data.get("stock_quantity") or 0)
        part.min_stock = int(form_data.get("min_stock") or 0)
        part.max_stock = int(form_data.get("max_stock") or 0)
        part.status = form_data.get("status") or "Đang kinh doanh"
        
        # Nhập hàng
        part.supplier = form_data.get("supplier")
        part.supplier_code = form_data.get("supplier_code")
        part.purchase_price = int(form_data.get("purchase_price") or 0)
        part.price = int(form_data.get("price") or 0)
        part.vat_rate = form_data.get("vat_rate")
        part.first_import_date = form_data.get("first_import_date")
        
        # Bảo hành
        part.has_warranty = form_data.get("has_warranty")
        part.warranty_period = form_data.get("warranty_period")
        part.warranty_conditions = form_data.get("warranty_conditions")
        part.warranty_notes = form_data.get("warranty_notes")
        
        # Mã vạch
        part.barcode = form_data.get("barcode")
        part.qrcode = form_data.get("qrcode")
        part.serial_number = form_data.get("serial_number")
        
        # Lịch sử
        part.updated_by = user.get("full_name") or user.get("sub")
        part.updated_at = datetime.utcnow()
        
        image = form_data.get("image")
        if image and hasattr(image, "filename") and image.filename:
            os.makedirs("app/static/uploads/parts", exist_ok=True)
            ext = image.filename.split(".")[-1]
            filename = f"{int(time.time())}_{part.part_number}.{ext}"
            filepath = f"app/static/uploads/parts/{filename}"
            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            part.image_url = f"/static/uploads/parts/{filename}"
            
        db.commit()
    
    return RedirectResponse("/tech/parts", status_code=302)

@router.post("/tech/order/add-part")
async def add_part_to_order(
    request: Request,
    order_id: int = Form(...),
    part_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if quantity <= 0:
        return RedirectResponse("/tech/dashboard", status_code=302)
    # Chỉ thêm linh kiện khi phiếu còn mở (chờ duyệt/đang sửa) và chưa xuất hóa đơn
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if not order or order.status not in ("Pending", "In Progress") or order.invoice:
        return RedirectResponse("/tech/dashboard", status_code=302)
    if part and part.stock_quantity >= quantity:
        # Trừ tồn kho
        part.stock_quantity -= quantity
        # Thêm vào order
        rop = RepairOrderPart(
            repair_order_id=order_id,
            part_id=part_id,
            quantity=quantity,
            unit_price=part.price
        )
        db.add(rop)
        db.commit()
        
    return RedirectResponse("/tech/dashboard", status_code=302)

@router.post("/tech/order/generate-invoice")
async def generate_invoice(
    request: Request,
    order_id: int = Form(...),
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
    if order and order.status == 'Completed':
        # Kiểm tra xem đã có hóa đơn chưa (kèm unique DB chống race 2 request)
        if not order.invoice:
            # Tính tổng tiền = Tiền công (estimated_cost) + Tiền phụ tùng
            total_parts = sum([p.quantity * p.unit_price for p in order.used_parts])
            labor_cost = order.estimated_cost or 0
            subtotal = labor_cost + total_parts
            vat_amount = subtotal * 0.1  # Thuế VAT mặc định 10%
            discount = 0.0
            total_amount = subtotal + vat_amount - discount

            warranty_info = "Bảo hành dịch vụ 1 tháng, phụ tùng thay thế bảo hành theo hãng sản xuất."

            new_invoice = Invoice(
                repair_order_id=order.id,
                subtotal=subtotal,
                vat_amount=vat_amount,
                discount=discount,
                total_amount=total_amount,
                warranty_info=warranty_info,
                status="Unpaid"
            )
            db.add(new_invoice)
            try:
                db.commit()
            except Exception:
                db.rollback()
            
    return RedirectResponse("/tech/dashboard", status_code=302)

@router.get("/tech/invoice/{invoice_id}/print", response_class=HTMLResponse)
async def print_invoice(
    request: Request,
    invoice_id: int,
    db: Session = Depends(get_db)
):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return RedirectResponse("/tech/dashboard", status_code=302)
        
    return templates.TemplateResponse(request, "invoice_print.html", {
        "invoice": invoice,
        "user": user,
    })

# --- QUẢN LÝ DỊCH VỤ RỬA XE / CHĂM SÓC XE ---
from app.models.models import ServiceCatalog

@router.get("/tech/services", response_class=HTMLResponse)
async def tech_services(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["technician", "manager"])
    if not user: return RedirectResponse("/login")
    
    services = db.query(ServiceCatalog).order_by(ServiceCatalog.service_code).all()
    return templates.TemplateResponse(request=request, name="tech_services.html", context={"user": user, "services": services})

@router.post("/tech/services/add")
async def add_service(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user: return RedirectResponse("/login")
    
    form_data = await request.form()
    
    image = form_data.get("image")
    image_url = None
    service_code = form_data.get("service_code", "")
    
    if image and hasattr(image, "filename") and image.filename:
        os.makedirs("app/static/uploads/services", exist_ok=True)
        ext = image.filename.split(".")[-1]
        filename = f"{int(time.time())}_{service_code}.{ext}"
        filepath = f"app/static/uploads/services/{filename}"
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_url = f"/static/uploads/services/{filename}"
        
    new_service = ServiceCatalog(
        service_code=service_code,
        name=form_data.get("name"),
        category=form_data.get("category"),
        description=form_data.get("description"),
        image_url=image_url,
        status=form_data.get("status") or "Active",
        base_price=int(form_data.get("base_price") or 0),
        promo_price=int(form_data.get("promo_price")) if form_data.get("promo_price") else None,
        price_type=form_data.get("price_type") or "Theo xe",
        vat_rate=form_data.get("vat_rate"),
        duration_minutes=int(form_data.get("duration_minutes") or 30),
        applicable_vehicle_type=form_data.get("applicable_vehicle_type"),
        applicable_vehicle_size=form_data.get("applicable_vehicle_size"),
        materials_used=form_data.get("materials_used"),
        process_steps=form_data.get("process_steps")
    )
    
    db.add(new_service)
    db.commit()
    
    return RedirectResponse("/tech/services", status_code=302)

@router.post("/tech/services/update")
async def update_service(request: Request, db: Session = Depends(get_db)):
    user = check_auth(request, db, ["manager"])
    if not user: return RedirectResponse("/login")
    
    form_data = await request.form()
    service_id = int(form_data.get("service_id"))
    
    service = db.query(ServiceCatalog).filter(ServiceCatalog.id == service_id).first()
    if service:
        service.service_code = form_data.get("service_code", service.service_code)
        service.name = form_data.get("name", service.name)
        service.category = form_data.get("category")
        service.description = form_data.get("description")
        service.status = form_data.get("status") or "Active"
        service.base_price = int(form_data.get("base_price") or 0)
        service.promo_price = int(form_data.get("promo_price")) if form_data.get("promo_price") else None
        service.price_type = form_data.get("price_type") or "Theo xe"
        service.vat_rate = form_data.get("vat_rate")
        service.duration_minutes = int(form_data.get("duration_minutes") or 30)
        service.applicable_vehicle_type = form_data.get("applicable_vehicle_type")
        service.applicable_vehicle_size = form_data.get("applicable_vehicle_size")
        service.materials_used = form_data.get("materials_used")
        service.process_steps = form_data.get("process_steps")
        
        image = form_data.get("image")
        if image and hasattr(image, "filename") and image.filename:
            os.makedirs("app/static/uploads/services", exist_ok=True)
            ext = image.filename.split(".")[-1]
            filename = f"{int(time.time())}_{service.service_code}.{ext}"
            filepath = f"app/static/uploads/services/{filename}"
            with open(filepath, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            service.image_url = f"/static/uploads/services/{filename}"
            
        db.commit()
        
    return RedirectResponse("/tech/services", status_code=302)
