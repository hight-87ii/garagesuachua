from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.database import engine
from app.models import models
from app.routers import auth
from app.routers.auth import get_current_user_from_cookie
from app.models.models import User, RepairOrder, Invoice, Vehicle, Appointment, SparePart
from app.database import get_db
from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime
from fastapi.responses import StreamingResponse
from app.services.gemini_service import get_gemini_response
from app.agents.base import (
    build_role_context, build_vehicle_context, detect_vehicle, call_gemini_safe,
)
from app.agents import tools as agent_tools
from app.routers import auth, customer, technician, manager, profile
from typing import Optional
# Create database tables
models.Base.metadata.create_all(bind=engine)
try:
    # DB cu thieu cot garage_documents.source (quy uoc 4.1.2) -> migrate nhe.
    from ingest_knowledge import ensure_source_column
    ensure_source_column(engine)
except Exception as e:
    print(f"Schema check: {e}")

app = FastAPI(title="Hệ thống Quản lý Garage Ô tô tích hợp AI")

from app.core.csrf import csrf_protect

@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    return await csrf_protect(request, call_next)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
# Thêm auth router
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(technician.router)
app.include_router(manager.router)
app.include_router(profile.router)

# Thêm Agent Routers
from app.agents.technical_agent.router import router as technical_agent_router
from app.agents.customer_agent.router import router as customer_agent_router
from app.agents.manager_agent.router import router as manager_agent_router
from app.agents.scheduling_agent.router import router as scheduling_agent_router
from app.agents.inventory_agent.router import router as inventory_agent_router
from app.agents.billing_agent.router import router as billing_agent_router
from app.agents.maintenance_agent.router import router as maintenance_agent_router

app.include_router(technical_agent_router)
app.include_router(customer_agent_router)
app.include_router(manager_agent_router)
app.include_router(scheduling_agent_router)
app.include_router(inventory_agent_router)
app.include_router(billing_agent_router)
app.include_router(maintenance_agent_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Hệ thống đang hoạt động bình thường"}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    
    metrics = {
        "active_cars": 0,
        "today_jobs": 0,
        "completed_cars": 0,
        "revenue": 0
    }
    
    if user:
        today_date = datetime.utcnow().date()
        
        # Lấy thông tin user một lần
        db_user = db.query(User).filter(User.username == user.get("sub")).first()
        
        # Base queries
        ro_query = db.query(RepairOrder)
        inv_query = db.query(Invoice).join(RepairOrder)
        
        # Biến dữ liệu cá nhân của khách hàng
        customer_vehicles = []
        customer_v_ids = []
        
        if user.get("role") == "technician":
            # Kỹ thuật viên chỉ xem của cá nhân
            if db_user:
                ro_query = ro_query.filter(RepairOrder.technician_id == db_user.id)
                inv_query = inv_query.filter(RepairOrder.technician_id == db_user.id)
                metrics["role_label"] = "Cá nhân"
        elif user.get("role") == "customer":
            # Khách hàng chỉ thấy dữ liệu của các xe mình sở hữu
            if db_user:
                customer_vehicles = db.query(Vehicle).filter(Vehicle.user_id == db_user.id).all()
                customer_v_ids = [v.id for v in customer_vehicles]
                ro_query = ro_query.filter(RepairOrder.vehicle_id.in_(customer_v_ids))
                inv_query = inv_query.filter(RepairOrder.vehicle_id.in_(customer_v_ids))
            metrics["role_label"] = "Xe của bạn"
        else:
            metrics["role_label"] = "Garage"
            
        # 1. Xe đang sửa (In Progress)
        metrics["active_cars"] = ro_query.filter(RepairOrder.status == "In Progress").count()
        
        # 2. Công việc hôm nay (Đang chờ + Đang sửa)
        metrics["today_jobs"] = ro_query.filter(RepairOrder.status.in_(["Pending", "In Progress"])).count()
        
        # 3. Xe hoàn thành (tổng)
        metrics["completed_cars"] = ro_query.filter(RepairOrder.status == "Completed").count()
        
        # 4. Doanh thu (Đã xuất HĐ, trạng thái Unpaid hay Paid đều tính là doanh thu tạm tính)
        total_rev = inv_query.with_entities(func.sum(Invoice.total_amount)).scalar()
        metrics["revenue"] = total_rev or 0
        
        # 5. Lịch sử sửa chữa gần đây
        recent_orders = []
        tech_appointments = []
        # --- Dữ liệu dashboard khách hàng ---
        customer_next_appt = None
        customer_unpaid_invoices = []
        customer_unpaid_total = 0
        customer_active_order = None
        if db_user:
            if user.get("role") == "customer":
                vehicles = customer_vehicles
                if customer_v_ids:
                    recent_orders = db.query(RepairOrder).filter(RepairOrder.vehicle_id.in_(customer_v_ids)).order_by(RepairOrder.created_at.desc()).limit(5).all()
                    
                    # Lịch hẹn sắp tới (từ hôm nay trở đi, còn hiệu lực)
                    today_str = datetime.utcnow().strftime("%Y-%m-%d")
                    customer_next_appt = db.query(Appointment).filter(
                        Appointment.user_id == db_user.id,
                        Appointment.status.in_(["Pending", "Confirmed"]),
                        Appointment.appointment_date >= today_str
                    ).order_by(Appointment.appointment_date.asc()).first()
                    
                    # Hóa đơn chưa thanh toán
                    customer_unpaid_invoices = inv_query.filter(Invoice.status == "Unpaid").all()
                    customer_unpaid_total = sum(i.total_amount or 0 for i in customer_unpaid_invoices)
                    
                    # Xe đang sửa chữa
                    customer_active_order = ro_query.filter(RepairOrder.status.in_(["In Progress", "Pending"])).order_by(RepairOrder.created_at.desc()).first()
            elif user.get("role") == "technician":
                recent_orders = db.query(RepairOrder).filter(RepairOrder.technician_id == db_user.id).order_by(RepairOrder.created_at.desc()).limit(5).all()
                # Fetch pending or confirmed appointments for this tech
                tech_appointments = db.query(Appointment).filter(
                    Appointment.preferred_technician_id == db_user.id,
                    Appointment.status.in_(["Pending", "Confirmed"])
                ).order_by(Appointment.appointment_date).limit(5).all()

                # === Dữ liệu dashboard nhân viên kỹ thuật ===
                _now = datetime.utcnow()
                _ymd = _now.strftime("%Y-%m-%d")
                _month_start = _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                _weekday_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"][_now.weekday()]

                _my = db.query(RepairOrder).filter(RepairOrder.technician_id == db_user.id)
                tech_stats = {
                    "my_open": _my.filter(RepairOrder.status.in_(["Pending", "In Progress"])).count(),
                    "my_repairing": _my.filter(RepairOrder.status == "In Progress").count(),
                    "my_month_done": _my.filter(RepairOrder.status == "Completed", RepairOrder.completed_at >= _month_start).count(),
                    "my_total_done": _my.filter(RepairOrder.status == "Completed").count(),
                    "today_str": _now.strftime("%d/%m/%Y"),
                    "today_ymd": _ymd,
                    "weekday": _weekday_vi,
                    "full_name": db_user.full_name or user.get("sub") or "bạn",
                }
                # Việc chung của xưởng cần xử lý
                pending_receptions = db.query(RepairOrder).filter(
                    RepairOrder.status == "Pending",
                    RepairOrder.reception_datetime.is_(None)
                ).count()
                quotes_waiting = db.query(RepairOrder).filter(
                    RepairOrder.customer_approval == "Pending",
                    RepairOrder.estimated_cost.isnot(None),
                    RepairOrder.status.in_(["Pending", "In Progress"])
                ).count()
                # Lịch hẹn hôm nay của tôi
                tech_today_appts = db.query(Appointment).filter(
                    Appointment.preferred_technician_id == db_user.id,
                    Appointment.appointment_date == _ymd,
                    Appointment.status.in_(["Pending", "Confirmed"])
                ).all()
                # Phụ tùng sắp hết (cùng công thức trang Kho: stock <= min_stock or 5)
                low_stock_parts = [
                    p for p in db.query(SparePart).all()
                    if (p.stock_quantity or 0) <= (p.min_stock or 5)
                ][:5]
            else:
                recent_orders = db.query(RepairOrder).order_by(RepairOrder.created_at.desc()).limit(5).all()
                pending_issues_count = db.query(Appointment).filter(Appointment.status == "Pending").count()

    from app.models.models import Promotion
    promotions = db.query(Promotion).filter(Promotion.status == "Active").all()
    
    # === THÔNG TIN CHO TRANG CHỦ QUẢN LÝ ===
    context = {
        "title": "ThreeH Workshop - Trang chủ", 
        "user": user, 
        "metrics": metrics, 
        "recent_orders": recent_orders if user else [],
        "tech_appointments": tech_appointments if 'tech_appointments' in locals() else [],
        "pending_issues_count": pending_issues_count if 'pending_issues_count' in locals() else 0,
        "promotions": promotions,
        # Dashboard khách hàng
        "vehicles": customer_vehicles if user else [],
        "next_appt": customer_next_appt if 'customer_next_appt' in locals() else None,
        "unpaid_invoices": customer_unpaid_invoices if 'customer_unpaid_invoices' in locals() else [],
        "unpaid_total": customer_unpaid_total if 'customer_unpaid_total' in locals() else 0,
        "active_order": customer_active_order if 'customer_active_order' in locals() else None,
        # Dashboard nhân viên kỹ thuật
        "tech_stats": tech_stats if 'tech_stats' in locals() else None,
        "pending_receptions": pending_receptions if 'pending_receptions' in locals() else 0,
        "quotes_waiting": quotes_waiting if 'quotes_waiting' in locals() else 0,
        "tech_today_appts": tech_today_appts if 'tech_today_appts' in locals() else [],
        "low_stock_parts": low_stock_parts if 'low_stock_parts' in locals() else [],
    }

    if user and user.get("role") in ["manager", "admin"]:
        from datetime import date, timedelta
        from dateutil.relativedelta import relativedelta
        today = date.today()
        today_str = today.strftime("%d/%m/%Y")
        today_ymd = today.strftime("%Y-%m-%d")

        period = request.query_params.get("period", "day")
        months = int(request.query_params.get("months", "3"))
        
        if period == "day":
            start_date = today
            period_label = "1 Ngày (Hôm nay)"
        elif period == "week":
            start_date = today - timedelta(days=7)
            period_label = "1 Tuần nay"
        elif period == "month":
            start_date = today - relativedelta(months=1)
            period_label = "1 Tháng nay"
        elif period == "custom":
            start_date = today - relativedelta(months=months)
            period_label = f"{months} Tháng nay"
        else:
            start_date = today
            period_label = "1 Ngày (Hôm nay)"

        all_orders = db.query(RepairOrder).order_by(RepairOrder.id.desc()).all()
        all_invoices = db.query(Invoice).order_by(Invoice.id.desc()).all()
        all_appointments = db.query(Appointment).order_by(Appointment.appointment_date.asc()).all()

        orders = [o for o in all_orders if o.created_at and o.created_at.date() >= start_date]
        invoices = [i for i in all_invoices if i.created_at and i.created_at.date() >= start_date]
        
        def parse_apt_date(d_str):
            if not d_str: return None
            try: return datetime.strptime(d_str, "%Y-%m-%d").date()
            except: return None

        appointments = [a for a in all_appointments if parse_apt_date(a.appointment_date) and parse_apt_date(a.appointment_date) >= start_date]

        today_appointments = [a for a in all_appointments if a.appointment_date and a.appointment_date.startswith(today_ymd)]
        period_revenue = sum(inv.total_amount for inv in invoices)
        
        kpi = {
            "received": len([o for o in orders if o.status == 'Pending']),
            "in_progress": len([o for o in orders if o.status == 'In Progress']),
            "completed_today": len([o for o in orders if o.status == 'Completed']),
            "appointments_today": len(appointments),
            "revenue_today": period_revenue,
            "pending_issues": len([a for a in appointments if a.status == 'Pending'])
        }
        
        status_counts = {
            "pending": len([o for o in all_orders if o.status == 'Pending']),
            "checking": 0,
            "repairing": len([o for o in all_orders if o.status == 'In Progress']),
            "waiting_parts": 0,
            "completed": len([o for o in all_orders if o.status == 'Completed']),
            "handed_over": len([o for o in all_orders if getattr(o, 'handover_datetime', None)])
        }
        
        techs = db.query(User).filter(User.role == 'technician').limit(3).all()
        tech_perf = []
        for t in techs:
            tech_orders = [o for o in orders if o.technician_id == t.id]
            tech_perf.append({
                "name": t.full_name,
                "in_progress": len([o for o in tech_orders if o.status == 'In Progress']),
                "completed_today": len([o for o in tech_orders if o.status == 'Completed'])
            })
            
        context.update({
            "kpi": kpi,
            "status_counts": status_counts,
            "today_appointments": today_appointments[:5],
            "tech_perf": tech_perf,
            "today_str": today_str,
            "current_period": period,
            "custom_months": months,
            "period_label": period_label
        })

    return templates.TemplateResponse(request=request, name="index.html", context=context)

@app.get("/ai-assistant", response_class=HTMLResponse)
async def read_ai_assistant(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    
    vehicles = []
    if user:
        if user.get("role") in ["technician", "manager", "admin"]:
            # Quản lý/KTV/Admin: được chọn bất kỳ xe khách nào để phân tích
            vehicles = db.query(Vehicle).all()
        else:
            # Khách hàng: chỉ xe của mình
            db_user = db.query(User).filter(User.username == user["sub"]).first()
            if db_user:
                vehicles = db.query(Vehicle).filter(Vehicle.user_id == db_user.id).all()
        
    return templates.TemplateResponse(
        request=request, name="ai_assistant.html", context={"title": "AI Diagnostic Assistant", "user": user, "vehicles": vehicles}
    )



class ChatRequest(BaseModel):
    message: str
    is_first_message: bool = True
    history: list = []

# Quy tac trich nguon RAG (khop format citation rag_service.py):
# ghep kem moi khi dua tai lieu noi bo vao context_msg de Gemini
# bat buoc ghi nguon thay vi tra loi chay.
RAG_CITE_RULE = (
    "YÊU CẦU TRÍCH NGUỒN: khi trả lời có dùng thông tin từ tài liệu nội bộ trên, "
    "bắt buộc ghi rõ nguồn theo đúng định dạng [Trích từ <source>#<chunk_index>] "
    "(giữ nguyên tên file và số chunk, VD [Trích từ bao-duong-dinh-ky.txt#2]). "
    "Không được bịa tên nguồn."
)

@app.post("/api/chatbot")
async def chat_bot(data: ChatRequest, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    
    def generate_error(msg):
        yield msg
        
    if not user:
        msg = "Bạn cần đăng nhập để mình có thể kiểm tra sổ bảo hành và lịch sử xe nhé!" if data.is_first_message else "Vui lòng đăng nhập để mình hỗ trợ tốt hơn."
        return StreamingResponse(generate_error(msg), media_type="text/plain")
    
    # Get user from db
    db_user = db.query(User).filter(User.username == user.get("sub")).first()
    if not db_user:
        return StreamingResponse(generate_error("Lỗi: Không tìm thấy người dùng."), media_type="text/plain")
    
    # Get user's vehicles
    vehicles = db.query(Vehicle).filter(Vehicle.user_id == db_user.id).all()
    
    # Role + ten nguoi chat (chung base.build_role_context)
    context_msg = build_role_context(user, db_user)
    user_role = user.get("role", "customer")
    
    if user_role == "customer":
        if vehicles:
            context_msg += "Thông tin các xe của khách:\n"
            for car in vehicles:
                context_msg += build_vehicle_context(db, car) + "\n"
        else:
            context_msg += "Khách hàng chưa có dữ liệu xe nào trong hệ thống."
    elif user_role in ("technician", "manager", "admin"):
        context_msg += "Hãy hỗ trợ nhân viên xưởng chẩn đoán lỗi xe nâng cao, tư vấn quy trình sửa chữa hoặc tra cứu phụ tùng."

        # Quản lý/KTV/Admin: được hỏi về bất kỳ xe khách nào qua biển số trong tin nhắn
        found_vehicle = detect_vehicle(data.message, db.query(Vehicle).all())

        if found_vehicle:
            context_msg += f"\n[HỆ THỐNG] Nhân viên xưởng đang hỏi về xe khách: {found_vehicle.make} {found_vehicle.model} (Biển số: {found_vehicle.license_plate}). "
            context_msg += "\n" + build_vehicle_context(db, found_vehicle)
            
    # Tích hợp RAG: Tìm kiếm tài liệu nội bộ (chung tools.search_knowledge, "" khi Chroma rỗng/lỗi)
    rag_context = agent_tools.search_knowledge(data.message)
    if rag_context:
        context_msg += f"\n\n[TÀI LIỆU NỘI BỘ HỖ TRỢ]:\n{rag_context}\n{RAG_CITE_RULE}\n"

    # Gọi AI (stream) qua wrapper chung: lỗi 503/429 -> text TV đồng nhất,
    # log server-side (docstring base.call_gemini_safe).
    def generate():
        for chunk in call_gemini_safe(message=data.message, context_msg=context_msg,
                                      history=data.history, stream=True):
            # Xóa các ký tự markdown như AI có thể vẫn sinh ra
            clean_chunk = chunk.replace('*', '').replace('#', '')
            yield clean_chunk

    return StreamingResponse(generate(), media_type="text/plain")

class DiagnoseRequest(BaseModel):
    symptoms: str
    vehicle_id: Optional[str] = None

@app.post("/api/ai/diagnose")
async def ai_diagnose(data: DiagnoseRequest, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return JSONResponse({"status": "error", "code": "login_required",
                             "reply": "Bạn cần đăng nhập để dùng chẩn đoán AI."}, status_code=401)

    context_msg = "Phân tích lỗi xe (AI Assistant). "
    if data.vehicle_id:
        try:
            vid = int(data.vehicle_id)
        except (TypeError, ValueError):
            return JSONResponse({"status": "error", "reply": "Xe không hợp lệ."}, status_code=400)
        vehicle = db.query(Vehicle).filter(Vehicle.id == vid).first()
        if not vehicle:
            return JSONResponse({"status": "error", "reply": "Không tìm thấy xe."}, status_code=404)
        # Phân quyền xe: khách chỉ xe mình, KTV/quản lý/admin được chọn xe khách bất kỳ
        if user.get("role") not in ("technician", "manager", "admin"):
            db_user = db.query(User).filter(User.username == user.get("sub")).first()
            if not db_user or vehicle.user_id != db_user.id:
                return JSONResponse({"status": "error", "reply": "Xe này không thuộc tài khoản của bạn."}, status_code=403)
            context_msg += "\nXe được chọn để chẩn đoán. " + build_vehicle_context(db, vehicle)
        else:
            context_msg += (
                f"\n[NHÂN VIÊN XƯỞNG] {user.get('role')} đang phân tích xe khách "
                f"{vehicle.make} {vehicle.model} (Biển số: {vehicle.license_plate}). "
            ) + build_vehicle_context(db, vehicle)
    else:
        context_msg += "Kỹ thuật viên không chọn xe cụ thể. Hãy phân tích dựa trên kiến thức chuyên môn, cẩm nang sửa chữa chung của garage và kinh nghiệm tổng hợp."
        
    prompt = (
        f"Triệu chứng lỗi xe: '{data.symptoms}'.\n"
        "Hãy đóng vai chuyên gia sửa chữa ô tô phân tích và trả về kết quả dưới định dạng HTML thuần túy (KHÔNG bọc trong markdown code block ```html).\n"
        "Hãy sử dụng các thẻ class Bootstrap cơ bản (text-danger, text-success) và biểu tượng Bootstrap Icons.\n"
        "Cấu trúc bắt buộc:\n"
        "<div class='mb-4'>\n"
        "    <h5 class='fw-bold text-danger mb-3'><i class='bi bi-exclamation-triangle-fill me-2'></i> Nguyên nhân khả năng:</h5>\n"
        "    <ul class='mb-0 fs-5'>\n"
        "        <li class='mb-2'>...</li>\n"
        "    </ul>\n"
        "</div>\n"
        "<hr style='opacity: 0.1'>\n"
        "<div class='mt-4'>\n"
        "    <h5 class='fw-bold text-success mb-2'><i class='bi bi-lightbulb-fill me-2'></i> Đề xuất xử lý:</h5>\n"
        "    <p class='mb-0 fs-5 text-dark'>...</p>\n"
        "</div>\n\n"
        "Nội dung chuyên môn, ngắn gọn, súc tích. TUYỆT ĐỐI KHÔNG dùng ký tự Markdown như ** hay #."
    )
    
    # Tích hợp RAG: Tìm kiếm tài liệu nội bộ (chung tools.search_knowledge, "" khi Chroma rỗng/lỗi)
    rag_context = agent_tools.search_knowledge(data.symptoms)
    if rag_context:
        context_msg += f"\n\n[TÀI LIỆU NỘI BỘ HỖ TRỢ]:\n{rag_context}\n{RAG_CITE_RULE}\n"

    result = get_gemini_response(message=prompt, history=[], context_msg=context_msg)
    
    # Strip markdown code blocks if AI still adds them
    result = result.strip()
    if result.startswith("```html"):
        result = result[7:]
    if result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
        
    return {"status": "success", "html": result.strip()}
