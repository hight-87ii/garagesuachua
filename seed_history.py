import os
import random
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.models import User, Vehicle, RepairOrder, Invoice

db = SessionLocal()

def random_date(start_date, end_date):
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    return start_date + timedelta(days=random_number_of_days)

# Lấy tất cả khách hàng
customers = db.query(User).filter(User.role == 'customer').all()

# Lấy kỹ thuật viên
technicians = db.query(User).filter(User.role == 'technician').all()
tech_ids = [t.id for t in technicians] if technicians else [None]

start_date = datetime.utcnow() - timedelta(days=365 * 3) # Trong 3 năm qua
end_date = datetime.utcnow()

symptoms_list = [
    "Thay dầu máy định kỳ",
    "Bảo dưỡng 10.000 km",
    "Xe báo lỗi động cơ (Check engine)",
    "Thay má phanh trước",
    "Vệ sinh dàn lạnh điều hòa",
    "Xe đi có tiếng kêu ở gầm",
    "Thay lọc gió động cơ, lọc gió điều hòa",
    "Kiểm tra ắc quy, đề khó nổ",
    "Thay lốp và cân bằng động",
    "Rửa xe, dọn nội thất chi tiết",
    "Phủ ceramic bảo vệ sơn",
    "Đồng sơn cản trước do va quẹt"
]

total_orders = 0

for customer in customers:
    # Đảm bảo khách hàng có ít nhất 1 xe
    vehicle = db.query(Vehicle).filter(Vehicle.user_id == customer.id).first()
    if not vehicle:
        vehicle = Vehicle(
            license_plate=f"30G-{random.randint(10000, 99999)}",
            make=random.choice(["Toyota", "Honda", "Hyundai", "Mazda", "Ford"]),
            model=random.choice(["Vios", "City", "Accent", "Mazda 3", "Ranger"]),
            user_id=customer.id
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
    
    # Tạo từ 5 đến 30 lần sửa chữa
    num_repairs = random.randint(5, 30)
    for _ in range(num_repairs):
        repair_date = random_date(start_date, end_date)
        
        # 1. Tạo RepairOrder
        ro = RepairOrder(
            vehicle_id=vehicle.id,
            technician_id=random.choice(tech_ids),
            order_type=random.choice(["Repair", "Maintenance", "Detailing"]),
            symptoms=random.choice(symptoms_list),
            status="Completed",
            created_at=repair_date,
            completed_at=repair_date + timedelta(hours=random.randint(1, 48)),
            handover_datetime=(repair_date + timedelta(hours=random.randint(1, 48))).strftime("%Y-%m-%d %H:%M"),
            service_rating=random.choice([4, 5, 5, 5]) # Đa số đánh giá cao
        )
        db.add(ro)
        db.commit()
        db.refresh(ro)
        
        # 2. Tạo Invoice
        amount = random.randint(300000, 15000000)
        inv = Invoice(
            repair_order_id=ro.id,
            total_amount=amount,
            subtotal=amount / 1.1, # 10% VAT
            vat_amount=amount - (amount / 1.1),
            payment_method=random.choice(["Tiền mặt", "Chuyển khoản", "Thẻ tín dụng"]),
            status="Paid",
            created_at=ro.completed_at
        )
        db.add(inv)
        db.commit()
        
        total_orders += 1

print(f"Added {total_orders} repair orders and invoices across {len(customers)} customers.")
