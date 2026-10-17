"""Test inventory agent (POST /agent/inventory/chat truc tiep ham).

Case: RBAC (technician/manager qua, admin bypass, customer 403) | message trang
400 | ton kho + canh bao + goi y + du doan dung DB + thu tu prompt + hau to
safety | goi y phu tung theo loi xe | KHONG tu xuat kho (ton kho bat bien) |
quota -> 503 + Retry-After | 4 tools truc tiep.

Chay: python test_inventory_agent.py (exit 0 = pass het).
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
from app.models.models import (
    User, Vehicle, RepairOrder, RepairOrderPart, SparePart,
)
from app.agents.schemas import InventoryIn
from app.agents.inventory_agent.router import inventory_chat

MOCK_OK = "MOCK_REPLY"
BIZ = "Đang kinh doanh"


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    tech = User(username="t1", password_hash="x", full_name="Tho",
                phone="0901", role="technician", is_active=1)
    mgr = User(username="m1", password_hash="x", full_name="Quan Ly",
               phone="0902", role="manager", is_active=1)
    cust = User(username="c1", password_hash="x", full_name="Khach",
                phone="0903", role="customer", is_active=1)
    db.add_all([tech, mgr, cust])
    db.flush()
    v = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                user_id=cust.id)
    db.add(v)
    db.flush()

    p1 = SparePart(part_number="BP-01", name="Má phanh trước", brand="Toyota",
                   status=BIZ, stock_quantity=12, min_stock=5, max_stock=40,
                   price=450000)
    p2 = SparePart(part_number="AF-02", name="Lọc gió động cơ", brand="Toyota",
                   status=BIZ, stock_quantity=2, min_stock=5, max_stock=30,
                   price=150000)
    p3 = SparePart(part_number="OF-03", name="Lọc dầu", brand="Toyota",
                   status=BIZ, stock_quantity=0, min_stock=3, max_stock=20,
                   price=120000)
    db.add_all([p1, p2, p3])
    db.flush()

    # Tieu thu 30 ngay: 2x ma phanh (on), 40x loc gio (can nhap)
    ro1 = RepairOrder(vehicle_id=v.id, symptoms="má phanh kêu", status="Completed")
    ro2 = RepairOrder(vehicle_id=v.id, symptoms="thay lọc gió", status="Completed")
    db.add_all([ro1, ro2])
    db.flush()
    db.add(RepairOrderPart(repair_order_id=ro1.id, part_id=p1.id, quantity=2,
                           unit_price=450000))
    db.add(RepairOrderPart(repair_order_id=ro2.id, part_id=p2.id, quantity=40,
                           unit_price=150000))
    db.commit()
    return db


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))


def _stock_snapshot(db):
    return sorted((p.id, p.stock_quantity or 0) for p in db.query(SparePart).all())


async def case1_rbac(db):
    from fastapi.params import Depends as DependsClass
    from app.core.rbac import require_roles, Role
    raw = require_roles([Role.TECHNICIAN, Role.MANAGER])
    fn = raw.dependency if isinstance(raw, DependsClass) else raw
    for role in ("technician", "manager"):
        assert fn({"role": role})["role"] == role, role
    assert fn({"role": "admin"})["role"] == "admin", "admin phai bypass"
    try:
        fn({"role": "customer"})
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    else:
        raise AssertionError("customer phai 403")
    print("PASS i-1 RBAC technician/manager qua, admin bypass, customer 403")


async def case2_400_trang(db):
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await inventory_chat(InventoryIn(message="   "), db, user)
    except HTTPException as e:
        assert e.status_code == 400, e.status_code
        print("PASS i-2 message trang -> 400")
    else:
        raise AssertionError("i-2: khong raise 400")


async def case3_stock_alert_demand(db):
    """Ton kho + canh bao + goi y + du doan dung DB + prompt + safety + read-only."""
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    seen = {}

    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK

    before = _stock_snapshot(db)
    n_rop = db.query(RepairOrderPart).count()

    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await inventory_chat(
            InventoryIn(message="kiểm tra tồn kho lọc gió, cái nào sắp hết, "
                                "dự đoán nhu cầu nhập hàng"), db, user)

    # Ton kho: khop "lọc gió"
    assert out["stock"][0]["name"] == "Lọc gió động cơ", out["stock"]
    assert out["stock"][0]["stock"] == 2, out["stock"]
    # Canh bao
    assert [p["name"] for p in out["alerts"]["low"]] == ["Lọc gió động cơ"], out["alerts"]
    assert [p["name"] for p in out["alerts"]["out"]] == ["Lọc dầu"], out["alerts"]
    assert out["alerts"]["total_parts"] == 3, out["alerts"]   # tong so phu tung
    assert out["alerts"]["alert_count"] == 2, out["alerts"]   # sap het + da het
    # Du doan nhap hang
    demand = out["restock_demand"]
    assert demand[0]["name"] == "Lọc dầu" and demand[0]["urgency"] == "out", demand
    assert demand[0]["suggested_order"] == 20, demand[0]
    loc = next(d for d in demand if d["name"] == "Lọc gió động cơ")
    assert loc["urgency"] == "low" and loc["suggested_order"] == 28, loc
    assert out["actions_proposed"], out["actions_proposed"]
    from app.agents.common import SAFETY_INVENTORY
    assert out["message"] == MOCK_OK + SAFETY_INVENTORY
    # Prompt thu tu + an toan
    p = seen["prompt"]
    marks = ["Tho", "Câu hỏi:", "TỒN KHO:", "CẢNH BÁO SẮP HẾT:",
             "GỢI Ý PHỤ TÙNG", "DỰ ĐOÁN NHẬP HÀNG", "NGUYÊN TẮC AN TOÀN"]
    pos = [p.find(m) for m in marks]
    assert all(i >= 0 for i in pos), [m for m, i in zip(marks, pos) if i < 0]
    assert pos == sorted(pos), f"sai thu tu prompt: {pos}"
    # Read-only
    db.expire_all()
    assert _stock_snapshot(db) == before, "agent lam doi ton kho"
    assert db.query(RepairOrderPart).count() == n_rop, "agent lam doi chi tiet tieu thu"
    print("PASS i-3 ton kho + canh bao + du doan + prompt + read-only")


async def case4_suggest_by_fault(db):
    """Goi y phu tung theo loi xe (chi hang con), scope theo vehicle_id."""
    v = db.query(Vehicle).filter_by(license_plate="30E-222.33").first()
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await inventory_chat(
            InventoryIn(message="xe bị kêu phanh, nên thay gì", vehicle_id=v.id),
            db, user)
    names = [p["name"] for p in out["suggested_parts"]]
    assert "Má phanh trước" in names, names
    assert "Lọc dầu" not in names, "hang het khong duoc goi y"
    assert out["vehicle"]["plate"] == "30E-222.33"
    assert "Má phanh trước" not in [p["name"] for p in out["alerts"]["out"]]

    # Xe khong ton tai -> 404
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await inventory_chat(InventoryIn(message="kiểm tra", vehicle_id=9999),
                                 db, user)
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
    else:
        raise AssertionError("i-4: xe khong ton tai phai 404")
    print("PASS i-4 goi y phu tung theo loi xe + vehicle 404")


async def case5_no_auto_issue(db):
    """Yeu cau xuat kho KHONG lam doi ton kho (khong tu xuat neu chua xac nhan)."""
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    before = _stock_snapshot(db)
    n_rop = db.query(RepairOrderPart).count()
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await inventory_chat(
            InventoryIn(message="xuất 2 lọc gió động cơ cho phiếu đang sửa đi"),
            db, user)
    db.expire_all()
    assert _stock_snapshot(db) == before, "tu xuat kho khi chua xac nhan"
    assert db.query(RepairOrderPart).count() == n_rop
    assert out["message"].endswith(
        __import__("app.agents.common", fromlist=["SAFETY_INVENTORY"]).SAFETY_INVENTORY)
    print("PASS i-5 khong tu xuat kho (ton kho + chi tiet bat bien)")


async def case6_quota_503(db):
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks("Hệ thống AI đã vượt quá giới hạn truy cập. "
                        "Bạn vui lòng thử lại sau nhé.")
    try:
        with m1, m2, m3:
            await inventory_chat(InventoryIn(message="tồn kho còn bao nhiêu"), db, user)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        assert (e.headers or {}).get("Retry-After") == "60", e.headers
        print("PASS i-6 quota -> 503 + Retry-After 60")
    else:
        raise AssertionError("i-6: khong raise 503")


async def main():
    db = setup_db()
    try:
        await case1_rbac(db)
        await case2_400_trang(db)
        await case3_stock_alert_demand(db)
        await case4_suggest_by_fault(db)
        await case5_no_auto_issue(db)
        await case6_quota_503(db)
    finally:
        db.close()
    print("ALL 6 INVENTORY CASES PASSED (mock, khong can key that).")


def test_eval_gate_inventory_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


def test_inventory_tools_direct():
    """4 tools kho truc tiep tren DB rieng."""
    from app.agents import tools as T

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        c = User(username="ic", password_hash="x", full_name="K",
                 phone="1", role="customer", is_active=1)
        db.add(c)
        db.flush()
        v = Vehicle(license_plate="77K-111.11", make="Kia", model="K3", user_id=c.id)
        db.add(v)
        db.flush()
        p1 = SparePart(part_number="X1", name="Bugi", status=BIZ,
                       stock_quantity=50, min_stock=10, price=90000)
        p2 = SparePart(part_number="X2", name="Dây curoa", status=BIZ,
                       stock_quantity=1, min_stock=4, price=200000)
        p3 = SparePart(part_number="X3", name="Lọc xăng", status=BIZ,
                       stock_quantity=0, min_stock=2, price=300000)
        db.add_all([p1, p2, p3])
        db.flush()
        ro = RepairOrder(vehicle_id=v.id, symptoms="thay", status="Completed")
        db.add(ro)
        db.flush()
        db.add(RepairOrderPart(repair_order_id=ro.id, part_id=p2.id, quantity=30,
                               unit_price=200000))
        db.commit()

        st = T.get_part_stock(db, "", limit=2)
        assert [p["name"] for p in st] == ["Lọc xăng", "Dây curoa"], st  # ton thap truoc
        assert st[0]["out"] is True and st[1]["low"] is True

        assert T.search_stock(db, "thay bugi")[0]["name"] == "Bugi"
        assert T.search_stock(db, "abcxyz") == []

        al = T.get_stock_alerts(db)
        assert al["total_parts"] == 3, al       # TONG so phu tung (khong phai so canh bao)
        assert al["alert_count"] == 2, al       # sap het + da het
        assert [p["name"] for p in al["low"]] == ["Dây curoa"]
        assert [p["name"] for p in al["out"]] == ["Lọc xăng"]

        dm = T.predict_restock_demand(db, days=30)
        names = [d["name"] for d in dm]
        assert names[0] == "Lọc xăng", dm
        cu = next(d for d in dm if d["name"] == "Dây curoa")
        assert cu["used"] == 30 and cu["suggested_order"] > 0, cu
        assert "Bugi" not in names, "hang du khong vao de xuat"
        print("PASS i-7 4 tools kho truc tiep")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
