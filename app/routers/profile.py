from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import User, EmployeeProfile
from app.routers.auth import get_current_user_from_cookie, get_password_hash

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request, db: Session = Depends(get_db)):
    user_cookie = get_current_user_from_cookie(request, db)
    if not user_cookie:
        return RedirectResponse("/login")
        
    db_user = db.query(User).filter(User.username == user_cookie["sub"]).first()
    
    return templates.TemplateResponse(request=request, name="profile.html", context={
        "user": user_cookie, "db_user": db_user
    })

@router.post("/profile/update")
async def update_profile(
    request: Request,
    db: Session = Depends(get_db)
):
    form_data = await request.form()
    
    user_cookie = get_current_user_from_cookie(request, db)
    if not user_cookie:
        return RedirectResponse("/login")
        
    db_user = db.query(User).filter(User.username == user_cookie["sub"]).first()
    if db_user:
        db_user.full_name = form_data.get("full_name", db_user.full_name)
        db_user.phone = form_data.get("phone")
        db_user.email = form_data.get("email")
        db_user.address = form_data.get("address")
        db_user.birth_date = form_data.get("birth_date")
        db_user.preferred_contact = form_data.get("preferred_contact")
        password = form_data.get("password")
        if password: # Nếu có nhập mật khẩu mới
            db_user.password_hash = get_password_hash(password)
            
        # Xử lý thông tin Employee Profile nếu là nhân viên
        if db_user.role in ["technician", "manager"]:
            if not db_user.employee_profile:
                db_user.employee_profile = EmployeeProfile(user_id=db_user.id)
            
            profile = db_user.employee_profile
            
            profile.dob_year = int(form_data.get("dob_year")) if form_data.get("dob_year") else None
            profile.gender = form_data.get("gender")
            profile.avatar_url = form_data.get("avatar_url")
            profile.work_area = form_data.get("work_area")
            
            profile.job_title = form_data.get("job_title")
            profile.garage_name = form_data.get("garage_name")
            profile.years_of_experience = int(form_data.get("years_of_experience")) if form_data.get("years_of_experience") else None
            profile.hire_date = form_data.get("hire_date") or None
            profile.past_roles = form_data.get("past_roles")
            
            # Checkbox fields
            profile.technical_skills = ",".join(form_data.getlist("technical_skills")) if form_data.getlist("technical_skills") else None
            
            profile.education_school = form_data.get("education_school")
            profile.education_degree = form_data.get("education_degree")
            profile.trade_certificates = ",".join(form_data.getlist("trade_certificates")) if form_data.getlist("trade_certificates") else None
            profile.brand_certificates = form_data.get("brand_certificates")
            profile.safety_certificates = form_data.get("safety_certificates")
            
            profile.past_garages = form_data.get("past_garages")
            profile.vehicle_types = ",".join(form_data.getlist("vehicle_types")) if form_data.getlist("vehicle_types") else None
            profile.key_projects = form_data.get("key_projects")
            
            profile.zalo_link = form_data.get("zalo_link")
            profile.facebook_link = form_data.get("facebook_link")
            profile.linkedin_link = form_data.get("linkedin_link")
            profile.garage_address = form_data.get("garage_address")
            
            profile.customer_rating_score = float(form_data.get("customer_rating_score")) if form_data.get("customer_rating_score") else None
            profile.feedback_summary = form_data.get("feedback_summary")
            
            profile.social_profiles = form_data.get("social_profiles")
            profile.tutorial_videos = form_data.get("tutorial_videos")
            profile.tech_posts = form_data.get("tech_posts")
            profile.community_participation = form_data.get("community_participation")
            
        db.commit()
        
    return RedirectResponse("/profile?success=1", status_code=302)
