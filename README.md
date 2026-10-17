# Hệ thống Quản lý Garage Sửa chữa Ô tô có tích hợp AI

Hệ thống quản lý khách hàng, xe, lịch hẹn, phiếu sửa chữa, hóa đơn và phụ tùng, kết hợp ứng dụng AI (LLM & Vector DB) để hỗ trợ chẩn đoán lỗi xe, tóm tắt lịch sử sửa chữa và tự động sinh báo giá.

## 1. Mục tiêu dự án
- Xây dựng hệ thống quản lý garage gồm 5 phân hệ lõi: Khách hàng/Xe, Đặt lịch/Tiếp nhận, Sửa chữa/Kho, Thanh toán/Hóa đơn và Trợ lý AI.
- Sử dụng mô hình tạo sinh (GenAI) thông qua RAG để tư vấn dịch vụ bằng ngôn ngữ tự nhiên.
- Số hóa hồ sơ sức khỏe xe (Vehicle Health Record) với dữ liệu được xác thực và dữ liệu tham khảo do khách báo.

## 2. Kiến trúc và Công nghệ
- **Backend:** FastAPI (Python)
- **Frontend:** HTML/Jinja2 Templates (hoặc React/Vue tùy phân hệ)
- **Cơ sở dữ liệu:** 
  - RDBMS: SQLite (hoặc PostgreSQL/MySQL) cho dữ liệu quan hệ.
  - Vector DB: ChromaDB (hoặc pgvector) cho kho dữ liệu kỹ thuật và cẩm nang sửa chữa.
- **AI Engine:** OpenAI / Gemini kết hợp LangChain/LlamaIndex.

## 3. Cài đặt và Chạy thử (Dự kiến)
Tạo môi trường và cài đặt các thư viện yêu cầu:
```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install -r requirements.txt
```

Sao chép file cấu hình môi trường và điền API key:
```powershell
Copy-Item .env.example .env
```

Khởi động server FastAPI:
```powershell
uvicorn main:app --reload
```

## 4. Tài liệu
- Đặc tả yêu cầu: Xem chi tiết trong `docs/SRS.md`.

