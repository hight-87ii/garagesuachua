"""Ham chung duy nhat cho AI: ca 2 agent + /api/chatbot deu goi qua day.

- build_role_context: tach tu main.py (doi tuong + ten).
- detect_vehicle: regex bien so tu main.py (normalize bo [^A-Z0-9]).
- extract_plate_mention: trich chuoi dang-bien-so trong cau (VD '30E-222.33'),
  khong doi chieu DB; tim xe that do detect_vehicle quyet dinh.
- build_vehicle_context: xe + N RepairOrder Completed (mau main.py).
- call_gemini_safe: wrapper Gemini DUY NHAT cho ca 2 agent (da gop
  common.call_gemini vao day): tra {"ok", "message"}, nhan history that,
  map loi 503/429 thanh text TV, log loi server-side, KHONG lo traceback
  ra client. stream=True tra generator (dung cho StreamingResponse).

Quy tac import: base.py CHI import models/services. Cam import router,
main, tools co phu thuoc router -> khong circular import.
"""
import logging
import re
from html.parser import HTMLParser
from sqlalchemy.orm import Session
from app.models.models import User, Vehicle, RepairOrder
from app.services import gemini_service

logger = logging.getLogger("threeh.agents")


class _PlainTextParser(HTMLParser):
    """Bo HTML va bo ca noi dung script/style truoc khi dua vao LLM."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style"):
            self.blocked += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style") and self.blocked:
            self.blocked -= 1

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def sanitize_llm_text(value: str) -> str:
    """Chuyen HTML ve plain text, bo script/style va control chars."""
    parser = _PlainTextParser()
    parser.feed(value or "")
    parser.close()
    text = " ".join(part.strip() for part in parser.parts if part.strip())
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)


def sanitize_llm_history(history: list) -> list:
    """Sanitize cac field text/content/message trong history ma khong doi shape.
    Gon prompt: chi giu 6 turns cuoi, moi turn cat 300 ky tu (giam latency)."""
    clean = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        for key in ("text", "content", "message"):
            if key in row:
                row[key] = sanitize_llm_text(str(row[key]))[:300]
        clean.append(row)
    return clean[-6:]

ROLE_VI = {
    "customer": "Khách hàng",
    "technician": "Kỹ thuật viên",
    "manager": "Quản lý",
    "admin": "Quản trị viên",
}


def build_role_context(user: dict, db_user: User) -> str:
    """Tra ve 'Đối tượng: <vai tro>. Tên: <ten>. ' (mau main.py)."""
    role_vi = ROLE_VI.get((user or {}).get("role", "customer"), "Khách hàng")
    name = (db_user.full_name if db_user is not None else None) or (user or {}).get("sub", "")
    return f"Đối tượng đang chat: {role_vi}. Tên: {name}. "


def detect_vehicle(text: str, vehicles: list) -> "Vehicle | None":
    """Tim xe theo bien so xuat hien trong cau (mau main.py). Tra Vehicle hoac None."""
    normalized_msg = re.sub(r"[^a-zA-Z0-9]", "", text or "").upper()
    if not normalized_msg:
        return None
    for v in vehicles or []:
        plate = getattr(v, "license_plate", None)
        if not plate:
            continue
        normalized_plate = re.sub(r"[^a-zA-Z0-9]", "", plate).upper()
        if normalized_plate and normalized_plate in normalized_msg:
            return v
    return None


# Pattern bien so VN thong dung (VD 30E-222.33, 51F-99999): chi dung de PHAT HIEN
# cau co nhac dang bien so, KHONG dung de khop xe (khop xe do detect_vehicle).
PLATE_PATTERN = r"\b\d{2}[A-Z]-?\d{3,4}\.?\d{2}\b"


def extract_plate_mention(text: str) -> str | None:
    """Trich chuoi dang-bien-so trong cau, khong doi chieu DB."""
    m = re.search(PLATE_PATTERN, (text or "").upper())
    return m.group(0) if m else None


def build_vehicle_context(db: Session, vehicle: Vehicle, limit: int = 3) -> str:
    """Chuoi context: xe make/model/plate/odo + N don Completed gan nhat
    (symptoms, inspection, used_parts) — mau main.py."""
    if vehicle is None:
        return ""
    odo_str = f"{vehicle.current_odo:,} km" if vehicle.current_odo else "Chưa cập nhật"
    out = [f"Xe {vehicle.make} {vehicle.model} ({vehicle.license_plate}), ODO hiện tại: {odo_str}."]
    try:
        completed = db.query(RepairOrder).filter(
            RepairOrder.vehicle_id == vehicle.id,
            RepairOrder.status == "Completed",
        ).order_by(RepairOrder.created_at.desc()).limit(limit).all()
    except Exception as e:
        logger.warning("build_vehicle_context query failed: %s", e)
        return "\n".join(out)
    if not completed:
        out.append("(Chưa có lịch sử dịch vụ nào hoàn thành)")
        return "\n".join(out)
    out.append("Lịch sử dịch vụ/sửa chữa gần đây:")
    for order in completed:
        date_str = "Không rõ"
        try:
            if order.completed_at:
                date_str = order.completed_at.strftime("%d/%m/%Y")
            elif order.created_at:
                date_str = order.created_at.strftime("%d/%m/%Y")
        except Exception:
            pass
        type_str = "Dịch vụ/Rửa xe" if order.order_type == "CarWash" else "Sửa chữa"
        out.append(f"  + Lần {type_str} ngày {date_str} (Khách báo: {order.symptoms}).")
        try:
            used = [f"{p.part.name} (x{p.quantity})" for p in order.used_parts if p.part]
        except Exception:
            used = []
        if used:
            out.append(f"    Phụ tùng/vật tư đã thay: {', '.join(used)}.")
    return "\n".join(out)


_OVERLOAD_MSG = "Hệ thống AI hiện đang quá tải do nhu cầu cao. Bạn vui lòng thử lại sau vài phút nhé."
_QUOTA_MSG = "Hệ thống AI đã vượt quá giới hạn truy cập. Bạn vui lòng thử lại sau nhé."
_GENERIC_MSG = "Xin lỗi, AI đang gặp sự cố kết nối. Vui lòng thử lại sau."


def _map_error_text(err: str) -> str:
    if "503" in err or "UNAVAILABLE" in err:
        return _OVERLOAD_MSG
    if "429" in err or "Quota" in err or "quota" in err:
        return _QUOTA_MSG
    return _GENERIC_MSG


_ERROR_MARKERS = ("Lỗi:", "Xin lỗi,", "quá tải", "vượt quá giới hạn")

# Fail-fast: quota/503 tra 503 ngay kem Retry-After, khoi bat user cho retry.
QUOTA_RETRY_AFTER = 60
OVERLOAD_RETRY_AFTER = 30


def _retry_after_for(text: str | None) -> int | None:
    t = text or ""
    if "vượt quá giới hạn" in t or "Quota" in t or "quota" in t or "429" in t:
        return QUOTA_RETRY_AFTER
    if "quá tải" in t or "503" in t or "UNAVAILABLE" in t:
        return OVERLOAD_RETRY_AFTER
    return None


def call_gemini_safe(message: str, context_msg: str, history: list | None = None,
                     stream: bool = False):
    """Wrapper Gemini duy nhat cho ca 2 agent (gop tu common.call_gemini).

    - stream=False: tra {"ok": bool, "message": str, "retry_after": int|None}.
      Loi API / reply rong / text loi TV tu service (vd mat key) -> ok=False,
      router raise 503 (kem header Retry-After khi la quota/503).
    - stream=True: tra generator yield tung chunk (dung cho StreamingResponse).
    - history duoc truyen thang xuong service (ban cu common cung []).
    - Moi exception deu log server-side, client chi nhan text TV lich su.
    """
    if stream:
        return _stream_safe(message, history or [], context_msg or "")
    try:
        reply = gemini_service.get_gemini_response(
            message=message, history=history or [], context_msg=context_msg or "")
    except Exception as e:
        logger.warning("call_gemini_safe failed: %s", e)
        err = str(e)
        return {"ok": False, "message": _map_error_text(err),
                "retry_after": _retry_after_for(err)}
    if not reply or not reply.strip():
        return {"ok": False,
                "message": "AI chưa trả lời được. Bạn vui lòng thử lại.",
                "retry_after": None}
    text = reply.strip()
    # Service tra loi bang chuoi TV (khong raise) khi loi key/quota/503/ket noi.
    # So sanh exact voi cac message da biet + prefix markers cu (tranh substring
    # nhu "quá tải" trong cau xe cho hang qua tai lam fail oan reply that).
    _known_errors = {
        gemini_service.NO_KEY_MSG,
        gemini_service.OVERLOAD_MSG,
        gemini_service.QUOTA_MSG,
        gemini_service.CONN_ERR_MSG,
        gemini_service.GENERIC_ERR_MSG,
    }
    if text in _known_errors or text.startswith(_ERROR_MARKERS):
        return {"ok": False, "message": text, "retry_after": _retry_after_for(text)}
    return {"ok": True, "message": text, "retry_after": None}


def _stream_safe(message: str, history: list, context_msg: str):
    try:
        yield from gemini_service.get_gemini_response_stream(
            message=message, history=history, context_msg=context_msg)
    except Exception as e:
        logger.warning("call_gemini_safe stream failed: %s", e)
        yield _map_error_text(str(e))
