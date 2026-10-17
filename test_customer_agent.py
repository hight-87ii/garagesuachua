"""Test GĐ2 customer agent (POST /agent/customer/chat truc tiep ham).

Case: 403 sai xe | bien la (anti-IDOR) | needs thieu ngay |
draft ok | duplicate | khung kin -> chan dat | ngay nghi -> chan dat |
gia DB | fallback RAG-off.

Chay: python test_customer_agent.py (exit 0 = pass het).
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
from app.models.models import User, Vehicle, RepairOrder, ServiceCatalog
from app.agents.schemas import ChatIn
from app.agents.customer_agent.router import customer_support

MOCK_OK = "MOCK_REPLY"


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    c1 = User(username="g2_c1", password_hash="x", full_name="Khach 1",
              phone="0901", role="customer", is_active=1)
    c2 = User(username="g2_c2", password_hash="x", full_name="Khach 2",
              phone="0902", role="customer", is_active=1)
    db.add_all([c1, c2])
    db.flush()
    v1 = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                 user_id=c1.id, current_odo=50000)
    v2 = Vehicle(license_plate="51F-999.99", make="Honda", model="City",
                 user_id=c2.id, current_odo=30000)
    db.add_all([v1, v2])
    db.flush()
    db.add(RepairOrder(vehicle_id=v1.id, symptoms="keu loc coc",
                       inspection_result="ro tuyn", estimated_cost=500000,
                       status="Completed"))
    db.flush()
    ro1 = db.query(RepairOrder).filter_by(vehicle_id=v1.id).first()
    db.add(RepairOrder(vehicle_id=v2.id, symptoms="xe c2 keu",
                       inspection_result="kiem tra", estimated_cost=200000,
                       status="Completed"))
    db.flush()
    ro2 = db.query(RepairOrder).filter_by(vehicle_id=v2.id).first()
    from app.models.models import Invoice
    db.add(Invoice(repair_order_id=ro1.id, total_amount=1500000, status="Unpaid"))
    db.add(Invoice(repair_order_id=ro2.id, total_amount=2000000, status="Paid"))
    db.add(ServiceCatalog(service_code="G2S1", name="Rửa xe chi tiết",
                           category="Cham soc", description="Rua vo",
                           status="Active", base_price=200000,
                           duration_minutes=30))
    db.commit()
    return db, {"v1_id": v1.id, "v2_id": v2.id, "c2_id": c2.id}


def _mocks(gemini_ret=MOCK_OK):
    return (patch("app.services.gemini_service.get_gemini_response",
                  return_value=gemini_ret),
            patch("app.agents.tools.search_knowledge", return_value=""),
            patch("app.agents.tools.get_weather_context", return_value=""))


async def case1_403_sai_xe(db, ids):
    """vehicle_id xe nguoi khac -> 403."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    m1, m2, m3 = _mocks()
    try:
        with m1, m2, m3:
            await customer_support(
                ChatIn(message="xem xe nay", vehicle_id=ids["v2_id"]), db, user)
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
        assert "không thuộc tài khoản" in e.detail
        print("PASS g2-1 403 sai xe")
    else:
        raise AssertionError("g2-1: khong raise 403")


async def case2_bien_la(db, ids):
    """Bien so la -> canh bao, khong ro ri lich su xe khac."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(ChatIn(message="xe 99Z-999.99 bị kêu"), db, user)
    assert out.get("vehicle") is None and out.get("history") is None
    assert "KHÔNG thuộc tài khoản" in seen.get("prompt", "")
    print("PASS g2-2 bien la anti-IDOR")


async def case3_needs_thieu_ngay(db, ids):
    """Dat lich thieu ngay -> needs, khong draft."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(ChatIn(message="dat lich"), db, user)
    assert out.get("needs") == ["ngày hẹn (VD: ngày mai, thứ 2, 15/10)"], out.get("needs")
    assert "draft" not in out
    assert "còn thiếu:" in seen.get("prompt", "")
    print("PASS g2-3 needs thieu ngay, khong draft")


async def case4_draft_ok(db, ids):
    """Du xe + ngay -> draft Pending."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await customer_support(ChatIn(message="dat lich ngay mot"), db, user)
    d = out.get("draft")
    assert d and d.get("duplicate") is False and d.get("plate") == "30E-222.33", d
    print(f"PASS g2-4 draft ok #{d['id']} ngay {d['date']}")


async def case5_duplicate(db, ids):
    """Dat trung ngay -> duplicate:true, khong insert them."""
    from app.models.models import Appointment
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await customer_support(ChatIn(message="dat lich ngay mot"), db, user)
    d = out.get("draft")
    assert d and d.get("duplicate") is True, d
    from datetime import datetime, timedelta
    day = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    n = db.query(Appointment).filter(
        Appointment.vehicle_id == ids["v1_id"],
        Appointment.appointment_date == day,
        Appointment.status.in_(["Pending", "Confirmed"])).count()
    assert n == 1, f"DB phai 1 dong, got {n}"
    print("PASS g2-5 duplicate:true, DB 1 dong")


async def case5b_khung_kin(db, ids):
    """Khung gio da kin -> CHAN dat lich (khong tao draft)."""
    from datetime import datetime, timedelta
    from app.models.models import Appointment
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    # Dung "thu 3" (+3 ngay) de tranh trung lich da co o case4/case5.
    day = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    # Chiem khung 09:00 ngay do (suc chua = 1 KTV) bang xe khach khac -> kin.
    db.add(Appointment(user_id=ids["c2_id"], vehicle_id=ids["v2_id"],
                       appointment_date=day, appointment_time="09:00",
                       symptoms="chiem cho", status="Pending"))
    db.commit()
    before = db.query(Appointment).count()
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(
            ChatIn(message="dat lich thu 3 lúc 9h cho xe 30E-222.33"), db, user)
    assert out.get("blocked"), out
    assert "draft" not in out, out
    assert out.get("needs") == ["khung giờ khác"], out.get("needs")
    assert "KHÔNG THỂ ĐẶT LỊCH" in seen.get("prompt", "")
    db.expire_all()
    assert db.query(Appointment).count() == before, "bi chan thi khong tao lich"
    print("PASS g2-5b khung kin -> CHAN dat lich (khong tao draft)")


async def case5c_ngay_nghi(db, ids):
    """Ngay xuong nghi (le 02/09) -> CHAN dat lich (khong tao draft)."""
    from app.models.models import Appointment
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    before = db.query(Appointment).count()
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(
            ChatIn(message="dat lich ngay 02/09/2027 cho xe 30E-222.33"), db, user)
    assert out.get("blocked"), out
    assert "draft" not in out, out
    assert out.get("needs") == ["ngày khác"], out.get("needs")
    assert "KHÔNG THỂ ĐẶT LỊCH" in seen.get("prompt", "")
    db.expire_all()
    assert db.query(Appointment).count() == before, "ngay nghi thi khong tao lich"

    # Chu Nhat (05/09/2027) cung la ngay nghi -> chan.
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out2 = await customer_support(
            ChatIn(message="dat lich ngay 05/09/2027 cho xe 30E-222.33"), db, user)
    assert out2.get("blocked"), out2
    assert out2.get("needs") == ["ngày khác"], out2.get("needs")
    db.expire_all()
    assert db.query(Appointment).count() == before, "Chu Nhat thi khong tao lich"
    print("PASS g2-5c ngay nghi (le + Chu Nhat) -> CHAN dat lich (khong tao draft)")


async def case6_gia_db(db, ids):
    """Suggestions gia dung DB (Active, promo)."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    m1, m2, m3 = _mocks()
    with m1, m2, m3:
        out = await customer_support(ChatIn(message="tôi muốn rửa xe"), db, user)
    names = [s["name"] for s in out.get("suggestions", [])]
    assert names == ["Rửa xe chi tiết"], names
    assert out["suggestions"][0]["price"] == 200000
    print("PASS g2-6 gia DB, chi Active")


async def case7_rag_off(db, ids):
    """Chroma rong (RAG '') -> van tra loi binh thuong."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    m1, m2, m3 = _mocks("MOCK_RAG_OFF van tra loi")
    with m1, m2, m3:
        out = await customer_support(ChatIn(message="tu van bao duong"), db, user)
    assert "MOCK_RAG_OFF" in out.get("message", "")
    print("PASS case7 RAG-off van tra loi")


async def case8_hoa_don_cua_toi(db, ids):
    """2.2: hoi 'hoa don cua toi' -> join Invoice-RepairOrder-Vehicle,
    chi HD xe minh (scope uid), total tu DB."""
    user = {"sub": "g2_c1", "role": "customer", "name": "Khach 1"}
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(ChatIn(message="hóa đơn của tôi"), db, user)
    invs = out.get("invoices", [])
    assert len(invs) == 1, f"ro ri/thieu HD: {invs}"
    assert invs[0]["total"] == 1500000 and invs[0]["plate"] == "30E-222.33", invs[0]
    expect = (f"HD-{invs[0]['id']} ({invs[0]['plate']}, {invs[0]['created']}): "
              f"{invs[0]['total']:,}đ — {invs[0]['status']}")
    assert expect in seen.get("prompt", ""), f"sai render: {expect}"
    print(f"PASS case8 hoa don cua toi -> 1 HD + render '{expect}'")


async def main():
    db, ids = setup_db()
    try:
        await case1_403_sai_xe(db, ids)
        await case2_bien_la(db, ids)
        await case3_needs_thieu_ngay(db, ids)
        await case4_draft_ok(db, ids)
        await case5_duplicate(db, ids)
        await case5b_khung_kin(db, ids)
        await case5c_ngay_nghi(db, ids)
        await case6_gia_db(db, ids)
        await case7_rag_off(db, ids)
        await case8_hoa_don_cua_toi(db, ids)
    finally:
        db.close()
    print("ALL 8 GĐ2 CASES PASSED (mock, khong can key that).")


def test_eval_gate_customer_agent():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


def test_customer_chat_stream_protocol():
    """Stream NDJSON /chat/stream: meta + delta + done, 1 lan goi Gemini."""
    import json as _json
    from app.agents.customer_agent.router import customer_support_stream

    async def run():
        db, ids = setup_db()
        try:
            def fake_stream(message, history, context_msg):
                yield "Xin chao "
                yield "ban!"

            with patch("app.services.gemini_service.get_gemini_response_stream",
                       side_effect=fake_stream), \
                 patch("app.agents.tools.search_knowledge", return_value=""), \
                 patch("app.agents.tools.get_weather_context", return_value=""):
                resp = await customer_support_stream(
                    ChatIn(message="rua xe"),
                    db, {"sub": "g2_c1", "role": "customer", "name": "Khach 1"})
                assert resp.media_type == "application/x-ndjson"
                events = []
                # Doc stream NGAY trong with: generator lazy, de ngoai la goi API that.
                async for chunk in resp.body_iterator:
                    events += [_json.loads(line) for line in chunk.split("\n")
                               if line.strip()]
            assert events[0]["type"] == "meta", events[0]
            assert events[-1] == {"type": "done"}, events[-1]
            full = "".join(e["text"] for e in events if e["type"] == "delta")
            from app.agents.common import SAFETY_CUSTOMER
            assert full.startswith("Xin chao ban!"), full[:40]
            assert full.endswith(SAFETY_CUSTOMER), full[-40:]
            assert events[0]["data"]["suggestions"][0]["name"] == "Rửa xe chi tiết"
        finally:
            db.close()
        print("PASS stream meta + delta + done, 1 lan goi Gemini")

    asyncio.run(run())


if __name__ == "__main__":
    asyncio.run(main())
