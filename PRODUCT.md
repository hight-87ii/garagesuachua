# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Ba vai trò bình đẳng, không ưu tiên riêng (đã xác nhận):

- **Khách hàng (customer):** đặt lịch, theo dõi tình trạng xe đang sửa, xem lịch sử sửa chữa và hóa đơn chưa thanh toán, chat AI về xe của mình.
- **Kỹ thuật viên (technician):** tiếp nhận xe, chẩn đoán lỗi, cập nhật phiếu sửa chữa, tra cứu lịch sử xe và phụ tùng, xử lý lịch hẹn được gán.
- **Quản lý / Admin (manager, admin):** vận hành xưởng (tiếp nhận, tiến độ, báo giá chờ duyệt), quản lý kho phụ tùng, doanh thu và hiệu suất kỹ thuật viên, xử lý lịch hẹn chờ.

## Product Purpose

Hệ thống quản lý garage sửa chữa ô tô ThreeH Workshop gồm 5 phân hệ lõi: Khách hàng/Xe, Đặt lịch/Tiếp nhận, Sửa chữa/Kho, Thanh toán/Hóa đơn và Trợ lý AI.

Mục đích: số hóa toàn bộ vòng đời xe trong xưởng — từ đặt lịch, tiếp nhận, sửa chữa, đến thanh toán — đồng thời số hóa hồ sơ sức khỏe xe (Vehicle Health Record) gồm dữ liệu được xác thực tại xưởng và dữ liệu tham khảo do khách báo.

Thành công nghĩa là cả 3 vai đều làm được việc hàng ngày trên cùng một hệ thống: khách đặt và dõi theo xe, kỹ thuật viên sửa đúng bệnh đúng lịch, quản lý thấy được xưởng và doanh thu.

## Positioning

Điểm khác biệt phải giữ (đã xác nhận): tư vấn dịch vụ bằng ngôn ngữ tự nhiên và chẩn đoán lỗi xe bằng GenAI (Gemini) kết hợp RAG trên kho tri thức nội bộ (ChromaDB + sentence-transformers), gắn với lịch sử xe cụ thể — tóm tắt lịch sử sửa chữa, phân tích triệu chứng theo xe, hỗ trợ sinh báo giá — thay vì một phần mềm quản lý garage thuần CRUD.

## Operating Context

- Môi trường xưởng sửa chữa ô tô, dùng trên trình duyệt desktop tại quầy/laptop xưởng và trình duyệt của khách.
- Luồng chính: Khách hàng/Xe → Lịch hẹn → Phiếu sửa chữa (Pending → In Progress → Completed, kèm tiếp nhận/bàn giao, duyệt báo giá) → Hóa đơn (Unpaid/Paid) → Phụ tùng xuất theo phiếu.
- Chạy local: `uvicorn main:app --reload` sau `pip install -r requirements.txt` và cấu hình `.env` từ `.env.example` (API key Gemini).
- Dữ liệu quan hệ trong SQLite (`garage.db`); tri thức kỹ thuật trong Vector DB (ChromaDB) phục vụ RAG qua `search_knowledge_base`.
- Giao diện tiếng Việt, server-render bằng Jinja2 tại `app/templates`, tài nguyên tĩnh tại `app/static`.

## Capabilities and Constraints

Confirmed:

- Quản lý người dùng/xe, lịch hẹn (kèm kỹ thuật viên ưu tiên), phiếu sửa chữa, hóa đơn, kho phụ tùng, khuyến mãi, trợ lý AI (`/ai-assistant`, `/api/chatbot` stream, `/api/ai/diagnose`).
- Phân quyền theo vai trong dashboard `/`: khách chỉ thấy xe mình, kỹ thuật viên chỉ thấy việc mình, quản lý thấy toàn xưởng.
- Ràng buộc đã xác nhận: giữ stack FastAPI + Jinja2 + SQLite/ChromaDB hiện tại, giữ giao diện tiếng Việt.
- Thuật ngữ: RepairOrder status (Pending/In Progress/Completed), Invoice status (Unpaid/Paid), Appointment status (Pending/Confirmed), Vehicle Health Record.

Undecided: có chuyển RDBMS sang PostgreSQL/MySQL và frontend sang React/Vue cho một số phân hệ như README nêu hay không — hiện tại vẫn là Jinja2 + SQLite.

## Brand Commitments

- Tên: ThreeH Workshop ("ThreeH Workshop - Trang chủ").
- Giọng tiếng Việt, xưng hô thân thiện trong AI assistant.
- Ràng buộc hiển thị hiện có: Bootstrap + Bootstrap Icons trong output AI diagnose, layout Jinja2 hiện tại. Không có logo/slogan ràng buộc nào khác được xác nhận.

## Evidence on Hand

- Đặc tả: `docs/SRS.md`, `docs/DEVELOPMENT_ROADMAP.md`, `docs/TOM_TAT_NHOM11.md`.
- Code chạy được: `main.py`, `app/routers/`, `app/templates/`, `app/static/`.
- Dữ liệu thật: `garage.db`, `data/`, script seed (`seed_*.py`, `data_generator.py`), tài khoản mẫu (`accounts_*.md`, `export_accounts.py`), ingest tri thức (`ingest_knowledge.py`).
- Absences không được bịa: chưa có testimonial, case study, số liệu benchmark, giá/licensing công bố nào — công việc sau không được tự chế các nội dung này.

## Product Principles

1. Một xe — một hồ sơ xuyên suốt: mọi chẩn đoán, báo giá và hóa đơn đều gắn với lịch sử xe cụ thể.
2. AI phục vụ việc xưởng, không thay việc xưởng: đề xuất phải đối chiếu được với lịch sử và tài liệu nội bộ.
3. Ba vai cùng một sự thật: phân quyền hiển thị khác nhau nhưng dữ liệu gốc thống nhất.
4. Vận hành được ngay local: giữ cài đặt đơn giản, không bắt buộc hạ tầng ngoài ngoài API key AI.
