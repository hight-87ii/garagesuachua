"""Inventory agent: tro ly kho phu tung (CHI DOC).

Chuc nang:
- Kiem tra ton kho (search_stock / get_part_stock).
- Canh bao phu tung sap het / da het (get_stock_alerts).
- Goi y phu tung theo loi xe (common.suggest_parts, chi hang con).
- Du doan nhu cau nhap hang (predict_restock_demand tu tieu thu RepairOrderPart).

Nguyen tac:
- KHONG tu xuat/nhap/dieu chinh ton kho. Router khong ghi DB.
- Moi cau tra loi kem SAFETY_INVENTORY; de xuat nhap hang chi la tham khao.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import time
from app.core.rbac import Role, require_roles
from app.routers.auth import get_current_user
from app.database import get_db
from app.models.models import User, Vehicle
from app.agents.base import call_gemini_safe, sanitize_llm_text, sanitize_llm_history
from app.core.rate_limit import agent_rate_limit
from app.core.agent_monitor import classify_agent_error, log_agent_call
from app.agents.common import (
    suggest_parts,
    SAFETY_RULES_INVENTORY, SAFETY_INVENTORY,
    WEATHER_KEYS, STOCK_KEYS, LOW_STOCK_KEYS, PART_SUGGEST_KEYS, DEMAND_KEYS,
)
from app.agents import tools as T
from app.agents.schemas import InventoryIn

router = APIRouter(prefix="/agent/inventory", tags=["Inventory Agent"])


def _db_user(db: Session, user: dict) -> User | None:
    return db.query(User).filter(User.username == user.get("sub")).first()


@router.post("/chat", dependencies=[
    Depends(require_roles([Role.TECHNICIAN, Role.MANAGER])),
    Depends(agent_rate_limit),
])
async def inventory_chat(data: InventoryIn, db: Session = Depends(get_db),
                         user: dict = Depends(get_current_user)):
    question = sanitize_llm_text(data.message).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu câu hỏi.")
    db_user = _db_user(db, user)
    if not db_user:
        raise HTTPException(status_code=401, detail="Không tìm thấy tài khoản.")
    uid = db_user.id
    low = question.lower()

    # Xe (tuy chon) de goi y phu tung sat lich su loi cua xe.
    car = None
    if data.vehicle_id is not None:
        car = db.query(Vehicle).filter(Vehicle.id == data.vehicle_id).first()
        if car is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy xe.")

    out: dict = {}

    # 1. Kiem tra ton kho
    stock_rows = []
    if data.part_number:
        stock_rows = T.get_part_stock(db, data.part_number, limit=5)
    if not stock_rows:
        stock_rows = T.search_stock(db, question)
    if stock_rows:
        out["stock"] = stock_rows

    # 2. Canh bao sap het (luon tinh vi an toan)
    alerts = T.get_stock_alerts(db)
    out["alerts"] = alerts

    # 3. Goi y phu tung theo loi xe
    suggest_text = question
    if car:
        out["vehicle"] = {"id": car.id, "plate": car.license_plate,
                          "make": car.make, "model": car.model}
        hist = T.get_vehicle_history(db, car.id, limit=3, status=None)
        suggest_text = question + " " + " ".join(
            (h.get("symptoms") or "") for h in hist)
        out["vehicle_history"] = hist
    parts = suggest_parts(db, suggest_text)
    out["suggested_parts"] = parts

    # 4. Du doan nhu cau nhap hang
    demand = T.predict_restock_demand(db, days=30)
    out["restock_demand"] = demand
    out["actions_proposed"] = [
        f"Nhập thêm {d['suggested_order']} × {d['name']}"
        for d in demand if d["suggested_order"] > 0]

    # Prompt gon + thu tu co dinh: Cau hoi -> TON KHO -> CANH BAO -> GOI Y
    # -> DU DOAN NHAP -> RAG -> THOI TIET (neu lien quan) -> SAFETY cuoi.
    ctx = []
    wants_stock = bool(stock_rows) or any(k in low for k in STOCK_KEYS) or bool(data.part_number)
    wants_suggest = bool(parts) or any(k in low for k in PART_SUGGEST_KEYS) or car is not None
    wants_demand = any(k in low for k in DEMAND_KEYS + LOW_STOCK_KEYS)

    if car:
        ctx.append(f"XE ĐANG XÉT: {car.make} {car.model} (biển {car.license_plate})")
    if wants_stock:
        ctx.append("TỒN KHO: " + ("; ".join(
            f"{p['name']} [{p['part_number']}] tồn {p['stock']} (min {p['min']})"
            for p in stock_rows) if stock_rows else "(không khớp tên phụ tùng cụ thể)"))
    ctx.append("CẢNH BÁO SẮP HẾT: " + (
        "; ".join(f"{p['name']} (tồn {p['stock']}/min {p['min']})" for p in alerts["low"])
        or "(không có)") + " | ĐÃ HẾT: " + (
        "; ".join(f"{p['name']} [{p['part_number']}]" for p in alerts["out"])
        or "(không có)"))
    if wants_suggest:
        ctx.append("GỢI Ý PHỤ TÙNG (chỉ hàng còn): " + (
            "; ".join(f"{p['name']} [{p['part_number']}] {p['price']:,}đ (tồn {p['stock']})"
                      for p in parts) if parts else "(chưa khớp phụ tùng nào)"))
    if wants_demand or demand:
        ctx.append("DỰ ĐOÁN NHẬP HÀNG (30 ngày qua): " + (
            "; ".join(
                f"{d['name']} tồn {d['stock']}, dùng {d['used']}, "
                f"~{d['avg_per_day']}/ngày"
                + (f", còn {d['cover_days']} ngày" if d["cover_days"] is not None else "")
                + f" → đề xuất nhập {d['suggested_order']} ({d['urgency']})"
                for d in demand) if demand else "(chưa đủ dữ liệu tiêu thụ)"))

    rag = T.search_knowledge(question)
    weather = T.get_weather_context(db)
    weather_txt = weather if any(k in low for k in WEATHER_KEYS) else ""
    name = user.get("name") or db_user.full_name or "bạn"

    system_prompt = (
        f"Bạn là AI Kho phụ tùng của garage ThreeH Workshop, hỗ trợ {name} ngắn gọn, "
        f"đúng số liệu kho. KHÔNG tự xuất/nhập kho — chỉ đề xuất cho người có quyền.\n"
        f"Câu hỏi: {question}\n"
        + (chr(10).join(ctx) + "\n" if ctx else "")
        + (f"TÀI LIỆU NỘI BỘ:\n{rag}\n" if rag else "")
        + f"THỜI TIẾT (1 câu, chỉ khi liên quan): {weather_txt}\n"
        + SAFETY_RULES_INVENTORY
    )

    started = time.perf_counter()
    result = call_gemini_safe(
        message=system_prompt, context_msg="Ho tro kho phu tung garage",
        history=sanitize_llm_history(data.history))
    latency_ms = int((time.perf_counter() - started) * 1000)
    if not result["ok"]:
        log_agent_call(agent="inventory", user_id=uid,
                       vehicle_id=car.id if car else None,
                       prompt_len=len(system_prompt), ok=False,
                       latency_ms=latency_ms,
                       error=classify_agent_error(result.get("message")))
        headers = {"Retry-After": str(result.get("retry_after"))} if result.get("retry_after") else None
        raise HTTPException(status_code=503, detail=result["message"], headers=headers)
    log_agent_call(agent="inventory", user_id=uid,
                   vehicle_id=car.id if car else None,
                   prompt_len=len(system_prompt), ok=True, latency_ms=latency_ms)

    out["message"] = result["message"] + SAFETY_INVENTORY
    out["question"] = question
    return out
