"""Test scheduling & reception agent (POST /agent/scheduling/chat truc tiep ham).

Case: RBAC (customer/technician/manager qua, admin bypass, role la 403) |
message trang 400 | khung gio trong + KTV + trung lich (khong ghi DB) |
tao lich NHAP khi co y dinh dat lich (chi Appointment, CHUA co phieu) |
CHAN dat khi khung da kin (khong tao gi) nhung khung trong van dat duoc |
xac minh truong truc tiep (gio ngoai khung 400, KTV sai 400, ngay nghi chan) |
xac nhan lich -> moi sinh phieu + Confirmed (idempotent, pham vi so huu) |
quota -> 503 + Retry-After | tools truc tiep + khoa chong dat dong thoi.

Chay: python test_scheduling_agent.py (exit 0 = pass het).
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
    User, Vehicle, RepairOrder, Appointment,
)
from app.agents.schemas import ScheduleIn
from app.agents.scheduling_agent.router import scheduling_chat

MOCK_OK = "MOCK_REPLY"
FUTURE = "2027-06-01"


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    mgr = User(username="m1", password_hash="x", full_name="Quan Ly",
               phone="0901", role="manager", is_active=1)
    tech = User(username="t1", password_hash="x", full_name="Tho Chin",
                phone="0902", role="technician", is_active=1)
    c1 = User(username="c1", password_hash="x", full_name="Khach Mot",
              phone="0903", role="customer", is_active=1)
    c2 = User(username="c2", password_hash="x", full_name="Khach Hai",
              phone="0904", role="customer", is_active=1)
    db.add_all([mgr, tech, c1, c2])
    db.flush()
    v1 = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                 user_id=c1.id)
    v2 = Vehicle(license_plate="51F-999.99", make="Honda", model="City",
                 user_id=c2.id)
    v3 = Vehicle(license_plate="30E-333.33", make="Ford", model="Ranger",
                 user_id=c1.id)
    db.add_all([v1, v2, v3])
    db.commit()
    return db


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))


async def case1_rbac(db):
    """customer/technician/manager qua, admin bypass, role khac 403."""
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
        raise AssertionError("role la phai 403")
    print("PASS s-1 RBAC customer/technician/manager qua, admin bypass, guest 403")


async def case2_400_trang(db):
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await scheduling_chat(ScheduleIn(message="   "), db, user)
    except HTTPException as e:
        assert e.status_code == 400, e.status_code
        print("PASS s-2 message trang -> 400")
    else:
        raise AssertionError("s-2: khong raise 400")


async def case3_slots_techs_conflicts(db):
    """Khung gio trong + KTV + trung lich, va KHONG ghi DB khi chi hoi."""
    from app.agents import tools as T
    t1 = db.query(User).filter_by(username="t1").first()
    c1 = db.query(User).filter_by(username="c1").first()
    v1 = db.query(Vehicle).filter_by(license_plate="30E-222.33").first()
    # Chiem khung 09:00 (suc chua = 1 KTV hoat dong -> kin)
    db.add(Appointment(user_id=c1.id, vehicle_id=v1.id, appointment_date=FUTURE,
                       appointment_time="09:00", symptoms="keu", status="Pending",
                       preferred_technician_id=t1.id))
    db.commit()

    snapshot = lambda: (db.query(Appointment).count(), db.query(RepairOrder).count())
    before = snapshot()

    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    seen = {}

    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK

    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await scheduling_chat(
            ScheduleIn(message=f"ngày {FUTURE} lúc 9h còn khung giờ nào trống, "
                               "gợi ý kỹ thuật viên rảnh", date=FUTURE), db, user)

    db.expire_all()
    assert snapshot() == before, "chi hoi ma da ghi DB"

    slots = out["available_slots"]
    assert "09:00" in slots["busy"] and "09:00" not in slots["free"], slots
    assert slots["free"], "phai con khung khac trong"
    assert out["technicians"][0]["name"] == "Tho Chin", out["technicians"]
    assert out["conflicts"]["has_conflict"] is True, out["conflicts"]
    assert out["conflicts"]["overload"] is True, out["conflicts"]
    p = seen["prompt"]
    for mark in ("KHUNG GIỜ TRỐNG:", "KTV GỢI Ý:", "CẢNH BÁO XUNG ĐỘT:",
                 "NGUYÊN TẮC AN TOÀN"):
        assert mark in p, mark
    from app.agents.common import SAFETY_SCHEDULING
    assert out["message"] == MOCK_OK + SAFETY_SCHEDULING

    # Tools truc tiep
    assert T.get_available_slots(db, FUTURE)["busy"] == ["09:00"]
    assert T.detect_schedule_conflicts(db, FUTURE, "09:00")["overload"] is True
    assert T.detect_schedule_conflicts(db, FUTURE, "08:00")["has_conflict"] is False
    assert T.suggest_technicians(db, FUTURE, "09:00")[0]["busy_at_slot"] is True
    print("PASS s-3 khung gio trong + KTV + trung lich (khong ghi DB)")


async def case4_draft_booking(db):
    """Y dinh dat lich -> tao lich NHAP (Pending) cho xe cua khach, CHUA co phieu.

    Luong nhap dung: chi tao Appointment; khi xac nhan moi sinh RepairOrder.
    """
    c1 = db.query(User).filter_by(username="c1").first()
    before = db.query(Appointment).count()
    before_ro = db.query(RepairOrder).count()
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await scheduling_chat(
            ScheduleIn(message=f"đặt lịch ngày {FUTURE} lúc 9h cho xe 30E-222.33"),
            db, user)
    assert "draft" in out, out
    draft = out["draft"]
    assert draft["plate"] == "30E-222.33", draft
    appt = db.query(Appointment).filter_by(id=draft["id"]).first()
    assert appt and appt.status == "Pending", "lich AI tao phai Pending"
    assert appt.user_id == c1.id, "lich phai thuoc dung khach"
    # Lich NHAP: KHONG tao phieu sua chua som.
    assert db.query(RepairOrder).filter_by(appointment_id=appt.id).first() is None, \
        "lich nhap khong duoc tao phieu"
    assert db.query(RepairOrder).count() == before_ro, "khong duoc sinh phieu moi"
    assert db.query(Appointment).count() == before + 1

    # Xac nhan lich nhap -> moi sinh phieu + chuyen Confirmed.
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        confirmed = await scheduling_chat(
            ScheduleIn(message="xác nhận lịch", appointment_id=appt.id), db, user)
    order = confirmed["order"]
    assert order["created"] is True and order["appointment_status"] == "Confirmed", order
    db.expire_all()
    assert db.query(RepairOrder).filter_by(appointment_id=appt.id).count() == 1
    assert db.query(Appointment).filter_by(id=appt.id).first().status == "Confirmed"
    print("PASS s-4 dat lich -> lich NHAP Pending (chua co phieu) -> xac nhan moi sinh phieu")


async def case4b_khung_kin(db):
    """Khung gio DA KIN -> CHAN dat lich (khong tao gi); khung trong van dat duoc."""
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    before = (db.query(Appointment).count(), db.query(RepairOrder).count())

    # 09:00 da kin (case3 chiem; suc chua = 1 KTV). Dung xe v3 de tranh trung-lich.
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await scheduling_chat(
            ScheduleIn(message=f"đặt lịch ngày {FUTURE} lúc 9h cho xe 30E-333.33",
                       date=FUTURE, time="09:00"), db, user)
    assert out.get("blocked"), out
    assert "draft" not in out, out
    assert out.get("needs"), out
    # Khong tao gi khi bi chan.
    db.expire_all()
    assert (db.query(Appointment).count(), db.query(RepairOrder).count()) == before, \
        "bi chan thi khong duoc tao lich/phieu"

    # Khung con trong (14:30) -> van dat duoc (khong chan qua tay).
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        ok = await scheduling_chat(
            ScheduleIn(message=f"đặt lịch ngày {FUTURE} lúc 14h30 cho xe 30E-333.33",
                       date=FUTURE, time="14:30"), db, user)
    assert ok.get("draft") and not ok.get("blocked"), ok
    assert db.query(Appointment).count() == before[0] + 1
    print("PASS s-4b khung kin -> CHAN dat lich; khung trong van dat duoc")


async def case4c_validate_fields(db):
    """Xac minh truong truc tiep: gio ngoai khung 400 | KTV sai 400 | ngay nghi -> chan."""
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}

    # 1) data.time ngoai WORK_SLOTS -> 400.
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await scheduling_chat(ScheduleIn(message="đặt lịch", date=FUTURE, time="07:00"),
                                  db, user)
    except HTTPException as e:
        assert e.status_code == 400 and "hợp lệ" in e.detail, e.detail
    else:
        raise AssertionError("gio ngoai khung phai 400")

    # 2) preferred_technician_id khong phai KTV (khach) -> 400.
    c1 = db.query(User).filter_by(username="c1").first()
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await scheduling_chat(ScheduleIn(message="đặt lịch", date=FUTURE,
                                             time="09:00",
                                             preferred_technician_id=c1.id), db, user)
    except HTTPException as e:
        assert e.status_code == 400 and "Kỹ thuật viên" in e.detail, e.detail
    else:
        raise AssertionError("KTV sai phai 400")

    # 3) Ngay nghi le (02/09) -> chan dat lich, khong tao gi.
    c1_v3 = db.query(Vehicle).filter_by(license_plate="30E-333.33").first()
    before = db.query(Appointment).count()
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await scheduling_chat(
            ScheduleIn(message="đặt lịch ngày 02/09/2027 lúc 9h cho xe 30E-333.33",
                       date="2027-09-02", time="09:00"), db, user)
    assert out.get("closed"), out
    assert out.get("blocked"), out
    assert "draft" not in out, out
    db.expire_all()
    assert db.query(Appointment).count() == before, "ngay nghi khong duoc tao lich"
    print("PASS s-4c gio ngoai khung 400, KTV sai 400, ngay nghi -> chan")


async def case5_convert(db):
    """Chuyen lich thanh phieu: idempotent + pham vi so huu."""
    c1 = db.query(User).filter_by(username="c1").first()
    c2 = db.query(User).filter_by(username="c2").first()
    v2 = db.query(Vehicle).filter_by(license_plate="51F-999.99").first()

    # Lich cua c2, chua co phieu
    a_c2 = Appointment(user_id=c2.id, vehicle_id=v2.id, appointment_date=FUTURE,
                       appointment_time="15:30", symptoms="rung", status="Pending")
    db.add(a_c2)
    db.commit()

    # customer khac (c1) khong duoc chuyen lich cua c2 -> 403
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await scheduling_chat(
                ScheduleIn(message="xác nhận lịch", appointment_id=a_c2.id),
                db, {"sub": "c1", "role": "customer", "name": "Khach Mot"})
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    else:
        raise AssertionError("s-5: khach khac phai 403")

    # manager chuyen duoc (idempotent)
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await scheduling_chat(
            ScheduleIn(message="chuyển lịch thành phiếu", appointment_id=a_c2.id),
            db, {"sub": "m1", "role": "manager", "name": "Quan Ly"})
    order = out["order"]
    assert order["created"] is True and order["appointment_id"] == a_c2.id, order
    db.expire_all()
    db_a = db.query(Appointment).filter_by(id=a_c2.id).first()
    assert db_a.status == "Confirmed", "lich Pending phai -> Confirmed"
    n_ro = db.query(RepairOrder).filter_by(appointment_id=a_c2.id).count()
    assert n_ro == 1, n_ro

    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out2 = await scheduling_chat(
            ScheduleIn(message="xác nhận lịch", appointment_id=a_c2.id),
            db, {"sub": "m1", "role": "manager", "name": "Quan Ly"})
    assert out2["order"]["created"] is False, out2["order"]
    assert db.query(RepairOrder).filter_by(appointment_id=a_c2.id).count() == 1
    print("PASS s-5 chuyen lich thanh phieu (idempotent + pham vi so huu)")


async def case6_quota_503(db):
    user = {"sub": "c1", "role": "customer", "name": "Khach Mot"}
    m1, m2, m3 = _mocks("Hệ thống AI đã vượt quá giới hạn truy cập. "
                        "Bạn vui lòng thử lại sau nhé.")
    try:
        with m1, m2, m3:
            await scheduling_chat(ScheduleIn(message="còn giờ trống nào"),
                                  db, user)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        assert (e.headers or {}).get("Retry-After") == "60", e.headers
        print("PASS s-6 quota -> 503 + Retry-After 60")
    else:
        raise AssertionError("s-6: khong raise 503")


async def main():
    db = setup_db()
    try:
        await case1_rbac(db)
        await case2_400_trang(db)
        await case3_slots_techs_conflicts(db)
        await case4_draft_booking(db)
        await case4b_khung_kin(db)
        await case4c_validate_fields(db)
        await case5_convert(db)
        await case6_quota_503(db)
    finally:
        db.close()
    print("ALL 8 SCHEDULING CASES PASSED (mock, khong can key that).")


def test_eval_gate_scheduling_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


def test_scheduling_tools_direct():
    """4 tools lich hen truc tiep tren DB rieng."""
    from app.agents import tools as T

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        t1 = User(username="st1", password_hash="x", full_name="Tho A",
                  phone="1", role="technician", is_active=1)
        t2 = User(username="st2", password_hash="x", full_name="Tho B",
                  phone="2", role="technician", is_active=1)
        c1 = User(username="sc1", password_hash="x", full_name="Khach",
                  phone="3", role="customer", is_active=1)
        db.add_all([t1, t2, c1])
        db.flush()
        v = Vehicle(license_plate="77H-123.45", make="Kia", model="Morning",
                    user_id=c1.id)
        db.add(v)
        db.flush()
        db.add(Appointment(user_id=c1.id, vehicle_id=v.id, appointment_date=FUTURE,
                           appointment_time="09:00", symptoms="keu", status="Pending",
                           preferred_technician_id=t1.id))
        db.commit()

        slots = T.get_available_slots(db, FUTURE)
        assert slots["slots"][1]["time"] == "09:00"
        assert slots["slots"][1]["booked"] == 1 and slots["slots"][1]["free"] is True
        assert "09:00" in slots["free"]  # capacity = 2 KTV

        slots_t1 = T.get_available_slots(db, FUTURE, technician_id=t1.id)
        assert "09:00" in slots_t1["busy"], slots_t1

        techs = T.suggest_technicians(db, FUTURE, "09:00")
        assert techs[0]["name"] == "Tho B" and techs[0]["busy_at_slot"] is False
        assert techs[1]["name"] == "Tho A" and techs[1]["busy_at_slot"] is True

        assert T.detect_schedule_conflicts(db, FUTURE, "09:00")["has_conflict"] is False
        assert T.detect_schedule_conflicts(db, FUTURE, "09:00", technician_id=t1.id)[
            "has_conflict"] is True

        a = db.query(Appointment).first()
        res = T.convert_appointment_to_order(db, a.id)
        assert res["created"] is True and res["status"] == "Pending", res
        db.expire_all()
        assert db.get(Appointment, a.id).status == "Confirmed"
        again = T.convert_appointment_to_order(db, a.id)
        assert again["created"] is False and again["id"] == res["id"]
        assert db.query(RepairOrder).filter_by(appointment_id=a.id).count() == 1

        # Du lieu cu / dat qua web: lich Pending da co phieu -> convert van phai
        # CHOT lich (Pending -> Confirmed), khong duoc tra ve som roi bo quen.
        a2 = Appointment(user_id=c1.id, vehicle_id=v.id, appointment_date="2027-06-02",
                         appointment_time="10:30", symptoms="cu", status="Pending")
        db.add(a2)
        db.flush()
        legacy_ro = RepairOrder(vehicle_id=v.id, appointment_id=a2.id,
                                order_type="Repair", symptoms="cu", status="Pending")
        db.add(legacy_ro)
        db.commit()
        legacy = T.convert_appointment_to_order(db, a2.id)
        assert legacy["created"] is False and legacy["id"] == legacy_ro.id, legacy
        assert legacy["appointment_status"] == "Confirmed", legacy
        db.expire_all()
        assert db.get(Appointment, a2.id).status == "Confirmed", "lich cu phai duoc chot"
        print("PASS s-7 4 tools lich hen truc tiep (+ lich cu co phieu van duoc Confirmed)")

        # --- CHAN dat lich khi khung kin / KTV ban (1 nguon duy nhat: tools) ---
        DAY = "2027-07-01"
        v2 = Vehicle(license_plate="77H-777.77", make="Mazda", model="CX5", user_id=c1.id)
        v3 = Vehicle(license_plate="77H-888.88", make="Ford", model="Ranger", user_id=c1.id)
        db.add_all([v2, v3])
        db.commit()
        # Khung 09:00 co 1 lich cho t1 (suc chua 2) -> chua kin; t1 ban, t2 ranh.
        db.add(Appointment(user_id=c1.id, vehicle_id=v.id, appointment_date=DAY,
                           appointment_time="09:00", symptoms="x", status="Pending",
                           preferred_technician_id=t1.id))
        db.commit()
        assert T.booking_conflicts(db, DAY, "09:00", technician_id=t1.id), "t1 dang ban"
        assert T.booking_conflicts(db, DAY, "09:00", technician_id=t2.id) == [], "t2 ranh"
        assert T.booking_conflicts(db, DAY, "09:00") == [], "chua kin -> khong chan"
        assert T.booking_conflicts(db, DAY, None, technician_id=t1.id) == [], \
            "chua chot gio -> khong ket luan"
        # Dat vao khung t1 dang ban -> blocked, khong tao gi.
        blk = T.create_appointment_draft(db, c1.id, v2.id, DAY, "09:00",
                                         symptoms="x", preferred_technician_id=t1.id)
        assert blk["blocked"] is True and blk["id"] is None, blk
        assert db.query(Appointment).filter_by(vehicle_id=v2.id).count() == 0
        # Khung 14:30 voi t2 (ranh) -> dat duoc (khong chan qua tay).
        ok = T.create_appointment_draft(db, c1.id, v2.id, DAY, "14:30",
                                        symptoms="x", preferred_technician_id=t2.id)
        assert ok.get("blocked") is not True and ok["id"], ok
        # Lam kin khung 13:30 (2/2 cho) -> chan ke ca khi khong chi dinh KTV.
        for tech in (t1, t2):
            db.add(Appointment(user_id=c1.id, vehicle_id=v.id, appointment_date=DAY,
                               appointment_time="13:30", symptoms="x", status="Pending",
                               preferred_technician_id=tech.id))
        db.commit()
        kin = T.create_appointment_draft(db, c1.id, v3.id, DAY, "13:30", symptoms="x")
        assert kin["blocked"] is True and "kín" in kin["reasons"][0], kin
        assert db.query(Appointment).filter_by(vehicle_id=v3.id).count() == 0
        print("PASS s-7b chan dat khi khung kin / KTV ban (1 nguon: tools)")
    finally:
        db.close()


def test_booking_concurrent_lock():
    """2 request DONG THOI dat cung khung chi con 1 cho -> chi 1 thanh cong.

    Dung SQLite file + 2 Session/2 thread de mo phong that; BOOKING_LOCK dam bao
    buoc kiem-tra-roi-tao la nguyen tu (khong dat trung).
    """
    import os
    import tempfile
    import threading
    from app.agents import tools as T

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        eng = create_engine(f"sqlite:///{os.path.join(td, 'bk.db')}",
                            connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        Session = sessionmaker(bind=eng)
        seed = Session()
        tech = User(username="ct_t", password_hash="x", full_name="Tho",
                    phone="1", role="technician", is_active=1)
        c = User(username="ct_c", password_hash="x", full_name="Khach",
                 phone="2", role="customer", is_active=1)
        seed.add_all([tech, c])
        seed.flush()
        v1 = Vehicle(license_plate="30A-111.11", make="A", model="a", user_id=c.id)
        v2 = Vehicle(license_plate="30A-222.22", make="B", model="b", user_id=c.id)
        seed.add_all([v1, v2])
        seed.commit()
        cid, v1id, v2id = c.id, v1.id, v2.id
        seed.close()

        DAY = "2027-08-02"  # capacity = 1 KTV
        barrier = threading.Barrier(2)
        results, errors = [], []

        def worker(vid):
            s = Session()
            try:
                barrier.wait(timeout=10)
                results.append(T.create_appointment_draft(s, cid, vid, DAY, "09:00", "x"))
            except Exception as e:  # pragma: no cover - chan loi bat ngo
                errors.append(repr(e))
            finally:
                s.close()

        ts = [threading.Thread(target=worker, args=(vid,)) for vid in (v1id, v2id)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=15)

        assert not errors, errors
        created = [r for r in results if r.get("id") and not r.get("blocked")]
        blocked = [r for r in results if r.get("blocked")]
        assert len(created) == 1 and len(blocked) == 1, results
        chk = Session()
        try:
            assert chk.query(Appointment).filter_by(
                appointment_date=DAY, appointment_time="09:00").count() == 1
        finally:
            chk.close()
        print("PASS s-8 khoa chong dat trung: 2 request dong thoi -> chi 1 thanh cong")


def test_schedule_policy_functions():
    """Chinh sach lich: le co dinh + nghi Chu Nhat mac dinh + cau hinh qua env."""
    import os
    from app.core import schedule_config as SC

    # Mac dinh: le 02/09 nghi; Chu Nhat nghi; ngay thuong lam; gio thuoc khung.
    assert SC.day_off_reason("2027-09-02"), "02/09 la ngay le"
    assert SC.day_off_reason("2027-06-06"), "Chu Nhat nghi (mac dinh)"
    assert SC.day_off_reason("2027-06-01") is None, "Thu Ba lam binh thuong"
    assert SC.is_valid_slot("09:00") and not SC.is_valid_slot("07:00")
    assert SC.is_valid_slot(None)

    try:
        # Mo ca tuan + them ngay nghi cu the qua env.
        os.environ["GARAGE_CLOSED_WEEKDAYS"] = ""       # rong -> khong nghi thu nao
        os.environ["GARAGE_HOLIDAYS"] = "2027-12-25"
        SC.reload_policy()
        assert SC.day_off_reason("2027-06-06") is None, "da mo Chu Nhat"
        assert SC.day_off_reason("2027-12-25"), "ngay nghi cau hinh"
        assert SC.day_off_reason("2027-06-01") is None
    finally:
        os.environ.pop("GARAGE_HOLIDAYS", None)
        os.environ.pop("GARAGE_CLOSED_WEEKDAYS", None)
        SC.reload_policy()

    # Sau khi reset: Chu Nhat lai nghi mac dinh.
    assert SC.day_off_reason("2027-06-06"), "mac dinh Chu Nhat nghi"
    print("PASS s-9 chinh sach lich (le/Chu Nhat/ngay nghi env)")


if __name__ == "__main__":
    asyncio.run(main())
