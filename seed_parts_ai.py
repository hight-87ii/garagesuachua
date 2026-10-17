import os
from app.database import SessionLocal
from app.models.models import SparePart, RepairOrderPart

db = SessionLocal()

# Delete existing parts
db.query(RepairOrderPart).delete()
db.query(SparePart).delete()
db.commit()

parts_data = [
    {
        "part_number": "04465-0D150", 
        "name": "Má phanh trước Toyota Vios", 
        "other_name": "Bộ má phanh đĩa trước Toyota Vios 2018-2022", 
        "category": "Hệ thống phanh", 
        "part_type": "Má phanh trước",
        
        # 2. Thông tin kỹ thuật
        "brand": "Toyota Genuine Parts", 
        "manufacturer_code": "Toyota Automotive", 
        "origin": "Nhật Bản",
        
        # 3. Thông tin tương thích xe
        "compatible_make": "Toyota", 
        "compatible_model": "Vios", 
        "compatible_year": "2018-2022",
        "compatible_version": "1.5G CVT",
        "compatible_engine": "1.5L / 2NR-FE",
        
        # 4. Thông tin kho
        "warehouse": "Kho A", 
        "shelf_location": "Tầng 2 - Ô 05", 
        "stock_quantity": 25, 
        "min_stock": 10, 
        "max_stock": 50,
        "unit": "Bộ",
        
        # 5. Giá và nhà cung cấp
        "purchase_price": 600000, 
        "price": 850000, 
        "supplier": "ABC Auto Parts",
        "supplier_code": "ABC-001",
        "first_import_date": "2026-06-15",
        
        # 6. Bảo hành & Lịch sử
        "has_warranty": "Có",
        "warranty_period": "3 Tháng",
        "warranty_conditions": "Lỗi kỹ thuật do nhà sản xuất",
        "warranty_notes": "Yêu cầu hóa đơn và nguyên tem lắp đặt",
        "barcode": "8935001201501",
        "serial_number": "TOY-BR-2026-001",
        "created_by": "admin",
        
        # Chu kỳ bảo dưỡng
        "shelf_life": "Chu kỳ kiểm tra: 30.000 km",
        "description": "Dịch vụ liên quan: Thay má phanh trước. Thay khi độ dày má phanh dưới 2mm."
    },
    {
        "part_number": "90915-YZZE1", 
        "name": "Lọc dầu động cơ Toyota Vios", 
        "other_name": "Lọc nhớt động cơ Toyota Vios 2018-2022 chính hãng", 
        "category": "Lọc xe", 
        "part_type": "Lọc dầu động cơ",
        
        "brand": "Toyota", 
        "manufacturer_code": "Denso", 
        "origin": "Thái Lan",
        
        "compatible_make": "Toyota", 
        "compatible_model": "Vios", 
        "compatible_year": "2018-2022",
        "compatible_version": "Tất cả các bản",
        "compatible_engine": "1.5L",
        
        "warehouse": "Kho B", 
        "shelf_location": "Tầng 1 - Ô 02", 
        "stock_quantity": 50, 
        "min_stock": 20, 
        "max_stock": 100,
        "unit": "Cái",
        
        "purchase_price": 80000, 
        "price": 120000, 
        "supplier": "ABC Auto Parts",
        "supplier_code": "ABC-001",
        "first_import_date": "2026-05-20",
        
        "has_warranty": "Có",
        "warranty_period": "30 Ngày",
        "warranty_conditions": "Thủng hoặc xì nhớt do lỗi vỏ lọc",
        "warranty_notes": "Lắp đặt tại Garage THREEH",
        "barcode": "8935001202003",
        "serial_number": "TOY-FL-2026-002",
        "created_by": "admin",
        
        "shelf_life": "Chu kỳ thay thế: 10.000 km",
        "description": "Dịch vụ liên quan: Thay dầu máy và lọc dầu. Hỗ trợ lọc sạch cặn bẩn bôi trơn động cơ."
    },
    {
        "part_number": "CAST-5W30-4L", 
        "name": "Dầu nhớt Castrol 5W30", 
        "other_name": "Dầu động cơ tổng hợp Castrol Magnatec 5W-30 4 Lít", 
        "category": "Dầu nhớt & dung dịch", 
        "part_type": "Dầu động cơ",
        
        "brand": "Castrol", 
        "manufacturer_code": "Castrol BP", 
        "origin": "Việt Nam",
        "dimensions": "Dung tích: 4L | SAE: 5W-30 | API: SP",
        
        "compatible_make": "Đa dụng", 
        "compatible_model": "Các dòng xe dùng máy xăng", 
        "compatible_year": "Tất cả",
        "compatible_version": "Tất cả",
        "compatible_engine": "Xăng",
        
        "warehouse": "Kho Hóa chất", 
        "shelf_location": "Kệ C - Tầng 1", 
        "stock_quantity": 35, 
        "min_stock": 10, 
        "max_stock": 100,
        "unit": "Can",
        
        "purchase_price": 400000, 
        "price": 550000, 
        "supplier": "NPP Castrol",
        "supplier_code": "CAS-MB",
        "first_import_date": "2026-08-10",
        
        "has_warranty": "Không",
        "warranty_period": "",
        "warranty_conditions": "",
        "warranty_notes": "Xác minh tem chống hàng giả trước khi dùng",
        "barcode": "4008177123456",
        "serial_number": "CAS-2026-003",
        "created_by": "admin",
        
        "shelf_life": "Chu kỳ thay thế: 10.000 km",
        "description": "Dịch vụ liên quan: Thay dầu máy. Công nghệ phân tử thông minh bảo vệ động cơ."
    },
    {
        "part_number": "GS-NS60LS", 
        "name": "Bình ắc quy GS 12V 45Ah", 
        "other_name": "Ắc quy nước GS NS60LS (46B24LS)", 
        "category": "Hệ thống điện ô tô", 
        "part_type": "Bình ắc quy",
        
        "brand": "GS Battery", 
        "manufacturer_code": "GS", 
        "origin": "Việt Nam",
        "dimensions": "12V | 45Ah | CCA: 330A",
        
        "compatible_make": "Honda, Toyota", 
        "compatible_model": "City, Vios", 
        "compatible_year": "Tất cả",
        "compatible_version": "Tất cả",
        "compatible_engine": "Dưới 1.5L",
        
        "warehouse": "Kho Điện", 
        "shelf_location": "Kệ E - Tầng trệt", 
        "stock_quantity": 15, 
        "min_stock": 5, 
        "max_stock": 30,
        "unit": "Bình",
        
        "purchase_price": 950000, 
        "price": 1250000, 
        "supplier": "Đại lý bình điện GS",
        "supplier_code": "GS-VN",
        "first_import_date": "2026-09-05",
        
        "has_warranty": "Có",
        "warranty_period": "12 Tháng",
        "warranty_conditions": "Phù, nứt vỏ bình hoặc không sạc được do lỗi SX",
        "warranty_notes": "Giữ lại phiếu bảo hành hoặc tra cứu S/N trên hệ thống",
        "barcode": "8934567890123",
        "serial_number": "GS-2026-004",
        "created_by": "admin",
        
        "shelf_life": "Bảo hành: 6 tháng",
        "description": "Dịch vụ liên quan: Thay bình ắc quy. Ắc quy chì axit truyền thống."
    }
]

added_count = 0
for p in parts_data:
    part = SparePart(**p)
    db.add(part)
    added_count += 1

db.commit()
print(f"Added {added_count} parts with AI standard structure.")
