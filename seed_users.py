from app.database import SessionLocal
from app.models.models import User
from app.routers.auth import get_password_hash

def seed_users():
    db = SessionLocal()
    
    # Định nghĩa 3 tài khoản mẫu (kèm liên lạc để phiếu tiếp nhận tự điền)
    users = [
        {
            "username": "khachhang", 
            "password_hash": get_password_hash("123456"), 
            "full_name": "Nguyễn Văn Khách",
            "phone": "0981111222",
            "email": "khachhang@example.com",
            "address": "Số 1 Hoàng Văn Thụ, Thái Nguyên",
            "role": "customer"
        },
        {
            "username": "kythuat", 
            "password_hash": get_password_hash("123456"), 
            "full_name": "Trần Thợ Máy",
            "phone": "0981333444",
            "email": "kythuat@example.com",
            "role": "technician"
        },
        {
            "username": "quanly", 
            "password_hash": get_password_hash("123456"), 
            "full_name": "Lê Sếp Quản Lý",
            "phone": "0981555666",
            "email": "quanly@example.com",
            "role": "manager"
        },
        {
            "username": "admin", 
            "password_hash": get_password_hash("123456"), 
            "full_name": "Quản Trị Hệ Thống",
            "phone": "0981777888",
            "email": "admin@example.com",
            "role": "admin"
        }
    ]
    
    # Thêm vào Database nếu chưa tồn tại; tài khoản demo thiếu liên lạc thì bù (không ghi đè dữ liệu đã có)
    for u in users:
        existing = db.query(User).filter(User.username == u["username"]).first()
        if not existing:
            new_user = User(**u)
            db.add(new_user)
            print(f"Created: {u['username']}")
        else:
            touched = False
            for field in ("phone", "email", "address"):
                if not getattr(existing, field, None) and u.get(field):
                    setattr(existing, field, u[field])
                    touched = True
            print(f"Skipped (already exists): {u['username']}" + (" + backfilled contact" if touched else "") + ")")
            
    db.commit()
    db.close()
    print("Finished seeding users.")

if __name__ == "__main__":
    seed_users()
