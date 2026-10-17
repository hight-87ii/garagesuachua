from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    full_name = Column(String)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    role = Column(String, default="customer") # roles: customer, technician, manager, admin
    address = Column(String, nullable=True)
    birth_date = Column(String, nullable=True) # YYYY-MM-DD
    preferred_contact = Column(String, nullable=True) # phone, zalo, email, facebook
    # Vòng đời nhân sự: khóa khi nghỉ, mở lại khi quay lại làm
    is_active = Column(Integer, default=1) # 1: đang hoạt động, 0: đã khóa
    leave_reason = Column(String, nullable=True) # Nghi viec | Di hoc nang cao | Trai nghiem | Khac
    leave_date = Column(String, nullable=True) # YYYY-MM-DD
    return_date = Column(String, nullable=True) # ngày quay lại (nếu có)

    vehicles = relationship("Vehicle", back_populates="owner")
    appointments = relationship("Appointment", foreign_keys="[Appointment.user_id]", back_populates="user")
    employee_profile = relationship("EmployeeProfile", back_populates="user", uselist=False)

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    license_plate = Column(String, unique=True, index=True)
    make = Column(String)
    model = Column(String)
    
    # Các trường mở rộng thêm
    manufacture_year = Column(Integer, nullable=True)
    version = Column(String, nullable=True)
    color = Column(String, nullable=True)
    fuel_type = Column(String, nullable=True)
    vin = Column(String, nullable=True)
    engine_number = Column(String, nullable=True)
    current_odo = Column(Integer, nullable=True, default=0)
    registration_date = Column(String, nullable=True)
    purchase_date = Column(String, nullable=True)
    usage_type = Column(String, nullable=True)
    warranty_status = Column(String, nullable=True)
    
    user_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="vehicles")
    appointments = relationship("Appointment", back_populates="vehicle")
    repair_orders = relationship("RepairOrder", back_populates="vehicle")

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    appointment_date = Column(String)
    appointment_time = Column(String, nullable=True)  # Khung giờ hẹn: HH:MM
    appointment_type = Column(String, default="Repair") # Repair, CarWash
    symptoms = Column(Text)
    ai_diagnosis = Column(Text, nullable=True)
    status = Column(String, default="Pending") # Pending, Confirmed, Completed, Cancelled
    preferred_technician_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime, nullable=True) # Mốc hủy: lịch hủy tự xóa sau 1 ngày

    user = relationship("User", foreign_keys=[user_id], back_populates="appointments")
    preferred_technician = relationship("User", foreign_keys=[preferred_technician_id])
    vehicle = relationship("Vehicle", back_populates="appointments")

class RepairOrder(Base):
    __tablename__ = "repair_orders"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True) # Lịch hẹn đã tạo ra phiếu này
    order_type = Column(String, default="Repair") # Repair, CarWash
    
    # Thông tin khách báo ban đầu
    symptoms = Column(String)
    ai_diagnosis = Column(String)
    
    # Thông tin Phiếu tiếp nhận
    reception_datetime = Column(String, nullable=True)
    deliverer_name = Column(String, nullable=True)
    exterior_scratches = Column(String, nullable=True)
    fuel_level = Column(String, nullable=True)
    current_odo = Column(Integer, nullable=True)
    personal_belongings = Column(String, nullable=True)
    vehicle_images = Column(Text, nullable=True)
    symptom_severity = Column(String, nullable=True)
    abnormal_sounds = Column(String, nullable=True)
    warning_lights = Column(String, nullable=True)
    key_count = Column(Integer, nullable=True, default=0)
    
    # Kết quả kiểm tra và Báo giá
    inspection_result = Column(String, nullable=True)
    estimated_cost = Column(Integer, nullable=True)
    customer_approval = Column(String, default="Pending") # Pending, Approved, Rejected
    
    # Trạng thái và Đánh giá
    status = Column(String, default="Pending") # Pending (Chờ sửa), In Progress (Đang sửa), Completed (Hoàn thành)
    created_at = Column(DateTime, default=datetime.utcnow)
    repair_started_at = Column(DateTime, nullable=True)
    repair_notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    handover_datetime = Column(String, nullable=True)
    service_rating = Column(Integer, nullable=True) # 1-5 sao

    # Biên bản nghiệm thu sau sửa chữa (KTV nhập ngay khi sửa xong)
    final_odo = Column(Integer, nullable=True)
    completion_notes = Column(Text, nullable=True)
    completion_images = Column(Text, nullable=True) # nhiều ảnh, cách nhau bởi dấu phẩy
    repair_video_path = Column(String, nullable=True) # VD: /static/uploads/repairs/12_xxx.mp4
    repair_video_uploaded_at = Column(DateTime, nullable=True)

    vehicle = relationship("Vehicle", back_populates="repair_orders")
    technician = relationship("User", foreign_keys=[technician_id])
    invoice = relationship("Invoice", back_populates="repair_order", uselist=False)
    used_parts = relationship("RepairOrderPart", back_populates="repair_order")

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    repair_order_id = Column(Integer, ForeignKey("repair_orders.id"), unique=True, index=True)
    total_amount = Column(Float, default=0.0)
    subtotal = Column(Float, default=0.0)
    vat_amount = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    payment_method = Column(String, nullable=True)
    warranty_info = Column(String, nullable=True)
    status = Column(String, default="Unpaid") # Unpaid, Paid
    created_at = Column(DateTime, default=datetime.utcnow)

    repair_order = relationship("RepairOrder", back_populates="invoice")

class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # 1. Cơ bản
    dob_year = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    work_area = Column(String, nullable=True)
    
    # 2. Nghề nghiệp
    job_title = Column(String, nullable=True)
    garage_name = Column(String, nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    hire_date = Column(String, nullable=True)
    past_roles = Column(Text, nullable=True)
    
    # 3. Chuyên môn kỹ thuật
    technical_skills = Column(Text, nullable=True)
    
    # 4. Trình độ và chứng chỉ
    education_school = Column(String, nullable=True)
    education_degree = Column(String, nullable=True)
    trade_certificates = Column(Text, nullable=True)
    brand_certificates = Column(Text, nullable=True)
    safety_certificates = Column(Text, nullable=True)
    
    # 5. Kinh nghiệm làm việc
    past_garages = Column(Text, nullable=True)
    vehicle_types = Column(Text, nullable=True)
    key_projects = Column(Text, nullable=True)
    
    # 6. Thông tin liên hệ
    zalo_link = Column(String, nullable=True)
    facebook_link = Column(String, nullable=True)
    linkedin_link = Column(String, nullable=True)
    garage_address = Column(String, nullable=True)
    
    # 7. Đánh giá và uy tín
    customer_rating_score = Column(Float, nullable=True)
    feedback_summary = Column(Text, nullable=True)
    
    # 8. Hoạt động online
    social_profiles = Column(Text, nullable=True)
    tutorial_videos = Column(Text, nullable=True)
    tech_posts = Column(Text, nullable=True)
    community_participation = Column(Text, nullable=True)

    user = relationship("User", back_populates="employee_profile")

class SparePart(Base):
    __tablename__ = "spare_parts"

    id = Column(Integer, primary_key=True, index=True)
    part_number = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    other_name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    part_type = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    
    # Thông tin kỹ thuật
    oem_code = Column(String, nullable=True)
    manufacturer_code = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    origin = Column(String, nullable=True)
    dimensions = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    weight = Column(String, nullable=True)
    shelf_life = Column(String, nullable=True)
    
    # Tương thích xe
    compatible_make = Column(String, nullable=True)
    compatible_model = Column(String, nullable=True)
    compatible_year = Column(String, nullable=True)
    compatible_version = Column(String, nullable=True)
    compatible_engine = Column(String, nullable=True)
    compatible_fuel = Column(String, nullable=True)
    
    # Kho hàng
    warehouse = Column(String, nullable=True)
    shelf_location = Column(String, nullable=True)
    stock_quantity = Column(Integer, default=0)
    min_stock = Column(Integer, default=0)
    max_stock = Column(Integer, default=0)
    status = Column(String, default="Đang kinh doanh")
    
    # Nhập hàng
    supplier = Column(String, nullable=True)
    supplier_code = Column(String, nullable=True)
    purchase_price = Column(Integer, default=0)
    price = Column(Integer, default=0)
    vat_rate = Column(String, nullable=True)
    first_import_date = Column(String, nullable=True)
    
    # Bảo hành
    has_warranty = Column(String, nullable=True)
    warranty_period = Column(String, nullable=True)
    warranty_conditions = Column(Text, nullable=True)
    warranty_notes = Column(Text, nullable=True)
    
    # Mã vạch
    barcode = Column(String, nullable=True)
    qrcode = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)
    
    # Lịch sử
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    used_in = relationship("RepairOrderPart", back_populates="part")

class RepairOrderPart(Base):
    __tablename__ = "repair_order_parts"

    id = Column(Integer, primary_key=True, index=True)
    repair_order_id = Column(Integer, ForeignKey("repair_orders.id"))
    part_id = Column(Integer, ForeignKey("spare_parts.id"))
    quantity = Column(Integer, default=1)
    unit_price = Column(Integer, default=0) # Lưu giá tại thời điểm thay

    repair_order = relationship("RepairOrder", back_populates="used_parts")
    part = relationship("SparePart", back_populates="used_in")

class ServiceCatalog(Base):
    __tablename__ = "service_catalogs"

    id = Column(Integer, primary_key=True, index=True)
    service_code = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    category = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    status = Column(String, default="Active")
    
    base_price = Column(Integer, default=0)
    promo_price = Column(Integer, nullable=True)
    price_type = Column(String, default="Theo xe")
    vat_rate = Column(String, nullable=True)
    duration_minutes = Column(Integer, default=30)
    
    applicable_vehicle_type = Column(String, nullable=True)
    applicable_vehicle_size = Column(String, nullable=True)
    
    materials_used = Column(Text, nullable=True)
    process_steps = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

class GarageDocument(Base):
    __tablename__ = "garage_documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(Text)
    document_type = Column(String, default="report") # report, manual, guideline, policy
    # Basename file seed (VD 'bao-duong-dinh-ky.txt'); NULL voi doc tao tu form.
    # Dung lam metadata 'source' de citation (quy uoc 4.1.2).
    source = Column(String, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Để biết tài liệu đã được đưa vào VectorDB chưa
    is_ingested = Column(Integer, default=0)

    uploader = relationship("User", foreign_keys=[uploaded_by])

class DailyWeather(Base):
    __tablename__ = "daily_weather"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, index=True) # YYYY-MM-DD
    temperature = Column(Float, nullable=True) # Nhiệt độ (C)
    humidity = Column(Float, nullable=True) # Độ ẩm (%)
    rainfall = Column(Float, nullable=True) # Lượng mưa (mm)
    air_quality_aqi = Column(Integer, nullable=True) # Chỉ số chất lượng không khí
    weather_condition = Column(String, nullable=True) # Nắng, Mưa, Nhiều mây...
    
    # Ghi chú / Lời khuyên do AI tự tổng hợp trong ngày hôm đó
    ai_daily_advice = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    discount_percent = Column(Float, default=0.0)
    start_date = Column(String, nullable=True) # YYYY-MM-DD
    end_date = Column(String, nullable=True) # YYYY-MM-DD
    status = Column(String, default="Active") # Active, Inactive
    created_at = Column(DateTime, default=datetime.utcnow)


# ================= Agent platform (v9): roles, chat, runs, memory, approvals ==
# Quy ước: giữ cột users.role hiện tại để tương thích; user_roles là mở rộng
# nhiều-nhiều. SQLite-create_all có tính cộng dồn nên migrate an toàn.

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True) # customer, technician, manager, admin
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), index=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)


class ExternalIdentity(Base):
    __tablename__ = "external_identities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    provider = Column(String, index=True) # zalo, web, messenger
    external_id = Column(String, index=True)
    display_name = Column(String, nullable=True)
    meta_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    agent_code = Column(String, index=True) # customer, technical, manager, scheduling, inventory, billing, maintenance
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    title = Column(String, nullable=True)
    status = Column(String, default="Open") # Open, Closed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String, default="user") # user, assistant, system, tool
    content = Column(Text)
    tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True) # customer, technical, manager, scheduling, inventory, billing, maintenance
    name = Column(String)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    model = Column(String, default="gemini-2.0-flash")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=600)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    input_text = Column(Text, nullable=True)
    output_text = Column(Text, nullable=True)
    prompt_len = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    ok = Column(Integer, default=1)
    error_class = Column(String, nullable=True) # quota, 503, other
    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    status = Column(String, default="Pending") # Pending, Doing, Done, Cancelled
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    due_at = Column(String, nullable=True) # YYYY-MM-DD
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id = Column(Integer, primary_key=True, index=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=True, index=True)
    tool_name = Column(String, index=True)
    args_json = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    ok = Column(Integer, default=1)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    scope = Column(String, default="user") # user, vehicle, global
    mem_key = Column(String, index=True)
    mem_value = Column(Text)
    is_allowed = Column(Integer, default=1) # 1: được phép lưu, 0: cấm/xóa
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    approval_type = Column(String, index=True) # quote, appointment, part_order, task
    ref_id = Column(Integer, nullable=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approver_role = Column(String, default="manager")
    status = Column(String, default="Pending") # Pending, Approved, Rejected
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, index=True)
    entity = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    ip = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
