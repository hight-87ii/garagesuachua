"""Dung chung cho AI agents (P6-04, P6-05, P6-06).

- Goi Gemini: dung base.call_gemini_safe (wrapper duy nhat).
- Tools DB: chi lay du lieu dang Active/kinh doanh, gia lay tu DB.
- Guardrails an toan: chan AI khang dinh chac chan, moi quyet dinh
  sua chua thuoc ve ky thuat vien + khach hang.
"""
import re
from sqlalchemy.orm import Session
from app.models.models import ServiceCatalog, SparePart

SAFETY_CUSTOMER = (
    "\n\n---\n"
    "Lưu ý: đây chỉ là gợi ý tham khảo, không thay thế kiểm tra trực tiếp tại xưởng. "
    "Giá chính xác theo báo giá của kỹ thuật viên sau khi kiểm tra xe."
)
SAFETY_TECHNICAL = (
    "\n\n---\n"
    "CẢNH BÁO CHUYÊN MÔN: đây chỉ là gợi ý chẩn đoán sơ bộ, KHÔNG phải kết luận. "
    "Kỹ thuật viên bắt buộc kiểm tra trực tiếp và tự chịu trách nhiệm về quyết định sửa chữa."
)

SAFETY_RULES_CUSTOMER = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Không khẳng định chắc chắn nguyên nhân hỏng hóc ("chắc chắn là...", "100%...").
- Mọi đề xuất dịch vụ/phụ tùng CHỈ được lấy từ danh mục garage cung cấp dưới đây, không bịa thêm.
- Giá nêu ra phải đúng giá trong danh mục, ghi rõ là giá tham khảo chưa gồm VAT/phát sinh.
- Luôn kết thúc bằng việc khuyên mang xe tới xưởng kiểm tra trực tiếp.
- Không tự ý quyết định thay khách hàng hay kỹ thuật viên.
"""

SAFETY_RULES_TECHNICAL = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Không đưa ra kết luận chẩn đoán chắc chắn; chỉ nêu các khả năng theo thứ tự xác suất kèm cách kiểm chứng.
- Đề xuất phụ tùng CHỈ từ danh mục kho thật dưới đây (còn hàng), giá đúng giá kho.
- Mọi quyết định sửa chữa/thay thế thuộc về kỹ thuật viên sau kiểm tra trực tiếp — nêu rõ điều này.
- Với lỗi liên quan an toàn (phanh, lái, túi khí), yêu cầu kiểm tra ngay, không cho xe chạy tiếp khi chưa rõ.
"""

# Prompt gon: chi inject weather/catalog khi cau hoi lien quan (keyword).
WEATHER_KEYS = ("mưa", "ngập", "nắng", "nóng", "lạnh", "ẩm", "bão")
PRICE_KEYS = ("giá", "gia", "tiền", "dịch vụ", "bao nhiêu", "báo giá")

SAFETY_RULES_MANAGER = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Chỉ trả lời dựa trên số liệu vận hành garage cung cấp dưới đây, không bịa số.
- Không nêu tên/chi tiết cá nhân khách hàng ngoài phạm vi quản lý.
- Mọi quyết định điều hành (giá, nhân sự, nhập hàng) thuộc về quản lý — AI chỉ tổng hợp, gợi ý.
- Luôn kết thúc bằng 1 hành động đề xuất cụ thể cho quản lý.
"""

SAFETY_MANAGER = (
    "\n\n---\n"
    "Lưu ý: số liệu tổng hợp tại thời điểm hỏi, quản lý đối chiếu lại trên dashboard trước khi quyết định."
)

SAFETY_RULES_SCHEDULING = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Chỉ đề xuất khung giờ trống/kỹ thuật viên từ dữ liệu thật cung cấp dưới đây, không bịa lịch.
- Lịch hẹn do AI tạo CHỈ ở trạng thái NHÁP (Pending); khách/nhân viên phải tự xác nhận, AI không tự chốt.
- Nêu rõ trùng lịch/quá tải nếu có, không che giấu; đề xuất khung giờ khác khi kín.
- Chuyển lịch thành phiếu sửa chữa chỉ khi có yêu cầu rõ ràng; không tự ý tiếp nhận thay nhân viên.
"""

SAFETY_SCHEDULING = (
    "\n\n---\n"
    "Lưu ý: khung giờ/kỹ thuật viên gợi ý tại thời điểm hỏi có thể thay đổi. "
    "Lịch hẹn chỉ chính thức sau khi được xác nhận."
)

SAFETY_RULES_INVENTORY = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Chỉ nêu số liệu tồn kho/nhu cầu từ dữ liệu thật cung cấp dưới đây, không bịa số.
- AI KHÔNG tự xuất/nhập/điều chỉnh tồn kho. Mọi thay đổi kho chỉ do người có quyền
  (kỹ thuật viên/quản lý) xác nhận qua màn hình kho — AI chỉ đề xuất.
- Đề xuất nhập hàng chỉ mang tính tham khảo; quản lý duyệt trước khi đặt.
- Nếu phụ tùng sắp hết/đã hết, cảnh báo rõ và nêu phương án thay thế còn hàng.
"""

SAFETY_INVENTORY = (
    "\n\n---\n"
    "Lưu ý: số liệu kho tại thời điểm hỏi. Việc xuất/nhập kho phải được người có quyền "
    "xác nhận trên hệ thống — AI không tự thay đổi tồn kho."
)

# Prompt gon: chi inject khoi lien quan theo keyword.
STOCK_KEYS = ("tồn kho", "ton kho", "tồn", "ton", "còn bao nhiêu", "con bao nhieu",
              "kiểm tra kho", "kiem tra kho", "kho còn", "kho con", "còn mấy", "con may")
LOW_STOCK_KEYS = ("sắp hết", "sap het", "hết hàng", "het hang", "cạn hàng", "can hang",
                  "cảnh báo", "canh bao", "tồn thấp", "ton thap", "cần nhập", "can nhap")
PART_SUGGEST_KEYS = ("gợi ý phụ tùng", "goi y phu tung", "nên thay", "nen thay",
                     "thay gì", "thay gi", "phụ tùng gì", "phu tung gi", "bộ phận nào",
                     "lỗi", "loi", "hỏng", "hong", "kêu", "keu", "rung", "yếu", "yeu")
DEMAND_KEYS = ("nhập hàng", "nhap hang", "nhập thêm", "nhap them", "dự đoán", "du doan",
               "nhu cầu", "nhu cau", "đặt hàng", "dat hang", "kế hoạch nhập", "ke hoach nhap")

SAFETY_RULES_BILLING = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Chỉ tính toán từ dữ liệu thật cung cấp dưới đây (công, phụ tùng, VAT, giảm giá), không bịa số.
- Giá/Giảm giá phải đúng dữ liệu; nêu rõ VAT và giảm giá (nếu có) trong kết quả.
- AI KHÔNG tự xuất hóa đơn, KHÔNG tự xác nhận/ghi nhận thanh toán. Mọi thanh toán do người
  có quyền (quản lý) xác nhận trên hệ thống — AI chỉ tạo BẢN NHÁP và đề xuất.
- Nêu rõ cảnh báo nếu báo giá bất thường (âm, thiếu công, giảm giá lớn, lệch xa trung bình).
"""

SAFETY_BILLING = (
    "\n\n---\n"
    "Lưu ý: bản nháp báo giá/hóa đơn chỉ để tham khảo. Việc xuất hóa đơn và xác nhận "
    "thanh toán phải do người có quyền thực hiện trên hệ thống — AI không tự thanh toán."
)

# Prompt gon: chi inject khoi lien quan theo keyword.
QUOTE_KEYS = ("báo giá", "bao gia", "tính tiền", "tinh tien", "tính giá", "tinh gia",
              "hóa đơn", "hoa don", "chi phí", "chi phi", "hết bao nhiêu", "het bao nhieu",
              "tổng tiền", "tong tien", "báo nhiêu", "bao nhieu")
ABNORMAL_KEYS = ("bất thường", "bat thuong", "sai", "lệch", "lech", "kiểm tra báo giá",
                 "kiem tra bao gia", "cao quá", "cao qua", "đắt", "dat", "hợp lý", "hop ly")
DEBT_KEYS = ("công nợ", "cong no", "chưa thanh toán", "chua thanh toan", "nợ", "no",
             "quá hạn", "qua han", "thu tiền", "thu tien", "cần thu", "can thu")
PROMO_KEYS = ("khuyến mãi", "khuyen mai", "giảm giá", "giam gia", "ưu đãi", "uu dai",
              "promotion", "khuyen mai")

SAFETY_RULES_MAINTENANCE = """
NGUYÊN TẮC AN TOÀN (bắt buộc tuân thủ):
- Chỉ phân tích/khuyến nghị từ ODO và lịch sử sửa chữa thật cung cấp dưới đây, không bịa mốc.
- Mốc bảo dưỡng chỉ mang tính tham khảo theo định kỳ chuẩn; tình trạng thực tế phải kiểm tra
  trực tiếp tại xưởng — AI không kết luận chắc chắn.
- AI KHÔNG tự đặt lịch/không tự tạo phiếu. Khách/nhân viên xác nhận trước khi thực hiện.
- Ưu tiên nhắc các hạng mục quá hạn liên quan an toàn (phanh, lốp) lên trước.
"""

SAFETY_MAINTENANCE = (
    "\n\n---\n"
    "Lưu ý: mốc bảo dưỡng chỉ là gợi ý theo định kỳ, không thay thế kiểm tra trực tiếp. "
    "Hãy đặt lịch để kỹ thuật viên kiểm tra xe — AI không tự đặt lịch."
)

# Prompt gon: chi inject khoi lien quan theo keyword.
MAINTENANCE_KEYS = ("bảo dưỡng", "bao duong", "bảo trì", "bao tri", "định kỳ", "dinh ky",
                    "nhắc", "nhac", "đến hạn", "den han", "odo", "km", "thay dầu",
                    "thay dau", "lốp", "lop", "phanh", "ắc quy", "ac quy", "kiểm tra xe",
                    "kiem tra xe", "chăm sóc", "cham soc")

# Prompt gon: chi inject khoi lien quan theo keyword.
SLOT_KEYS = ("khung giờ", "khung gio", "giờ trống", "gio trong", "còn chỗ",
             "con cho", "rảnh", "ranh", "trống", "trong", "slot", "lịch trống")
SCHEDULE_TECH_KEYS = ("kỹ thuật viên", "ky thuat vien", "thợ", "tho", "ai làm",
                      "ai lam", "gợi ý thợ", "goi y tho", "phân công", "phan cong")
CONFLICT_KEYS = ("trùng", "trung", "quá tải", "qua tai", "kín", "kin", "full",
                 "xung đột", "xung dot")
CONVERT_KEYS = ("xác nhận lịch", "xac nhan lich", "chuyển thành phiếu",
                "chuyen thanh phieu", "tạo phiếu sửa", "tao phieu sua",
                "tiếp nhận xe", "tiep nhan xe", "duyệt lịch", "duyet lich",
                "chuyển lịch", "chuyen lich")


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-zA-ZÀ-ỹ0-9]+", (text or "").lower()))


def suggest_services(db: Session, text: str, limit: int = 3) -> list:
    """Gợi ý dịch vụ đang Active khớp từ khóa. Giá lấy từ DB.
    Gon prompt: mac dinh top 3 (giam latency)."""
    services = db.query(ServiceCatalog).filter(ServiceCatalog.status == "Active").all()
    if not services:
        return []
    keys = _tokens(text)
    scored = []
    for s in services:
        hay = _tokens(f"{s.name} {s.category or ''} {s.description or ''}")
        score = len(keys & hay)
        # Ưu tiên dịch vụ đang khuyến mãi khi trùng điểm
        scored.append((score, 1 if s.promo_price else 0, s))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    out = []
    for score, _, s in scored:
        if score <= 0 and out:
            break
        price = s.promo_price if s.promo_price else (s.base_price or 0)
        out.append({"type": "service", "id": s.id, "name": s.name,
                    "category": s.category, "price": price,
                    "promo": bool(s.promo_price),
                    "duration_minutes": s.duration_minutes})
        if len(out) >= limit:
            break
    return out


def suggest_parts(db: Session, text: str, limit: int = 6) -> list:
    """Gợi ý phụ tùng khớp từ khóa (token-score). HAM DUY NHAT cho suggest
    phu tung — router chi goi cho nay. Chi hang dang kinh doanh + con hang.
    Giá lấy từ DB."""
    parts = db.query(SparePart).filter(
        SparePart.status == "Đang kinh doanh",
        SparePart.stock_quantity > 0,
    ).all()
    if not parts:
        return []
    keys = _tokens(text)
    scored = []
    for p in parts:
        hay = _tokens(f"{p.name} {p.category or ''} {p.brand or ''} "
                      f"{p.compatible_make or ''} {p.part_number or ''}")
        scored.append((len(keys & hay), p))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for score, p in scored:
        if score <= 0 and out:
            break
        out.append({"type": "part", "id": p.id, "name": p.name,
                    "part_number": p.part_number, "brand": p.brand,
                    "price": p.price or 0, "stock": p.stock_quantity or 0,
                    "warranty": p.warranty_period})
        if len(out) >= limit:
            break
    return out


def estimate_range(items: list) -> dict | None:
    """Ước tính sơ bộ min-max từ giá DB. Không bao gồm công thợ."""
    prices = [i["price"] for i in items if i.get("price")]
    if not prices:
        return None
    return {"min": min(prices), "max": sum(sorted(prices, reverse=True)[:3])}
