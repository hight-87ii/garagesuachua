"""Test maintenance agent (POST /agent/maintenance/chat truc tiep ham).

Case: RBAC (customer/technician/manager qua, admin bypass, guest 403) | message
trang 400 | prof le ODO + lich su + moc bao duong + khuyen nghi + prompt +
safety + read-only | anti-IDOR (khach khac 403, nhan vien xem duoc) | thieu xe
-> needs | quota -> 503 + Retry-After | 3 tools truc tiep | moc thoi gian
(interval_months) + total_orders that.

Chay: python test_maintenance_agent.py (exit 0 = pass het).
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import (
    User, Vehicle, RepairOrder, RepairOrderPart, SparePart, ServiceCatalog,
)
from app.agents.schemas import MaintenanceIn
from app.agents.maintenance_agent.router import maintenance_chat

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
    c1 = User(username="c1", password_hash="x", full_name="Khach Mot",
              phone="0903", role="customer", is_active=1)
    c2 = User(username="c2", password_hash="x", full_name="Khach Hai",
              phone="0904", role="customer", is_active=1)
    c3 = User(username="c3", password_hash="x", full_name="Khach Ba",
              phone="0905", role="customer", is_active=1)
    db.add_all([tech, mgr, c1, c2, c3])
    db.flush()
    v1 = Vehicle(license_plate="30E-111.11", make="Toyota", model="Vios",
                 manufacture_year=2020, current_odo=12000, user_id=c1.id)
    v2 = Vehicle(license_plate="51F-222.22", make="Honda", model="City",
                 current_odo=8000, user_id=c2.id)
    db.add_all([v1, v2])
    db.flush()

    p_oil = SparePart(part_number="OF-1", name="Lọc dầu", status=BIZ,
                      stock_quantity=10, price=120000)
    p_brake = SparePart(part_number="BP-1", name="Má phanh trước", status=BIZ,
                        stock_quantity=10, price=450000)
    svc = [ServiceCatalog(service_code="S1", name="Thay dầu động cơ",
                          category="Bảo dưỡng", description="thay nhot",
                          status="Active", base_price=400000, duration_minutes=30),
           ServiceCatalog(service_code="S2", name="Kiểm tra lốp & cân bằng động",
                          category="Lốp", description="lop can bang",
                          status="Active", base_price=200000, duration_minutes=40),
           ServiceCatalog(service_code="S3", name="Vệ sinh lọc gió động cơ",
                          category="Bảo dưỡng", description="ve sinh loc gio",
                          status="Active", base_price=150000, duration_minutes=30)]
    db.add_all([p_oil, p_brake] + svc)
    db.flush()

    # Lan thay dau gan nhat o ODO 8000 (cach 4000 km -> sap toi han)
    ro_oil = RepairOrder(vehicle_id=v1.id, symptoms="thay dầu máy định kỳ",
                         status="Completed", final_odo=8000,
                         completed_at=datetime.utcnow() - timedelta(days=30),
                         created_at=datetime.utcnow() - timedelta(days=30))
    ro_brake = RepairOrder(vehicle_id=v1.id, symptoms="thay má phanh trước",
                           status="Completed", final_odo=5000,
                           completed_at=datetime.utcnow() - timedelta(days=200),
                           created_at=datetime.utcnow() - timedelta(days=200))
    db.add_all([ro_oil, ro_brake])
    db.flush()
    db.add(RepairOrderPart(repair_order_id=ro_oil.id, part_id=p_oil.id,
                           quantity=1, unit_price=120000))
    db.add(RepairOrderPart(repair_order_id=ro_brake.id, part_id=p_brake.id,
                           quantity=1, unit_price=450000))
    db.commit()
    return db


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))


def _db_snapshot(db):
    return (db.query(RepairOrder).count(), db.query(Vehicle).count())


async def case1_rbac(db):
    from fastapi.params import Depends as DependsClass
    from app.core.rbac import require_roles, Role
    raw = require_roles([Role.CUSTOMER, Role.TECHNICIAN, Role.MANAGER])
    fn = raw.dependency if isinstance(raw, DependsClass) else raw
    for role in ("customer", "technician", "manager"):
        assert fn({"role": role})["role"] == role, role
    assert fn({"role": "admin"})["role"] == "admin", "admin phai bypass"
    try:
        fn({"role": "guest"})
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    else:
        raise AssertionError("guest phai 403")
    print("PASS n-1 RBAC customer/technician/manager qua, admin bypass, guest 403")


async def case2_400_trang(db):
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await maintenance_chat(MaintenanceIn(message="   "), db, user)
    except HTTPException as e:
        assert e.status_code == 400, e.status_code
        print("PASS n-2 message trang -> 400")
    else:
        raise AssertionError("n-2: khong raise 400")


async def case3_plan_recs(db):
    """ODO + lich su + moc bao duong + khuyen nghi + prompt + safety."""
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    seen = {}

    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK

    before = _db_snapshot(db)
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await maintenance_chat(
            MaintenanceIn(message="xe tôi cần bảo dưỡng gì không?"), db, user)

    prof = out["profile"]
    assert prof["vehicle"]["plate"] == "30E-111.11", prof["vehicle"]
    assert prof["vehicle"]["odo"] == 12000, prof["vehicle"]
    assert prof["total_orders"] == 2, prof["total_orders"]
    assert {p["name"] for p in prof["top_parts_replaced"]} == {"Lọc dầu", "Má phanh trước"}

    plan = out["plan"]
    by = {i["code"]: i for i in plan["items"]}
    assert by["tire"]["status"] == "overdue", by["tire"]
    assert by["oil"]["status"] == "due_soon" and by["oil"]["km_remaining"] == 1000, by["oil"]
    assert by["oil"]["last_service"]["odo"] == 8000, by["oil"]
    assert by["filter_air"]["status"] == "due_soon", by["filter_air"]
    assert by["brake"]["status"] == "ok", by["brake"]
    assert plan["overdue_count"] == 1 and plan["due_soon_count"] == 2, plan
    assert plan["items"][0]["code"] == "tire", plan["items"][0]  # qua han len truoc

    recs = out["recommendations"]
    assert recs[0]["code"] == "tire" and recs[0]["status"] == "overdue", recs
    tire = recs[0]["service"]
    assert tire and "lốp" in tire["name"].lower(), tire
    oil = next(r for r in recs if r["code"] == "oil")
    assert oil["service"]["name"] == "Thay dầu động cơ", oil["service"]

    from app.agents.common import SAFETY_MAINTENANCE
    assert out["message"] == MOCK_OK + SAFETY_MAINTENANCE
    p = seen["prompt"]
    marks = ["Khach Mot", "Câu hỏi:", "XE ĐANG XÉT:", "LỊCH SỬ SỬA CHỮA",
             "MỐC BẢO DƯỠNG", "KHUYẾN NGHỊ", "NGUYÊN TẮC AN TOÀN"]
    pos = [p.find(m) for m in marks]
    assert all(i >= 0 for i in pos), [m for m, i in zip(marks, pos) if i < 0]
    assert pos == sorted(pos), f"sai thu tu prompt: {pos}"
    db.expire_all()
    assert _db_snapshot(db) == before, "agent lam doi DB"
    print("PASS n-3 ODO + lich su + moc bao duong + khuyen nghi + read-only")


async def case4_idor_staff(db):
    """Khach khac xem xe -> 403; nhan vien xem duoc; xe la -> 404."""
    v2 = db.query(Vehicle).filter_by(license_plate="51F-222.22").first()
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await maintenance_chat(MaintenanceIn(message="bảo dưỡng", vehicle_id=v2.id),
                                   db, {"sub": "c1", "role": "customer",
                                        "name": "Khach Mot"})
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    else:
        raise AssertionError("n-4: khach khac phai 403")

    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await maintenance_chat(MaintenanceIn(message="bảo dưỡng xe", vehicle_id=v2.id),
                                     db, {"sub": "m1", "role": "manager",
                                          "name": "Quan Ly"})
    assert out["profile"]["vehicle"]["plate"] == "51F-222.22", out["profile"]

    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await maintenance_chat(MaintenanceIn(message="bảo dưỡng", vehicle_id=9999),
                                   db, {"sub": "m1", "role": "manager",
                                        "name": "Quan Ly"})
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
    else:
        raise AssertionError("n-4: xe la (nhan vien) phai 404")
    print("PASS n-4 anti-IDOR khach 403, nhan vien xem duoc, xe la 404")


async def case5_thieu_xe(db):
    """Khach chua co xe -> needs."""
    user = {"sub": "c3", "role": "customer", "name": "Khach Ba"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await maintenance_chat(MaintenanceIn(message="xe tôi bảo dưỡng gì"), db, user)
    assert out.get("needs"), out
    assert "profile" not in out, out
    print("PASS n-5 khach chua co xe -> needs")


async def case6_quota_503(db):
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    m1, m2, m3 = _mocks("Hệ thống AI đã vượt quá giới hạn truy cập. "
                        "Bạn vui lòng thử lại sau nhé.")
    try:
        with m1, m2, m3:
            await maintenance_chat(MaintenanceIn(message="bảo dưỡng"), db, user)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        assert (e.headers or {}).get("Retry-After") == "60", e.headers
        print("PASS n-6 quota -> 503 + Retry-After 60")
    else:
        raise AssertionError("n-6: khong raise 503")


async def main():
    db = setup_db()
    try:
        await case1_rbac(db)
        await case2_400_trang(db)
        await case3_plan_recs(db)
        await case4_idor_staff(db)
        await case5_thieu_xe(db)
        await case6_quota_503(db)
    finally:
        db.close()
    print("ALL 6 MAINTENANCE CASES PASSED (mock, khong can key that).")


def test_eval_gate_maintenance_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


def test_maintenance_tools_direct():
    """3 tools bao duong truc tiep tren DB rieng."""
    from app.agents import tools as T

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        c = User(username="nc", password_hash="x", full_name="K",
                 phone="1", role="customer", is_active=1)
        db.add(c)
        db.flush()
        v = Vehicle(license_plate="77N-111.11", make="Mazda", model="CX5",
                    current_odo=52000, user_id=c.id)
        db.add(v)
        db.flush()
        ro = RepairOrder(vehicle_id=v.id, symptoms="kiểm tra phanh", status="Completed",
                         final_odo=10000,
                         created_at=datetime.utcnow() - timedelta(days=300))
        db.add(ro)
        db.commit()

        prof = T.analyze_vehicle_profile(db, v.id)
        assert prof["vehicle"]["odo"] == 52000 and prof["total_orders"] == 1, prof

        plan = T.predict_maintenance(db, v.id)
        by = {i["code"]: i for i in plan["items"]}
        assert by["brake"]["last_service"]["odo"] == 10000, by["brake"]
        assert by["brake"]["status"] == "overdue", by["brake"]     # 52000-10000 >= 20000
        assert by["battery"]["status"] == "overdue", by["battery"]  # 52000 >= 40000
        assert plan["overdue_count"] >= 2, plan

        db.add(ServiceCatalog(service_code="SB", name="Kiểm tra phanh tổng thể",
                              category="Phanh", status="Active", base_price=250000))
        db.commit()
        recs = T.maintenance_recommendations(db, v.id)
        codes = [r["code"] for r in recs]
        assert "brake" in codes, recs
        brake = next(r for r in recs if r["code"] == "brake")
        assert brake["service"] and "phanh" in T._fold(brake["service"]["name"]), brake
        print("PASS n-7 3 tools bao duong truc tiep")
    finally:
        db.close()


def test_maintenance_time_based_and_total_orders():
    """Moc THOI GIAN (interval_months) + total_orders = tong so phieu (khong phai 5).

    Xe di it nhung da ~12 thang chua thay dau -> PHAI bao qua han (theo thoi gian),
    du km con nhieu. purchase_date dung cho hang muc chua co lich su.
    """
    from app.agents import tools as T

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        c = User(username="nt", password_hash="x", full_name="K",
                 phone="1", role="customer", is_active=1)
        db.add(c)
        db.flush()
        v = Vehicle(license_plate="88T-333.33", make="Kia", model="Seltos",
                    current_odo=9000, user_id=c.id, purchase_date="2024-01-15")
        db.add(v)
        db.flush()
        # Thay dau ~370 ngay truoc o ODO 8000 -> 12 thang nhung chi +1000 km.
        now = datetime.utcnow()
        db.add(RepairOrder(vehicle_id=v.id, symptoms="thay dầu máy định kỳ",
                           status="Completed", final_odo=8000,
                           completed_at=now - timedelta(days=370),
                           created_at=now - timedelta(days=370)))
        # Them 6 phieu khong lien quan -> total_orders = 7 (> 5).
        for k in range(6):
            db.add(RepairOrder(vehicle_id=v.id, symptoms=f"việc {k}",
                               status="Completed", final_odo=8000 + k, created_at=now))
        db.commit()

        plan = T.predict_maintenance(db, v.id)
        by = {i["code"]: i for i in plan["items"]}
        oil = by["oil"]
        assert oil["km_status"] == "ok", oil            # +1000 km: chua toi km
        assert oil["time_status"] == "overdue", oil      # ~12 thang >= 6 -> qua han
        assert oil["status"] == "overdue", oil           # gop: qua han theo thoi gian
        assert "time" in oil["due_by"], oil
        assert oil["months_since"] and oil["months_since"] >= 6, oil

        # Hang muc chua co lich su dung purchase_date (2024-01 -> ~33 thang).
        assert by["battery"]["time_base"]["source"] == "purchase_date", by["battery"]
        assert by["battery"]["time_status"] == "overdue", by["battery"]

        prof = T.analyze_vehicle_profile(db, v.id)
        assert prof["total_orders"] == 7, prof["total_orders"]   # khong bi cat con 5
        assert len(prof["history"]) == 5, len(prof["history"])   # hien thi toi da 5

        recs = T.maintenance_recommendations(db, v.id)
        oil_rec = next(r for r in recs if r["code"] == "oil")
        assert "tháng" in oil_rec["reason"], oil_rec
        assert oil_rec["months_since"] and oil_rec["months_since"] >= 6, oil_rec
        print("PASS n-8 moc thoi gian + total_orders that (khong cat con 5)")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
