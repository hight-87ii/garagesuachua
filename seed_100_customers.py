"""Seed 100 khach hang co lich su sua chua 5 nam (2021-2026).

- Moi khach: full info (ten, SDT, email, dia chi).
- 60% 1 xe, 30% 2 xe, 10% 3 xe.
- Moi xe: 3-6 phieu Completed + xe dang sua gan day (20% xe).
- Phieu Completed co: tho sua, bao gia, linh kien, danh gia sao, hoa don (Paid 85%).
- Chay:  python seed_100_customers.py   (bo qua tai khoan da ton tai)
"""
import random
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.models import (User, Vehicle, RepairOrder, RepairOrderPart,
                               Invoice, Appointment, SparePart)
from app.routers.auth import get_password_hash

random.seed(20261008)
NOW = datetime(2026, 10, 8)
START = datetime(2021, 10, 8)

HO = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Huynh", "Phan", "Vu", "Vo",
      "Dang", "Bui", "Do", "Ho", "Ngo", "Duong", "Ly"]
TEN_DEM_NAM = ["Van", "Huu", "Duc", "Minh", "Quoc", "Thanh", "Cong", "Xuan"]
TEN_DEM_NU = ["Thi", "Ngoc", "Thu", "Thanh", "Kim", "My", "Thuy", "Dieu"]
TEN_NAM = ["Anh", "Tuan", "Hung", "Dung", "Nam", "Long", "Hai", "Son", "Binh",
           "Cuong", "Khanh", "Phong", "Vinh", "Bao", "Khoa", "Dat"]
TEN_NU = ["Anh", "Hoa", "Lan", "Huong", "Ngoc", "Trang", "Linh", "Thao", "Mai",
          "Phuong", "Hanh", "Quyen", "Tram", "Yen", "Nhan", "Dao"]
PHO = ["Hoang Van Thu", "Luong Ngoc Quyen", "Phan Dinh Phung", "Ben Oanh",
       "Thong Nhat", "Gang Thep", "Bac Son", "Nui Coc", "Viet Bac", "Minh Cau"]
CARS = [("Toyota", "Vios"), ("Toyota", "Innova"), ("Toyota", "Fortuner"),
        ("Honda", "City"), ("Honda", "CR-V"), ("Mazda", "Mazda 3"),
        ("Mazda", "CX-5"), ("Kia", "Morning"), ("Kia", "K3"), ("Kia", "Seltos"),
        ("Hyundai", "Accent"), ("Hyundai", "Creta"), ("Hyundai", "Tucson"),
        ("Ford", "Ranger"), ("Ford", "Everest"), ("Mitsubishi", "Xpander"),
        ("VinFast", "Fadil"), ("VinFast", "Lux A2.0"), ("Suzuki", "XL7"),
        ("Nissan", "Almera")]
COLORS = ["Den", "Trang", "Bac", "Do", "Xanh duong", "Xam", "Nau"]
FUELS = ["Xang", "Dau (Diesel)"]
JOBS = [
    ("Thay dau may dinh ky", "Thay dau + loc dau, kiem tra tong quat", 350000, 650000),
    ("Bao duong cap 10000 km", "Bao duong dinh ky theo hang muc NSX", 800000, 1500000),
    ("Bao duong cap 40000 km", "Thay toan bo loc, dau hop so, bugi", 2500000, 4500000),
    ("Xe bao loi dong co (Check engine)", "Doc loi, ve sinh kim phun, thay bugi", 900000, 2200000),
    ("Thay ma phanh truoc", "Thay ma phanh + lang dia", 700000, 1600000),
    ("Ve sinh dan lanh dieu hoa", "Ve sinh + nap ga dieu hoa", 600000, 1200000),
    ("Xe keu gam khi qua o ga", "Thay rotuyn + cao su chan may", 1200000, 2800000),
    ("Thay loc gio dong co + loc gio dieu hoa", "Thay 2 loc chinh hang", 450000, 800000),
    ("Kiem tra ac quy, de kho no", "Thay ac quy 12V-45Ah", 1500000, 2200000),
    ("Thay lop + can bang dong", "4 lop moi + can mam", 3200000, 6800000),
    ("Rua xe, don noi that chi tiet", "Rua + hut bui + duong da", 400000, 900000),
    ("Danh bong + phu ceramic", "3 buoc danh bong, phu 9H", 3500000, 6000000),
    ("Dong son can truoc va quet", "Son dam + danh bong", 1800000, 3200000),
    ("Sua dieu hoa khong mat", "Thay loc + nap ga + ve sinh", 800000, 1800000),
    ("Thay giam soc sau", "Cap giam soc + cong thay", 2200000, 4200000),
]
PAY_METHODS = ["Tiền mặt", "Chuyển khoản", "Ví điện tử", "Thẻ ngân hàng"]
SEV = ["Nhẹ", "Trung bình", "Nặng"]


def rand_date(a, b):
    return a + timedelta(days=random.randrange((b - a).days + 1),
                         hours=random.randrange(8, 18))


def main():
    db = SessionLocal()
    tech_ids = [t.id for t in db.query(User).filter(User.role == "technician").all()]
    parts = db.query(SparePart).all()
    used_plates, used_phones = set(), set()
    for v in db.query(Vehicle.license_plate).all():
        used_plates.add(v[0])
    for u in db.query(User.phone).all():
        if u[0]:
            used_phones.add(u[0])

    def new_phone():
        while True:
            p = random.choice(["09", "03", "07", "08"]) + "".join(
                random.choice("0123456789") for _ in range(8))
            if p not in used_phones:
                used_phones.add(p)
                return p

    def new_plate():
        while True:
            pl = f"{random.choice(['20H', '29D', '30E', '30G', '98B', '89C'])}-{random.randint(100, 999)}.{random.randint(10, 99)}"
            if pl not in used_plates:
                used_plates.add(pl)
                return pl

    n_cust = n_veh = n_ord = n_inv = 0
    for i in range(1, 101):
        uname = f"seedkh{i:03d}"
        if db.query(User).filter(User.username == uname).first():
            continue
        female = random.random() < 0.45
        name = (f"{random.choice(HO)} {random.choice(TEN_DEM_NU)} {random.choice(TEN_NU)}"
                if female else
                f"{random.choice(HO)} {random.choice(TEN_DEM_NAM)} {random.choice(TEN_NAM)}")
        phone = new_phone()
        u = User(username=uname, password_hash=get_password_hash("123456"),
                 full_name=name, phone=phone,
                 email=f"{uname}@example.com",
                 address=f"Số {random.randint(1, 200)} {random.choice(PHO)}, Thái Nguyên",
                 role="customer")
        db.add(u)
        db.flush()
        n_cust += 1

        r = random.random()
        n_cars = 1 if r < 0.6 else (2 if r < 0.9 else 3)
        for _ in range(n_cars):
            make, model = random.choice(CARS)
            odo = random.randint(15000, 180000)
            v = Vehicle(license_plate=new_plate(), make=make, model=model,
                        manufacture_year=random.randint(2015, 2025),
                        color=random.choice(COLORS), fuel_type=random.choice(FUELS),
                        vin=f"RL4{random.randint(100000000000000, 999999999999999)}",
                        engine_number=f"{random.randint(100000, 999999)}{make[:2].upper()}",
                        current_odo=odo, user_id=u.id)
            db.add(v)
            db.flush()
            n_veh += 1

            # Lich su: 3-6 phieu Completed rai 5 nam
            cur_odo, cur = odo - random.randint(20000, 60000), START
            hist = sorted(rand_date(START, NOW - timedelta(days=40))
                          for _ in range(random.randint(3, 6)))
            for h in hist:
                cur_odo += random.randint(3000, 12000)
                sym, insp, lo, hi = random.choice(JOBS)
                labor = random.randint(lo, hi) // 1000 * 1000
                tech = random.choice(tech_ids) if tech_ids else None
                ro = RepairOrder(
                    vehicle_id=v.id, technician_id=tech, symptoms=sym,
                    ai_diagnosis=None, reception_datetime=h.strftime("%Y-%m-%dT%H:%M"),
                    deliverer_name=name, fuel_level=random.choice(["Đầy", "1/2", "Gần hết"]),
                    current_odo=cur_odo, symptom_severity=random.choice(SEV),
                    key_count=random.choice([1, 2]), inspection_result=insp,
                    estimated_cost=labor, customer_approval="Approved",
                    status="Completed", created_at=h,
                    repair_started_at=h + timedelta(hours=2),
                    completed_at=h + timedelta(days=random.randint(1, 4)),
                    handover_datetime=(h + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%dT10:00"),
                    final_odo=cur_odo + random.randint(0, 50),
                    service_rating=random.choices([5, 5, 5, 4, 4, 3], k=1)[0] if random.random() < 0.75 else None)
                db.add(ro)
                db.flush()
                n_ord += 1
                # Linh kien 0-3 dong
                parts_total = 0
                for rp in random.sample(parts, k=min(len(parts), random.randint(0, 3))):
                    q = random.randint(1, 2)
                    db.add(RepairOrderPart(repair_order_id=ro.id, part_id=rp.id,
                                           quantity=q, unit_price=rp.price or 0))
                    parts_total += q * (rp.price or 0)
                # Hoa don
                sub = labor + parts_total
                vat = round(sub * 0.1)
                disc = random.choice([0, 0, 0, 50000, 100000])
                paid = random.random() < 0.85
                db.add(Invoice(repair_order_id=ro.id, subtotal=sub, vat_amount=vat,
                               discount=disc, total_amount=sub + vat - disc,
                               payment_method=random.choice(PAY_METHODS) if paid else None,
                               warranty_info="Bảo hành dịch vụ 1 tháng, phụ tùng thay thế bảo hành theo hãng sản xuất.",
                               status="Paid" if paid else "Unpaid",
                               created_at=ro.completed_at))
                n_inv += 1
                # Lich hen lien ket (40%)
                if random.random() < 0.4:
                    db.add(Appointment(user_id=u.id, vehicle_id=v.id,
                                       appointment_date=(h - timedelta(days=1)).strftime("%Y-%m-%d"),
                                       appointment_time=random.choice(["08:00", "09:00", "14:30"]),
                                       appointment_type="Repair", symptoms=sym,
                                       status="Completed",
                                       preferred_technician_id=tech))
                cur = h
            v.current_odo = cur_odo
            # 20% xe co phieu dang sua gan day
            if random.random() < 0.2:
                h = NOW - timedelta(days=random.randint(0, 10))
                sym, insp, lo, hi = random.choice(JOBS)
                ro = RepairOrder(
                    vehicle_id=v.id, technician_id=random.choice(tech_ids) if tech_ids else None,
                    symptoms=sym, reception_datetime=h.strftime("%Y-%m-%dT%H:%M"),
                    deliverer_name=name, current_odo=cur_odo + 500,
                    symptom_severity="Trung bình", key_count=1,
                    inspection_result=insp, estimated_cost=random.randint(lo, hi) // 1000 * 1000,
                    customer_approval="Approved", status="In Progress",
                    created_at=h, repair_started_at=h + timedelta(hours=1))
                db.add(ro)
                db.flush()
                n_ord += 1
        if n_cust % 20 == 0:
            db.commit()
            print(f"... {n_cust} khach")
    db.commit()
    print(f"DONE: {n_cust} khach, {n_veh} xe, {n_ord} phieu, {n_inv} hoa don")
    db.close()


if __name__ == "__main__":
    main()
