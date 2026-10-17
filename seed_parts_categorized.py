import os
from app.database import SessionLocal
from app.models.models import SparePart, RepairOrderPart

db = SessionLocal()

# Delete existing parts
db.query(RepairOrderPart).delete()
db.query(SparePart).delete()
db.commit()

parts_data = [
    # 1. Dầu nhớt & dung dịch
    {
        "part_number": "LUB-001", "name": "Dầu nhớt Castrol 5W30", "category": "Dầu nhớt & dung dịch", "brand": "Castrol", 
        "stock_quantity": 25, "min_stock": 10, "price": 450000, "purchase_price": 300000, "unit": "Chai"
    },
    {
        "part_number": "LUB-002", "name": "Nước làm mát Prestone đỏ", "category": "Dầu nhớt & dung dịch", "brand": "Prestone", 
        "stock_quantity": 40, "min_stock": 15, "price": 250000, "purchase_price": 180000, "unit": "Chai"
    },
    {
        "part_number": "LUB-003", "name": "Dầu hộp số tự động ATF", "category": "Dầu nhớt & dung dịch", "brand": "Aisin", 
        "stock_quantity": 18, "min_stock": 10, "price": 800000, "purchase_price": 500000, "unit": "Can"
    },
    
    # 2. Lọc xe (Filters)
    {
        "part_number": "FIL-001", "name": "Lọc dầu Toyota Vios 2020", "category": "Lọc xe", "brand": "Toyota", 
        "stock_quantity": 50, "min_stock": 20, "price": 150000, "purchase_price": 90000, "unit": "Cái", "compatible_model": "Toyota Vios 2020", "shelf_life": "Thay sau 10.000 km"
    },
    {
        "part_number": "FIL-002", "name": "Lọc gió động cơ Honda CR-V", "category": "Lọc xe", "brand": "Honda", 
        "stock_quantity": 30, "min_stock": 10, "price": 280000, "purchase_price": 180000, "unit": "Cái", "compatible_model": "Honda CR-V", "shelf_life": "Thay sau 20.000 km"
    },
    
    # 3. Hệ thống động cơ (Engine Parts)
    {
        "part_number": "ENG-001", "name": "Bugi NGK Laser Iridium", "category": "Hệ thống động cơ", "brand": "NGK", 
        "stock_quantity": 80, "min_stock": 40, "price": 250000, "purchase_price": 160000, "unit": "Cái"
    },
    {
        "part_number": "ENG-002", "name": "Dây curoa tổng Bando", "category": "Hệ thống động cơ", "brand": "Bando", 
        "stock_quantity": 15, "min_stock": 5, "price": 550000, "purchase_price": 380000, "unit": "Sợi"
    },
    {
        "part_number": "ENG-003", "name": "Bơm xăng Denso", "category": "Hệ thống động cơ", "brand": "Denso", 
        "stock_quantity": 5, "min_stock": 2, "price": 1800000, "purchase_price": 1200000, "unit": "Cái"
    },

    # 4. Hệ thống điện ô tô (Electrical)
    {
        "part_number": "ELE-001", "name": "Bình ắc quy GS 12V 45Ah", "category": "Hệ thống điện ô tô", "brand": "GS", 
        "stock_quantity": 12, "min_stock": 5, "price": 1150000, "purchase_price": 900000, "unit": "Bình"
    },
    {
        "part_number": "ELE-002", "name": "Bóng đèn pha LED Philips H4", "category": "Hệ thống điện ô tô", "brand": "Philips", 
        "stock_quantity": 20, "min_stock": 8, "price": 1400000, "purchase_price": 1000000, "unit": "Bộ"
    },
    
    # 5. Hệ thống phanh (Brake System)
    {
        "part_number": "BRK-001", "name": "Má phanh trước Ford Ranger", "category": "Hệ thống phanh", "brand": "Ford", 
        "stock_quantity": 25, "min_stock": 10, "price": 950000, "purchase_price": 600000, "unit": "Bộ"
    },
    {
        "part_number": "BRK-002", "name": "Dầu phanh DOT 4 Bosch", "category": "Hệ thống phanh", "brand": "Bosch", 
        "stock_quantity": 30, "min_stock": 10, "price": 220000, "purchase_price": 140000, "unit": "Chai"
    },

    # 6. Hệ thống gầm - treo - lái
    {
        "part_number": "SUS-001", "name": "Phuộc giảm xóc trước KYB", "category": "Hệ thống gầm - treo - lái", "brand": "KYB", 
        "stock_quantity": 8, "min_stock": 4, "price": 1500000, "purchase_price": 1100000, "unit": "Cái"
    },
    {
        "part_number": "SUS-002", "name": "Rotuyn lái ngoài 555 Nhật", "category": "Hệ thống gầm - treo - lái", "brand": "555", 
        "stock_quantity": 14, "min_stock": 6, "price": 450000, "purchase_price": 300000, "unit": "Cái"
    },

    # 7. Lốp & bánh xe
    {
        "part_number": "TIR-001", "name": "Lốp Michelin 225/55R17", "category": "Lốp & bánh xe", "brand": "Michelin", 
        "stock_quantity": 16, "min_stock": 8, "price": 2800000, "purchase_price": 2300000, "unit": "Quả"
    },
    {
        "part_number": "TIR-002", "name": "Cảm biến áp suất lốp Steelmate", "category": "Lốp & bánh xe", "brand": "Steelmate", 
        "stock_quantity": 10, "min_stock": 5, "price": 1600000, "purchase_price": 1100000, "unit": "Bộ"
    },

    # 8. Điều hòa ô tô
    {
        "part_number": "AC-001", "name": "Lốc điều hòa Denso Innova", "category": "Điều hòa ô tô", "brand": "Denso", 
        "stock_quantity": 3, "min_stock": 2, "price": 4800000, "purchase_price": 3500000, "unit": "Cái"
    },
    {
        "part_number": "AC-002", "name": "Gas lạnh R134a Dupont", "category": "Điều hòa ô tô", "brand": "Dupont", 
        "stock_quantity": 20, "min_stock": 5, "price": 350000, "purchase_price": 200000, "unit": "Bình"
    },

    # 9. Hệ thống hộp số
    {
        "part_number": "GBX-001", "name": "Lá côn Hyundai Accent", "category": "Hệ thống hộp số", "brand": "Valeo", 
        "stock_quantity": 6, "min_stock": 2, "price": 1200000, "purchase_price": 850000, "unit": "Cái"
    },

    # 10. Phụ kiện nội thất
    {
        "part_number": "INT-001", "name": "Camera hành trình Vietmap M1", "category": "Phụ kiện nội thất", "brand": "Vietmap", 
        "stock_quantity": 15, "min_stock": 5, "price": 4500000, "purchase_price": 3200000, "unit": "Bộ"
    },
    {
        "part_number": "INT-002", "name": "Màn hình Android Zestech Z800", "category": "Phụ kiện nội thất", "brand": "Zestech", 
        "stock_quantity": 8, "min_stock": 3, "price": 8500000, "purchase_price": 6000000, "unit": "Bộ"
    },

    # 11. Ngoại thất & chăm sóc xe
    {
        "part_number": "EXT-001", "name": "Gạt mưa Bosch AeroTwin 20 inch", "category": "Ngoại thất & chăm sóc xe", "brand": "Bosch", 
        "stock_quantity": 45, "min_stock": 15, "price": 280000, "purchase_price": 180000, "unit": "Cặp"
    },
    {
        "part_number": "EXT-002", "name": "Dung dịch Ceramic 9H", "category": "Ngoại thất & chăm sóc xe", "brand": "3M", 
        "stock_quantity": 10, "min_stock": 5, "price": 1500000, "purchase_price": 950000, "unit": "Chai"
    },

    # 12. Phụ tùng thân vỏ
    {
        "part_number": "BOD-001", "name": "Cản trước Mazda 3 2022", "category": "Phụ tùng thân vỏ", "brand": "Mazda", 
        "stock_quantity": 2, "min_stock": 1, "price": 3500000, "purchase_price": 2400000, "unit": "Cái"
    },
    {
        "part_number": "BOD-002", "name": "Gương chiếu hậu phải Kia Cerato", "category": "Phụ tùng thân vỏ", "brand": "Kia", 
        "stock_quantity": 4, "min_stock": 2, "price": 1800000, "purchase_price": 1200000, "unit": "Cụm"
    }
]

added_count = 0
for p in parts_data:
    part = SparePart(**p)
    db.add(part)
    added_count += 1

db.commit()
print(f"Added {added_count} parts across 12 categories.")
