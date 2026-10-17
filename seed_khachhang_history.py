from app.database import SessionLocal
from app.models.models import User, Vehicle, RepairOrder, Invoice
from datetime import datetime, timedelta
import random

def seed_history():
    db = SessionLocal()
    
    # 1. Lấy user khachhang
    user = db.query(User).filter(User.username == "khachhang").first()
    if not user:
        print("Không tìm thấy user 'khachhang'. Vui lòng chạy seed_users.py trước.")
        db.close()
        return

    # 2. Lấy hoặc tạo Vehicle
    vehicle = db.query(Vehicle).filter(Vehicle.user_id == user.id).first()
    if not vehicle:
        vehicle = Vehicle(
            license_plate="51H-123.45",
            make="Toyota",
            model="Camry",
            version="2.0G",
            manufacture_year=2020,
            color="Đen",
            fuel_type="Xăng",
            vin="VIN123456789",
            engine_number="ENG987654321",
            current_odo=45000,
            usage_type="Cá nhân / Gia đình",
            warranty_status="Còn bảo hành",
            user_id=user.id
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        print(f"Đã tạo xe {vehicle.license_plate} cho user {user.username}")
    else:
        print(f"User {user.username} đã có xe {vehicle.license_plate}")

    # 3. Tạo Repair Orders
    orders = db.query(RepairOrder).filter(RepairOrder.vehicle_id == vehicle.id).all()
    if len(orders) < 3:
        history = [
            {
                "symptoms": "Bảo dưỡng 20.000km, thay dầu máy, lọc dầu.",
                "inspection_result": "Động cơ hoạt động bình thường, gầm bệ chắc chắn.",
                "status": "Completed",
                "customer_approval": "Approved",
                "created_at": datetime.utcnow() - timedelta(days=240),
                "completed_at": datetime.utcnow() - timedelta(days=239),
                "reception_datetime": (datetime.utcnow() - timedelta(days=240)).isoformat(),
                "handover_datetime": (datetime.utcnow() - timedelta(days=239)).isoformat(),
                "estimated_cost": 1500000,
                "current_odo": 20100,
                "service_rating": 5
            },
            {
                "symptoms": "Xe chạy bị nhao lái, mòn lốp không đều.",
                "inspection_result": "Góc đặt bánh xe sai lệch, cần cân chỉnh thước lái và đảo lốp.",
                "status": "Completed",
                "customer_approval": "Approved",
                "created_at": datetime.utcnow() - timedelta(days=120),
                "completed_at": datetime.utcnow() - timedelta(days=119),
                "reception_datetime": (datetime.utcnow() - timedelta(days=120)).isoformat(),
                "handover_datetime": (datetime.utcnow() - timedelta(days=119)).isoformat(),
                "estimated_cost": 800000,
                "current_odo": 30500,
                "service_rating": 4
            },
            {
                "symptoms": "Bảo dưỡng 40.000km, thay má phanh trước, kêu két két.",
                "inspection_result": "Má phanh mòn quá hạn, các dung dịch hao hụt.",
                "status": "Completed",
                "customer_approval": "Approved",
                "created_at": datetime.utcnow() - timedelta(days=15),
                "completed_at": datetime.utcnow() - timedelta(days=14),
                "reception_datetime": (datetime.utcnow() - timedelta(days=15)).isoformat(),
                "handover_datetime": (datetime.utcnow() - timedelta(days=14)).isoformat(),
                "estimated_cost": 3500000,
                "current_odo": 44800,
                "service_rating": 5
            }
        ]
        
        for h in history:
            ro = RepairOrder(
                vehicle_id=vehicle.id,
                order_type="Repair",
                symptoms=h["symptoms"],
                inspection_result=h["inspection_result"],
                status=h["status"],
                customer_approval=h["customer_approval"],
                created_at=h["created_at"],
                completed_at=h["completed_at"],
                reception_datetime=h["reception_datetime"],
                handover_datetime=h["handover_datetime"],
                estimated_cost=h["estimated_cost"],
                current_odo=h["current_odo"],
                service_rating=h["service_rating"]
            )
            db.add(ro)
            db.commit()
            db.refresh(ro)
            
            # create invoice
            inv = Invoice(
                repair_order_id=ro.id,
                total_amount=h["estimated_cost"],
                subtotal=h["estimated_cost"],
                status="Paid",
                created_at=h["completed_at"]
            )
            db.add(inv)
        db.commit()
        print(f"Đã thêm 3 lịch sử sửa chữa và hóa đơn cho xe {vehicle.license_plate}")
    else:
        print("Lịch sử sửa chữa đã tồn tại cho xe này.")

    db.close()
    print("Hoàn tất thêm dữ liệu cho khách hàng.")

if __name__ == "__main__":
    seed_history()
