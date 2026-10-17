# HỆ THỐNG QUẢN LÝ GARAGE Ô TÔ TÍCH HỢP AI — NHÓM 11 (Tóm tắt)

> Bản rút gọn từ file Word SRS Nhóm 11, đối chiếu với code hiện tại. Chi tiết đầy đủ xem `docs/SRS.md`.

## 1. GIỚI THIỆU CHUNG

### 1.1 Mục đích
- Chuẩn hóa luồng xưởng: đặt lịch → tiếp nhận → báo giá → sửa chữa → hóa đơn.
- Đặc tả AI: chatbot chẩn đoán cho khách + trợ lý RAG tra cứu kỹ thuật cho thợ.
- Làm căn cứ nghiệm thu, viết test case.

### 1.2 Phạm vi
- Web app: `FastAPI + Jinja2 + SQLite (SQLAlchemy)` (`main.py:23`, `app/database.py:4-9`). Không dùng React như SRS đề xuất.
- 3 actor: Quản lý, Nhân viên (cố vấn/thợ), Khách hàng.
- 5 phân hệ: Khách hàng & Xe; Đặt lịch & Tiếp nhận; Sửa chữa & Kho; Thanh toán & Báo cáo; AI.

### 1.3 Thuật ngữ
| Từ | Nghĩa |
|---|---|
| RO / Work Order | Lệnh sửa chữa (`repair_orders`) |
| VHR | Hồ sơ sức khỏe xe (timeline ODO + lịch sử) |
| RAG | Truy xuất cẩm nang từ Vector DB rồi mới sinh câu trả lời |
| ODO | Số km đồng hồ |
| RBAC | Phân quyền theo vai trò |

### 1.4 Tài liệu tham khảo
1. Slide AI tạo sinh trong phát triển phần mềm (2026).
2. Docs LangChain/LlamaIndex (RAG).
3. Docs API OpenAI/Gemini; Docs PostgreSQL/pgvector.

## 2. MÔ TẢ TỔNG QUAN

### 2.1 Use case tổng quát
- Khách: quản lý xe, hỏi AI, đặt lịch, theo dõi tiến độ.
- Nhân viên: tiếp nhận, lập RO, cập nhật tiến độ, xuất kho, hóa đơn, tra cứu RAG.
- Quản lý: giá/kho, nhân sự, doanh thu.
- Tất cả qua Đăng nhập (JWT + RBAC).

### 2.2 Actors
| Actor | Quyền | Ghi chú |
|---|---|---|
| Quản lý | Full access, xem báo cáo | `role=manager/admin` |
| Nhân viên | Tiếp nhận, RO, kho, hóa đơn | Dữ liệu ghi = `Verified` |
| Khách hàng | Xe của mình, đặt lịch, hỏi AI | Tự khai ngoại viện = `Unverified` |

### 2.3 Danh sách UC
| ID | Tên | Mapping code |
|---|---|---|
| UC001 | Đăng nhập, tài khoản | `app/routers/auth.py`, `/login`, `/register`, `/profile` |
| UC002 | Khách hàng + xe | `app/routers/customer.py`, `Vehicle` |
| UC003 | Đặt lịch | `POST /my-appointments/book`, `Appointment` |
| UC004 | Tiếp nhận + lập RO | `POST /tech/reception`, `reception_ticket.html` |
| UC005 | AI chẩn đoán, nhắc bảo dưỡng | `ai_service.py`, `gemini_service.py`, `rag_service.py` |
| UC006 | Tiến độ sửa chữa | `POST /tech/update-status`, `tech_dashboard.html` |
| UC007 | Dịch vụ + phụ tùng | `/tech/parts`, `/tech/services`, `SparePart` |
| UC008 | Báo giá + hóa đơn | `POST /tech/quote`, `/tech/order/generate-invoice`, `Invoice` |
| UC009 | Hồ sơ xe VHR | `GET /my-repairs/{id}`, ODO timeline |
| UC010 | Nhân sự + thống kê | `/manager/overview`, `/manager/users` |

### 2.4 Điều kiện phụ thuộc
- Backend Python; Frontend SSR Jinja2 (hiện tại) thay vì React.
- RDBMS: SQLite dev (`garage.db`), đích PostgreSQL/MySQL.
- Vector DB: ChromaDB (`data/chroma_db/`, hiện chưa ingest nên RAG trả rỗng).
- LLM: Gemini (`GEMINI_API_KEY`); thay Zalo ZNS bằng thông báo nội bộ.
- Cần mạng cho AI; mất mạng chỉ dùng CRUD.

## 3. ĐẶC TẢ CHỨC NĂNG (rút gọn)

### UC001 — Đăng nhập, tài khoản
- Actor: all. Vào `/login`, check `bcrypt`, cấp JWT cookie 24h, điều hướng theo role.
- Phụ: sai pass báo lỗi nhập lại; đổi pass/cập nhật profile.

### UC002 — Khách hàng + xe
- Nhân viên thêm/sửa khách, xe (`license_plate unique`, VIN, hãng, đời).
- Validate trùng biển số; làm nền cho RO.

### UC003 — Đặt lịch
- Khách chọn xe, dịch vụ, khung `08:00–16:30` → tạo `Appointment(Pending)` + `RO(Pending)`.
- Nhân viên duyệt; kín giờ thì đổi giờ.

### UC004 — Tiếp nhận + lập RO
- Nhập ODO, nhiên liệu, trầy xước, triệu chứng → `POST /tech/reception`.
- Hiện tại lưu xong về dashboard, không auto-in. ODO lan lên `Vehicle` nếu lớn hơn.

### UC005 — AI phân tích (core)
- Nhập triệu chứng → `TF-IDF+NB` local gợi ý nhóm lỗi + Gemini sinh tư vấn + RAG tra cứu cẩm nang.
- Cron dự báo bảo dưỡng theo km/tháng (hiện mock `weather_service.py`, agent mock).

### UC006 — Tiến độ sửa chữa
- Thợ bấm nhận sửa (`In Progress`, ghi KTV + `repair_started_at` + `repair_notes`) → cập nhật linh kiện → hoàn thành (`Completed` + `final_odo` + ảnh/video).
- Khách xem timeline 5 bước ở `my_repair_detail.html`.

### UC007 — Dịch vụ + phụ tùng
- CRUD `SparePart` (`part_number unique`, `stock/min_stock`), `ServiceCatalog`.
- Xuất kho trừ tồn (`stock>=qty`), snapshot `unit_price`; cảnh báo tồn thấp.

### UC008 — Báo giá + hóa đơn
- Thợ nhập `inspection_result + estimated_cost` → `POST /tech/quote` chuyển thẳng `In Progress` (hiện bỏ chờ khách duyệt).
- Tổng = công + linh kiện, VAT 10%; `Invoice(repair_order_id unique)`.

### UC009 — Hồ sơ xe VHR (core)
- Timeline tiếp nhận → báo giá → sửa → hoàn thành → bàn giao.
- Khách cập nhật ODO; ODO thụt lùi bị chặn; khai ngoại viện gắn nhãn chưa xác thực.

### UC010 — Nhân sự + thống kê
- Quản lý CRUD user, xem KPI doanh thu/tồn kho/hiệu suất, lọc day/week/month.

## 4. THÔNG TIN HỖ TRỢ KHÁC
- Giả định: khách tự giác cập nhật ODO; dữ liệu ngoại viện cách ly nhãn chưa xác thực.
- Pháp lý: tuân thủ NĐ 13/2023 (mã hóa SĐT/biển số khi production); guardrails chặn hỏi ngoài ô tô.
- KB cho AI: mã OBD-II, lịch bảo dưỡng Toyota/Hyundai/Kia/Mazda/Honda, bảng giá nội bộ (hiện chỉ `sample_guide.txt`).
- Phụ lục: A-Figma mockup, B-Prompt templates, C-ERD (`app/models/models.py`).
