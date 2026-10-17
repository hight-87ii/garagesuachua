import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.models import User, EmployeeProfile
from app.routers.auth import get_password_hash

def seed_technicians():
    db = SessionLocal()
    
    # 2 lâu năm (10+ years), 6 tầm trung (3-5 years), 2 tay nghề cứng (6-9 years)
    techs_data = [
        # Lâu năm (Chuyên gia)
        {"username": "ktv_chuyen_gia_1", "full_name": "Lê Trọng Tấn", "exp": 15, "skills": "Chẩn đoán bằng máy scan,Sửa chữa động cơ,Hộp số", "title": "Quản đốc xưởng", "rating": 4.9, 
         "edu_school": "ĐH Bách Khoa Hà Nội", "edu_degree": "Đại học", "trade_certs": "Chẩn đoán,Sửa chữa cơ khí", "brand_certs": "Toyota Master, Mercedes-Benz Certified", "vehicles": "Xe Đức,Xe Nhật", "past_garages": "Mercedes-Benz Haxaco, Toyota Mỹ Đình", "dob_year": 1982, "gender": "Nam"},
        {"username": "ktv_chuyen_gia_2", "full_name": "Trần Văn Sáng", "exp": 12, "skills": "Hệ thống điện – ECU,Chẩn đoán bằng máy scan", "title": "Kỹ thuật viên chẩn đoán lỗi", "rating": 4.8,
         "edu_school": "ĐH Sư phạm Kỹ thuật Hưng Yên", "edu_degree": "Đại học", "trade_certs": "Điện ô tô,Chẩn đoán", "brand_certs": "BMW Diagnostic Expert", "vehicles": "Xe Đức,Xe Mỹ", "past_garages": "BMW Lê Văn Lương", "dob_year": 1985, "gender": "Nam"},
        
        # Tay nghề cứng
        {"username": "ktv_cung_1", "full_name": "Nguyễn Hoàng Minh", "exp": 8, "skills": "Sửa chữa động cơ,Hệ thống điện – ECU,Phanh, gầm, treo", "title": "Kỹ thuật viên sửa chữa ô tô", "rating": 4.7,
         "edu_school": "Cao đẳng Kỹ thuật Cao Thắng", "edu_degree": "Cao đẳng", "trade_certs": "Sửa chữa cơ khí,Điện ô tô", "brand_certs": "Ford Master", "vehicles": "Xe Mỹ,Xe Hàn", "past_garages": "Ford Thủ Đô", "dob_year": 1990, "gender": "Nam"},
        {"username": "ktv_cung_2", "full_name": "Phạm Quốc Toản", "exp": 7, "skills": "Hộp số,Điều hòa ô tô", "title": "Thợ máy", "rating": 4.6,
         "edu_school": "Trường Trung cấp Nghề Giao thông Vận tải", "edu_degree": "Trung cấp", "trade_certs": "Sửa chữa cơ khí", "brand_certs": "Hyundai Certified", "vehicles": "Xe Hàn,Xe Nhật", "past_garages": "Hyundai Đông Đô", "dob_year": 1992, "gender": "Nam"},
        
        # Tầm trung
        {"username": "ktv_trung_1", "full_name": "Đinh Văn Dũng", "exp": 4, "skills": "Phanh, gầm, treo,Bảo dưỡng định kỳ", "title": "Kỹ thuật viên sửa chữa ô tô", "rating": 4.5,
         "edu_school": "Cao đẳng Cơ điện Hà Nội", "edu_degree": "Cao đẳng", "trade_certs": "Sửa chữa cơ khí", "brand_certs": "", "vehicles": "Xe Nhật,Xe Hàn", "past_garages": "Kia Giải Phóng", "dob_year": 1996, "gender": "Nam"},
        {"username": "ktv_trung_2", "full_name": "Vũ Anh Khoa", "exp": 5, "skills": "Điều hòa ô tô,Bảo dưỡng định kỳ", "title": "Thợ điện – điện lạnh ô tô", "rating": 4.4,
         "edu_school": "Cao đẳng Nghề Công nghiệp", "edu_degree": "Cao đẳng", "trade_certs": "Điện ô tô", "brand_certs": "Denso AC Expert", "vehicles": "Xe Nhật", "past_garages": "Garage tự do", "dob_year": 1995, "gender": "Nam"},
        {"username": "ktv_trung_3", "full_name": "Lý Quang Thái", "exp": 3, "skills": "Đồng sơn", "title": "Thợ đồng sơn", "rating": 4.3,
         "edu_school": "Trung tâm dạy nghề thanh xuân", "edu_degree": "Trung cấp", "trade_certs": "Đồng sơn", "brand_certs": "", "vehicles": "Xe tải,Xe Nhật", "past_garages": "Gara Quang Minh", "dob_year": 1998, "gender": "Nam"},
        {"username": "ktv_trung_4", "full_name": "Bùi Đức Tài", "exp": 4, "skills": "Bảo dưỡng định kỳ,Phanh, gầm, treo", "title": "Kỹ thuật viên sửa chữa ô tô", "rating": 4.5,
         "edu_school": "Cao đẳng Kỹ thuật Ô tô", "edu_degree": "Cao đẳng", "trade_certs": "Sửa chữa cơ khí", "brand_certs": "Mazda Certified", "vehicles": "Xe Nhật", "past_garages": "Mazda Lê Văn Lương", "dob_year": 1996, "gender": "Nam"},
        {"username": "ktv_trung_5", "full_name": "Hồ Nhật Nam", "exp": 5, "skills": "Xe điện/hybrid,Chẩn đoán bằng máy scan", "title": "Kỹ thuật viên chẩn đoán lỗi", "rating": 4.6,
         "edu_school": "ĐH Công nghiệp Hà Nội", "edu_degree": "Đại học", "trade_certs": "Chẩn đoán,Điện ô tô", "brand_certs": "VinFast EV Certified", "vehicles": "Xe Nhật,Xe Hàn", "past_garages": "VinFast Thăng Long", "dob_year": 1995, "gender": "Nam"},
        {"username": "ktv_trung_6", "full_name": "Cao Thanh Trọng", "exp": 3, "skills": "Bảo dưỡng định kỳ,Sửa chữa động cơ", "title": "Thợ máy", "rating": 4.2,
         "edu_school": "Trường Trung cấp Nghề Cơ điện", "edu_degree": "Trung cấp", "trade_certs": "Sửa chữa cơ khí", "brand_certs": "", "vehicles": "Xe Hàn", "past_garages": "Gara An Phát", "dob_year": 1999, "gender": "Nam"}
    ]

    for i, data in enumerate(techs_data):
        existing_user = db.query(User).filter(User.username == data["username"]).first()
        if not existing_user:
            new_user = User(
                username=data["username"],
                password_hash=get_password_hash("123"),
                full_name=data["full_name"],
                phone=f"09876543{i:02d}",
                email=f"{data['username']}@threeh.vn",
                role="technician"
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            existing_user = new_user
            
        # Update or Create EmployeeProfile
        profile = db.query(EmployeeProfile).filter(EmployeeProfile.user_id == existing_user.id).first()
        if not profile:
            profile = EmployeeProfile(user_id=existing_user.id)
            db.add(profile)
            
        profile.years_of_experience = data["exp"]
        profile.job_title = data["title"]
        profile.technical_skills = data["skills"]
        profile.customer_rating_score = data["rating"]
        profile.garage_name = "ThreeH Workshop Thái Nguyên"
        
        # New enriched fields
        profile.education_school = data.get("edu_school")
        profile.education_degree = data.get("edu_degree")
        profile.trade_certificates = data.get("trade_certs")
        profile.brand_certificates = data.get("brand_certs")
        profile.vehicle_types = data.get("vehicles")
        profile.past_garages = data.get("past_garages")
        profile.dob_year = data.get("dob_year")
        profile.gender = data.get("gender")
        
        db.commit()
        print(f"Processed technician: {data['username']}")
            
    db.close()
    
    # Update files
    try:
        from export_accounts import export_users_to_files
        export_users_to_files()
    except Exception as e:
        print("Failed to update export files:", e)

    print("Seeding technicians complete.")

if __name__ == "__main__":
    seed_technicians()
