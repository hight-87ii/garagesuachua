"""Test GĐ3 technical agent (POST /agent/technical/diagnose truc tiep ham).

6 case: co bien so / khong bien so / xe khong lich su /
phu tung het hang bi loai / mat key -> 503 / IDOR khong ap dung.

Chay: python test_technical_agent.py (exit 0 = pass het).
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
from app.models.models import User, Vehicle, RepairOrder, SparePart
from app.agents.schemas import DiagnoseIn
from app.agents.technical_agent.router import diagnose_vehicle

MOCK_OK = "MOCK_REPLY"


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    tech = User(username="g3_tech", password_hash="x", full_name="Tho",
                phone="0901", role="technician", is_active=1)
    other = User(username="g3_other", password_hash="x", full_name="Khach La",
                 phone="0902", role="customer", is_active=1)
    db.add_all([tech, other])
    db.flush()
    v1 = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                 user_id=other.id, current_odo=50000)
    v2 = Vehicle(license_plate="62T-000.02", make="Honda", model="City",
                 user_id=other.id, current_odo=10000)
    db.add_all([v1, v2])
    db.flush()
    db.add(RepairOrder(vehicle_id=v1.id, symptoms="keu loc coc",
                       inspection_result="ro tuyn", estimated_cost=500000,
                       status="Completed"))
    db.add_all([
        SparePart(part_number="G3P1", name="Rotuyn lái", brand="Toyota",
                  status="Đang kinh doanh", stock_quantity=12, price=450000,
                  warranty_period="12 tháng"),
        SparePart(part_number="G3P2", name="Rotuyn lái hết hàng", brand="Toyota",
                  status="Đang kinh doanh", stock_quantity=0, price=400000),
    ])
    db.commit()
    return db


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))

USER = {"sub": "g3_tech", "role": "technician", "name": "Tho"}


async def case1_co_bien_so(db):
    """license_plate tuong minh -> resolve xe + lich su."""
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await diagnose_vehicle(
            DiagnoseIn(symptom="kêu", license_plate="30e-222.33"), db, USER)
    assert out.get("vehicle", {}).get("plate") == "30E-222.33", out.get("vehicle")
    assert len(out.get("history", [])) >= 1
    print("PASS t3-1 co bien so -> xe + lich su")


async def case2_khong_bien_so(db):
    """Khong bien so -> phan tich chung, khong vehicle/history."""
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await diagnose_vehicle(DiagnoseIn(symptom="máy rung chung chung"), db, USER)
    assert out.get("vehicle") is None and out.get("history") is None
    assert "MOCK" in out.get("message", "")
    print("PASS t3-2 khong bien so -> chung, van tra loi")


async def case3_xe_khong_lich_su(db):
    """Xe co nhung chua lich su -> '(chua co lich su)', van 200."""
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await diagnose_vehicle(
            DiagnoseIn(symptom="kiem tra", license_plate="62T-000.02"), db, USER)
    assert out.get("vehicle", {}).get("plate") == "62T-000.02"
    assert out.get("history") == []
    assert "(chưa có lịch sử)" in seen.get("prompt", "")
    print("PASS t3-3 xe khong lich su -> nhan + van 200")


async def case4_het_hang_bi_loai(db):
    """Part stock=0 bi loai ngay tu SQL, khong vao prompt."""
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await diagnose_vehicle(DiagnoseIn(symptom="rotuyn lái"), db, USER)
    assert [p["part_number"] for p in out.get("parts", [])] == ["G3P1"], out.get("parts")
    assert "G3P2" not in seen.get("prompt", ""), "het hang phai bi loai"
    print("PASS t3-4 het hang bi loai")


async def case5_mat_key_503(db):
    """Mat key -> 503 msg TV."""
    m1, m2, m3 = _mocks("Lỗi: Chưa cấu hình GEMINI_API_KEY trong file .env.")
    try:
        with m1, m2, m3:
            await diagnose_vehicle(DiagnoseIn(symptom="kêu"), db, USER)
    except HTTPException as e:
        assert e.status_code == 503, e.status_code
        assert "GEMINI" in e.detail or "AI" in e.detail
        print("PASS t3-5 mat key -> 503 TV")
    else:
        raise AssertionError("t3-5: khong raise 503")


async def case6_idor_khong_ap_dung(db):
    """KTV xem duoc moi xe: bien xe user khac van resolve + co history."""
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await diagnose_vehicle(
            DiagnoseIn(symptom="xe 30E-222.33 kêu"), db, USER)
    assert out.get("vehicle", {}).get("plate") == "30E-222.33", out.get("vehicle")
    assert len(out.get("history", [])) >= 1, "KTV phai thay lich su moi xe"
    print("PASS t3-6 IDOR khong ap dung (KTV thay moi xe)")


async def main():
    db = setup_db()
    try:
        await case1_co_bien_so(db)
        await case2_khong_bien_so(db)
        await case3_xe_khong_lich_su(db)
        await case4_het_hang_bi_loai(db)
        await case5_mat_key_503(db)
        await case6_idor_khong_ap_dung(db)
    finally:
        db.close()
    print("ALL 6 GĐ3 CASES PASSED (mock, khong can key that).")


def test_eval_gate_technical_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
