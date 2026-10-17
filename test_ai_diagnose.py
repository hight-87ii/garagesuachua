"""Mo rong test AI diagnose/chat: 4 case mock, khong can key that.

- Case 1 (history dung xe): customer chat kem vehicle_id dung -> tra history.
- Case 2 (sai vehicle_id -> 403, mau main.py:441): customer chat + main.ai_diagnose
  voi xe cua nguoi khac -> 403 "Xe nay khong thuoc tai khoan cua ban."
- Case 3 (mat key -> msg loi TV): mock get_gemini_response tra NO_KEY_MSG
  ("Loi: Chua cau hinh GEMINI_API_KEY...") -> router 503 msg TV.
- Case 4 (Chroma rong -> van tra loi): mock search_knowledge -> "" + mock
  gemini tra cau tra loi -> diagnose van co message.
- Case 5 (chat_bot stream chung): di qua call_gemini_safe(stream=True),
  body du chunk + history forward xuong service.
- Case 6 (stream loi TV): service raise 503/429 -> body la text TV dong nhat.

Chay: python test_ai_diagnose.py (exit 0 = pass het).
"""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import User, Vehicle, RepairOrder, Invoice
from app.agents.schemas import ChatIn, DiagnoseIn
from app.agents.customer_agent.router import customer_support
from app.agents.technical_agent.router import diagnose_vehicle

MOCK_OK = "MOCK: da nhan lich su xe, goi y mang xe toi xuong kiem tra."
NO_KEY_MSG = "Lỗi: Chưa cấu hình GEMINI_API_KEY trong file .env."


def setup_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    c1 = User(username="cust1", password_hash="x", full_name="Khach 1",
              phone="0901", role="customer", is_active=1)
    c2 = User(username="cust2", password_hash="x", full_name="Khach 2",
              phone="0902", role="customer", is_active=1)
    tech = User(username="tech1", password_hash="x", full_name="Tho 1",
                phone="0903", role="technician", is_active=1)
    db.add_all([c1, c2, tech])
    db.flush()
    v1 = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                 user_id=c1.id, current_odo=50000)
    v2 = Vehicle(license_plate="51F-999.99", make="Honda", model="City",
                 user_id=c2.id, current_odo=30000)
    db.add_all([v1, v2])
    db.flush()
    ro = RepairOrder(vehicle_id=v1.id, symptoms="keu loc coc khi danh lai",
                     inspection_result="ro tuyn sup", estimated_cost=500000,
                     status="Completed")
    db.add(ro)
    db.flush()
    ro2 = RepairOrder(vehicle_id=v2.id, symptoms="xe cust2 keu",
                      inspection_result="kiem tra", estimated_cost=200000,
                      status="Completed")
    db.add(ro2)
    db.flush()
    db.add(Invoice(repair_order_id=ro.id, total_amount=1500000, status="Unpaid"))
    db.add(Invoice(repair_order_id=ro2.id, total_amount=2000000, status="Paid"))
    db.commit()
    ids = {"c1_id": c1.id, "c2_id": c2.id, "v1_id": v1.id, "v2_id": v2.id}
    return db, ids


async def case1_history_dung_xe(db, ids):
    """Customer chat dung vehicle_id -> co vehicle + history."""
    user = {"sub": "cust1", "role": "customer", "name": "Khach 1"}
    data = ChatIn(message="cho xem lich su xe cua toi", vehicle_id=ids["v1_id"])
    with patch("app.services.gemini_service.get_gemini_response", return_value=MOCK_OK), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user)
    assert out.get("vehicle", {}).get("id") == ids["v1_id"], f"sai vehicle: {out.get('vehicle')}"
    assert len(out.get("history", [])) >= 1, "thieu history xe dung"
    assert "MOCK" in out.get("message", ""), "thieu message mock"
    print("PASS case1 history dung xe:", out["vehicle"], f"history={len(out['history'])}")

    # 1b. 2.1.2: fallback bien so (normalize + substring, scope uid).
    data = ChatIn(message="xe 30E-222.33 kêu")
    with patch("app.services.gemini_service.get_gemini_response", return_value=MOCK_OK), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user)
    assert out.get("vehicle", {}).get("plate") == "30E-222.33", f"sai plate: {out.get('vehicle')}"
    print("PASS case1b fallback bien so -> plate 30E-222.33")

    # 1c. 2.1.3 anti-IDOR: bien so la (match regex) nhung khong phai xe minh
    # -> inject "KHONG thuoc tai khoan", KHONG tra lich su xe khac.
    seen = {}
    def spy_gemini(message, history, context_msg):
        seen["prompt"] = message
        return MOCK_OK
    data = ChatIn(message="xe 99Z-999.99 bị kêu")
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy_gemini), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user)
    assert out.get("vehicle") is None, f"ro ri xe: {out.get('vehicle')}"
    assert out.get("history") is None, "ro ri lich su xe khac"
    assert "KHÔNG thuộc tài khoản" in seen.get("prompt", ""), "thieu inject canh bao"
    print("PASS case1c bien so la -> canh bao, khong ro ri (anti-IDOR)")

    # 1d. 2.1.4: 1 xe duy nhat + keyword -> auto chon, inject dung format.
    seen2 = {}
    def spy_gemini2(message, history, context_msg):
        seen2["prompt"] = message
        return MOCK_OK
    data = ChatIn(message="cho xem lich su xe cua toi")
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy_gemini2), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user)
    assert out.get("vehicle", {}).get("id") == ids["v1_id"], f"khong auto chon: {out.get('vehicle')}"
    h0 = out["history"][0]
    assert set(["id", "status", "symptoms", "inspection", "labor", "parts", "created"]) <= set(h0), h0.keys()
    line = f"- #{h0['id']} [{h0['status']}]"
    assert line in seen2.get("prompt", "") and "(công" in seen2["prompt"], "sai format inject"
    print("PASS case1d 1 xe auto chon + inject '- #id [status] ... (cong labor d)'")

    # 1e. 2.2.1: keyword hoa don -> get_my_invoices, scope dung xe minh.
    seen3 = {}
    def spy_gemini3(message, history, context_msg):
        seen3["prompt"] = message
        return MOCK_OK
    data = ChatIn(message="cho xem hoa don cua toi")
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy_gemini3), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user)
    invs = out.get("invoices", [])
    assert len(invs) == 1, f"ro ri/thieu hoa don: {invs}"
    assert invs[0]["total"] == 1500000 and invs[0]["plate"] == "30E-222.33", invs[0]
    print("PASS case1e trigger hoa don -> dung 1 HD xe minh")

    # 1f. 2.2.2: render "HD-<id> (<plate>, <created>): <total>đ — <status>",
    # total lay tu Invoice.total_amount (models.py:133), khong tu tinh.
    from app.models.models import Invoice as InvModel
    db_total = db.query(InvModel).filter(InvModel.id == invs[0]["id"]).first().total_amount
    assert invs[0]["total"] == db_total, "total bi tinh lai"
    expect = f"HD-{invs[0]['id']} ({invs[0]['plate']}, {invs[0]['created']}): {invs[0]['total']:,}đ — {invs[0]['status']}"
    assert expect in seen3.get("prompt", ""), f"sai format render: {expect}"
    print(f"PASS case1f render dung: {expect}")

    # 1g. 2.2.3: chua co hoa don -> van goi Gemini binh thuong.
    from app.models.models import User as UserModel, Vehicle as VehicleModel
    c3 = UserModel(username="cust3", password_hash="x", full_name="Khach 3",
                   phone="0903", role="customer", is_active=1)
    db.add(c3)
    db.flush()
    db.add(VehicleModel(license_plate="33H-111.11", make="Kia", model="Morning",
                        user_id=c3.id))
    db.commit()
    user3 = {"sub": "cust3", "role": "customer", "name": "Khach 3"}
    seen4 = {}
    def spy_gemini4(message, history, context_msg):
        seen4["prompt"] = message
        return MOCK_OK
    data = ChatIn(message="cho xem hoa don cua toi")
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy_gemini4), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user3)
    assert out.get("invoices") == [], f"phai rong: {out.get('invoices')}"
    assert "(chưa có hóa đơn)" in seen4.get("prompt", ""), "thieu nhan rong"
    assert "MOCK" in out.get("message", ""), "phai goi Gemini binh thuong"
    print("PASS case1g rong -> '(chua co hoa don)' + van goi Gemini")

    # 1h. 2.3.1: keyword lich hen -> get_my_appointments + inject dung format.
    from app.models.models import Appointment as ApptModel
    db.add(ApptModel(user_id=ids["c1_id"], vehicle_id=ids["v1_id"],
                     appointment_date="2026-10-15", appointment_time="09:00",
                     appointment_type="Repair", symptoms="kiem tra dinh ky",
                     status="Pending"))
    db.commit()
    seen5 = {}
    def spy_gemini5(message, history, context_msg):
        seen5["prompt"] = message
        return MOCK_OK
    data = ChatIn(message="cho xem lich hen cua toi")
    with patch("app.services.gemini_service.get_gemini_response", side_effect=spy_gemini5), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await customer_support(data, db, user)
    appts = out.get("appointments", [])
    assert len(appts) == 1, f"sai lich hen: {appts}"
    a = appts[0]
    assert set(["id", "date", "time", "type", "status", "plate"]) <= set(a), a.keys()
    assert (a["date"], a["time"], a["plate"], a["status"]) == \
        ("2026-10-15", "09:00", "30E-222.33", "Pending"), a
    expect = f"#{a['id']} {a['date']} {a['time']} ({a['plate']}) — {a['status']}"
    assert expect in seen5.get("prompt", ""), f"sai format inject: {expect}"
    print(f"PASS case1h liet ke lich hen + inject '{expect}'")


async def case2_sai_vehicle_id_403(db, ids):
    """Sai vehicle_id -> 403 (mau main.py:441). Cover ca main.ai_diagnose."""
    # 2a. customer agent truc tiep
    user = {"sub": "cust1", "role": "customer", "name": "Khach 1"}
    data = ChatIn(message="xem xe nay", vehicle_id=ids["v2_id"])  # xe cua cust2
    try:
        with patch("app.services.gemini_service.get_gemini_response", return_value=MOCK_OK):
            await customer_support(data, db, user)
    except HTTPException as e:
        assert e.status_code == 403, f"can 403, got {e.status_code}"
        assert "không thuộc tài khoản" in e.detail, "sai msg 403"
        print("PASS case2a customer sai vehicle_id -> 403")
    else:
        raise AssertionError("2a: khong raise 403 khi sai vehicle_id")

    # 2b. main.ai_diagnose (mau main.py:439-442)
    import main as main_mod
    from main import DiagnoseRequest
    fake_user = {"sub": "cust1", "role": "customer"}
    req = DiagnoseRequest(symptoms="xe keu", vehicle_id=str(ids["v2_id"]))

    class FakeRequest:
        pass

    with patch.object(main_mod, "get_current_user_from_cookie", return_value=fake_user):
        res = await main_mod.ai_diagnose(req, FakeRequest(), db)
    assert isinstance(res, JSONResponse), f"can JSONResponse, got {type(res)}"
    assert res.status_code == 403, f"can 403, got {res.status_code}"
    print("PASS case2b main.ai_diagnose sai vehicle_id -> 403 (mau main.py:441)")

    # 2c. 2.1.1: vehicle_id khong ton tai (999) -> 403 (loc kep id + uid).
    data = ChatIn(message="xe tôi bị sao?", vehicle_id=999)
    try:
        with patch("app.services.gemini_service.get_gemini_response", return_value=MOCK_OK):
            await customer_support(data, db, user)
    except HTTPException as e:
        assert e.status_code == 403, f"can 403, got {e.status_code}"
        assert "không thuộc tài khoản" in e.detail, "sai msg 403"
        print("PASS case2c vehicle_id=999 khong ton tai -> 403")
    else:
        raise AssertionError("2c: khong raise 403 khi vehicle_id ao")


async def case3_mat_key_msg_tv(db, ids):
    """Mat key -> msg loi TV, router 503 (khong can key that)."""
    user = {"sub": "tech1", "role": "technician", "name": "Tho 1"}
    data = DiagnoseIn(symptom="xe rung khi chay nhanh")
    with patch("app.services.gemini_service.get_gemini_response", return_value=NO_KEY_MSG), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        try:
            await diagnose_vehicle(data, db, user)
        except HTTPException as e:
            assert e.status_code == 503, f"can 503, got {e.status_code}"
            assert ("GEMINI" in e.detail or "AI" in e.detail), \
                f"msg chua TV: {ascii(e.detail)}"
            print("PASS case3 mat key -> 503 msg TV ok")
        else:
            raise AssertionError("3: khong raise 503 khi mat key")


async def case4_chroma_rong_van_tra_loi(db, ids):
    """Chroma rong ("") -> van tra loi binh thuong."""
    user = {"sub": "tech1", "role": "technician", "name": "Tho 1"}
    data = DiagnoseIn(symptom="dieu hoa khong mat")
    with patch("app.services.gemini_service.get_gemini_response",
               return_value="MOCK_CHROMA_EMPTY van tra loi duoc"), \
         patch("app.agents.tools.search_knowledge", return_value=""), \
         patch("app.agents.tools.get_weather_context", return_value=""):
        out = await diagnose_vehicle(data, db, user)
    assert "MOCK_CHROMA_EMPTY" in out.get("message", ""), f"mat message: {out}"
    print("PASS case4 Chroma rong -> van tra loi:", out["message"][:60])


async def case5_chatbot_stream_chung(db, ids):
    """chat_bot di qua call_gemini_safe(stream=True): body stream + history forward."""
    import main as main_mod
    from main import ChatRequest
    seen = {}

    def fake_stream(message, history, context_msg):
        seen.update(message=message, history=history, context_msg=context_msg)
        yield "MOCK_CHUNK_A "
        yield "MOCK_CHUNK_B"

    hist = [{"sender": "user", "text": "hi"}]
    with patch.object(main_mod, "get_current_user_from_cookie",
                      return_value={"sub": "cust1", "role": "customer"}), \
         patch("app.services.gemini_service.get_gemini_response_stream",
               side_effect=fake_stream), \
         patch("app.agents.tools.search_knowledge", return_value=""):
        resp = await main_mod.chat_bot(ChatRequest(message="hello", history=hist),
                                       _FakeRequest(), db)
        # Tieu thu stream NGAY trong with: generate() cua chat_bot la lazy.
        body = "".join([c async for c in resp.body_iterator])
    assert "MOCK_CHUNK_A MOCK_CHUNK_B" in body, f"mat chunk: {body}"
    assert seen.get("history") == hist, "history chua forward xuong service"
    assert "30E-222.33" in seen.get("context_msg", ""), "thieu vehicle context chung"
    print("PASS case5 chatbot stream qua wrapper chung + forward history")


async def case6_chatbot_stream_loi_tv(db, ids):
    """Stream loi 503/429 -> text TV dong nhat (khong vo stream)."""
    import main as main_mod
    from main import ChatRequest
    for err, marker in [("503 Service Unavailable", "quá tải"),
                        ("429 Quota exceeded", "giới hạn")]:
        with patch.object(main_mod, "get_current_user_from_cookie",
                          return_value={"sub": "cust1", "role": "customer"}), \
             patch("app.services.gemini_service.get_gemini_response_stream",
                   side_effect=Exception(err)), \
             patch("app.agents.tools.search_knowledge", return_value=""):
            resp = await main_mod.chat_bot(ChatRequest(message="hello", history=[]),
                                           _FakeRequest(), db)
            # Tieu thu stream NGAY trong with: generate() cua chat_bot la lazy.
            body = "".join([c async for c in resp.body_iterator])
        assert marker in body, f"{err} -> thieu msg TV: {ascii(body)}"
        print(f"PASS case6 stream {err[:3]} -> msg TV dong nhat")


async def case7_unified_plate_parts(db, ids):
    """Bien so 1 logic (tolerant) + phu tung 1 ham (suggest_parts)."""
    from app.agents import tools as T
    from app.agents.common import suggest_parts
    from app.models.models import SparePart

    # 7a. Bien cach nhau: regex cu miss, tolerant match qua wrapper.
    assert T.find_vehicle_by_plate(db, "exact 30E-222.33 here") is not None
    car = T.find_vehicle_by_plate(db, "xe 30E 222 33 cua toi", ids["c1_id"])
    assert car is not None and car.id == ids["v1_id"], "tolerant match loi"
    print("PASS case7a plate spaced van khop (wrapper tolerant)")

    # 7b. Bien xe nguoi khac + scope uid -> khong ro ri.
    other = T.find_vehicle_by_plate(db, "xe 51F 999 99", ids["c1_id"])
    assert other is None, "lo bien xe nguoi khac"
    print("PASS case7b scope user_id giu nguyen")

    # 7c. Phu tung chi 1 ham: tools.search_parts da xoa, suggest_parts loc
    # dung (loai het stock + ngung kinh doanh).
    assert not hasattr(T, "search_parts"), "tools.search_parts chua xoa"
    db.add_all([
        SparePart(part_number="T7A", name="loc dau nhot cao cap",
                  status="Đang kinh doanh", stock_quantity=5, price=100),
        SparePart(part_number="T7B", name="loc dau gio re",
                  status="Đang kinh doanh", stock_quantity=0, price=50),
    ])
    db.commit()
    got = sorted(p["part_number"] for p in suggest_parts(db, "can thay loc dau"))
    assert got == ["T7A"], f"suggest_parts loc sai: {got}"
    print("PASS case7c 1 ham suggest_parts, loc dung")


async def case8_rag_source_of_truth(db, ids):
    """Quy uoc RAG 4.1.2: seed parse + sync idempotent + metadata chuan."""
    import glob
    import os
    from ingest_knowledge import (
        parse_seed_header, sync_seeds_to_db, build_doc_payload, ingest_document,
        normalize_doc_type, VALID_DOC_TYPES,
    )

    # 8a. Moi file seed dung format: [LOAI] + xe ap dung + ngay hieu luc.
    files = sorted(glob.glob("data/knowledge_base/*.txt"))
    assert len(files) >= 13, f"can >=13 seed, got {len(files)}"
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        title, dtype = parse_seed_header(text, path)
        assert title and dtype in VALID_DOC_TYPES, path
        low = text.lower()
        assert "áp dụng cho:" in low or "ap dung cho:" in low, path
        assert "hiệu lực:" in low or "hieu luc:" in low, path
    print(f"PASS case8a {len(files)} seed dung format header")

    # 8b. Sync lan 2 khong trung (DB la truth, giu ban DB).
    ins1, _ = sync_seeds_to_db(db)
    ins2, skip2 = sync_seeds_to_db(db)
    assert ins1 >= 13 and ins2 == 0 and skip2 >= 13, (ins1, ins2, skip2)
    print(f"PASS case8b sync idempotent (lan1 +{ins1}, lan2 +{ins2})")

    # 8c. Backfill source + clamp type cho doc cu (giong DB that truoc migrate).
    from app.models.models import GarageDocument
    legacy = db.query(GarageDocument).first()
    legacy.source, legacy.document_type = None, "tu-do"
    db.commit()
    sync_seeds_to_db(db)
    db.refresh(legacy)
    assert legacy.source and legacy.source.endswith(".txt"), legacy.source
    assert legacy.document_type in VALID_DOC_TYPES, legacy.document_type
    assert normalize_doc_type("tu-do") == "guideline"
    assert normalize_doc_type("POLICY") == "policy"
    print("PASS case8c backfill source + clamp document_type")

    # 8d. Payload metadata chuan 4.1.2 + id on dinh + ingest danh dau flag.
    doc = db.query(GarageDocument).filter(GarageDocument.is_ingested == 0).first()
    assert doc is not None
    docs1, metas1, ids1 = build_doc_payload(doc)
    docs2, metas2, ids2 = build_doc_payload(doc)
    assert docs1 and ids1 == ids2, "id chunk phai on dinh"
    assert set(metas1[0].keys()) == {"source", "chunk_index", "doc_id", "document_type"}, metas1[0]
    assert isinstance(metas1[0]["doc_id"], str) and metas1[0]["doc_id"] == doc.source
    assert metas1[0]["source"].endswith(".txt"), metas1[0]
    assert metas1[0]["document_type"] in VALID_DOC_TYPES

    class FakeCollection:
        def __init__(self):
            self.deleted, self.upserted = [], []
        def delete(self, where=None):
            self.deleted.append(where)
        def upsert(self, documents=None, metadatas=None, ids=None):
            self.upserted.append((documents, metadatas, ids))

    fake = FakeCollection()
    n = ingest_document(db, doc, fake)
    assert n == len(docs1) and fake.deleted == [{"doc_id": doc.source}]
    assert fake.upserted[0][2] == ids1
    assert doc.is_ingested == 1
    print(f"PASS case8d delete/upsert theo doc_id str + flag is_ingested ({n} chunks)")


async def case11_ingest_files_basename():
    """ingest_files(): vong glob cu, doc_id=basename, offline MiniLM."""
    from ingest_knowledge import ingest_files, EMBEDDING_MODEL, VALID_DOC_TYPES

    assert EMBEDDING_MODEL == "all-MiniLM-L6-v2", "doi embedding model?"

    class FakeCollection:
        def __init__(self):
            self.upserted = []
        def upsert(self, documents=None, metadatas=None, ids=None):
            self.upserted.append((documents, metadatas, ids))

    fake = FakeCollection()
    total = ingest_files(collection=fake)
    assert total > 0, "khong nap duoc file nao"
    all_ids, all_metas = [], []
    for _, metas, ids in fake.upserted:
        all_ids += ids
        all_metas += metas
    assert len(all_ids) == total == len(all_metas)
    assert len(set(all_ids)) == total, "trung id chunk"
    for m in all_metas:
        assert m["doc_id"] == m["source"] and m["source"].endswith(".txt"), m
        assert m["document_type"] in VALID_DOC_TYPES
        assert isinstance(m["chunk_index"], int)
    print(f"PASS case11 ingest_files {len(fake.upserted)} files, doc_id=basename ({total} chunks)")


async def case9_chunk_theo_cau():
    """4.2.1: chunk 800/100 cat theo cau, khong vo '120-200 bar'."""
    from ingest_knowledge import chunk_text

    with open("data/knowledge_base/sample_guide.txt", "r", encoding="utf-8") as f:
        sample = f.read()
    assert len(sample.splitlines()) >= 10, "sample qua ngan"
    chunks = chunk_text(sample)
    assert 1 <= len(chunks) <= 2, f"can 1-2 chunk, got {len(chunks)}"
    assert all(len(c) <= 800 for c in chunks), "chunk vuot 800"
    assert any("120-200 bar" in c for c in chunks), "vo '120-200 bar'"
    full = "phải đạt mức 120-200 bar khi nổ máy tĩnh"
    assert any(full in c for c in chunks), "vo cau ap suat"
    if len(chunks) == 2:
        # Overlap: cau dau chunk sau phai la cau nguyen ven co mat trong chunk truoc.
        from ingest_knowledge import _split_segments
        shared = [s for s in _split_segments(chunks[1]) if s in chunks[0] and len(s) > 30]
        assert shared, "mat overlap giua 2 chunk"
    print(f"PASS case9a sample -> {len(chunks)} chunk, cau nguyen ven + overlap")

    assert chunk_text("") == [], "rong phai []"
    assert chunk_text("ngắn") == ["ngắn"], "1 cau ngan"
    big = "x" * 2000  # segment don le qua dai: cat cung nhung phai dung
    hard = chunk_text(big)
    assert hard and all(len(c) <= 800 for c in hard), "treo/cat sai segment dai"
    print("PASS case9b edge: rong + 1 cau + segment 2000 ky tu")


async def case10_ingest_text_core():
    """4.2.2: core ingest_text chunk -> ids doc{doc_id}_c{i} -> upsert."""
    from ingest_knowledge import ingest_text

    class FakeCollection:
        def __init__(self):
            self.upserted = []
        def upsert(self, documents=None, metadatas=None, ids=None):
            self.upserted.append((documents, metadatas, ids))

    fake = FakeCollection()
    n = ingest_text("Câu một hoàn chỉnh. Câu hai cũng hoàn chỉnh để nạp.",
                    "seed-demo.txt", 42, "manual", fake)
    assert n >= 1, "phai nap duoc chunk"
    docs, metas, ids = fake.upserted[0]
    assert ids == [f"doc42_c{i}" for i in range(n)], ids
    assert set(metas[0].keys()) == {"source", "chunk_index", "doc_id", "document_type"}
    assert (metas[0]["source"], metas[0]["doc_id"], metas[0]["document_type"]) == \
        ("seed-demo.txt", "42", "manual")
    assert metas[0]["chunk_index"] == 0

    fake2 = FakeCollection()
    assert ingest_text("   ", "x.txt", 1, "report", fake2) == 0
    assert fake2.upserted == [], "rong khong duoc upsert"
    print(f"PASS case10 ingest_text core (ids doc42_c*, rong -> 0)")


async def case12_ingest_db_document():
    """ingest_db_document: tu mo session, xong flag 1; loi giu 0."""
    import app.database as dbmod
    from app.models.models import GarageDocument
    from ingest_knowledge import ingest_db_document

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    TestingSession = sessionmaker(bind=eng)
    db = TestingSession()
    db.add(GarageDocument(title="Doc Seed Test", content="Noi dung cau mot. Cau hai.",
                          document_type="manual", source="seed-test.txt",
                          is_ingested=0))
    db.add(GarageDocument(title="Doc Loi", content="Noi dung loi.",
                          document_type="report", is_ingested=0))
    db.commit()
    seed_id = db.query(GarageDocument).filter_by(title="Doc Seed Test").first().id
    bad_id = db.query(GarageDocument).filter_by(title="Doc Loi").first().id
    db.close()

    class FakeCollection:
        def __init__(self):
            self.upserted = []
            self.deleted = []
        def delete(self, where=None):
            self.deleted.append(where)
        def upsert(self, documents=None, metadatas=None, ids=None):
            self.upserted.append((documents, metadatas, ids))

    class BoomCollection(FakeCollection):
        def upsert(self, documents=None, metadatas=None, ids=None):
            raise Exception("boom")

    fake = FakeCollection()
    with patch.object(dbmod, "SessionLocal", TestingSession):
        assert ingest_db_document(999999, collection=fake) == 0, "doc ao phai 0"
        n = ingest_db_document(seed_id, collection=fake)
    assert n >= 1, "phai nap duoc chunk"
    assert fake.deleted == [], "spec moi: khong xoa, chi upsert + flag"
    docs, metas, ids = fake.upserted[0]
    assert ids == [f"doc{seed_id}_c{i}" for i in range(n)], ids
    assert metas[0]["source"] == "Doc Seed Test", metas[0]
    assert metas[0]["doc_id"] == str(seed_id), metas[0]
    assert metas[0]["document_type"] == "manual", metas[0]
    db = TestingSession()
    assert db.query(GarageDocument).filter_by(id=seed_id).first().is_ingested == 1
    db.close()
    print(f"PASS case12a tu mo session, flag 1, doc_id=id so ({n} chunks)")

    with patch.object(dbmod, "SessionLocal", TestingSession):
        assert ingest_db_document(bad_id, collection=BoomCollection()) == 0
    db = TestingSession()
    assert db.query(GarageDocument).filter_by(id=bad_id).first().is_ingested == 0
    db.close()
    print("PASS case12b loi upsert -> giu is_ingested=0")


async def case13_reingest_route():
    """POST /manager/documents/{id}/reingest: goi ingest_db_document 1 doc."""
    from fastapi import Request
    from app.routers import manager as manager_mod
    from app.models.models import GarageDocument
    import ingest_knowledge as ik

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    TestingSession = sessionmaker(bind=eng)
    db = TestingSession()
    db.add(GarageDocument(title="Doc Cho", content="Noi dung cho ingest.",
                          document_type="guideline", is_ingested=0))
    db.commit()
    did = db.query(GarageDocument).first().id

    calls = []
    def spy(doc_id):
        calls.append(doc_id)
        return 2

    def scope(path="/manager/documents/1/reingest"):
        return {"type": "http", "method": "POST", "headers": [],
                "path": path, "query_string": b""}

    with patch.object(manager_mod, "check_auth",
                      return_value={"sub": "quanly", "role": "manager"}), \
         patch.object(ik, "ingest_db_document", side_effect=spy):
        ok = await manager_mod.reingest_document(Request(scope()), did, db)
        assert ok.status_code == 302 and "reingested=1" in ok.headers["location"], \
            ok.headers.get("location")
        assert calls == [did], calls
        print("PASS case13a reingest goi ingest_db_document 1 doc")

        miss = await manager_mod.reingest_document(Request(scope()), 999999, db)
        assert miss.status_code == 302 and "notfound=1" in miss.headers["location"]
        assert calls == [did], "doc ao khong duoc ingest"
        print("PASS case13b doc ao -> notfound, khong ingest")
    db.close()


async def case14_rag_reload():
    """4.3.1: reload() reset cache + moi ingest tu goi reload."""
    import app.services.rag_service as rs
    from ingest_knowledge import ingest_text

    rs.collection, rs.client = "STALE", "STALE"
    rs.reload()
    assert rs.collection is None and rs.client is None, "reload phai reset cache"
    print("PASS case14a reload reset collection/client")

    class FakeCollection:
        def upsert(self, documents=None, metadatas=None, ids=None):
            pass

    with patch.object(rs, "reload") as spy:
        n = ingest_text("Cau mot. Cau hai.", "f.txt", "f.txt", "manual",
                        FakeCollection())
    assert n >= 1 and spy.call_count == 1, "ingest phai goi reload 1 lan"
    print("PASS case14b ingest_text tu goi reload sau upsert")


async def case15_search_filter_distance():
    """4.3.2: loc distance > 1.2 + chunk rong; collection rong -> '' ngay."""
    import app.services.rag_service as rs

    class FakeCol:
        def __init__(self, docs, metas, dists, n=3):
            self.docs, self.metas, self.dists, self.n = docs, metas, dists, n
            self.queried = 0
        def count(self):
            return len(self.docs)
        def query(self, query_texts=None, n_results=3):
            self.queried += 1
            k = min(n_results, len(self.docs))
            return {"documents": [self.docs[:k]],
                    "metadatas": [self.metas[:k]],
                    "distances": [self.dists[:k]]}

    meta = {"source": "f.txt", "chunk_index": 0, "doc_id": "1",
            "document_type": "manual"}
    col = FakeCol(["gan chu de", "   ", "xa chu de"],
                  [dict(meta), dict(meta), dict(meta)], [0.3, 0.1, 1.5])
    with patch.object(rs, "get_chroma_collection", return_value=col):
        out = rs.search_knowledge_base("chu de gan", n_results=3)
    assert "gan chu de" in out and "xa chu de" not in out, ascii(out[:120])
    assert "[Trích từ f.txt#0]:" in out, ascii(out[:120])
    assert col.queried == 1
    print("PASS case15a giu gan, bo xa (>1.2) + rong + citation [Trich tu source#chunk]")

    far = FakeCol(["a", "b"], [dict(meta), dict(meta)], [1.3, 2.0])
    with patch.object(rs, "get_chroma_collection", return_value=far):
        assert rs.search_knowledge_base("x") == "", "tat ca xa phai ''"
    print("PASS case15b tat ca xa -> ''")

    empty = FakeCol([], [], [])
    with patch.object(rs, "get_chroma_collection", return_value=empty):
        assert rs.search_knowledge_base("x") == ""
        assert empty.queried == 0, "collection rong khong query"
    with patch.object(rs, "get_chroma_collection", return_value=None):
        assert rs.search_knowledge_base("x") == ""
    print("PASS case15c rong/missing -> '' ngay")


async def case16_backup_rebuild():
    """4.4.3: backup garage.db + chroma truoc rebuild + doi chieu hut."""
    import os
    import tempfile
    from ingest_knowledge import backup_before_rebuild, check_ingest_complete

    class FakeCollection:
        def count(self):
            return 41

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "garage.db")
        chroma = os.path.join(tmp, "chroma_db")
        os.mkdir(chroma)
        open(db_path, "w").write("fake-db")
        open(os.path.join(chroma, "seg.bin"), "w").write("fake-vec")
        dest, before = backup_before_rebuild(
            FakeCollection(), db_path=db_path, chroma_dir=chroma,
            backup_root=os.path.join(tmp, "backup"))
        assert before == 41, before
        assert os.path.exists(os.path.join(dest, "garage.db")), "thieu backup db"
        assert os.path.exists(os.path.join(dest, "chroma_db", "seg.bin")), "thieu backup chroma"
    print("PASS case16a backup db + chroma theo ngay")

    assert check_ingest_complete(30, 30, "backup/x") is True
    assert check_ingest_complete(30, 25, "backup/x") is False
    assert check_ingest_complete(None, 25, "backup/x") is True
    print("PASS case16b du -> True, hut -> False + canh bao")


async def case17_parse_vi_date():
    """2.3.2: parse_vi_date relative/weekday/numeric + sai -> None."""
    from datetime import datetime
    from app.agents.tools import parse_vi_date

    ref = datetime(2026, 10, 8, 12, 0)  # Thu (weekday 3)
    assert parse_vi_date("dat lich ngay mai", ref) == "2026-10-09"
    assert parse_vi_date("ngày mốt nhe", ref) == "2026-10-10"
    assert parse_vi_date("hôm nay", ref) == "2026-10-08"
    # Weekday: thu 2 tuan sau (10-08 la thu 5 -> thu 2 gan nhat 10-12),
    # trung thu (thu 5) -> +7.
    assert parse_vi_date("thu 2", ref) == "2026-10-12", parse_vi_date("thu 2", ref)
    assert parse_vi_date("thứ 5", ref) == "2026-10-15", parse_vi_date("thứ 5", ref)
    assert parse_vi_date("chủ nhật", ref) == "2026-10-11"
    # Numeric: du nam, thieu nam (qua -> nam sau).
    assert parse_vi_date("15/10/2026", ref) == "2026-10-15"
    assert parse_vi_date("15/10", ref) == "2026-10-15"
    assert parse_vi_date("01/01", ref) == "2027-01-01", parse_vi_date("01/01", ref)
    # Sai -> None (vao needs).
    assert parse_vi_date("hom nao do", ref) is None
    assert parse_vi_date("32/13", ref) is None
    assert parse_vi_date("", ref) is None
    print("PASS case17 parse_vi_date relative/weekday/numeric/None")


async def case18_parse_time_draft():
    """2.3.3: parse_time h/mi + buoi + gio hanh chinh; draft thieu gio."""
    from app.agents.tools import parse_time

    assert parse_time("2 gio chieu") == "14:00"
    assert parse_time("9h sáng") == "09:00"
    assert parse_time("10:30 sáng") == "10:30"
    assert parse_time("3 giờ chiều") == "15:00"
    assert parse_time("12 giờ trưa") == "12:00"
    assert parse_time("7h tối") is None, "19h ngoai gio xuong"
    assert parse_time("30E-222.33") is None, "so bien so phai bo"
    assert parse_time("xin chao") is None
    print("PASS case18a parse_time buoi/gio-hanh-chinh/bien-so")

    # E2E: dat lich thieu gio -> draft time=None + nhan "chua chot gio".
    from app.agents.schemas import ChatIn
    from app.agents.customer_agent.router import customer_support
    from unittest.mock import patch
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.models import User, Vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="bk1", password_hash="x", full_name="BK", phone="1",
             role="customer", is_active=1)
    db.add(u)
    db.flush()
    db.add(Vehicle(license_plate="40A-111.11", make="Kia", model="Morning",
                   user_id=u.id))
    db.commit()
    seen = {}
    def spy(message, history, context_msg):
        seen["prompt"] = message
        return "MOCK"
    try:
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await customer_support(
                ChatIn(message="dat lich ngay mot"), db,
                {"sub": "bk1", "role": "customer", "name": "BK"})
    finally:
        db.close()
    assert out.get("draft", {}).get("time") is None, out.get("draft")
    assert "(chưa chốt giờ)" in seen.get("prompt", ""), "thieu nhan chua chot gio"
    print("PASS case18b draft thieu gio -> time=None + '(chua chot gio)'")


async def case19_appointment_draft_dup():
    """2.3.4: dat 2 lan cung ngay -> lan 2 duplicate:true, DB 1 dong."""
    from datetime import datetime, timedelta
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.models import User, Vehicle, Appointment, RepairOrder
    from app.agents.tools import create_appointment_draft

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="dup1", password_hash="x", full_name="D", phone="1",
             role="customer", is_active=1)
    db.add(u)
    db.flush()
    v = Vehicle(license_plate="44D-222.22", make="Kia", model="Morning", user_id=u.id)
    db.add(v)
    db.commit()
    day = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    r1 = create_appointment_draft(db, u.id, v.id, day, "09:00", symptoms="kiem tra")
    assert r1.get("duplicate") is False, r1
    r2 = create_appointment_draft(db, u.id, v.id, day, "10:00", symptoms="kiem tra lai")
    assert r2.get("duplicate") is True and r2["id"] == r1["id"], r2
    assert db.query(Appointment).filter(
        Appointment.user_id == u.id, Appointment.vehicle_id == v.id,
        Appointment.appointment_date == day).count() == 1, "DB phai 1 dong"
    # Luong NHAP: chi tao Appointment, KHONG tao phieu sua chua som.
    assert db.query(RepairOrder).filter(
        RepairOrder.appointment_id == r1["id"]).count() == 0, "nhap khong duoc co phieu"
    from app.agents.tools import convert_appointment_to_order
    conv = convert_appointment_to_order(db, r1["id"])
    assert conv["created"] is True and conv["appointment_status"] == "Confirmed", conv
    assert db.query(Appointment).filter(Appointment.id == r1["id"]).first().status == "Confirmed"
    assert db.query(RepairOrder).filter(RepairOrder.appointment_id == r1["id"]).count() == 1
    # Xe khong thuoc user -> ValueError.
    try:
        create_appointment_draft(db, 999999, v.id, day, None, symptoms="x")
    except ValueError as e:
        assert "không thuộc tài khoản" in str(e), e
    else:
        raise AssertionError("xe la phai ValueError")
    # Ngay qua khu -> ValueError.
    try:
        create_appointment_draft(db, u.id, v.id, "2000-01-01", None, symptoms="x")
    except ValueError:
        pass
    else:
        raise AssertionError("ngay cu phai ValueError")
    db.close()
    print("PASS case19 draft trung -> duplicate:true, DB 1 dong + check xe/ngay "
          "+ nhap khong co phieu -> convert moi sinh phieu")


async def case20_booking_needs():
    """2.3.5: thieu info -> needs[] + hoi lai, khong tao draft."""
    from app.agents.schemas import ChatIn
    from app.agents.customer_agent.router import customer_support
    from unittest.mock import patch
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.models import User, Vehicle, Appointment

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u1 = User(username="n1", password_hash="x", full_name="N1", phone="1",
              role="customer", is_active=1)
    u2 = User(username="n2", password_hash="x", full_name="N2", phone="2",
              role="customer", is_active=1)
    db.add_all([u1, u2])
    db.flush()
    db.add(Vehicle(license_plate="45N-111.11", make="Kia", model="Morning", user_id=u1.id))
    db.add(Vehicle(license_plate="46N-222.22", make="Kia", model="Morning", user_id=u2.id))
    db.add(Vehicle(license_plate="47N-333.33", make="Kia", model="Morning", user_id=u2.id))
    db.commit()

    async def ask(sub, msg):
        seen = {}
        def spy(message, history, context_msg):
            seen["prompt"] = message
            return "MOCK"
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await customer_support(
                ChatIn(message=msg), db, {"sub": sub, "role": "customer", "name": sub})
        return out, seen.get("prompt", "")

    try:
        # Thieu ngay (1 xe -> co xe, thieu ngay).
        out, prompt = await ask("n1", "dat lich")
        assert out.get("needs") == ["ngày hẹn (VD: ngày mai, thứ 2, 15/10)"], out.get("needs")
        assert "draft" not in out, "thieu info khong duoc tao draft"
        assert "còn thiếu:" in prompt and "Hãy hỏi lại" in prompt, "thieu context hoi lai"
        print("PASS case20a thieu ngay -> needs + hoi lai, khong draft")

        # Thieu ca xe (2 xe) + ngay.
        out, prompt = await ask("n2", "dat lich")
        assert out.get("needs") == ["xe (nêu biển số, VD: 30E-222.33)",
                                    "ngày hẹn (VD: ngày mai, thứ 2, 15/10)"], out.get("needs")
        assert "draft" not in out
        assert db.query(Appointment).count() == 0, "khong duoc insert khi needs"
        print("PASS case20b thieu xe + ngay -> needs[2], DB 0 dong")
    finally:
        db.close()


async def case21_suggest_services():
    """2.4.1: suggest_services Active + score + promo + gia DB."""
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.models import User, Vehicle, ServiceCatalog
    from app.agents.common import suggest_services
    from app.agents.schemas import ChatIn
    from app.agents.customer_agent.router import customer_support
    from unittest.mock import patch

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add_all([
        ServiceCatalog(service_code="S1", name="Rửa xe chi tiết", category="Chăm sóc",
                       description="Rua vo xe", status="Active", base_price=200000,
                       duration_minutes=30),
        ServiceCatalog(service_code="S2", name="Rửa xe cao cấp", category="Chăm sóc",
                       description="Rua ky", status="Active", base_price=250000,
                       promo_price=150000, duration_minutes=45),
        ServiceCatalog(service_code="S3", name="Rửa xe tại nhà", category="Chăm sóc",
                       description="Rua tan noi", status="Inactive", base_price=100000,
                       duration_minutes=30),
        ServiceCatalog(service_code="S4", name="Sửa máy lạnh", category="Dien lanh",
                       description="Nap gas", status="Active", base_price=500000,
                       duration_minutes=60),
    ])
    u = User(username="sv1", password_hash="x", full_name="SV", phone="1",
             role="customer", is_active=1)
    db.add(u)
    db.flush()
    db.add(Vehicle(license_plate="48S-111.11", make="Kia", model="Morning", user_id=u.id))
    db.commit()

    try:
        got = suggest_services(db, "rửa xe")
        assert [g["name"] for g in got] == ["Rửa xe cao cấp", "Rửa xe chi tiết"], got
        assert [(g["price"], g["promo"]) for g in got] == [(150000, True), (200000, False)], got
        assert len(got) <= 5
        print("PASS case21a Active + score + promo truoc + gia DB")

        with patch("app.services.gemini_service.get_gemini_response", return_value="MOCK"), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await customer_support(
                ChatIn(message="tôi muốn rửa xe"), db,
                {"sub": "sv1", "role": "customer", "name": "SV"})
        assert [s["name"] for s in out["suggestions"]] == ["Rửa xe cao cấp", "Rửa xe chi tiết"]
        assert out["estimate"] == {"min": 150000, "max": 350000}, out["estimate"]
        print("PASS case21b router suggestions + estimate tu DB")
    finally:
        db.close()


async def case22_estimate_range():
    """2.4.2: min/max tu DB, rong -> None, khong cong cong/VAT o day."""
    from app.agents.common import estimate_range

    assert estimate_range([]) is None
    assert estimate_range([{"price": 0}, {"price": None}]) is None
    assert estimate_range([{"price": 200000}]) == {"min": 200000, "max": 200000}
    got = estimate_range([{"price": p} for p in [100000, 50000, 300000, 200000]])
    assert got == {"min": 50000, "max": 600000}, got  # 300k+200k+100k
    print("PASS case22 estimate min/max/None, khong cong cong")

    # Ghi chu "chua gom cong/VAT" phai co trong prompt 2 agent
    # (customer qua SAFETY_RULES_CUSTOMER, tech inline trong prompt).
    import inspect
    from app.agents.common import SAFETY_RULES_CUSTOMER
    from app.agents.customer_agent.router import customer_support, _prepare_customer_chat
    from app.agents.technical_agent.router import diagnose_vehicle
    assert "chưa gồm VAT" in SAFETY_RULES_CUSTOMER, "thieu note VAT"
    assert "SAFETY_RULES_CUSTOMER" in inspect.getsource(_prepare_customer_chat)
    assert "SAFETY_CUSTOMER" in inspect.getsource(customer_support)
    assert "chưa gồm công thợ và VAT" in inspect.getsource(diagnose_vehicle), \
        "thieu note cong/VAT tech"
    print("PASS case22b prompt 2 agent ghi ro chua gom cong/VAT")


async def case23_prompt_contract():
    """2.5: validate input + thu tu prompt + contract call_gemini_safe."""
    from pydantic import ValidationError
    from app.agents.schemas import ChatIn
    from app.agents.customer_agent.router import customer_support
    from app.agents.common import SAFETY_RULES_CUSTOMER, SAFETY_CUSTOMER
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.models import User, Vehicle
    from unittest.mock import patch
    from fastapi import HTTPException

    # Validate schemas.py:12: message 1-2000 chars.
    try:
        ChatIn(message="")
        raise AssertionError("rong phai ValidationError")
    except ValidationError:
        pass
    try:
        ChatIn(message="x" * 2001)
        raise AssertionError("qua dai phai ValidationError")
    except ValidationError:
        pass
    print("PASS case23a ChatIn 1-2000 chars")

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="p1", password_hash="x", full_name="Ten Khach",
             phone="1", role="customer", is_active=1)
    db.add(u)
    db.flush()
    db.add(Vehicle(license_plate="49P-111.11", make="Toyota", model="Vios",
                   user_id=u.id, current_odo=10000))
    db.commit()

    async def run(msg, gemini_ret, hist=None):
        seen = {}
        def spy(**kw):
            seen.update(kw)
            return gemini_ret
        with patch("app.agents.customer_agent.router.call_gemini_safe", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value="RAG_MARK"), \
             patch("app.agents.tools.get_weather_context", return_value="WEATHER_MARK"):
            try:
                out = await customer_support(
                    ChatIn(message=msg, history=hist or []), db,
                    {"sub": "p1", "role": "customer", "name": "Ten Khach"})
            except HTTPException as e:
                return None, seen, e
        return out, seen, None

    try:
        # Trang chi toan space -> 400.
        _, _, err = await run("   ", {"ok": True, "message": "x"})
        assert err is not None and err.status_code == 400, "trang phai 400"
        print("PASS case23b message trang -> 400")

        # Thu tu prompt co dinh + kwargs goi (weather/catalog co dieu kien keyword).
        hist = [{"sender": "user", "text": "hi"}]
        out, seen, err = await run("xe 49P-111.11 hóa đơn giá bao nhiêu, trời mưa to",
                                   {"ok": True, "message": "REPLY"}, hist)
        assert err is None, err
        p = seen["message"]
        marks = ["Ten Khach", "Câu hỏi:", "49P-111.11", "XE:", "LỊCH SỬ:",
                 "XE ĐANG XÉT", "HÓA ĐƠN", "TÀI LIỆU NỘI BỘ:", "RAG_MARK",
                 "DANH MỤC (chỉ khi hỏi giá):", "THỜI TIẾT (1 câu, chỉ khi liên quan):",
                 "WEATHER_MARK", "NGUYÊN TẮC AN TOÀN"]
        pos = [p.find(m) for m in marks]
        assert all(i >= 0 for i in pos), [m for m, i in zip(marks, pos) if i < 0]
        assert pos == sorted(pos), f"sai thu tu prompt: {pos}"
        assert seen.get("history") == hist, "history phai forward"
        assert "context_msg" in seen, "thieu context_msg"
        assert out["message"] == "REPLY" + SAFETY_CUSTOMER, "thieu hau to safety"
        print("PASS case23c thu tu prompt + kwargs + hau to safety")

        # ok False -> 503 detail TV.
        _, _, err = await run("chao", {"ok": False, "message": "TV loi mat key"})
        assert err is not None and err.status_code == 503 and err.detail == "TV loi mat key"
        print("PASS case23d ok False -> 503 TV")
    finally:
        db.close()


async def case24_tech_input_validation():
    """3.1.1: schema + 400 + chuan hoa bien so."""
    from pydantic import ValidationError
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.models.models import User, Vehicle
    from unittest.mock import patch
    from fastapi import HTTPException

    try:
        DiagnoseIn(symptom="")
        raise AssertionError("rong phai ValidationError")
    except ValidationError:
        pass
    try:
        DiagnoseIn(symptom="x" * 2001)
        raise AssertionError("qua dai phai ValidationError")
    except ValidationError:
        pass
    try:
        DiagnoseIn(symptom="keu", license_plate="x" * 21)
        raise AssertionError("bien dai phai ValidationError")
    except ValidationError:
        pass
    d = DiagnoseIn(symptom="keu", license_plate=" 51f-999.99 ")
    assert d.license_plate == " 51f-999.99 ", "schema giu nguyen input tho"
    print("PASS case24a DiagnoseIn 1-2000/plate<=20/history[]")

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="t24", password_hash="x", full_name="T", phone="1",
             role="technician", is_active=1)
    db.add(u)
    db.flush()
    db.add(Vehicle(license_plate="51F-999.99", make="Honda", model="City", user_id=u.id))
    db.commit()
    try:
        # symptom trang -> 400.
        try:
            with patch("app.services.gemini_service.get_gemini_response", return_value="MOCK"), \
                 patch("app.agents.tools.search_knowledge", return_value=""), \
                 patch("app.agents.tools.get_weather_context", return_value=""):
                await diagnose_vehicle(
                    DiagnoseIn(symptom="   "), db, {"sub": "t24", "role": "technician"})
        except HTTPException as e:
            assert e.status_code == 400 and "Thiếu triệu chứng" in e.detail, e.detail
            print("PASS case24b symptom trang -> 400")
        else:
            raise AssertionError("trang phai 400")

        # Chuan hoa " 51f-999.99 " -> "51F-999.99", khop xe.
        with patch("app.services.gemini_service.get_gemini_response", return_value="MOCK"), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await diagnose_vehicle(
                DiagnoseIn(symptom="keu", license_plate=" 51f-999.99 "), db,
                {"sub": "t24", "role": "technician"})
        assert out.get("vehicle", {}).get("plate") == "51F-999.99", out.get("vehicle")
        print("PASS case24c ' 51f-999.99 ' -> '51F-999.99', khop xe")
    finally:
        db.close()


async def case25_find_vehicle_no_user_filter():
    """3.1.2: normalize + khong loc user + loi DB None + goi 2 lan."""
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import MagicMock, patch
    from app.models.models import User, Vehicle
    from app.agents import tools as T
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="t25", password_hash="x", full_name="T", phone="1",
             role="technician", is_active=1)
    db.add(u)
    db.flush()
    # Bien luu khong dau cham: "51F-99999".
    db.add(Vehicle(license_plate="51F-99999", make="Honda", model="City", user_id=u.id))
    db.add(Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios", user_id=u.id))
    db.commit()
    try:
        # Normalize 2 chieu, khong loc user (ky thuat vien thay moi xe).
        assert T.find_vehicle_by_plate(db, "xe 51f99999 kêu").license_plate == "51F-99999"
        assert T.find_vehicle_by_plate(db, "xe 30E22233 keu").license_plate == "30E-222.33"
        assert T.find_vehicle_by_plate(db, "xe khong bien so") is None
        print("PASS case25a normalize + khong loc user")

        # Loi DB -> None (khong vo).
        bad = MagicMock()
        bad.query.side_effect = Exception("db down")
        assert T.find_vehicle_by_plate(bad, "xe 30E-222.33") is None
        print("PASS case25b loi DB -> None")

        # Router goi 2 lan: license_plate truoc, symptom fallback.
        calls = []
        real = T.find_vehicle_by_plate
        def spy(db_, text, user_id=None):
            calls.append(text)
            return real(db_, text, user_id)
        with patch("app.services.gemini_service.get_gemini_response", return_value="MOCK"), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""), \
             patch("app.agents.technical_agent.router.T.find_vehicle_by_plate",
                   side_effect=spy):
            out = await diagnose_vehicle(
                DiagnoseIn(symptom="xe 30E-222.33 kêu", license_plate="99Z-999.99"),
                db, {"sub": "t25", "role": "technician"})
        assert calls == ["99Z-999.99", "xe 30E-222.33 kêu"], calls
        assert out.get("vehicle", {}).get("plate") == "30E-222.33", out.get("vehicle")
        print("PASS case25c router goi plate truoc, symptom fallback")
    finally:
        db.close()


async def case26_tech_inject_template():
    """3.2.2: inject template exact 'XE DANG XET...' + dong lich su."""
    from datetime import datetime
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from app.models.models import User, Vehicle, RepairOrder
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="t26", password_hash="x", full_name="T", phone="1",
             role="technician", is_active=1)
    db.add(u)
    db.flush()
    v = Vehicle(license_plate="30E-222.33", make="Toyota", model="Vios",
                user_id=u.id, current_odo=50000)
    db.add(v)
    db.flush()
    db.add(RepairOrder(vehicle_id=v.id, symptoms="kêu khi phanh",
                       inspection_result="mòn má phanh", estimated_cost=350000,
                       status="Completed", service_rating=5,
                       created_at=datetime(2026, 9, 10, 8, 0)))
    db.commit()
    try:
        seen = {}
        def spy(message, history, context_msg):
            seen["prompt"] = message
            return "MOCK"
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await diagnose_vehicle(
                DiagnoseIn(symptom="xe 30E-222.33 kêu khi phanh"), db,
                {"sub": "t26", "role": "technician"})
        prompt = seen.get("prompt", "")
        head = (f"XE ĐANG XÉT: Toyota Vios {v.id} "
                f"(biển 30E-222.33, ODO 50000)\nTOÀN BỘ LỊCH SỬ REPAIRORDER:")
        assert head in prompt, f"thieu head: {head}"
        hid = out["history"][0]["id"]
        line = (f"- #{hid} [Completed] 10/09/2026: kêu khi phanh | "
                f"xử lý: mòn má phanh (công 350,000đ) | sao: 5")
        assert line in prompt, f"sai dong lich su: {line}"
        print(f"PASS case26 inject exact head + '{line[:40]}...'")
    finally:
        db.close()


async def case26_tech_inject_template():
    """3.2.2: template inject XE + lich su dung format VN."""
    from datetime import datetime
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from app.models.models import User, Vehicle, RepairOrder
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    u = User(username="t26", password_hash="x", full_name="T", phone="1",
             role="technician", is_active=1)
    db.add(u)
    db.flush()
    v = Vehicle(license_plate="60T-123.45", make="Toyota", model="Vios",
                user_id=u.id, current_odo=45000)
    db.add(v)
    db.flush()
    db.add(RepairOrder(vehicle_id=v.id, symptoms="kêu khi phanh",
                       inspection_result="mòn má phanh", estimated_cost=350000,
                       status="Completed", service_rating=5,
                       created_at=datetime(2026, 9, 10, 8, 0),
                       completed_at=datetime(2026, 9, 10, 10, 0)))
    v2 = Vehicle(license_plate="61T-000.01", make="Honda", model="City", user_id=u.id)
    db.add(v2)
    db.commit()
    v2id = v2.id

    async def run(plate):
        seen = {}
        def spy(message, history, context_msg):
            seen["prompt"] = message
            return "MOCK"
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await diagnose_vehicle(
                DiagnoseIn(symptom="kiem tra", license_plate=plate), db,
                {"sub": "t26", "role": "technician"})
        return out, seen.get("prompt", "")

    try:
        out, prompt = await run("60T-123.45")
        assert f"XE ĐANG XÉT: Toyota Vios {out['vehicle']['id']} (biển 60T-123.45, ODO 45000)" in prompt
        assert "TOÀN BỘ LỊCH SỬ REPAIRORDER:" in prompt
        line = ("- #{} [Completed] 10/09/2026: kêu khi phanh "
                "| xử lý: mòn má phanh (công 350,000đ) | sao: 5").format(out["history"][0]["id"])
        assert line in prompt, f"sai dong lich su"
        print(f"PASS case26a inject day du: '{line[:60]}...'")

        # inspection/rating None -> "—".
        db.query(RepairOrder).update({RepairOrder.inspection_result: None,
                                      RepairOrder.service_rating: None})
        db.commit()
        _, prompt = await run("60T-123.45")
        assert "| xử lý: — (công 350,000đ) | sao: —" in prompt, "thieu fallback —"
        print("PASS case26b inspection/rating None -> '—'")

        # Xe khong lich su -> "(chua co lich su)".
        _, prompt = await run("61T-000.01")
        assert "(chưa có lịch sử)" in prompt
        print("PASS case26c rong -> '(chua co lich su)'")
    finally:
        db.close()


async def case27_suggest_parts():
    """3.3.1: filter + token-score + output + inject phu tung."""
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from app.models.models import User, SparePart
    from app.agents.common import suggest_parts
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="t27", password_hash="x", full_name="T", phone="1",
                role="technician", is_active=1))
    db.add_all([
        SparePart(part_number="P-001", name="Má phanh trước Toyota", brand="Toyota",
                  status="Đang kinh doanh", stock_quantity=12, price=450000,
                  warranty_period="12 tháng"),
        SparePart(part_number=None, name="Má phanh sau", brand=None,
                  status="Đang kinh doanh", stock_quantity=5, price=300000),
        SparePart(part_number="P-003", name="Má phanh het hang", brand="Toyota",
                  status="Đang kinh doanh", stock_quantity=0, price=100000),
        SparePart(part_number="P-004", name="Má phanh cu", brand="Toyota",
                  status="Ngừng kinh doanh", stock_quantity=10, price=100000),
        SparePart(part_number="P-005", name="Bugi", brand="NGK",
                  status="Đang kinh doanh", stock_quantity=9, price=80000),
    ])
    db.commit()
    try:
        got = suggest_parts(db, "má phanh kêu")
        assert [g["part_number"] for g in got] == ["P-001", None], got
        p1 = got[0]
        assert (p1["type"], p1["price"], p1["stock"], p1["warranty"]) == \
            ("part", 450000, 12, "12 tháng"), p1
        assert set(p1) == {"type", "id", "name", "part_number", "brand",
                           "price", "stock", "warranty"}, set(p1)
        print("PASS case27a filter + score 2 + dong diem giu thu tu DB")

        seen = {}
        def spy(message, history, context_msg):
            seen["prompt"] = message
            return "MOCK"
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            await diagnose_vehicle(
                DiagnoseIn(symptom="má phanh kêu báo giá"), db,
                {"sub": "t27", "role": "technician"})
        prompt = seen.get("prompt", "")
        assert "- Má phanh trước Toyota (mã P-001, Toyota): 450,000đ, tồn 12" in prompt, \
            "sai inject P-001"
        assert "- Má phanh sau (mã —, không rõ hãng): 300,000đ, tồn 5" in prompt, \
            "sai fallback —/khong ro hang"
        assert "P-003" not in prompt and "P-004" not in prompt and "Bugi" not in prompt
        print("PASS case27b inject dung format + fallback + loai het-hang")
    finally:
        db.close()


async def case28_tech_services_estimate():
    """3.4.1: suggest_services tech + estimate_range gop + note cong/VAT."""
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from app.models.models import User, ServiceCatalog
    from app.agents.common import suggest_services, estimate_range
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="t28", password_hash="x", full_name="T", phone="1",
                role="technician", is_active=1))
    db.add_all([
        ServiceCatalog(service_code="T28A", name="Bảo dưỡng phanh", category="Phanh",
                       description="Ve sinh", status="Active", base_price=300000,
                       duration_minutes=60),
        ServiceCatalog(service_code="T28B", name="Bảo dưỡng phanh cao cấp", category="Phanh",
                       description="Ve sinh ky", status="Active", base_price=400000,
                       promo_price=250000, duration_minutes=90),
        ServiceCatalog(service_code="T28C", name="Bảo dưỡng phanh tại nhà", category="Phanh",
                       description="Tan noi", status="Inactive", base_price=100000,
                       duration_minutes=60),
        ServiceCatalog(service_code="T28D", name="Rửa xe", category="Cham soc",
                       description="Rua vo", status="Active", base_price=200000,
                       duration_minutes=30),
    ])
    db.commit()
    try:
        got = suggest_services(db, "bảo dưỡng phanh")
        assert [g["name"] for g in got] == ["Bảo dưỡng phanh cao cấp", "Bảo dưỡng phanh"], got
        assert [(g["price"], g["promo"]) for g in got] == [(250000, True), (300000, False)]
        print("PASS case28a Active + tie-break promo + gia promo/base")

        est = estimate_range([{"price": p} for p in [450000, 300000, 150000, 100000]])
        assert est == {"min": 100000, "max": 900000}, est
        assert estimate_range([]) is None and estimate_range([{"price": 0}]) is None
        print("PASS case28b estimate {min:100k, max:900k}, rong -> None")

        seen = {}
        def spy(message, history, context_msg):
            seen["prompt"] = message
            return "MOCK"
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            out = await diagnose_vehicle(
                DiagnoseIn(symptom="bảo dưỡng phanh báo giá"), db,
                {"sub": "t28", "role": "technician"})
        prompt = seen.get("prompt", "")
        assert "- Bảo dưỡng phanh: 300,000đ" in prompt, "sai inject service"
        assert "chưa gồm công thợ" in prompt and "VAT" in prompt, "thieu note cong/VAT"
        assert out["estimate"] == {"min": 250000, "max": 550000}, out["estimate"]
        print("PASS case28c inject + note cong/VAT + estimate gop parts+services")
    finally:
        db.close()


async def case29_weather_rag_exact():
    """3.5.1: weather + RAG string exact trong prompt tech."""
    from datetime import datetime
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from app.models.models import User, DailyWeather
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="t29", password_hash="x", full_name="T", phone="1",
                role="technician", is_active=1))
    today = datetime.utcnow().strftime("%Y-%m-%d")
    db.add(DailyWeather(date=today, temperature=28.5, humidity=85.0, rainfall=12.0,
                        air_quality_aqi=90, weather_condition="Mưa rào",
                        ai_daily_advice="Kiem tra gat mua"))
    db.commit()

    async def run(rag):
        seen = {}
        def spy(message, history, context_msg):
            seen["prompt"] = message
            return "MOCK"
        with patch("app.services.gemini_service.get_gemini_response", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value=rag):
            out = await diagnose_vehicle(
                DiagnoseIn(symptom="kiem tra trời mưa"), db,
                {"sub": "t29", "role": "technician"})
        return out, seen.get("prompt", "")

    try:
        expect_w = (f"Thông tin thời tiết hôm nay ({today}): Mưa rào, "
                    f"Nhiệt độ 28.5°C, Độ ẩm 85.0%, Mưa 12.0mm, AQI 90. "
                    f"Lời khuyên AI hôm nay: Kiem tra gat mua")
        out, prompt = await run("[Trích từ c.txt#0]:\nNoi dung cam nang.")
        assert expect_w in prompt, "sai format weather"
        assert "[Trích từ c.txt#0]:\nNoi dung cam nang." in prompt, "RAG phai nguyen van"
        assert "MOCK" in out.get("message", "")
        print("PASS case29a weather exact + RAG nguyen van")

        db.query(DailyWeather).delete()
        db.commit()
        out, prompt = await run("")
        assert "TÀI LIỆU NỘI BỘ" not in prompt, "rong phai bo block RAG"
        assert "MOCK" in out.get("message", ""), "van chay khi thieu weather/RAG"
        print("PASS case29b thieu weather/RAG van chay 200")
    finally:
        db.close()


async def case30_tech_prompt_contract():
    """3.6.1: thu tu prompt tech + contract call + hau to."""
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from fastapi import HTTPException
    from app.models.models import User, Vehicle, RepairOrder
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle
    from app.agents.common import SAFETY_TECHNICAL

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="t30", password_hash="x", full_name="Tho Bay",
                phone="1", role="technician", is_active=1))
    db.flush()
    u = db.query(User).filter_by(username="t30").first()
    v = Vehicle(license_plate="62T-111.11", make="Toyota", model="Vios",
                user_id=u.id, current_odo=20000)
    db.add(v)
    db.flush()
    db.add(RepairOrder(vehicle_id=v.id, symptoms="keu cu",
                       inspection_result="xu ly cu", estimated_cost=100000,
                       status="Completed"))
    db.commit()

    async def run(symptom, ret, hist=None):
        seen = {}
        def spy(**kw):
            seen.update(kw)
            return ret
        with patch("app.agents.technical_agent.router.call_gemini_safe", side_effect=spy), \
             patch("app.agents.tools.search_knowledge", return_value="RAG_MARK"), \
             patch("app.agents.tools.get_weather_context", return_value="WEATHER_MARK"):
            try:
                out = await diagnose_vehicle(
                    DiagnoseIn(symptom=symptom, history=hist or []), db,
                    {"sub": "t30", "role": "technician", "name": "Tho Bay"})
            except HTTPException as e:
                return None, seen, e
        return out, seen, None

    try:
        hist = [{"sender": "user", "text": "old"}]
        out, seen, err = await run("xe 62T-111.11 keu trời mưa", {"ok": True, "message": "REPLY"}, hist)
        assert err is None, err
        p = seen["message"]
        marks = ["AI Cố vấn Kỹ thuật", "Tho Bay", "Hãy chú ý xem thời tiết",
                 "Triệu chứng:", "62T-111.11", "XE:", "LỊCH SỬ:", "XE ĐANG XÉT",
                 "TÀI LIỆU NỘI BỘ LIÊN QUAN:", "RAG_MARK",
                 "DANH MỤC (chỉ khi hỏi giá):", "LINH KIỆN CÒN HÀNG TRONG KHO",
                 "DỊCH VỤ ĐANG KINH DOANH LIÊN QUAN",
                 "THỜI TIẾT (1 câu, chỉ khi liên quan):", "WEATHER_MARK",
                 "YÊU CẦU TRẢ LỜI:", "NGUYÊN TẮC AN TOÀN"]
        pos = [p.find(m) for m in marks]
        assert all(i >= 0 for i in pos), [m for m, i in zip(marks, pos) if i < 0]
        assert pos == sorted(pos), f"sai thu tu: {pos}"
        assert seen.get("history") == hist, "history phai forward"
        assert seen.get("context_msg") == "Ho tro ky thuat vien chan doan"
        assert out["message"] == "REPLY" + SAFETY_TECHNICAL
        assert out["symptom"] == "xe 62T-111.11 keu trời mưa"
        print("PASS case30a thu tu prompt + kwargs + hau to + symptom echo")

        _, _, err = await run("keu", {"ok": False, "message": "TV loi quota"})
        assert err is not None and err.status_code == 503 and err.detail == "TV loi quota"
        print("PASS case30b ok False -> 503 TV")
    finally:
        db.close()


async def case31_tech_rbac_output_keys():
    """Prompt/Safety/Output tech: RBAC roles + full out keys 2 nhanh."""
    from fastapi import HTTPException
    from app.core.rbac import require_roles, Role
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from unittest.mock import patch
    from app.models.models import User, Vehicle, RepairOrder
    from app.agents.schemas import DiagnoseIn
    from app.agents.technical_agent.router import diagnose_vehicle

    # RBAC: technician/manager qua, customer 403, admin bypass.
    # require_roles tra ve ham role_checker (Depends boc o route);
    # goi truc tiep de test logic ma khong can HTTP.
    from fastapi.params import Depends as DependsClass
    from app.core import rbac as rbac_mod
    import inspect as _inspect
    assert "ADMIN" in _inspect.getsource(rbac_mod.require_roles), "thieu admin bypass"
    raw = require_roles([Role.TECHNICIAN, Role.MANAGER])
    fn = raw.dependency if isinstance(raw, DependsClass) else raw
    assert fn({"role": "technician"})["role"] == "technician"
    assert fn({"role": "manager"})["role"] == "manager"
    assert fn({"role": "admin"})["role"] == "admin", "admin phai bypass"
    try:
        fn({"role": "customer"})
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
        print("PASS case31a RBAC tech/manager qua, customer 403, admin bypass")
    else:
        raise AssertionError("customer phai 403")

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    db.add(User(username="t31", password_hash="x", full_name="T", phone="1",
                role="technician", is_active=1))
    db.flush()
    u = db.query(User).filter_by(username="t31").first()
    v = Vehicle(license_plate="63T-333.33", make="Toyota", model="Vios", user_id=u.id)
    db.add(v)
    db.flush()
    db.add(RepairOrder(vehicle_id=v.id, symptoms="keu", status="Completed"))
    db.commit()

    async def run(symptom):
        with patch("app.services.gemini_service.get_gemini_response", return_value="MOCK"), \
             patch("app.agents.tools.search_knowledge", return_value=""), \
             patch("app.agents.tools.get_weather_context", return_value=""):
            return await diagnose_vehicle(
                DiagnoseIn(symptom=symptom), db, {"sub": "t31", "role": "technician"})
    try:
        out = await run("xe 63T-333.33 keu")
        assert set(out) == {"vehicle", "history", "parts", "services",
                            "estimate", "message", "symptom"}, set(out)
        print("PASS case31b co xe -> du 7 keys")
        out = await run("keu chung chung khong bien so xyz")
        assert set(out) == {"parts", "services", "estimate", "message", "symptom"}, set(out)
        print("PASS case31c khong xe -> 5 keys (khong vehicle/history)")
    finally:
        db.close()


class _FakeRequest:
    pass


async def main():
    db, ids = setup_db()
    try:
        await case1_history_dung_xe(db, ids)
        await case2_sai_vehicle_id_403(db, ids)
        await case3_mat_key_msg_tv(db, ids)
        await case4_chroma_rong_van_tra_loi(db, ids)
        await case5_chatbot_stream_chung(db, ids)
        await case6_chatbot_stream_loi_tv(db, ids)
        await case7_unified_plate_parts(db, ids)
        await case8_rag_source_of_truth(db, ids)
        await case9_chunk_theo_cau()
        await case10_ingest_text_core()
        await case11_ingest_files_basename()
        await case12_ingest_db_document()
        await case13_reingest_route()
        await case14_rag_reload()
        await case15_search_filter_distance()
        await case16_backup_rebuild()
        await case17_parse_vi_date()
        await case18_parse_time_draft()
        await case19_appointment_draft_dup()
        await case20_booking_needs()
        await case21_suggest_services()
        await case22_estimate_range()
        await case23_prompt_contract()
        await case24_tech_input_validation()
        await case25_find_vehicle_no_user_filter()
        await case26_tech_inject_template()
        await case27_suggest_parts()
        await case28_tech_services_estimate()
        await case29_weather_rag_exact()
        await case30_tech_prompt_contract()
        await case31_tech_rbac_output_keys()
    finally:
        db.close()
    print("ALL 31 CASES PASSED (mock, khong can key that).")


def test_eval_gate_ai_diagnose():
    """Pytest gate P8-01/02: reuse script suite."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
