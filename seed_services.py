import os
from app.database import SessionLocal
from app.models.models import ServiceCatalog

db = SessionLocal()

# Delete existing services
db.query(ServiceCatalog).delete()
db.commit()

services_data = [
    # 1. Rửa xe (Car Wash)
    {
        "service_code": "CW-001", "category": "Rửa xe (Car Wash)", "name": "Rửa xe cơ bản",
        "description": "Rửa ngoại thất, làm sạch mâm xe, lau khô, vệ sinh kính",
        "base_price": 80000, "duration_minutes": 30, "process_steps": "- Rửa ngoại thất\n- Làm sạch mâm xe\n- Lau khô\n- Vệ sinh kính",
        "image_url": "https://img.icons8.com/color/48/car-wash.png"
    },
    {
        "service_code": "CW-002", "category": "Rửa xe (Car Wash)", "name": "Rửa xe cao cấp",
        "description": "Rửa bọt tuyết, làm sạch khe cửa, vệ sinh lốp, dưỡng lốp",
        "base_price": 150000, "duration_minutes": 45, "process_steps": "- Rửa bọt tuyết\n- Làm sạch khe cửa\n- Vệ sinh lốp\n- Dưỡng lốp",
        "image_url": "https://img.icons8.com/color/48/foam.png"
    },
    {
        "service_code": "CW-003", "category": "Rửa xe (Car Wash)", "name": "Vệ sinh khoang máy",
        "description": "Làm sạch bụi bẩn, vệ sinh chi tiết động cơ, bảo dưỡng nhựa cao su",
        "base_price": 350000, "duration_minutes": 60, "process_steps": "- Làm sạch bụi bẩn\n- Vệ sinh chi tiết động cơ\n- Bảo dưỡng nhựa cao su",
        "image_url": "https://img.icons8.com/color/48/engine.png"
    },
    {
        "service_code": "CW-004", "category": "Rửa xe (Car Wash)", "name": "Vệ sinh gầm xe",
        "description": "Làm sạch bùn đất gầm xe, kiểm tra gầm",
        "base_price": 200000, "duration_minutes": 40, "process_steps": "- Làm sạch bùn đất\n- Kiểm tra gầm",
        "image_url": "https://img.icons8.com/color/48/car-chassis.png"
    },
    
    # 2. Detailing - Chăm sóc chuyên sâu
    {
        "service_code": "DT-001", "category": "Detailing", "name": "Vệ sinh nội thất toàn diện",
        "description": "Hút bụi, vệ sinh ghế, taplo, làm sạch trần xe, khử mùi",
        "base_price": 800000, "duration_minutes": 180, "process_steps": "- Hút bụi\n- Vệ sinh ghế\n- Vệ sinh taplo\n- Làm sạch trần xe\n- Khử mùi",
        "image_url": "https://img.icons8.com/color/48/car-seat.png"
    },
    {
        "service_code": "DT-002", "category": "Detailing", "name": "Dưỡng nội thất",
        "description": "Dưỡng da, dưỡng nhựa, bảo vệ bề mặt nội thất",
        "base_price": 350000, "duration_minutes": 45, "process_steps": "- Dưỡng da\n- Dưỡng nhựa\n- Bảo vệ bề mặt",
        "image_url": "https://img.icons8.com/color/48/steering-wheel.png"
    },
    {
        "service_code": "DT-003", "category": "Detailing", "name": "Đánh bóng sơn xe",
        "description": "Xóa xước nhẹ, phục hồi độ bóng, làm mới bề mặt sơn",
        "base_price": 1200000, "duration_minutes": 240, "process_steps": "- Xóa xước nhẹ\n- Phục hồi độ bóng\n- Làm mới bề mặt sơn",
        "image_url": "https://img.icons8.com/color/48/polishing-machine.png"
    },
    {
        "service_code": "DT-004", "category": "Detailing", "name": "Hiệu chỉnh sơn (Paint Correction)",
        "description": "Xử lý xước xoáy, làm bóng chuyên sâu",
        "base_price": 2500000, "duration_minutes": 360, "process_steps": "- Xử lý xước xoáy\n- Làm bóng chuyên sâu",
        "image_url": "https://img.icons8.com/color/48/paint-sprayer.png"
    },
    {
        "service_code": "DT-005", "category": "Detailing", "name": "Tẩy ố kính",
        "description": "Xử lý kính mờ, loại bỏ cặn nước",
        "base_price": 300000, "duration_minutes": 60, "process_steps": "- Xử lý kính mờ\n- Loại bỏ cặn nước",
        "image_url": "https://img.icons8.com/color/48/window-cleaning.png"
    },
    
    # 3. Dán bảo vệ xe
    {
        "service_code": "PPF-001", "category": "Dán bảo vệ xe", "name": "Phim cách nhiệt kính",
        "description": "Kính lái, kính cửa, kính hậu. Giảm nóng, chống tia UV, tăng riêng tư",
        "base_price": 3500000, "duration_minutes": 240, "process_steps": "- Kính lái\n- Kính cửa\n- Kính hậu",
        "image_url": "https://img.icons8.com/color/48/tinted-window.png"
    },
    {
        "service_code": "PPF-002", "category": "Dán bảo vệ xe", "name": "Dán PPF bảo vệ sơn",
        "description": "Cản trước, tay nắm cửa, gương, full xe",
        "base_price": 15000000, "duration_minutes": 720, "process_steps": "- Cản trước\n- Tay nắm cửa\n- Gương\n- Full xe",
        "image_url": "https://img.icons8.com/color/48/shield.png"
    },
    
    # 4. Phủ bảo vệ bề mặt
    {
        "service_code": "CT-001", "category": "Phủ bảo vệ bề mặt", "name": "Phủ ceramic",
        "description": "Tăng độ bóng, chống bám nước, bảo vệ sơn",
        "base_price": 5000000, "duration_minutes": 480, "process_steps": "- Tăng độ bóng\n- Chống bám nước\n- Bảo vệ sơn",
        "image_url": "https://img.icons8.com/color/48/sparkling.png"
    },
    {
        "service_code": "CT-002", "category": "Phủ bảo vệ bề mặt", "name": "Phủ nano kính",
        "description": "Tạo hiệu ứng lá sen, tăng tầm nhìn khi mưa",
        "base_price": 450000, "duration_minutes": 45, "process_steps": "- Tạo hiệu ứng lá sen\n- Tăng tầm nhìn khi mưa",
        "image_url": "https://img.icons8.com/color/48/drop-of-blood.png"
    },
    {
        "service_code": "CT-003", "category": "Phủ bảo vệ bề mặt", "name": "Phủ gầm chống ồn/chống rỉ",
        "description": "Bảo vệ gầm, hạn chế ăn mòn, giảm ồn",
        "base_price": 2500000, "duration_minutes": 180, "process_steps": "- Bảo vệ gầm\n- Hạn chế ăn mòn",
        "image_url": "https://img.icons8.com/color/48/sound.png"
    },
    
    # 5. Độ xe & nâng cấp
    {
        "service_code": "MOD-001", "category": "Độ xe & nâng cấp", "name": "Độ ngoại thất",
        "description": "Body kit, Lip cản, Mâm xe, Đèn xe",
        "base_price": 10000000, "duration_minutes": 600, "process_steps": "- Lắp ráp Body kit\n- Lắp Lip cản\n- Thay mâm xe\n- Độ đèn xe",
        "image_url": "https://img.icons8.com/color/48/car-roof-box.png"
    },
    {
        "service_code": "MOD-002", "category": "Độ xe & nâng cấp", "name": "Độ nội thất",
        "description": "Bọc ghế da, đèn nội thất, màn hình Android, Camera 360",
        "base_price": 8000000, "duration_minutes": 480, "process_steps": "- Bọc ghế da\n- Đèn nội thất\n- Màn hình Android\n- Camera 360",
        "image_url": "https://img.icons8.com/color/48/monitor.png"
    },
    {
        "service_code": "MOD-003", "category": "Độ xe & nâng cấp", "name": "Nâng cấp tiện nghi",
        "description": "Cảm biến áp suất lốp, Camera hành trình, Cảm biến lùi",
        "base_price": 2000000, "duration_minutes": 120, "process_steps": "- Lắp cảm biến áp suất lốp\n- Lắp camera hành trình\n- Lắp cảm biến lùi",
        "image_url": "https://img.icons8.com/color/48/action-camera.png"
    },
    
    # 6. Dịch vụ nhanh
    {
        "service_code": "QS-001", "category": "Dịch vụ nhanh", "name": "Rửa xe nhanh",
        "description": "Rửa nhanh tiết kiệm thời gian",
        "base_price": 50000, "duration_minutes": 15, "process_steps": "- Xịt rửa nhanh",
        "image_url": "https://img.icons8.com/color/48/speed.png"
    },
    {
        "service_code": "QS-002", "category": "Dịch vụ nhanh", "name": "Khử mùi xe",
        "description": "Xông hơi khử mùi sinh học",
        "base_price": 150000, "duration_minutes": 30, "process_steps": "- Khử mùi bằng dung dịch sinh học",
        "image_url": "https://img.icons8.com/color/48/air-purifier.png"
    },
    {
        "service_code": "QS-003", "category": "Dịch vụ nhanh", "name": "Đánh bóng đèn pha",
        "description": "Phục hồi độ sáng trong của đèn pha",
        "base_price": 250000, "duration_minutes": 45, "process_steps": "- Chà nhám, đánh bóng đèn",
        "image_url": "https://img.icons8.com/color/48/headlight.png"
    },
    {
        "service_code": "QS-004", "category": "Dịch vụ nhanh", "name": "Vá lốp",
        "description": "Vá trong, vá rút lốp không săm",
        "base_price": 50000, "duration_minutes": 15, "process_steps": "- Tháo lốp\n- Vá ép nhiệt",
        "image_url": "https://img.icons8.com/color/48/tire.png"
    },
    {
        "service_code": "QS-005", "category": "Dịch vụ nhanh", "name": "Bơm nitơ",
        "description": "Bơm khí nitơ giúp ổn định áp suất lốp",
        "base_price": 100000, "duration_minutes": 10, "process_steps": "- Xả khí cũ\n- Bơm Nitơ tinh khiết",
        "image_url": "https://img.icons8.com/color/48/gas-industry.png"
    },
    {
        "service_code": "QS-006", "category": "Dịch vụ nhanh", "name": "Kiểm tra xe miễn phí",
        "description": "Kiểm tra 24 hạng mục an toàn cơ bản",
        "base_price": 0, "duration_minutes": 20, "process_steps": "- Kiểm tra đèn, còi, lốp, phanh\n- Kiểm tra ắc quy, dung dịch",
        "image_url": "https://img.icons8.com/color/48/ok.png"
    }
]

added = 0
for s in services_data:
    svc = ServiceCatalog(**s)
    db.add(svc)
    added += 1

db.commit()
print(f"Added {added} services.")
