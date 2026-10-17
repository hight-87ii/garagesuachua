"""Test manager agent (POST /agent/manager/chat truc tiep ham).

5 case: RBAC manager/admin qua + customer/technician 403 | message trang 400 |
mock ok -> stats + hau to safety | mat key -> 503 + Retry-After |
so lieu KPI dung DB.

Chay: python test_manager_agent.py (exit 0 = pass het).
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import User, Vehicle, RepairOrder, Invoice, SparePart
from app.agents.schemas import ManagerChatIn
from app.agents.manager_agent.router import manager_chat

MOCK_OK = "MOCK_REPLY"


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    mgr = User(username="m1", password_hash="x", full_name="Quan Ly",
               phone="0901", role="manager", is_active=1)
    tech = User(username="t1", password_hash="x", full_name="Tho",
                phone="0902", role="technician", is_active=1)
    cust = User(username="c1", password_hash="x", full_name="Khach",
                phone="0903", role="customer", is_active=1)
    db.add_all([mgr, tech, cust])
    db.flush()
    v = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                user_id=cust.id)
    db.add(v)
    db.flush()
    db.add(RepairOrder(vehicle_id=v.id, symptoms="keu", status="Pending",
                       technician_id=tech.id))
    db.add(RepairOrder(vehicle_id=v.id, symptoms="rung", status="Completed",
                       technician_id=tech.id))
    db.flush()
    ros = db.query(RepairOrder).all()
    db.add(Invoice(repair_order_id=ros[0].id, total_amount=1000000, status="Unpaid"))
    db.add(Invoice(repair_order_id=ros[1].id, total_amount=2000000, status="Paid"))
    db.add(SparePart(part_number="MP1", name="Loc dau", status="Đang kinh doanh",
                     stock_quantity=1, min_stock=5, price=100000))
    db.commit()
    return db


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))


async def case1_rbac(db):
    """manager qua, admin bypass, customer/technician 403."""
    from fastapi.params import Depends as DependsClass
    from app.core.rbac import require_roles, Role
    raw = require_roles([Role.MANAGER])
    fn = raw.dependency if isinstance(raw, DependsClass) else raw
    assert fn({"role": "manager"})["role"] == "manager"
    assert fn({"role": "admin"})["role"] == "admin", "admin phai bypass"
    for role in ("customer", "technician"):
        try:
            fn({"role": role})
        except HTTPException as e:
            assert e.status_code == 403, (role, e.status_code)
        else:
            raise AssertionError(f"{role} phai 403")
    print("PASS m-1 RBAC manager qua, admin bypass, customer/technician 403")


async def case2_400_trang(db):
    """message trang -> 400."""
    user = {"sub": "m1", "role": "manager", "name": "Quan Ly"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await manager_chat(ManagerChatIn(message="   "), db, user)
    except HTTPException as e:
        assert e.status_code == 400, e.status_code
        print("PASS m-2 message trang -> 400")
    else:
        raise AssertionError("m-2: khong raise 400")


async def case3_ok_stats_safety(db):
    """mock ok -> stats dung DB + hau to safety + thu tu prompt."""
    user = {"sub": "m1", "role": "manager", "name": "Quan Ly"}
    seen = {}

    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK

    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await manager_chat(ManagerChatIn(message="hom nay the nao"), db, user)
    from app.agents.common import SAFETY_MANAGER
    assert out["message"] == MOCK_OK + SAFETY_MANAGER, "thieu hau to safety"
    assert set(out) == {"stats", "message", "question"}, set(out)
    assert out["stats"]["orders"] == {"Pending": 1, "In Progress": 0,
                                      "Completed": 1}, out["stats"]["orders"]
    assert out["stats"]["revenue_total"] == 3000000
    assert out["stats"]["unpaid"] == {"count": 1, "amount": 1000000}
    assert out["stats"]["low_stock"][0]["name"] == "Loc dau"
    p = seen["prompt"]
    marks = ["Quan Ly", "Câu hỏi:", "VẬN HÀNH:", "KHO SẮP HẾT:", "TẢI KTV:",
             "NGUYÊN TẮC AN TOÀN"]
    pos = [p.find(m) for m in marks]
    assert all(i >= 0 for i in pos), [m for m, i in zip(marks, pos) if i < 0]
    assert pos == sorted(pos), f"sai thu tu prompt: {pos}"
    print("PASS m-3 stats dung DB + safety + thu tu prompt")


async def case4_mat_key_503(db):
    """mat key -> 503 TV (khong Retry-After khi loi thuong)."""
    user = {"sub": "m1", "role": "manager", "name": "Quan Ly"}
    m1, m2, m3 = _mocks("Lỗi: Chưa cấu hình GEMINI_API_KEY trong file .env.")
    try:
        with m1, m2, m3:
            await manager_chat(ManagerChatIn(message="bao cao"), db, user)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        print("PASS m-4 mat key -> 503 TV")
    else:
        raise AssertionError("m-4: khong raise 503")


async def case5_quota_retry_after(db):
    """quota -> 503 + header Retry-After 60."""
    user = {"sub": "m1", "role": "manager", "name": "Quan Ly"}
    m1, m2, m3 = _mocks("Hệ thống AI đã vượt quá giới hạn truy cập. "
                        "Bạn vui lòng thử lại sau nhé.")
    try:
        with m1, m2, m3:
            await manager_chat(ManagerChatIn(message="bao cao"), db, user)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        assert (e.headers or {}).get("Retry-After") == "60", e.headers
        print("PASS m-5 quota -> 503 + Retry-After 60")
    else:
        raise AssertionError("m-5: khong raise 503")


async def case6_readonly(db):
    """Manager chat read-only: goi 2 cau (ke ca cau dat lich) khong doi DB."""
    from app.models.models import Appointment
    user = {"sub": "m1", "role": "manager", "name": "Quan Ly"}

    def snapshot():
        return {
            "orders": db.query(RepairOrder).count(),
            "invoices": db.query(Invoice).count(),
            "appts": db.query(Appointment).count(),
            "parts": db.query(SparePart).count(),
            "statuses": sorted(
                r.status for r in db.query(RepairOrder.status).all()),
        }

    before = snapshot()
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        await manager_chat(ManagerChatIn(message="doanh thu bao nhieu"), db, user)
        await manager_chat(ManagerChatIn(message="dat lich ngay mai cho xe 30E-222.33"),
                           db, user)
    db.expire_all()
    after = snapshot()
    assert before == after, f"manager lam doi DB: {before} -> {after}"
    print("PASS m-6 read-only, khong doi du lieu")


async def main():
    db = setup_db()
    try:
        await case1_rbac(db)
        await case2_400_trang(db)
        await case3_ok_stats_safety(db)
        await case4_mat_key_503(db)
        await case5_quota_retry_after(db)
        await case6_readonly(db)
    finally:
        db.close()
    print("ALL 6 MANAGER CASES PASSED (mock, khong can key that).")


def test_eval_gate_manager_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


def test_manager_tools_direct():
    """6 tools manager truc tiep: kpis/appointments/low-stock/perf/revenue/quotes."""
    from app.agents import tools as T
    from app.models.models import Appointment

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        tech = User(username="mt_tech", password_hash="x", full_name="Tho May",
                    phone="1", role="technician", is_active=1)
        cust = User(username="mt_cust", password_hash="x", full_name="Khach",
                    phone="2", role="customer", is_active=1)
        db.add_all([tech, cust])
        db.flush()
        v = Vehicle(license_plate="77M-111.11", make="Toyota", model="Vios",
                    user_id=cust.id)
        db.add(v)
        db.flush()
        db.add(RepairOrder(vehicle_id=v.id, symptoms="keu", status="Pending",
                           technician_id=tech.id, estimated_cost=700000,
                           customer_approval="Pending"))
        db.add(RepairOrder(vehicle_id=v.id, symptoms="rung", status="Completed",
                           technician_id=tech.id, estimated_cost=300000,
                           customer_approval="Approved"))
        db.flush()
        ros = db.query(RepairOrder).order_by(RepairOrder.id).all()
        db.add(Invoice(repair_order_id=ros[0].id, total_amount=700000,
                       status="Unpaid"))
        db.add(Appointment(user_id=cust.id, vehicle_id=v.id,
                           appointment_date="2026-12-01", symptoms="keu",
                           status="Pending"))
        db.add(SparePart(part_number="MT1", name="Loc gio", status="Đang kinh doanh",
                         stock_quantity=2, min_stock=5, price=150000))
        db.add(SparePart(part_number="MT2", name="Dau may", status="Đang kinh doanh",
                         stock_quantity=50, min_stock=5, price=200000))
        db.commit()

        kpis = T.get_manager_kpis(db)
        assert kpis["orders"] == {"Pending": 1, "In Progress": 0, "Completed": 1}
        assert kpis["appointments_pending"] == 1, kpis

        appts = T.get_pending_appointments(db)
        assert len(appts) == 1 and appts[0]["plate"] == "77M-111.11", appts
        assert appts[0]["customer"] == "Khach", appts[0]

        low = T.get_low_stock_parts(db)
        assert [p["name"] for p in low] == ["Loc gio"], low

        perf = T.get_technician_performance(db)
        assert perf[0]["name"] == "Tho May" and perf[0]["completed"] == 1, perf
        assert perf[0]["in_progress"] == 0 and perf[0]["total"] == 2, perf[0]

        rev = T.get_revenue_summary(db)
        assert rev == {"total": 700000, "paid_amount": 0, "unpaid_count": 1,
                       "unpaid_amount": 700000}, rev

        quotes = T.get_quotes_waiting(db)
        assert len(quotes) == 1 and quotes[0]["estimated_cost"] == 700000, quotes
        assert quotes[0]["plate"] == "77M-111.11", quotes[0]
        print("PASS m-7 6 tools manager truc tiep")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
