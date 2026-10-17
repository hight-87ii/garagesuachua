import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.models import User, Vehicle
from app.routers.auth import get_password_hash

def seed_customers():
    db = SessionLocal()
    
    customers_data = [
        {"username": "kh_anh_tuan", "password": "123", "full_name": "Nguyễn Anh Tuấn", "phone": "0912345601", "email": "tuan.na@example.com", "vehicles": [("30A-123.45", "Toyota", "Camry 2.0Q")]},
        {"username": "kh_minh_ngoc", "password": "123", "full_name": "Trần Minh Ngọc", "phone": "0912345602", "email": "ngoc.tm@example.com", "vehicles": [("30G-567.89", "Honda", "CR-V L")]},
        {"username": "kh_van_binh", "password": "123", "full_name": "Lê Văn Bình", "phone": "0912345603", "email": "binh.lv@example.com", "vehicles": [("30F-999.99", "Ford", "Everest Titanium"), ("29C-111.22", "Ford", "Ranger Wildtrak")]},
        {"username": "kh_thu_huong", "password": "123", "full_name": "Phạm Thu Hương", "phone": "0912345604", "email": "huong.pt@example.com", "vehicles": [("29A-333.44", "Mazda", "CX-5 Premium")]},
        {"username": "kh_duc_thang", "password": "123", "full_name": "Hoàng Đức Thắng", "phone": "0912345605", "email": "thang.hd@example.com", "vehicles": [("30K-555.66", "Hyundai", "SantaFe Premium")]},
        {"username": "kh_thanh_hai", "password": "123", "full_name": "Ngô Thanh Hải", "phone": "0912345606", "email": "hai.nt@example.com", "vehicles": [("29D-777.88", "Kia", "Sorento Signature")]},
        {"username": "kh_bao_nam", "password": "123", "full_name": "Vũ Bảo Nam", "phone": "0912345607", "email": "nam.vb@example.com", "vehicles": [("30E-222.33", "Mercedes-Benz", "GLC 300 4MATIC")]},
        {"username": "kh_quang_huy", "password": "123", "full_name": "Đặng Quang Huy", "phone": "0912345608", "email": "huy.dq@example.com", "vehicles": [("30H-888.11", "BMW", "330i M Sport")]},
        {"username": "kh_mai_phuong", "password": "123", "full_name": "Đỗ Mai Phương", "phone": "0912345609", "email": "phuong.dm@example.com", "vehicles": [("29C-444.55", "VinFast", "VF 8 Eco")]},
        {"username": "kh_quoc_bao", "password": "123", "full_name": "Bùi Quốc Bảo", "phone": "0912345610", "email": "bao.bq@example.com", "vehicles": [("30L-666.77", "Mitsubishi", "Xpander Premium")]},
    ]

    for data in customers_data:
        # Check if user exists
        existing_user = db.query(User).filter(User.username == data["username"]).first()
        if not existing_user:
            new_user = User(
                username=data["username"],
                password_hash=get_password_hash(data["password"]),
                full_name=data["full_name"],
                phone=data["phone"],
                email=data["email"],
                role="customer"
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            for v_data in data["vehicles"]:
                new_vehicle = Vehicle(
                    user_id=new_user.id,
                    license_plate=v_data[0],
                    make=v_data[1],
                    model=v_data[2]
                )
                db.add(new_vehicle)
            db.commit()
            print("Created customer")
        else:
            print("Customer already exists")
            
    db.close()
    print("Seeding complete.")

if __name__ == "__main__":
    seed_customers()
