"""Manager agent: tro ly van hanh cho quan ly (read-only).

- Tong hop KPI: phieu theo trang thai, doanh thu/cong no, lich hen cho,
  ton kho thap, tai KTV.
- Chi doc DB, khong ghi/sua du lieu van hanh.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import User
from app.agents.base import call_gemini_safe, sanitize_llm_text, sanitize_llm_history
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call
from app.agents.common import (
    SAFETY_RULES_MANAGER, SAFETY_MANAGER,
    WEATHER_KEYS, PRICE_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import ManagerChatIn

router = APIRouter(prefix="/agent/manager", tags=["Manager Agent"])


def _db_user_id(db: Session, user: dict) -> int | None:
    u = db.query(User).filter(User.username == user.get("sub")).first()
    return u.id if u else None


def _ops_stats(db: Session) -> dict:
    """KPI van hanh gon nhe, loi DB -> gia tri mac dinh (khong 500).
    Dung tools manager dung chung (1 nguon, khong query rieng o router)."""
    kpis = T.get_manager_kpis(db)
    rev = T.get_revenue_summary(db)
    return {
        "orders": kpis.get("orders", {}),
        "revenue_total": rev.get("total", 0),
        "unpaid": {"count": rev.get("unpaid_count", 0),
                   "amount": rev.get("unpaid_amount", 0)},
        "appointments_pending": kpis.get("appointments_pending", 0),
        "low_stock": [{"name": p["name"], "stock": p["stock"]}
                      for p in T.get_low_stock_parts(db)],
        "tech_load": [{"name": t["name"], "in_progress": t["in_progress"]}
                      for t in T.get_technician_performance(db)[:5]],
    }


@router.post("/chat", dependencies=[
    Depends(require_roles([Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def manager_chat(data: ManagerChatIn, db: Session = Depends(get_db),
                       user: dict = Depends(get_current_user)):
    question = sanitize_llm_text(data.message).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")
    uid = _db_user_id(db, user)
    if not uid:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản.")

    stats = _ops_stats(db)
    out = {"stats": stats}
    low = question.lower()

    rag = T.search_knowledge(question)
    weather = T.get_weather_context(db)
    weather_txt = weather if any(k in low for k in WEATHER_KEYS) else ""
    # Tai chinh chi tiet chi khi hoi tien/doanh thu/cong no.
    money_txt = ""
    if any(k in low for k in PRICE_KEYS + ("doanh thu", "công nợ", "cong no")):
        money_txt = ("Tổng doanh thu (hóa đơn): {:,}đ; công nợ Unpaid: {} đơn / {:,}đ.".format(
            int(stats["revenue_total"]), stats["unpaid"]["count"],
            int(stats["unpaid"]["amount"])))

    name = user.get("name") or "bạn"
    system_prompt = (
        f"Bạn là AI Trợ lý Vận hành của garage ThreeH Workshop, hỗ trợ quản lý {name} ngắn gọn, đúng số liệu.\n"
        f"Câu hỏi: {question}\n"
        f"VẬN HÀNH: Pending {stats['orders'].get('Pending', 0)}, "
        f"In Progress {stats['orders'].get('In Progress', 0)}, "
        f"Completed {stats['orders'].get('Completed', 0)}; "
        f"lịch hẹn chờ {stats['appointments_pending']}.\n"
        f"KHO SẮP HẾT: "
        + (", ".join(f"{p['name']} (tồn {p['stock']})" for p in stats["low_stock"])
           or "(không có)") + "\n"
        f"TẢI KTV: "
        + (", ".join(f"{t['name']}: {t['in_progress']} xe" for t in stats["tech_load"])
           or "(chưa có KTV)") + "\n"
        + (f"TÀI CHÍNH: {money_txt}\n" if money_txt else "")
        + (f"TÀI LIỆU NỘI BỘ:\n{rag}\n" if rag else "")
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + SAFETY_RULES_MANAGER
    )

    started = time.perf_counter()
    result = call_gemini_safe(message=system_prompt, context_msg="Ho tro quan ly garage",
                              history=sanitize_llm_history(data.history))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="manager", user_id=uid, vehicle_id=None,
                       prompt_len=len(system_prompt), ok=False,
                       latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="manager", user_id=uid, vehicle_id=None,
                   prompt_len=len(system_prompt), ok=True,
                   latency_ms=latency_ms)
    out["message"] = result["message"] + SAFETY_MANAGER
    out["question"] = question
    return out
