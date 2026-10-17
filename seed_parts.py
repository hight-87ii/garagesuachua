import os
import sys

from app.database import SessionLocal
from app.models.models import SparePart

db = SessionLocal()

parts_data = [
    {"part_number": "PT-001", "name": "Lọc nhớt động cơ Toyota", "category": "Lọc", "brand": "Toyota", "stock_quantity": 15, "min_stock": 20, "price": 150000, "purchase_price": 100000},
    {"part_number": "PT-002", "name": "Dầu nhớt Castrol Magnatec", "category": "Dầu mỡ", "brand": "Castrol", "stock_quantity": 120, "min_stock": 50, "price": 450000, "purchase_price": 300000},
    {"part_number": "PT-003", "name": "Má phanh trước Honda", "category": "Phanh", "brand": "Honda", "stock_quantity": 3, "min_stock": 10, "price": 850000, "purchase_price": 500000},
    {"part_number": "PT-004", "name": "Bình ắc quy GS 12V 45Ah", "category": "Điện", "brand": "GS", "stock_quantity": 20, "min_stock": 10, "price": 1200000, "purchase_price": 900000},
    {"part_number": "PT-005", "name": "Lọc gió điều hòa", "category": "Lọc", "brand": "Denso", "stock_quantity": 30, "min_stock": 15, "price": 250000, "purchase_price": 150000},
    {"part_number": "PT-006", "name": "Gạt mưa Bosch 16 inch", "category": "Ngoại thất", "brand": "Bosch", "stock_quantity": 40, "min_stock": 20, "price": 180000, "purchase_price": 120000},
    {"part_number": "PT-007", "name": "Bugi NGK Iridium", "category": "Động cơ", "brand": "NGK", "stock_quantity": 80, "min_stock": 30, "price": 280000, "purchase_price": 200000},
    {"part_number": "PT-008", "name": "Lọc xăng Vios", "category": "Lọc", "brand": "Toyota", "stock_quantity": 10, "min_stock": 15, "price": 350000, "purchase_price": 220000},
    {"part_number": "PT-009", "name": "Má phanh sau Ford Ranger", "category": "Phanh", "brand": "Ford", "stock_quantity": 5, "min_stock": 10, "price": 1100000, "purchase_price": 700000},
    {"part_number": "PT-010", "name": "Dầu hộp số ATF", "category": "Dầu mỡ", "brand": "Motul", "stock_quantity": 45, "min_stock": 20, "price": 600000, "purchase_price": 400000},
    {"part_number": "PT-011", "name": "Nước làm mát Prestone", "category": "Dung dịch", "brand": "Prestone", "stock_quantity": 60, "min_stock": 25, "price": 300000, "purchase_price": 180000},
    {"part_number": "PT-012", "name": "Bơm xăng Denso", "category": "Động cơ", "brand": "Denso", "stock_quantity": 4, "min_stock": 5, "price": 2500000, "purchase_price": 1800000},
    {"part_number": "PT-013", "name": "Đèn pha LED Philips", "category": "Điện", "brand": "Philips", "stock_quantity": 12, "min_stock": 10, "price": 1500000, "purchase_price": 1000000},
    {"part_number": "PT-014", "name": "Cao su chân máy Mazda", "category": "Khung gầm", "brand": "Mazda", "stock_quantity": 8, "min_stock": 10, "price": 950000, "purchase_price": 600000},
    {"part_number": "PT-015", "name": "Lốc điều hòa", "category": "Điều hòa", "brand": "Denso", "stock_quantity": 2, "min_stock": 3, "price": 4500000, "purchase_price": 3200000},
    {"part_number": "PT-016", "name": "Dây curoa tổng", "category": "Động cơ", "brand": "Gates", "stock_quantity": 18, "min_stock": 10, "price": 450000, "purchase_price": 280000},
    {"part_number": "PT-017", "name": "Bi moay ơ trước", "category": "Khung gầm", "brand": "NTN", "stock_quantity": 6, "min_stock": 8, "price": 1200000, "purchase_price": 800000},
    {"part_number": "PT-018", "name": "Cảm biến oxy", "category": "Điện", "brand": "Bosch", "stock_quantity": 4, "min_stock": 5, "price": 1800000, "purchase_price": 1200000},
    {"part_number": "PT-019", "name": "Phuộc nhún sau", "category": "Khung gầm", "brand": "KYB", "stock_quantity": 10, "min_stock": 8, "price": 1600000, "purchase_price": 1100000},
    {"part_number": "PT-020", "name": "Bơm nước làm mát", "category": "Động cơ", "brand": "Aisin", "stock_quantity": 5, "min_stock": 5, "price": 1300000, "purchase_price": 850000},
    {"part_number": "PT-021", "name": "Lọc gió động cơ", "category": "Lọc", "brand": "Hengst", "stock_quantity": 25, "min_stock": 15, "price": 350000, "purchase_price": 200000},
    {"part_number": "PT-022", "name": "Rotuyn lái ngoài", "category": "Khung gầm", "brand": "555", "stock_quantity": 14, "min_stock": 10, "price": 550000, "purchase_price": 350000},
    {"part_number": "PT-023", "name": "Cao su gạt mưa", "category": "Ngoại thất", "brand": "NWB", "stock_quantity": 50, "min_stock": 30, "price": 120000, "purchase_price": 70000},
    {"part_number": "PT-024", "name": "Còi sên", "category": "Điện", "brand": "Denso", "stock_quantity": 16, "min_stock": 10, "price": 400000, "purchase_price": 250000},
    {"part_number": "PT-025", "name": "Dầu phanh DOT4", "category": "Dung dịch", "brand": "Brembo", "stock_quantity": 35, "min_stock": 20, "price": 250000, "purchase_price": 150000}
]

added_count = 0
for p in parts_data:
    existing = db.query(SparePart).filter(SparePart.part_number == p["part_number"]).first()
    if not existing:
        part = SparePart(**p)
        db.add(part)
        added_count += 1

db.commit()
print(f"Added {added_count} parts to the database.")
