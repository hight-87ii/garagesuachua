# HỆ THỐNG QUẢN LÝ GARAGE SỬA CHỮA Ô TÔ CÓ TÍCH HỢP AI - NHÓM 11
ĐẶC TẢ YÊU CẦU ỨNG DỤNG – V1.0

## 1. GIỚI THIỆU CHUNG
### 1.1 Mục đích
Tài liệu Đặc tả Yêu cầu Phần mềm (SRS) này được lập ra nhằm mục đích xác định rõ và chi tiết các yêu cầu cho dự án xây dựng Hệ thống Quản lý Garage sửa chữa Ô tô có tích hợp Trí tuệ nhân tạo. Cụ thể, tài liệu hướng tới các mục đích sau:
1. Chuẩn hóa và đặc tả luồng nghiệp vụ thực tế tại Gara: Mô tả chi tiết các yêu cầu chức năng để số hóa toàn bộ vòng đời của một chiếc xe khi vào xưởng: từ khâu khách hàng đặt lịch hẹn, Cố vấn dịch vụ tiếp nhận xe (ghi nhận tình trạng, số km, lỗi ban đầu), phân công lệnh sửa chữa cho thợ máy, cho đến khâu xuất kho phụ tùng, lập báo giá và cuối cùng là thanh toán/xuất xưởng. Quản lý chặt chẽ danh mục hàng hóa đặc thù của gara như: mã phụ tùng thay thế, vật tư tiêu hao (nhớt, nước làm mát), và các gói dịch vụ bảo dưỡng định kỳ.
2. Đặc tả các tính năng Trí tuệ nhân tạo (GenAI) giải quyết nút thắt của Gara: Tài liệu định nghĩa rõ cách AI tham gia vào quy trình sửa chữa và chăm sóc khách hàng:
   - Hỗ trợ Khách hàng: Đặc tả tính năng Chatbot AI có khả năng tiếp nhận mô tả lỗi xe bằng ngôn ngữ tự nhiên, từ đó chẩn đoán sơ bộ và gợi ý khách hàng đặt lịch.
   - Hỗ trợ Nhân viên/Thợ máy: Đặc tả Trợ lý ảo (RAG Assistant) giúp nhân viên kỹ thuật tra cứu nhanh thông số kỹ thuật xe, mã phụ tùng tương thích, biểu giá và cẩm nang sửa chữa.
3. Xác định các ràng buộc về kỹ thuật và vận hành (Yêu cầu phi chức năng): Cam kết các tiêu chuẩn về hiệu năng, bảo mật thông tin và đảm bảo tốc độ phản hồi (streaming) mượt mà của mô hình AI.
4. Làm cơ sở đồng thuận và nghiệm thu dự án.

### 1.2 Phạm vi
#### 1.2.1 Mô tả đặc điểm và bản chất ứng dụng
Hệ thống quản lý garage sửa chữa ô tô có tích hợp AI là giải pháp phần mềm dạng nền tảng Web (Web-based Application) kết hợp kiến trúc phần mềm truyền thống (CRUD/RDBMS) với công nghệ Trí tuệ Nhân tạo Tạo sinh (GenAI/LLM).

#### 1.2.2 Đối tượng phục vụ của ứng dụng (Target Users / Actors)
Hệ thống phục vụ trực tiếp 3 nhóm tác nhân chính:
- **Chủ Garage / Quản lý (Admin / Manager)**: Theo dõi và giám sát toàn bộ hoạt động vận hành của garage.
- **Nhân viên Garage (Employees)**: Đặt lịch hẹn, tiếp nhận xe vào xưởng, lập phiếu kiểm tra chẩn đoán, tạo báo giá gửi khách hàng và lập hóa đơn quyết toán. Cập nhật tiến độ sửa chữa, quản lý kho. Tra cứu kỹ thuật.
- **Khách hàng / Chủ xe (Customers)**: Tương tác trực tuyến với garage từ xa, quản lý thông tin xe, đặt lịch, theo dõi tiến độ sửa chữa. Tương tác chatbot AI.

#### 1.2.3 Các nhóm hệ thống con (Subsystems & Modules)
1. Phân hệ Quản lý Khách hàng & Phương tiện (Customer & Vehicle Subsystem)
2. Phân hệ Quản lý Đặt lịch & Tiếp nhận xe (Booking & Reception Subsystem)
3. Phân hệ Quản lý Sửa chữa & Kho Phụ tùng (Repair & Inventory Subsystem)
4. Phân hệ Thanh toán & Báo cáo Tài chính (Finance & Reporting Subsystem)
5. Phân hệ Trí tuệ Nhân tạo thông minh (AI Integration Subsystem):
   - Module Chatbot Tư vấn Chẩn đoán (cho Khách hàng)
   - Module Trợ lý Tra cứu Kỹ thuật RAG (cho Nhân viên)

## 2. MÔ TẢ TỔNG QUAN ỨNG DỤNG
### 2.1 Danh sách Use case và mô tả
- **UC001**: Đăng nhập và quản lý tài khoản
- **UC002**: Quản lý khách hàng và thông tin xe
- **UC003**: Đặt lịch sửa chữa / bảo dưỡng
- **UC004**: Tiếp nhận xe và lập phiếu sửa chữa
- **UC005**: AI phân tích và khuyến nghị chăm sóc xe (Core)
- **UC006**: Quản lý quá trình sửa chữa / bảo dưỡng
- **UC007**: Quản lý dịch vụ và phụ tùng
- **UC008**: Thanh toán và lập hóa đơn
- **UC009**: Quản lý hồ sơ và lịch sử xe (Vehicle Health Record) (Core)
- **UC010**: Quản lý nhân viên và thống kê

### 2.2 Các điều kiện phụ thuộc
1. Nền tảng và Công nghệ phát triển:
   - Backend: FastAPI/Flask/Django
   - Frontend: React/Vue/HTML template
   - Framework AI: LangChain hoặc LlamaIndex (RAG)
2. Cơ sở dữ liệu:
   - RDBMS: SQLite/MySQL/PostgreSQL
   - Vector DB: ChromaDB hoặc pgvector
3. AI Engine: OpenAI/Gemini/Claude/Hugging Face/Ollama.

## 3. ĐẶC TẢ CÁC YÊU CẦU CHỨC NĂNG (FUNCTIONAL)
*(Chi tiết các UC đã được mô tả ở trên)*
