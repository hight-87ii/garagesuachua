# Bảng công việc phát triển website Garage

## Hướng dẫn sử dụng

- Trạng thái: `Chưa làm` / `Đang làm` / `Hoàn thành` / `Bị chặn`.
- Mức độ hoàn thành dự án = tổng điểm các công việc đã hoàn thành / tổng điểm tất cả công việc.
- Điểm công việc: `1` = nhỏ, `2` = vừa, `3` = lớn hoặc quan trọng.
- Cập nhật bảng sau mỗi lần hoàn thành một chức năng và ghi chú link commit/PR nếu có.

## 1. Tổng quan tiến độ

| Giai đoạn | Nội dung | Điểm | Hoàn thành | Trạng thái |
|---|---|---:|---:|---|
| P0 | Khảo sát và chuẩn hóa nền tảng | 8 | 0/4 | Chưa làm |
| P1 | Xác thực và phân quyền | 8 | 0/4 | Chưa làm |
| P2 | Khách hàng và phương tiện | 12 | 0/5 | Chưa làm |
| P3 | Đặt lịch và tiếp nhận xe | 12 | 0/5 | Chưa làm |
| P4 | Sửa chữa, phụ tùng và dịch vụ | 18 | 0/7 | Chưa làm |
| P5 | Báo giá, hóa đơn và thanh toán | 12 | 0/5 | Chưa làm |
| P6 | AI, RAG và trợ lý người dùng | 18 | 0/6 | Chưa làm |
| P7 | Dashboard, thông báo và báo cáo | 12 | 0/5 | Chưa làm |
| P8 | Kiểm thử, bảo mật và triển khai | 18 | 0/6 | Chưa làm |
| **Tổng** |  | **118** | **0/47** | **0%** |

## 2. Bảng công việc chi tiết

### P0 — Khảo sát và chuẩn hóa nền tảng

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P0-01 | Chạy được dự án từ môi trường mới theo README | Cao | 2 | Cài requirements, tạo `.env`, chạy `uvicorn main:app --reload` không lỗi | Chưa làm |
| P0-02 | Kiểm tra và chuẩn hóa migration database | Cao | 3 | Chạy migration theo thứ tự, không mất dữ liệu mẫu | Chưa làm |
| P0-03 | Chuẩn hóa cấu hình môi trường và secret | Cao | 2 | API key không nằm trong mã nguồn; `.env.example` đầy đủ | Chưa làm |
| P0-04 | Thiết lập Git, quy ước commit và backup database | Trung bình | 1 | Có repository, `.gitignore`, hướng dẫn backup/restore | Chưa làm |

### P1 — Xác thực và phân quyền

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P1-01 | Hoàn thiện đăng ký, đăng nhập, đăng xuất | Cao | 2 | Tài khoản hợp lệ đăng nhập được; mật khẩu được hash | Chưa làm |
| P1-02 | Kiểm tra quyền truy cập theo role | Cao | 3 | Customer không truy cập trang manager/technician trái phép | Chưa làm |
| P1-03 | Bổ sung xử lý session/cookie an toàn | Cao | 2 | Cookie có cấu hình an toàn, logout vô hiệu phiên | Chưa làm |
| P1-04 | Xử lý lỗi form và thông báo thân thiện | Trung bình | 1 | Sai dữ liệu có thông báo tiếng Việt, không lộ traceback | Chưa làm |

### P2 — Khách hàng và phương tiện

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P2-01 | CRUD thông tin xe của khách hàng | Cao | 3 | Thêm, sửa, xem xe; biển số không trùng | Chưa làm |
| P2-02 | Cập nhật ODO và thông tin bảo hành | Cao | 2 | ODO mới không nhỏ hơn ODO cũ nếu không có quyền đặc biệt | Chưa làm |
| P2-03 | Trang hồ sơ và lịch sử sửa chữa xe | Cao | 3 | Chỉ chủ xe xem được dữ liệu xe của mình | Chưa làm |
| P2-04 | Hiển thị khuyến mãi và dịch vụ phù hợp | Trung bình | 2 | Chỉ hiển thị promotion còn hiệu lực | Chưa làm |
| P2-05 | Responsive cho giao diện khách hàng | Trung bình | 2 | Dùng được trên điện thoại và desktop | Chưa làm |

### P3 — Đặt lịch và tiếp nhận xe

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P3-01 | Khách đặt lịch sửa chữa/rửa xe | Cao | 3 | Chọn xe, ngày, loại dịch vụ, triệu chứng; tạo lịch Pending | Chưa làm |
| P3-02 | Quản lý duyệt, xác nhận hoặc hủy lịch | Cao | 2 | Trạng thái chuyển đúng theo nghiệp vụ | Chưa làm |
| P3-03 | Phân công kỹ thuật viên | Cao | 2 | Có thể chọn kỹ thuật viên và hiển thị lịch được giao | Chưa làm |
| P3-04 | Phiếu tiếp nhận xe | Cao | 3 | Ghi ODO, nhiên liệu, trầy xước, đồ cá nhân, ảnh và chìa khóa | Chưa làm |
| P3-05 | In/lưu phiếu tiếp nhận | Trung bình | 2 | Phiếu có mã lệnh, xe, khách, thời gian và chữ ký/ghi nhận | Chưa làm |

### P4 — Sửa chữa, phụ tùng và dịch vụ

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P4-01 | Quản lý trạng thái lệnh sửa chữa | Cao | 3 | Pending → In Progress → Completed; ghi thời gian chuyển trạng thái | Chưa làm |
| P4-02 | Nhập kết quả kiểm tra và đề xuất xử lý | Cao | 2 | Lưu nguyên nhân, hạng mục và ghi chú kỹ thuật | Chưa làm |
| P4-03 | CRUD danh mục phụ tùng | Cao | 3 | Mã phụ tùng duy nhất, giá, tồn kho và thông tin tương thích | Chưa làm |
| P4-04 | Xuất phụ tùng vào lệnh sửa chữa | Cao | 3 | Trừ tồn kho, lưu số lượng và giá tại thời điểm dùng | Chưa làm |
| P4-05 | Cảnh báo tồn kho thấp | Trung bình | 2 | Cảnh báo khi `stock_quantity <= min_stock` | Chưa làm |
| P4-06 | CRUD danh mục dịch vụ | Cao | 2 | Có mã, giá, thời lượng, VAT, quy trình và trạng thái | Chưa làm |
| P4-07 | Kiểm tra giao dịch tồn kho | Cao | 3 | Không cho xuất vượt tồn; có lịch sử nhập/xuất | Chưa làm |

### P5 — Báo giá, hóa đơn và thanh toán

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P5-01 | Lập báo giá từ dịch vụ và phụ tùng | Cao | 3 | Tính đúng subtotal, giảm giá, VAT, tổng tiền | Chưa làm |
| P5-02 | Khách duyệt/từ chối báo giá | Cao | 2 | Lưu trạng thái và thời điểm phản hồi | Chưa làm |
| P5-03 | Tạo và in hóa đơn | Cao | 2 | Hóa đơn liên kết đúng lệnh sửa và có mã duy nhất | Chưa làm |
| P5-04 | Ghi nhận thanh toán | Cao | 2 | Cập nhật Paid/Unpaid, phương thức và thời gian thanh toán | Chưa làm |
| P5-05 | Hiển thị lịch sử hóa đơn cho khách | Trung bình | 1 | Khách chỉ xem được hóa đơn của xe/lệnh của mình | Chưa làm |

### P6 — AI, RAG và trợ lý người dùng

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P6-01 | Hoàn thiện chatbot khách hàng có context xe | Cao | 3 | AI nhận biết khách, xe và lịch sử sửa chữa; phản hồi streaming | Chưa làm |
| P6-02 | Hoàn thiện chẩn đoán triệu chứng có RAG | Cao | 3 | Kết quả có nguyên nhân, đề xuất và cảnh báo cần đưa xe đến garage | Chưa làm |
| P6-03 | Ingest tài liệu nội bộ vào ChromaDB | Cao | 3 | Upload tài liệu, ingest thành công, tìm được nguồn trích dẫn | Chưa làm |
| P6-04 | Kết nối technical/customer agent với Gemini thật | Cao | 3 | Không còn mock response; có kiểm soát role và lỗi API | Xong (08/10/2026: gọi get_gemini_response thật, RBAC + 401/403, lỗi API trả 503) |
| P6-05 | AI đề xuất dịch vụ/phụ tùng và báo giá sơ bộ | Trung bình | 3 | Chỉ đề xuất dữ liệu đang Active; giá phải lấy từ database | Xong (08/10/2026: tools suggest_services/suggest_parts + estimate min-max từ giá DB) |
| P6-06 | Thêm giới hạn và cảnh báo an toàn AI | Cao | 3 | AI không khẳng định chẩn đoán chắc chắn; không tự quyết định thay kỹ thuật viên | Xong (08/10/2026: guardrails trong prompt + disclaimer gắn cứng mọi câu trả lời) |

### P7 — Dashboard, thông báo và báo cáo

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P7-01 | Hoàn thiện dashboard KPI quản lý | Cao | 3 | KPI theo ngày/tuần/tháng và số liệu khớp database | Chưa làm |
| P7-02 | Dashboard công việc kỹ thuật viên | Cao | 2 | Hiển thị lệnh được giao, lịch hẹn, trạng thái và deadline | Chưa làm |
| P7-03 | Thông báo lịch hẹn, báo giá, hoàn thành sửa chữa | Trung bình | 3 | Có thông báo trong hệ thống; không gửi trùng | Chưa làm |
| P7-04 | Nhắc bảo dưỡng theo ODO/thời gian | Trung bình | 2 | Tạo nhắc nhở đúng điều kiện và cho phép tắt/bật | Chưa làm |
| P7-05 | Báo cáo doanh thu, phụ tùng và lỗi phổ biến | Trung bình | 2 | Có bộ lọc thời gian và xuất CSV/PDF nếu cần | Chưa làm |

### P8 — Kiểm thử, bảo mật và triển khai

| ID | Công việc | Ưu tiên | Điểm | Tiêu chí nghiệm thu | Trạng thái |
|---|---|---|---:|---|---|
| P8-01 | Viết test cho model, service và API quan trọng | Cao | 3 | Có test auth, role, đặt lịch, kho, hóa đơn, AI fallback | Chưa làm |
| P8-02 | Kiểm thử luồng nghiệp vụ end-to-end | Cao | 3 | Hoàn thành luồng đặt lịch → sửa → báo giá → thanh toán | Chưa làm |
| P8-03 | Kiểm tra bảo mật đầu vào và phân quyền | Cao | 3 | Chống truy cập IDOR, input độc hại, upload không an toàn | Chưa làm |
| P8-04 | Tối ưu truy vấn và xử lý lỗi | Trung bình | 2 | Không query thừa nghiêm trọng; lỗi có log và response phù hợp | Chưa làm |
| P8-05 | Sao lưu, khôi phục và quản lý dữ liệu production | Cao | 3 | Có quy trình backup định kỳ và thử restore thành công | Chưa làm |
| P8-06 | Đóng gói và triển khai production | Cao | 3 | Có hướng dẫn deploy, health check, log và cấu hình HTTPS | Chưa làm |

## 3. Mốc nghiệm thu đề xuất

| Mốc | Điều kiện đạt | Kết quả |
|---|---|---|
| M1 — Bản chạy được | P0 hoàn thành | Cài mới và khởi động được hệ thống |
| M2 — MVP nghiệp vụ | P1–P3 hoàn thành | Đăng nhập, quản lý xe, đặt lịch, tiếp nhận xe |
| M3 — Vận hành garage | P4–P5 hoàn thành | Quản lý sửa chữa, kho, báo giá, hóa đơn |
| M4 — AI beta | P6 hoàn thành | Chatbot, chẩn đoán, RAG hoạt động có fallback |
| M5 — Bản trình diễn | P7 hoàn thành | Dashboard và thông báo đầy đủ |
| M6 — Bản phát hành | P8 hoàn thành | Đã test, bảo mật, backup và deploy |

## 4. Cách cập nhật tiến độ

Mỗi tuần cập nhật:

1. Đổi trạng thái trong bảng chi tiết.
2. Cập nhật cột `Hoàn thành` ở bảng tổng quan.
3. Tính phần trăm: `điểm công việc Hoàn thành / 118 × 100`.
4. Ghi lại công việc bị chặn và lý do.
5. Chạy test trước khi chuyển sang `Hoàn thành`.
