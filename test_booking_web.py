"""Test dat lich qua web (POST /my-appointments/book).

Kiem tra cung luat chan voi agents: KHONG nhan dat lich vao khung da kin /
KTV da ban (dung chung tools.booking_conflicts); chan ngay xuong nghi va KTV
khong hop le; khung trong van dat duoc binh thuong (tao Appointment + RepairOrder).

Chay: python test_booking_web.py (exit 0 = pass het).
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import User, Vehicle, Appointment, RepairOrder
from app.routers import customer as C


class _Form:
    def __init__(self, data, lists=None):
        self._d = data
        self._l = lists or {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def getlist(self, key):
        return self._l.get(key, [])


class _Req:
    def __init__(self, data, lists=None):
        self._form = _Form(data, lists)

    async def form(self):
        return self._form


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    tech = User(username="bw_t", password_hash="x", full_name="Tho",
                phone="1", role="technician", is_active=1)
    c1 = User(username="bw_c1", password_hash="x", full_name="Khach 1",
              phone="2", role="customer", is_active=1)
    c2 = User(username="bw_c2", password_hash="x", full_name="Khach 2",
              phone="3", role="customer", is_active=1)
    db.add_all([tech, c1, c2])
    db.flush()
    v1 = Vehicle(license_plate="30E-111.11", make="Toyota", model="Vios",
                 user_id=c1.id)
    v2 = Vehicle(license_plate="51F-222.22", make="Honda", model="City",
                 user_id=c2.id)
    db.add_all([v1, v2])
    db.commit()
    return db, {"tech": tech.id, "v1": v1.id, "v2": v2.id, "c2": c2.id}


def _auth(customer_name="bw_c1"):
    return {"sub": customer_name, "role": "customer"}


def test_booking_web_khung_kin_va_thanh_cong():
    db, ids = setup_db()
    try:
        day = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        free_day = (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d")

        # Chiem khung 09:00 cua `day` (suc chua = 1 KTV) -> kin.
        db.add(Appointment(user_id=ids["c2"], vehicle_id=ids["v2"],
                           appointment_date=day, appointment_time="09:00",
                           symptoms="chiem cho", status="Pending"))
        db.commit()
        before = (db.query(Appointment).count(), db.query(RepairOrder).count())

        # 1) Dat vao khung da kin -> redirect loi, KHONG tao gi.
        req = _Req({"vehicle_id": str(ids["v1"]), "appointment_date": day,
                    "appointment_time": "09:00", "appointment_type": "Repair",
                    "symptoms": "máy kêu"})
        with patch.object(C, "check_auth", return_value=_auth()), \
             patch.object(C, "analyze_vehicle_symptoms", return_value=None):
            resp = asyncio.run(C.book_appointment(req, db))
        assert resp.status_code == 302, resp.status_code
        loc = resp.headers["location"]
        assert loc.startswith("/my-appointments?error="), loc
        assert "k%C3%ADn" in loc or "kín" in loc or "b%E1%BA%ADn" in loc, loc
        db.expire_all()
        assert (db.query(Appointment).count(), db.query(RepairOrder).count()) == before, \
            "khung kin thi khong duoc tao lich/phieu"

        # 2) Khung con trong -> dat thanh cong (Appointment + RepairOrder).
        req2 = _Req({"vehicle_id": str(ids["v1"]), "appointment_date": free_day,
                     "appointment_time": "14:30", "appointment_type": "Repair",
                     "symptoms": "máy kêu"})
        with patch.object(C, "check_auth", return_value=_auth()), \
             patch.object(C, "analyze_vehicle_symptoms", return_value=None):
            resp2 = asyncio.run(C.book_appointment(req2, db))
        assert resp2.status_code == 302, resp2.status_code
        assert resp2.headers["location"] == "/my-appointments?booked=1", resp2.headers
        db.expire_all()
        appt = db.query(Appointment).filter_by(
            vehicle_id=ids["v1"], appointment_date=free_day).first()
        assert appt and appt.status == "Pending", appt
        assert db.query(RepairOrder).filter_by(appointment_id=appt.id).count() == 1
        print("PASS web-1 khung kin -> chan (khong tao); khung trong -> tao lich+phieu")
    finally:
        db.close()


def test_booking_web_validate_fields():
    """Web form cung xac minh: ngay xuong nghi -> chan; KTV sai -> chan."""
    db, ids = setup_db()
    try:
        before = (db.query(Appointment).count(), db.query(RepairOrder).count())

        # 1) Ngay le 02/09 (xuong nghi) -> redirect loi, khong tao gi.
        req = _Req({"vehicle_id": str(ids["v1"]), "appointment_date": "2027-09-02",
                    "appointment_time": "09:00", "appointment_type": "Repair",
                    "symptoms": "máy kêu"})
        with patch.object(C, "check_auth", return_value=_auth()), \
             patch.object(C, "analyze_vehicle_symptoms", return_value=None):
            resp = asyncio.run(C.book_appointment(req, db))
        assert resp.status_code == 302, resp.status_code
        loc = resp.headers["location"]
        assert loc.startswith("/my-appointments?error="), loc
        db.expire_all()
        assert (db.query(Appointment).count(), db.query(RepairOrder).count()) == before, \
            "ngay nghi thi khong duoc tao lich/phieu"

        # 1b) Chu Nhat (05/09/2027) cung la ngay nghi -> redirect loi.
        req_sun = _Req({"vehicle_id": str(ids["v1"]), "appointment_date": "2027-09-05",
                        "appointment_time": "09:00", "appointment_type": "Repair",
                        "symptoms": "máy kêu"})
        with patch.object(C, "check_auth", return_value=_auth()), \
             patch.object(C, "analyze_vehicle_symptoms", return_value=None):
            resp_sun = asyncio.run(C.book_appointment(req_sun, db))
        assert resp_sun.status_code == 302, resp_sun.status_code
        assert resp_sun.headers["location"].startswith("/my-appointments?error="), \
            resp_sun.headers["location"]

        # 2) preferred_technician_id khong phai KTV (khach) -> redirect loi.
        day = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        req2 = _Req({"vehicle_id": str(ids["v1"]), "appointment_date": day,
                     "appointment_time": "10:00", "appointment_type": "Repair",
                     "symptoms": "máy kêu",
                     "preferred_technician_id": str(ids["c2"])})
        with patch.object(C, "check_auth", return_value=_auth()), \
             patch.object(C, "analyze_vehicle_symptoms", return_value=None):
            resp2 = asyncio.run(C.book_appointment(req2, db))
        assert resp2.status_code == 302, resp2.status_code
        loc2 = resp2.headers["location"]
        assert loc2.startswith("/my-appointments?error="), loc2
        db.expire_all()
        assert (db.query(Appointment).count(), db.query(RepairOrder).count()) == before, \
            "KTV sai thi khong duoc tao lich/phieu"

        print("PASS web-2 ngay xuong nghi -> chan; KTV sai -> chan (khong tao)")
    finally:
        db.close()


if __name__ == "__main__":
    test_booking_web_khung_kin_va_thanh_cong()
    test_booking_web_validate_fields()
