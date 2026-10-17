"""Test billing agent (POST /agent/billing/chat truc tiep ham).

Case: RBAC (technician/manager qua, admin bypass, customer 403) | message trang
400 | bao gia (cong+phu tung+VAT+khuyen mai) + ban nhap + cong no dung DB + thu
tu prompt + hau to safety | bao gia bat thuong | KHONG tu thanh toan/xuat hoa
don (DB bat bien) | quota -> 503 + Retry-After | 6 tools truc tiep | chong IDOR
(KTV chi xem phieu + cong no cua minh, Manager xem toan garage) | khuyen mai
dang ap dung kiem tra ca start_date/end_date.

Chay: python test_billing_agent.py (exit 0 = pass het).
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
    User, Vehicle, RepairOrder, RepairOrderPart, SparePart, Invoice, Promotion,
)
from app.agents.schemas import BillingIn
from app.agents.billing_agent.router import billing_chat

MOCK_OK = "MOCK_REPLY"
BIZ = "Đang kinh doanh"
MAIN = {}  # id phieu chinh (chia se giua cac case)


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    tech = User(username="t1", password_hash="x", full_name="Tho",
                phone="0901", role="technician", is_active=1)
    tech2 = User(username="t2", password_hash="x", full_name="Tho 2",
                 phone="0904", role="technician", is_active=1)
    mgr = User(username="m1", password_hash="x", full_name="Quan Ly",
               phone="0902", role="manager", is_active=1)
    cust = User(username="c1", password_hash="x", full_name="Khach",
                phone="0903", role="customer", is_active=1)
    db.add_all([tech, tech2, mgr, cust])
    db.flush()
    v = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                user_id=cust.id)
    db.add(v)
    db.flush()

    p1 = SparePart(part_number="BP-01", name="Má phanh trước", status=BIZ,
                   stock_quantity=10, price=450000)
    p2 = SparePart(part_number="AF-02", name="Lọc gió động cơ", status=BIZ,
                   stock_quantity=10, price=150000)
    db.add_all([p1, p2])
    db.flush()

    ro = RepairOrder(vehicle_id=v.id, symptoms="phanh kêu", status="In Progress",
                     estimated_cost=500000, technician_id=tech.id)
    db.add(ro)
    db.flush()
    db.add(RepairOrderPart(repair_order_id=ro.id, part_id=p1.id, quantity=2,
                           unit_price=450000))
    db.add(RepairOrderPart(repair_order_id=ro.id, part_id=p2.id, quantity=1,
                           unit_price=150000))

    _t = datetime.utcnow().date()
    _fmt = lambda d: d.strftime("%Y-%m-%d")
    db.add(Promotion(title="Rửa xe hè", discount_percent=10, status="Active",
                     start_date=_fmt(_t - timedelta(days=15)),
                     end_date=_fmt(_t + timedelta(days=15))))
    # Status Active NHUNG ngoai khoang ngay -> PHAI bi loai khoi "dang ap dung".
    db.add(Promotion(title="KM hết hạn", discount_percent=20, status="Active",
                     start_date=_fmt(_t - timedelta(days=60)),
                     end_date=_fmt(_t - timedelta(days=1))))
    db.add(Promotion(title="KM chưa tới", discount_percent=15, status="Active",
                     start_date=_fmt(_t + timedelta(days=1)),
                     end_date=_fmt(_t + timedelta(days=60))))
    # Cong no: 1 moi (0_7), 1 qua han (31_plus) — deu thuoc KTV t1.
    db.add(Invoice(repair_order_id=ro.id, total_amount=1000000, status="Unpaid"))
    old_ro = RepairOrder(vehicle_id=v.id, symptoms="cũ", status="Completed",
                         technician_id=tech.id)
    db.add(old_ro)
    db.flush()
    db.add(Invoice(repair_order_id=old_ro.id, total_amount=2000000, status="Unpaid",
                   created_at=datetime.utcnow() - timedelta(days=40)))
    # Lich su hoa don da thu (du mau cho kiem tra lech)
    for k in range(5):
        r = RepairOrder(vehicle_id=v.id, symptoms=f"h{k}", status="Completed",
                        technician_id=tech.id)
        db.add(r)
        db.flush()
        db.add(Invoice(repair_order_id=r.id, total_amount=1000000, status="Paid"))
    # Phieu cua KTV khac (t2) + phieu chua giao -> kiem tra phan quyen du lieu.
    other_ro = RepairOrder(vehicle_id=v.id, symptoms="của t2", status="In Progress",
                           estimated_cost=100000, technician_id=tech2.id)
    unassigned_ro = RepairOrder(vehicle_id=v.id, symptoms="chưa giao", status="Pending",
                                estimated_cost=0)
    db.add_all([other_ro, unassigned_ro])
    db.flush()
    db.add(Invoice(repair_order_id=other_ro.id, total_amount=5000000, status="Unpaid"))
    db.commit()
    # luu id phieu chinh
    MAIN["order_id"] = ro.id
    MAIN["other_order_id"] = other_ro.id
    MAIN["unassigned_order_id"] = unassigned_ro.id
    MAIN["tech_id"] = tech.id
    return db


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))


def _db_snapshot(db):
    return (
        db.query(Invoice).count(),
        sorted((i.id, i.status, float(i.total_amount or 0))
               for i in db.query(Invoice).all()),
        sorted((o.id, o.status) for o in db.query(RepairOrder).all()),
    )


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
    print("PASS b-1 RBAC technician/manager qua, admin bypass, customer 403")


async def case2_400_trang(db):
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await billing_chat(BillingIn(message="  "), db, user)
    except HTTPException as e:
        assert e.status_code == 400, e.status_code
        print("PASS b-2 message trang -> 400")
    else:
        raise AssertionError("b-2: khong raise 400")


async def case3_quote_debt(db):
    """Cong thuc bao gia + ban nhap + cong no + prompt + safety."""
    oid = MAIN["order_id"]
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    seen = {}

    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK

    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await billing_chat(
            BillingIn(message=f"tính tiền cho phiếu #{oid} và xem công nợ"), db, user)

    q = out["quote"]
    assert q["labor"] == 500000, q
    assert q["parts_total"] == 1050000, q          # 2x450k + 1x150k
    assert q["subtotal"] == 1550000, q
    assert q["vat_amount"] == 155000, q             # 10%
    assert q["discount"] == 0 and q["total"] == 1705000, q
    assert out["draft_invoice"]["draft"] is True, out["draft_invoice"]
    assert out["abnormal"]["abnormal"] is False, out["abnormal"]
    assert out["promotions"][0]["title"] == "Rửa xe hè", out["promotions"]
    _ptitles = {p["title"] for p in out["promotions"]}
    assert "KM hết hạn" not in _ptitles and "KM chưa tới" not in _ptitles, _ptitles
    r = out["receivables"]
    assert r["unpaid_count"] == 2 and r["unpaid_amount"] == 3000000, r
    assert r["overdue_count"] == 1 and r["overdue_amount"] == 2000000, r
    assert r["aging"]["0_7"] == 1000000 and r["aging"]["31_plus"] == 2000000, r["aging"]
    from app.agents.common import SAFETY_BILLING
    assert out["message"] == MOCK_OK + SAFETY_BILLING
    p = seen["prompt"]
    marks = ["Tho", "Câu hỏi:", "BÁO GIÁ", "BẢN NHÁP HÓA ĐƠN", "KHUYẾN MÃI ĐANG CHẠY",
             "CÔNG NỢ (chỉ phiếu của bạn):", "NGUYÊN TẮC AN TOÀN"]
    pos = [p.find(m) for m in marks]
    assert all(i >= 0 for i in pos), [m for m, i in zip(marks, pos) if i < 0]
    assert pos == sorted(pos), f"sai thu tu prompt: {pos}"
    print("PASS b-3 bao gia + ban nhap + cong no + prompt + safety")


async def case4_abnormal(db):
    """Bao gia bat thuong: giam gia > 50% va tong <= 0."""
    oid = MAIN["order_id"]
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await billing_chat(
            BillingIn(message=f"kiểm tra báo giá phiếu #{oid}", discount_percent=60),
            db, user)
    assert out["abnormal"]["abnormal"] is True, out["abnormal"]
    assert any("Giảm giá" in r for r in out["abnormal"]["reasons"]), out["abnormal"]
    assert out["actions_proposed"], out["actions_proposed"]

    # Phieu rong (khong cong, khong phu tung) -> tong <= 0
    v = db.query(Vehicle).first()
    empty = RepairOrder(vehicle_id=v.id, symptoms="trống", status="Pending",
                        technician_id=MAIN["tech_id"])
    db.add(empty)
    db.commit()
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out2 = await billing_chat(BillingIn(message="bao giá phiếu", order_id=empty.id),
                                  db, user)
    assert out2["abnormal"]["abnormal"] is True, out2["abnormal"]
    assert any("Tổng tiền" in r for r in out2["abnormal"]["reasons"]), out2["abnormal"]
    print("PASS b-4 phat hien bao gia bat thuong")


async def case5_no_auto_payment(db):
    """Yeu cau xac nhan thanh toan KHONG doi DB (khong tu thu/xuat hoa don)."""
    user = {"sub": "m1", "role": "manager", "name": "Quan Ly"}
    before = _db_snapshot(db)
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await billing_chat(
            BillingIn(message="xác nhận thanh toán hết công nợ và xuất hóa đơn luôn"),
            db, user)
    db.expire_all()
    assert _db_snapshot(db) == before, "agent lam doi hoa don/thanh toan"
    from app.agents.common import SAFETY_BILLING
    assert out["message"].endswith(SAFETY_BILLING)
    print("PASS b-5 khong tu thanh toan/xuat hoa don (DB bat bien)")


async def case6_quota_503(db):
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks("Hệ thống AI đã vượt quá giới hạn truy cập. "
                        "Bạn vui lòng thử lại sau nhé.")
    try:
        with m1, m2, m3:
            await billing_chat(BillingIn(message="công nợ bao nhiêu"), db, user)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        assert (e.headers or {}).get("Retry-After") == "60", e.headers
        print("PASS b-6 quota -> 503 + Retry-After 60")
    else:
        raise AssertionError("b-6: khong raise 503")


async def case7_order_404(db):
    user = {"sub": "t1", "role": "technician", "name": "Tho"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await billing_chat(BillingIn(message="báo giá", order_id=999999), db, user)
    except HTTPException as e:
        assert e.status_code == 404, e.status_code
        print("PASS b-7 phieu khong ton tai -> 404")
    else:
        raise AssertionError("b-7: phieu la phai 404")


async def case9_scope_security(db):
    """Chong IDOR: KTV chi xem phieu + cong no cua minh; Manager xem toan garage."""
    t1 = {"sub": "t1", "role": "technician", "name": "Tho"}
    t2 = {"sub": "t2", "role": "technician", "name": "Tho 2"}
    mgr = {"sub": "m1", "role": "manager", "name": "Quan Ly"}
    other = MAIN["other_order_id"]
    unassigned = MAIN["unassigned_order_id"]

    # 1) KTV t1 xem phieu cua t2 -> 403 (khong lo du lieu).
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await billing_chat(BillingIn(message="báo giá", order_id=other), db, t1)
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    else:
        raise AssertionError("t1 xem phieu t2 phai 403")

    # 2) KTV t2 xem phieu cua minh -> OK.
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out_own = await billing_chat(BillingIn(message="báo giá", order_id=other), db, t2)
    assert out_own["quote"]["order_id"] == other, out_own.get("quote")

    # 3) Manager xem phieu cua t2 -> OK.
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out_mgr = await billing_chat(BillingIn(message="báo giá", order_id=other), db, mgr)
    assert out_mgr["quote"]["order_id"] == other, out_mgr.get("quote")

    # 4) Phieu chua giao -> KTV 403, Manager OK.
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await billing_chat(BillingIn(message="báo giá", order_id=unassigned), db, t1)
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    else:
        raise AssertionError("phieu chua giao voi KTV phai 403")
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out_mgu = await billing_chat(BillingIn(message="báo giá", order_id=unassigned), db, mgr)
    assert out_mgu["quote"]["order_id"] == unassigned, out_mgu.get("quote")

    # 5) Cong no: KTV chi thay cua minh (3M), Manager thay toan garage (8M).
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out_t1 = await billing_chat(BillingIn(message="xem công nợ"), db, t1)
    r = out_t1["receivables"]
    assert r["scope"] == "technician", r
    assert r["unpaid_count"] == 2 and r["unpaid_amount"] == 3000000, r
    assert "CÔNG NỢ (chỉ phiếu của bạn):" in seen["prompt"], seen["prompt"]
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out_mgr2 = await billing_chat(BillingIn(message="xem công nợ"), db, mgr)
    rm = out_mgr2["receivables"]
    assert rm["scope"] == "garage", rm
    assert rm["unpaid_count"] == 3 and rm["unpaid_amount"] == 8000000, rm
    # Admin cung thay toan garage (bypass).
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out_adm = await billing_chat(BillingIn(message="xem công nợ"), db,
                                     {"sub": "m1", "role": "admin", "name": "Admin"})
    assert out_adm["receivables"]["scope"] == "garage", out_adm["receivables"]
    print("PASS b-9 chong IDOR: KTV chi xem phieu + cong no cua minh")


async def main():
    db = setup_db()
    try:
        await case1_rbac(db)
        await case2_400_trang(db)
        await case3_quote_debt(db)
        await case4_abnormal(db)
        await case5_no_auto_payment(db)
        await case6_quota_503(db)
        await case7_order_404(db)
        await case9_scope_security(db)
    finally:
        db.close()
    print("ALL 8 BILLING CASES PASSED (mock, khong can key that).")


def test_eval_gate_billing_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


def test_billing_tools_direct():
    """6 tools bao gia/hoa don truc tiep tren DB rieng."""
    from app.agents import tools as T

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        # Cong thuc thuan
        a = T.compute_amounts(500000, 1050000, 0.1, 0)
        assert a["subtotal"] == 1550000 and a["vat_amount"] == 155000, a
        assert a["total"] == 1705000, a
        b = T.compute_amounts(0, 1550000, 0.1, 2000000)  # discount clamp ve subtotal
        assert b["discount"] == 1550000 and b["total"] == 155000, b

        c = User(username="bc", password_hash="x", full_name="K",
                 phone="1", role="customer", is_active=1)
        db.add(c)
        db.flush()
        v = Vehicle(license_plate="77B-111.11", make="Kia", model="K3", user_id=c.id)
        db.add(v)
        db.flush()
        p = SparePart(part_number="BP1", name="Má phanh", status=BIZ,
                      stock_quantity=5, price=400000)
        db.add(p)
        db.flush()
        ro = RepairOrder(vehicle_id=v.id, symptoms="x", status="In Progress",
                         estimated_cost=300000)
        db.add(ro)
        db.flush()
        db.add(RepairOrderPart(repair_order_id=ro.id, part_id=p.id, quantity=2,
                               unit_price=400000))

        old = RepairOrder(vehicle_id=v.id, symptoms="cũ", status="Completed")
        db.add(old)
        db.flush()
        db.add(Invoice(repair_order_id=old.id, total_amount=500000, status="Unpaid",
                       created_at=datetime.utcnow() - timedelta(days=45)))
        db.commit()

        q = T.compute_order_quote(db, ro.id, discount_percent=10)
        assert q["labor"] == 300000 and q["parts_total"] == 800000, q
        assert q["subtotal"] == 1100000 and q["vat_amount"] == 110000, q
        assert q["discount"] == 110000 and q["total"] == 1100000, q

        d = T.draft_invoice(db, ro.id)
        assert d["draft"] is True and d["total"] == 1210000, d  # khong giam gia

        ab = T.check_quote_abnormal(db, ro.id,
                                    quote=T.compute_order_quote(db, ro.id, 60))
        assert ab["abnormal"] is True, ab

        rc = T.get_receivables(db)
        assert rc["unpaid_count"] == 1 and rc["overdue_count"] == 1, rc
        assert rc["aging"]["31_plus"] == 500000, rc["aging"]
        assert rc["items"][0]["overdue"] is True, rc["items"]
        assert rc["scope"] == "garage", rc

        # Phan quyen tools: KTV chi thay cong no tren phieu minh phu trach.
        t_a = User(username="bt_a", password_hash="x", full_name="A",
                   phone="1", role="technician", is_active=1)
        db.add(t_a)
        db.flush()
        ro.technician_id = t_a.id
        old.technician_id = t_a.id
        db.commit()
        rc_a = T.get_receivables(db, technician_id=t_a.id)
        assert rc_a["scope"] == "technician" and rc_a["unpaid_count"] == 1, rc_a
        assert rc_a["overdue_count"] == 1, rc_a
        rc_other = T.get_receivables(db, technician_id=999999)
        assert rc_other["unpaid_count"] == 0 and rc_other["unpaid_amount"] == 0, rc_other

        db.add(Promotion(title="KM", discount_percent=5, status="Active"))
        db.commit()
        assert T.get_active_promotions(db)[0]["title"] == "KM"
        print("PASS b-8 6 tools bao gia/hoa don truc tiep")
    finally:
        db.close()


def test_promotion_date_window():
    """Khuyen mai 'dang ap dung': status Active VA trong [start_date, end_date].
    Loai het han / chua toi ngay; giu trong khoang, khong moc, moc == hom nay."""
    from app.agents import tools as T

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        today = datetime.utcnow().date()
        f = lambda d: d.strftime("%Y-%m-%d")

        def add(title, start, end, status="Active"):
            db.add(Promotion(title=title, discount_percent=10, status=status,
                             start_date=start, end_date=end))

        add("Đang chạy", f(today - timedelta(days=10)), f(today + timedelta(days=10)))
        add("Không mốc", None, None)
        add("Hết hạn hôm nay", f(today - timedelta(days=30)), f(today))
        add("Bắt đầu hôm nay", f(today), f(today + timedelta(days=30)))
        add("Hết hạn", f(today - timedelta(days=30)), f(today - timedelta(days=1)))
        add("Chưa tới", f(today + timedelta(days=1)), f(today + timedelta(days=30)))
        add("Inactive trong khoảng", f(today - timedelta(days=1)),
            f(today + timedelta(days=1)), status="Inactive")
        db.commit()

        titles = {p["title"] for p in T.get_active_promotions(db, limit=20)}
        assert {"Đang chạy", "Không mốc", "Hết hạn hôm nay", "Bắt đầu hôm nay"} <= titles, titles
        assert "Hết hạn" not in titles and "Chưa tới" not in titles, titles
        assert "Inactive trong khoảng" not in titles, titles
        assert len(T.get_active_promotions(db, limit=1)) == 1, "limit van ton trong"
        print("PASS b-10 khuyen mai dang ap dung (kiem tra start/end)")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
