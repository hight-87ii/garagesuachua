"""Seed ~110 linh kien day du thong tin (tong kho ~130 mon).

Chay:  python seed_100_parts.py   (bo qua ma PT da ton tai)
"""
import random
from app.database import SessionLocal
from app.models.models import SparePart

random.seed(20261009)

# (ma, ten, nhom, don vi, hang, xuat xu, gia nhap, gia ban, bao hanh, tuong thich)
CATALOG = [
    # Dau nhot - loc
    ("OIL-001", "Dầu động cơ 5W-30 4L", "Dầu nhớt - vật tư tiêu hao", "Can", "Castrol", "Thái Lan", 520000, 650000, "Không", "Toyota,Honda,Mazda"),
    ("OIL-002", "Dầu động cơ 0W-20 4L", "Dầu nhớt - vật tư tiêu hao", "Can", "Mobil", "Singapore", 680000, 850000, "Không", "Honda,Toyota"),
    ("OIL-003", "Dầu hộp số ATF 4L", "Dầu nhớt - vật tư tiêu hao", "Can", "Toyota Genuine", "Nhật Bản", 900000, 1150000, "Không", "Toyota"),
    ("OIL-004", "Nước làm mát động cơ 4L", "Dầu nhớt - vật tư tiêu hao", "Can", "Honda Genuine", "Thái Lan", 280000, 380000, "Không", "Honda"),
    ("OIL-005", "Dầu phanh DOT4 1L", "Dầu nhớt - vật tư tiêu hao", "Chai", "Bosch", "Đức", 180000, 250000, "Không", "Tất cả"),
    ("FIL-001", "Lọc dầu động cơ", "Dầu nhớt - vật tư tiêu hao", "Cái", "Toyota Genuine", "Nhật Bản", 90000, 150000, "6 tháng", "Toyota"),
    ("FIL-002", "Lọc gió động cơ", "Dầu nhớt - vật tư tiêu hao", "Cái", "Honda Genuine", "Thái Lan", 180000, 280000, "6 tháng", "Honda"),
    ("FIL-003", "Lọc gió điều hòa", "Dầu nhớt - vật tư tiêu hao", "Cái", "Denso", "Nhật Bản", 150000, 240000, "6 tháng", "Toyota,Honda,Mazda"),
    ("FIL-004", "Lọc nhiên liệu", "Dầu nhớt - vật tư tiêu hao", "Cái", "Hyundai Mobis", "Hàn Quốc", 220000, 340000, "6 tháng", "Hyundai,Kia"),
    ("FIL-005", "Lọc dầu hộp số", "Dầu nhớt - vật tư tiêu hao", "Cái", "Mazda Genuine", "Nhật Bản", 350000, 520000, "6 tháng", "Mazda"),
    # Phanh
    ("BRK-001", "Má phanh trước", "Hệ thống phanh", "Bộ", "Toyota Genuine", "Nhật Bản", 650000, 950000, "12 tháng", "Toyota Vios"),
    ("BRK-002", "Má phanh sau", "Hệ thống phanh", "Bộ", "Honda Genuine", "Thái Lan", 550000, 820000, "12 tháng", "Honda City"),
    ("BRK-003", "Đĩa phanh trước", "Hệ thống phanh", "Cái", "Brembo", "Ý", 850000, 1250000, "12 tháng", "Mazda 3"),
    ("BRK-004", "Đĩa phanh sau", "Hệ thống phanh", "Cái", "Bosch", "Đức", 720000, 1050000, "12 tháng", "Kia K3"),
    ("BRK-005", "Dây phanh tay", "Hệ thống phanh", "Sợi", "Hyundai Mobis", "Hàn Quốc", 280000, 420000, "6 tháng", "Hyundai Accent"),
    ("BRK-006", "Heo phanh (caliper) trước", "Hệ thống phanh", "Cái", "Toyota Genuine", "Nhật Bản", 1800000, 2600000, "12 tháng", "Toyota Innova"),
    ("BRK-007", "Bố thắng đùm sau", "Hệ thống phanh", "Bộ", "Honda Genuine", "Việt Nam", 420000, 620000, "12 tháng", "Honda CR-V"),
    # Dien - ac quy - den
    ("ELE-001", "Ắc quy 12V-45Ah", "Hệ thống điện", "Bình", "GS", "Việt Nam", 1350000, 1750000, "12 tháng", "Vios,City,Accent"),
    ("ELE-002", "Ắc quy 12V-70Ah", "Hệ thống điện", "Bình", "Atlas", "Hàn Quốc", 1900000, 2500000, "12 tháng", "Fortuner,Ranger"),
    ("ELE-003", "Bugi bạch kim (bộ 4)", "Hệ thống điện", "Bộ", "Denso", "Nhật Bản", 480000, 720000, "12 tháng", "Toyota,Honda"),
    ("ELE-004", "Bugi thường (bộ 4)", "Hệ thống điện", "Bộ", "NGK", "Nhật Bản", 260000, 400000, "12 tháng", "Kia,Hyundai"),
    ("ELE-005", "Bóng đèn pha LED H4", "Hệ thống điện", "Cặp", "Philips", "Đức", 850000, 1250000, "12 tháng", "Tất cả"),
    ("ELE-006", "Bóng đèn hậu", "Hệ thống điện", "Cặp", "Osram", "Đức", 120000, 200000, "6 tháng", "Tất cả"),
    ("ELE-007", "Còi xe 12V", "Hệ thống điện", "Cái", "Denso", "Nhật Bản", 180000, 280000, "6 tháng", "Tất cả"),
    ("ELE-008", "Máy phát điện (dinamo)", "Hệ thống điện", "Cái", "Mitsubishi Electric", "Nhật Bản", 3200000, 4500000, "12 tháng", "Xpander"),
    ("ELE-009", "Củ đề (máy khởi động)", "Hệ thống điện", "Cái", "Denso", "Nhật Bản", 2800000, 3900000, "12 tháng", "Vios,Accent"),
    ("ELE-010", "Cảm biến oxy", "Hệ thống điện", "Cái", "Denso", "Nhật Bản", 950000, 1400000, "12 tháng", "Toyota,Honda,Mazda"),
    # Dieu hoa
    ("AC-001", "Lốc điều hòa", "Điều hòa", "Cái", "Denso", "Nhật Bản", 4500000, 6200000, "12 tháng", "Vios"),
    ("AC-002", "Giàn nóng điều hòa", "Điều hòa", "Cái", "Valeo", "Pháp", 1800000, 2600000, "12 tháng", "City"),
    ("AC-003", "Giàn lạnh điều hòa", "Điều hòa", "Cái", "Denso", "Thái Lan", 1500000, 2200000, "12 tháng", "Accent"),
    ("AC-004", "Quạt gió dàn lạnh", "Điều hòa", "Cái", "Hyundai Mobis", "Hàn Quốc", 750000, 1100000, "12 tháng", "Tucson"),
    ("AC-005", "Ga điều hòa R134a", "Điều hòa", "Bình", "Honeywell", "Mỹ", 450000, 650000, "Không", "Tất cả"),
    ("AC-006", "Van tiết lưu", "Điều hòa", "Cái", "Denso", "Nhật Bản", 380000, 580000, "6 tháng", "CX-5"),
    # Gam - treo - lai
    ("SUS-001", "Giảm xóc trước", "Gầm xe", "Cặp", "Kayaba", "Nhật Bản", 1900000, 2700000, "12 tháng", "Vios"),
    ("SUS-002", "Giảm xóc sau", "Gầm xe", "Cặp", "Kayaba", "Nhật Bản", 1600000, 2300000, "12 tháng", "City"),
    ("SUS-003", "Rotuyn lái ngoài", "Gầm xe", "Cái", "555 (Sankei)", "Nhật Bản", 320000, 480000, "12 tháng", "Vios,Accent"),
    ("SUS-004", "Rotuyn lái trong", "Gầm xe", "Cái", "555 (Sankei)", "Nhật Bản", 350000, 520000, "12 tháng", "City,K3"),
    ("SUS-005", "Cao su chân máy", "Gầm xe", "Bộ", "Toyota Genuine", "Nhật Bản", 680000, 980000, "12 tháng", "Innova"),
    ("SUS-006", "Bạc đạn bánh trước", "Gầm xe", "Cái", "NSK", "Nhật Bản", 420000, 640000, "12 tháng", "Mazda 3"),
    ("SUS-007", "Thanh cân bằng", "Gầm xe", "Cái", "Hyundai Mobis", "Hàn Quốc", 520000, 780000, "12 tháng", "Tucson,Seltos"),
    # Dong co
    ("ENG-001", "Dây curoa cam", "Động cơ", "Sợi", "Gates", "Mỹ", 550000, 820000, "12 tháng", "Ranger"),
    ("ENG-002", "Dây curoa tổng", "Động cơ", "Sợi", "Bando", "Nhật Bản", 380000, 560000, "12 tháng", "Vios,City"),
    ("ENG-003", "Bơm nước làm mát", "Động cơ", "Cái", "GMB", "Nhật Bản", 850000, 1250000, "12 tháng", "Innova,Fortuner"),
    ("ENG-004", "Két nước", "Động cơ", "Cái", "Denso", "Thái Lan", 1900000, 2700000, "12 tháng", "City"),
    ("ENG-005", "Quạt két nước", "Động cơ", "Cái", "Hyundai Mobis", "Hàn Quốc", 950000, 1400000, "12 tháng", "Accent"),
    ("ENG-006", "Bơm xăng", "Động cơ", "Cái", "Denso", "Nhật Bản", 1500000, 2200000, "12 tháng", "Vios"),
    ("ENG-007", "Kim phun xăng (bộ 4)", "Động cơ", "Bộ", "Denso", "Nhật Bản", 2400000, 3400000, "12 tháng", "Mazda 3"),
    ("ENG-008", "Bướm ga", "Động cơ", "Cái", "Toyota Genuine", "Nhật Bản", 1800000, 2600000, "12 tháng", "Vios"),
    ("ENG-009", "Cảm biến trục khuỷu", "Động cơ", "Cái", "Bosch", "Đức", 620000, 920000, "12 tháng", "K3,Seltos"),
    ("ENG-010", "Gioăng nắp dàn cò", "Động cơ", "Cái", "Toyota Genuine", "Nhật Bản", 180000, 300000, "6 tháng", "Innova"),
    # Hop so - ly hop
    ("TRS-001", "Lá côn (bộ ly hợp)", "Hộp số", "Bộ", "Exedy", "Nhật Bản", 1900000, 2700000, "12 tháng", "Ranger số sàn"),
    ("TRS-002", "Bàn ép ly hợp", "Hộp số", "Cái", "Exedy", "Nhật Bản", 1500000, 2200000, "12 tháng", "Ranger số sàn"),
    ("TRS-003", "Bạc đạn bi Tê", "Hộp số", "Cái", "NSK", "Nhật Bản", 380000, 560000, "12 tháng", "Số sàn"),
    ("TRS-004", "Dây số", "Hộp số", "Sợi", "Hyundai Mobis", "Hàn Quốc", 420000, 620000, "6 tháng", "Accent"),
    # Lop - mam
    ("TYR-001", "Lốp 185/60R15", "Lốp - Mâm", "Cái", "Bridgestone", "Thái Lan", 1350000, 1750000, "12 tháng", "Vios,City"),
    ("TYR-002", "Lốp 205/65R16", "Lốp - Mâm", "Cái", "Michelin", "Thái Lan", 2100000, 2700000, "12 tháng", "Innova,CR-V"),
    ("TYR-003", "Lốp 265/65R17 (bán tải)", "Lốp - Mâm", "Cái", "BFGoodrich", "Mỹ", 3200000, 4200000, "12 tháng", "Ranger"),
    ("TYR-004", "Mâm đúc 15 inch", "Lốp - Mâm", "Cái", "Enkei", "Thái Lan", 1500000, 2100000, "12 tháng", "Vios"),
    ("TYR-005", "Van lốp + cân bằng động", "Lốp - Mâm", "Gói", "ThreeH", "Việt Nam", 150000, 250000, "Không", "Tất cả"),
    # Than vo - den - guong
    ("BDY-001", "Cản trước", "Thân vỏ", "Cái", "Toyota Genuine", "Việt Nam", 2200000, 3100000, "12 tháng", "Vios"),
    ("BDY-002", "Đèn pha trước", "Thân vỏ", "Cái", "Depo", "Đài Loan", 1500000, 2200000, "12 tháng", "City"),
    ("BDY-003", "Đèn hậu", "Thân vỏ", "Cặp", "Depo", "Đài Loan", 950000, 1400000, "12 tháng", "Accent"),
    ("BDY-004", "Gương chiếu hậu", "Thân vỏ", "Cái", "Honda Access", "Thái Lan", 850000, 1250000, "12 tháng", "CR-V"),
    ("BDY-005", "Kính chắn gió trước", "Thân vỏ", "Tấm", "AGC", "Việt Nam", 2500000, 3500000, "12 tháng", "K3"),
    ("BDY-006", "Gạt mưa (cặp)", "Thân vỏ", "Cặp", "Bosch", "Đức", 220000, 350000, "6 tháng", "Tất cả"),
    ("BDY-007", "Tay nắm cửa", "Thân vỏ", "Cái", "Hyundai Mobis", "Hàn Quốc", 180000, 300000, "6 tháng", "Tucson"),
    # Noi that - tien ich
    ("INT-001", "Bọc ghế da", "Nội thất", "Bộ", "ThreeH", "Việt Nam", 4500000, 6500000, "12 tháng", "Vios,City"),
    ("INT-002", "Thảm sàn 5D", "Nội thất", "Bộ", "Kata", "Việt Nam", 1200000, 1800000, "12 tháng", "Tất cả"),
    ("INT-003", "Màn hình Android 9 inch", "Nội thất", "Cái", "Zestech", "Việt Nam", 6500000, 8900000, "24 tháng", "Tất cả"),
    ("INT-004", "Camera hành trình", "Nội thất", "Cái", "Vietmap", "Việt Nam", 1800000, 2600000, "12 tháng", "Tất cả"),
    ("INT-005", "Cảm biến áp suất lốp", "Nội thất", "Bộ", "Steelmate", "Trung Quốc", 950000, 1400000, "12 tháng", "Tất cả"),
    ("INT-006", "Loa cánh cửa", "Nội thất", "Cặp", "JBL", "Mỹ", 1500000, 2200000, "12 tháng", "Tất cả"),
    # Bao duong goi
    ("SVC-001", "Gói bảo dưỡng 5.000 km", "Gói bảo dưỡng", "Gói", "ThreeH", "Việt Nam", 700000, 990000, "Không", "Tất cả"),
    ("SVC-002", "Gói bảo dưỡng 10.000 km", "Gói bảo dưỡng", "Gói", "ThreeH", "Việt Nam", 1400000, 1990000, "Không", "Tất cả"),
    ("SVC-003", "Gói vệ sinh khoang máy", "Gói bảo dưỡng", "Gói", "ThreeH", "Việt Nam", 350000, 550000, "Không", "Tất cả"),
    ("SVC-004", "Gói khử mùi diệt khuẩn", "Gói bảo dưỡng", "Gói", "ThreeH", "Việt Nam", 450000, 690000, "Không", "Tất cả"),
    # Them cho du ~110
    ("ENG-011", "Turbo tăng áp", "Động cơ", "Cái", "Garrett", "Mỹ", 8500000, 11500000, "12 tháng", "Ranger,Everest"),
    ("ENG-012", "Cổ hút gió", "Động cơ", "Cái", "Toyota Genuine", "Nhật Bản", 750000, 1100000, "6 tháng", "Fortuner"),
    ("ELE-011", "Hộp cầu chì", "Hệ thống điện", "Cái", "Hyundai Mobis", "Hàn Quốc", 420000, 620000, "6 tháng", "Seltos"),
    ("ELE-012", "Mô-bin đánh lửa", "Hệ thống điện", "Cái", "Denso", "Nhật Bản", 680000, 980000, "12 tháng", "Vios,City"),
    ("BRK-008", "Bầu trợ lực phanh", "Hệ thống phanh", "Cái", "Bosch", "Đức", 1900000, 2700000, "12 tháng", "Innova"),
    ("SUS-008", "Phuộc nhún sau (bán tải)", "Gầm xe", "Cặp", "Old Man Emu", "Úc", 6500000, 8900000, "24 tháng", "Ranger"),
    ("TYR-006", "Lốp dự phòng theo xe", "Lốp - Mâm", "Cái", "Deestone", "Thái Lan", 950000, 1350000, "12 tháng", "Tất cả"),
    ("BDY-008", "Nắp capo", "Thân vỏ", "Cái", "Toyota Genuine", "Việt Nam", 3200000, 4500000, "12 tháng", "Vios"),
    ("INT-007", "Bệ bước chân", "Nội thất", "Cặp", "ThreeH", "Việt Nam", 1800000, 2600000, "12 tháng", "Fortuner,Everest"),
    ("AC-007", "Lọc ga điều hòa", "Điều hòa", "Cái", "Denso", "Nhật Bản", 120000, 200000, "6 tháng", "Tất cả"),
    ("FIL-006", "Lọc dầu máy phát", "Dầu nhớt - vật tư tiêu hao", "Cái", "Toyota Genuine", "Nhật Bản", 110000, 180000, "6 tháng", "Toyota"),
    ("OIL-006", "Mỡ bò chịu nhiệt", "Dầu nhớt - vật tư tiêu hao", "Hộp", "Shell", "Thái Lan", 90000, 150000, "Không", "Tất cả"),
]

WAREHOUSES = ["Kho chính", "Kho chính", "Kho chính", "Kho phụ", "Kho ngoài"]
SUPPLIERS = [("Toyota Việt Nam", "NCC-TOY"), ("Honda Việt Nam", "NCC-HON"),
             ("Phụ tùng An Phát", "NCC-AP"), ("Kho tổng Miền Bắc", "NCC-MB"),
             ("Bosch Việt Nam", "NCC-BOSCH"), ("Denso Việt Nam", "NCC-DEN")]


def main():
    db = SessionLocal()
    have = {r[0] for r in db.query(SparePart.part_number).all()}
    n = 0
    for code, name, cat, unit, brand, origin, buy, sell, warranty, compat in CATALOG:
        if code in have:
            continue
        sup, sup_code = random.choice(SUPPLIERS)
        stock = random.randint(0, 120)
        db.add(SparePart(
            part_number=code, name=name, category=cat,
            part_type=random.choice(["Hàng chính hãng", "Hàng thay thế (OEM)"]),
            description=f"{name} - {brand}, xuất xứ {origin}.",
            oem_code=f"{code.replace('-', '')}-{random.randint(1000, 9999)}",
            manufacturer_code=f"MFG-{random.randint(10000, 99999)}",
            brand=brand, origin=origin,
            dimensions=f"{random.randint(5, 60)}x{random.randint(5, 40)}cm",
            unit=unit, weight=f"{round(random.uniform(0.1, 15), 1)} kg",
            shelf_life="Không giới hạn" if unit in ("Cái", "Bộ", "Cặp") else "36 tháng",
            compatible_make="; ".join(sorted(set(compat.split(",")))),
            compatible_model="Nhiều dòng", compatible_year="2015-2026",
            warehouse=random.choice(WAREHOUSES),
            shelf_location=f"{random.choice('ABCD')}-{random.randint(1, 12):02d}-{random.randint(1, 6)}",
            stock_quantity=stock, min_stock=random.choice([3, 5, 8, 10]),
            max_stock=random.randint(50, 200), status="Đang kinh doanh",
            supplier=sup, supplier_code=sup_code,
            purchase_price=buy, price=sell, vat_rate="10%",
            first_import_date=f"202{random.randint(3, 6)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            has_warranty="Có" if warranty != "Không" else "Không",
            warranty_period=warranty,
            warranty_conditions="Bảo hành lỗi nhà sản xuất, không áp dụng hao mòn tự nhiên." if warranty != "Không" else None,
            barcode=f"893{code.replace('-', '')}{random.randint(1000, 9999)}",
            qrcode=None, serial_number=None,
            created_by="admin",
        ))
        n += 1
    db.commit()
    total = db.query(SparePart).count()
    print(f"added {n}, total parts in stock: {total}")
    db.close()


if __name__ == "__main__":
    main()
