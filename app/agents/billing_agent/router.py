"""Billing agent: bao gia & hoa don (CHI DOC, khong tu thanh toan).

Chuc nang:
- Tinh tien cong + phu tung + VAT + khuyen mai (tools.compute_order_quote).
- Kiem tra bao gia bat thuong (tools.check_quote_abnormal).
- Sinh BAN NHAP bao gia/hoa don (tools.draft_invoice, khong ghi DB).
- Theo doi cong no (tools.get_receivables).

Nguyen tac:
- Router khong ghi DB: khong tao Invoice, khong doi trang thai thanh toan.
- Moi cau tra loi kem SAFETY_BILLING; ban nhap chi de tham khao.
- Phan quyen du lieu: TECHNICIAN chi xem phieu + cong no do minh phu trach
  (403 neu xem phieu nguoi khac); MANAGER/ADMIN xem toan garage.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import re
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import RepairOrder, User
from app.agents.base import call_gemini_safe, sanitize_llm_text, sanitize_llm_history
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call
from app.agents.common import (
    SAFETY_RULES_BILLING, SAFETY_BILLING,
    WEATHER_KEYS, QUOTE_KEYS, ABNORMAL_KEYS, DEBT_KEYS, PROMO_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import BillingIn

router = APIRouter(prefix="/agent/billing", tags=["Billing Agent"])

_ORDER_ID_RE = re.compile(r"(?:#|phiếu\s*#?|phieu\s*#?)(\d{1,7})", re.IGNORECASE)


def _db_user(db: Session, user: dict) -> User | None:
    return db.query(User).filter(User.username == user.get("sub")).first()


def _parse_order_id(data: BillingIn) -> int | None:
    if data.order_id is not None:
        return data.order_id
    m = _ORDER_ID_RE.search(data.message or "")
    return int(m.group(1)) if m else None


@router.post("/chat", dependencies=[
    Depends(require_roles([Role.TECHNICIAN, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def billing_chat(data: BillingIn, db: Session = Depends(get_db),
                       user: dict = Depends(get_current_user)):
    question = sanitize_llm_text(data.message).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")
    db_user = _db_user(db, user)
    if not db_user:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản.")
    uid = db_user.id
    low = question.lower()
    role = user.get("role") or ""
    # Pham vi du lieu: KTV CHI thay phieu/cong no cua minh; Manager/Admin thay
    # toan garage. tech_scope = uid khi la KTV, None khi la quan ly.
    tech_scope = uid if role == Role.TECHNICIAN.value else None

    discount_percent = float(data.discount_percent or 0)
    out: dict = {}

    # 1+2+3. Bao gia + ban nhap + kiem tra bat thuong (theo phieu #id)
    order_id = _parse_order_id(data)
    if order_id:
        order = db.query(RepairOrder).filter(RepairOrder.id == order_id).first()
        if order is None:
            raise HTTPException(status_code=404,
                                detail="Không tìm thấy phiếu sửa chữa.")
        # Chong IDOR: KTV khong duoc xem phieu khong phai do minh phu trach.
        if tech_scope is not None and order.technician_id != uid:
            raise HTTPException(
                status_code=403,
                detail="Bạn chỉ được xem phiếu sửa chữa do mình phụ trách.")
        quote = T.compute_order_quote(db, order.id,
                                      discount_percent=discount_percent)
        out["quote"] = quote
        out["draft_invoice"] = T.draft_invoice(
            db, order.id, discount_percent=discount_percent)
        out["abnormal"] = T.check_quote_abnormal(
            db, order.id, quote=quote, technician_id=tech_scope)

    # 4. Khuyen mai dang ap dung
    promos = T.get_active_promotions(db)
    out["promotions"] = promos

    # 5. Cong no (KTV: chi phieu cua minh; Manager/Admin: toan garage)
    recv = T.get_receivables(db, technician_id=tech_scope)
    out["receivables"] = recv
    out["actions_proposed"] = []
    if recv["overdue_count"]:
        out["actions_proposed"].append(
            f"Nhắc thu {recv['overdue_count']} hóa đơn quá hạn ({recv['overdue_amount']:,.0f}đ).")
    if out.get("abnormal", {}).get("abnormal"):
        out["actions_proposed"].append(
            "Rà soát báo giá bất thường trước khi gửi khách.")

    # Prompt gon + thu tu co dinh: Cau hoi -> BAO GIA -> BAN NHAP -> BAT THUONG
    # -> KHUYEN MAI -> CONG NO -> RAG -> SAFETY cuoi.
    ctx = []
    quote = out.get("quote")
    if quote:
        item_lines = "; ".join(
            f"{i['name']} x{i['quantity']} = {i['line_total']:,.0f}đ"
            for i in quote["items"]) or "(chưa gắn phụ tùng)"
        ctx.append(
            "BÁO GIÁ (phiếu #{}): công {labor:,.0f}đ; phụ tùng {parts_total:,.0f}đ "
            "[{items_txt}]; subtotal {subtotal:,.0f}đ; VAT {vat_rate:.0%} = {vat_amount:,.0f}đ; "
            "giảm giá {discount_percent}% = {discount:,.0f}đ; TỔNG {total:,.0f}đ.".format(
                quote["order_id"], items_txt=item_lines, **quote))
        ctx.append("BẢN NHÁP HÓA ĐƠN: {} ({}), tổng {total:,.0f}đ — CHƯA xuất.".format(
            "sẵn sàng" if out.get("draft_invoice") else "không có",
            out["draft_invoice"]["status"] if out.get("draft_invoice") else "-",
            total=quote["total"]))
    if out.get("abnormal", {}).get("abnormal"):
        ctx.append("CẢNH BÁO BÁO GIÁ BẤT THƯỜNG: "
                   + "; ".join(out["abnormal"]["reasons"]))
    if promos:
        ctx.append("KHUYẾN MÃI ĐANG CHẠY: " + "; ".join(
            f"{p['title']} (-{p['discount_percent']}%)" for p in promos))
    if any(k in low for k in DEBT_KEYS) or recv["unpaid_count"]:
        scope_txt = "(chỉ phiếu của bạn)" if tech_scope is not None else "(toàn garage)"
        ctx.append("CÔNG NỢ " + scope_txt + ": {} hóa đơn chưa thu / {:,}đ "
                   "(quá hạn {} / {:,}đ).".format(
                       recv["unpaid_count"], int(recv["unpaid_amount"]),
                       recv["overdue_count"], int(recv["overdue_amount"])))

    rag = T.search_knowledge(question)
    weather = T.get_weather_context(db)
    weather_txt = weather if any(k in low for k in WEATHER_KEYS) else ""
    name = user.get("name") or db_user.full_name or "bạn"

    system_prompt = (
        f"Bạn là AI Báo giá & Hóa đơn của garage ThreeH Workshop, hỗ trợ {name} ngắn gọn, "
        f"đúng số liệu. KHÔNG tự xuất hóa đơn/thanh toán — chỉ tạo bản nháp để người có quyền duyệt.\n"
        f"Câu hỏi: {question}\n"
        + (chr(10).join(ctx) + "\n" if ctx else "")
        + (f"TÀI LIỆU NỘI BỘ:\n{rag}\n" if rag else "")
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + SAFETY_RULES_BILLING
    )

    started = time.perf_counter()
    result = call_gemini_safe(
        message=system_prompt, context_msg="Ho tro bao gia va hoa don garage",
        history=sanitize_llm_history(data.history))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="billing", user_id=uid,
                       vehicle_id=None, prompt_len=len(system_prompt),
                       ok=False, latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="billing", user_id=uid, vehicle_id=None,
                   prompt_len=len(system_prompt), ok=True, latency_ms=latency_ms)

    out["message"] = result["message"] + SAFETY_BILLING
    out["question"] = question
    return out
