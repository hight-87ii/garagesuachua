from app.database import SessionLocal
from app.models.models import User, EmployeeProfile
from app.routers.auth import get_password_hash

def seed_technicians():
    db = SessionLocal()
    
    technicians = [
        {
            "user": {
                "username": "kythuat_dien",
                "password_hash": get_password_hash("123456"),
                "full_name": "Phạm Văn Điện",
                "phone": "0901234567",
                "email": "dien.pv@threeh.vn",
                "role": "technician"
            },
            "profile": {
                "dob_year": 1992,
                "gender": "Nam",
                "work_area": "Khu vực TP.HCM",
                "avatar_url": "https://i.pravatar.cc/150?u=dien",
                "job_title": "Thợ điện – điện lạnh ô tô",
                "garage_name": "ThreeH Workshop",
                "years_of_experience": 8,
                "past_roles": "Thợ học việc, KTV điện chính",
                "technical_skills": "Hệ thống điện – ECU,Điều hòa ô tô,Xe điện/hybrid,Chẩn đoán bằng máy scan",
                "education_school": "Cao đẳng Kỹ thuật Cao Thắng",
                "education_degree": "Cao đẳng",
                "trade_certificates": "Điện ô tô,Chẩn đoán",
                "brand_certificates": "Toyota, VinFast",
                "safety_certificates": "An toàn điện 2023",
                "past_garages": "Auto 365 - 2015-2018\nToyota Phú Mỹ Hưng - 2018-2022",
                "vehicle_types": "Xe Nhật,Xe điện/hybrid",
                "key_projects": "Lắp đặt và đồng bộ hệ thống điện cho xe VinFast VF8 tai nạn nặng.",
                "zalo_link": "https://zalo.me/0901234567",
                "facebook_link": "https://facebook.com/pham.dien.auto",
                "customer_rating_score": 4.8,
                "feedback_summary": "Thợ làm cẩn thận, xử lý lỗi điện nhanh và triệt để.",
                "tech_posts": "https://oto-hui.com/members/pham_dien.123/"
            }
        },
        {
            "user": {
                "username": "kythuat_may",
                "password_hash": get_password_hash("123456"),
                "full_name": "Trần Trọng Máy",
                "phone": "0912345678",
                "email": "may.tt@threeh.vn",
                "role": "technician"
            },
            "profile": {
                "dob_year": 1988,
                "gender": "Nam",
                "work_area": "Khu vực TP.HCM",
                "avatar_url": "https://i.pravatar.cc/150?u=may",
                "job_title": "Kỹ thuật viên sửa chữa ô tô",
                "garage_name": "ThreeH Workshop",
                "years_of_experience": 12,
                "past_roles": "Thợ gầm, Thợ máy",
                "technical_skills": "Sửa chữa động cơ,Hộp số,Bảo dưỡng định kỳ",
                "education_school": "Đại học Sư phạm Kỹ thuật TP.HCM",
                "education_degree": "Đại học",
                "trade_certificates": "Sửa chữa cơ khí",
                "brand_certificates": "Ford, Mercedes",
                "safety_certificates": "ATVSLĐ Nhóm 3",
                "past_garages": "Ford Phổ Quang - 2012-2016\nVietnam Star Automobile - 2016-2023",
                "vehicle_types": "Xe Đức,Xe Mỹ,Xe Nhật",
                "key_projects": "Đại tu động cơ Mercedes C200 W204 bị ngập nước.",
                "zalo_link": "https://zalo.me/0912345678",
                "customer_rating_score": 4.9,
                "feedback_summary": "Bắt bệnh cực kỳ chuẩn, giải thích rõ ràng cho khách.",
                "tutorial_videos": "https://youtube.com/c/TranTrongMayAuto"
            }
        },
        {
            "user": {
                "username": "kythuat_dongson",
                "password_hash": get_password_hash("123456"),
                "full_name": "Lê Viết Sơn",
                "phone": "0987654321",
                "email": "son.lv@threeh.vn",
                "role": "technician"
            },
            "profile": {
                "dob_year": 1995,
                "gender": "Nam",
                "work_area": "Khu vực TP.HCM",
                "avatar_url": "https://i.pravatar.cc/150?u=son",
                "job_title": "Thợ đồng sơn",
                "garage_name": "ThreeH Workshop",
                "years_of_experience": 6,
                "past_roles": "Thợ sơn học việc, KTV Pha màu",
                "technical_skills": "Phục hồi thân vỏ,Sơn dặm,Sơn đổi màu",
                "education_school": "Trường Trung cấp Nghề Lý Tự Trọng",
                "education_degree": "Trung cấp",
                "trade_certificates": "Đồng sơn",
                "brand_certificates": "Hệ thống sơn RM",
                "safety_certificates": "An toàn hóa chất sơn",
                "past_garages": "Garage H2 - 2018-2020",
                "vehicle_types": "Xe Hàn,Xe Nhật",
                "key_projects": "Phục hồi toàn bộ thân vỏ xe Porsche Macan bị đâm đụng.",
                "zalo_link": "https://zalo.me/0987654321",
                "facebook_link": "https://facebook.com/vietson.paint",
                "customer_rating_score": 4.6,
                "feedback_summary": "Sơn đẹp, đều màu, mài mịn. Tuy nhiên thỉnh thoảng bàn giao xe chậm 1 chút do kỹ tính.",
                "community_participation": "Hội Kỹ Thuật Viên Đồng Sơn Việt Nam"
            }
        }
    ]
    
    for item in technicians:
        user_data = item["user"]
        profile_data = item["profile"]
        
        # Check if user exists
        existing_user = db.query(User).filter(User.username == user_data["username"]).first()
        
        if not existing_user:
            # Create user
            new_user = User(**user_data)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            # Create profile
            profile = EmployeeProfile(user_id=new_user.id, **profile_data)
            db.add(profile)
            db.commit()
            print(f"Đã tạo kỹ thuật viên: {new_user.username}")
        else:
            print(f"Kỹ thuật viên {user_data['username']} đã tồn tại. Đang cập nhật profile...")
            
            # Update profile if exists
            if existing_user.employee_profile:
                for key, value in profile_data.items():
                    setattr(existing_user.employee_profile, key, value)
            else:
                profile = EmployeeProfile(user_id=existing_user.id, **profile_data)
                db.add(profile)
                
            db.commit()
            print(f"Đã cập nhật profile cho kỹ thuật viên: {existing_user.username}")
            
    db.close()
    print("Hoàn tất!")

if __name__ == "__main__":
    seed_technicians()
