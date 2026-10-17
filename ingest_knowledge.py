"""Quy uoc NGUON SU THAT cho RAG.

- GarageDocument (SQL, models.py:298) la source of truth DUY NHAT.
- data/knowledge_base/*.txt chi la seed ban dau: sync 1 lan vao DB.
  Tieu de da ton tai trong DB -> GIU BAN DB, bo qua seed (khong ghi de
  sua doi cua quan ly); backfill cot 'source' neu thieu.
- Metadata chuan moi chunk (quy uoc 4.1.2):
  {"source": basename, "chunk_index": i, "doc_id": str, "document_type": ...}
  document_type chi 1 trong manual/guideline/policy/report.
  'source' de citation (rag_service.py:53); 'doc_id' (str) de xoa/upsert
  theo doc; id chunk on dinh dang doc_<id>_c<i>.
- Co hieu luc / xe ap dung nam TRONG content (dong header file seed),
  khong tach cot rieng de khoi migration.
"""
import glob
import os
import re
import unicodedata

from app.services import rag_service

KNOWLEDGE_DIR = "data/knowledge_base"
CHROMA_DB_DIR = "data/chroma_db"
COLLECTION_NAME = "garage_knowledge"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

VALID_DOC_TYPES = ("manual", "guideline", "policy", "report")
DEFAULT_DOC_TYPE = "guideline"

TYPE_MAP = {
    "GUIDELINE": "guideline", "HUONG-DAN": "guideline", "GUIDE": "guideline",
    "MANUAL": "manual", "KY-THUAT": "manual",
    "POLICY": "policy", "CHINH-SACH": "policy", "BAO-GIA": "policy",
    "REPORT": "report", "BAO-CAO": "report",
}


def normalize_doc_type(value) -> str:
    """Ep document_type ve 1 trong manual/guideline/policy/report."""
    v = str(value or "").strip().lower()
    return v if v in VALID_DOC_TYPES else DEFAULT_DOC_TYPE


def ensure_source_column(engine) -> bool:
    """Migration nhe cho DB cu: them cot source neu thieu. Tra True neu OK."""
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            cols = [r[1] for r in conn.exec_driver_sql(
                "PRAGMA table_info(garage_documents)").fetchall()]
            if "source" not in cols:
                conn.exec_driver_sql(
                    "ALTER TABLE garage_documents ADD COLUMN source VARCHAR")
                conn.commit()
                print("Migrated: them cot garage_documents.source.")
        return True
    except Exception as e:
        print(f"Schema check that bai: {e}")
        return False


def _ascii_upper(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    no_mark = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", "-", no_mark.strip().upper())


# Ran gioi cau: dau cham/than/cham hoi + khoang trang + chu hoa/so.
# Chu hoa gom ASCII + Latin mo rong (O, U, D, A-Y co dau).
SENT_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÞĐƠƯẠ-Ỹ0-9])")


def _split_segments(text: str) -> list:
    """Che van ban thanh don vi cau/dong (khong cat giua cau).

    Moi dong tach tiep tai ranh gioi cau; dau cau (.!?) dinh kem cau truoc.
    VD '120-200 bar' khong co dau cham + cach + chu hoa ben trong nen
    khong bao gio bi che doi."""
    segments = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        for part in SENT_END_RE.split(line):
            part = part.strip()
            if part:
                segments.append(part)
    return segments


def _overlap_tail(cur: str, overlap: int) -> str:
    """Lay duoi ~overlap ky tu, lui ve ranh gioi cau gan nhat de overlap
    cung bat dau dung dau cau. Khong co ranh -> giu nguyen duoi."""
    if overlap <= 0 or not cur:
        return ""
    tail = cur[-overlap:]
    m = re.search(r"[.!?]\s+", tail)
    if m and tail[m.end():].strip():
        return tail[m.end():]
    return tail


def chunk_text(text, chunk_size=800, overlap=100):
    """Chia van ban thanh chunk ~chunk_size, CAT TAI RANH GIOI CAU.

    Gom cac cau/dong den gan chunk_size roi cat (khong cat giua cau nhu
    '120-200 bar'); chunk tiep theo om ~overlap ky tu duoi chunk truoc,
    cung can theo cau. Segment don le vuot chunk_size (hiem) thi cat cung
    de dam bao tien tri. Tra list str (rong -> [])."""
    segments = _split_segments(text)
    # Cat cung segment qua dai truoc (dam bao moi piece <= chunk_size).
    pieces = []
    for seg in segments:
        while len(seg) > chunk_size:
            pieces.append(seg[:chunk_size])
            seg = seg[chunk_size:]
        if seg:
            pieces.append(seg)
    chunks, cur, fresh = [], "", True
    for piece in pieces:
        while True:
            add = piece if not cur else "\n" + piece
            if not cur or len(cur) + len(add) <= chunk_size:
                cur += add
                break
            if not fresh and cur:
                # Overlap + piece van tran -> bo overlap, mo chunk moi.
                cur, fresh = "", True
                continue
            chunks.append(cur)
            cur, fresh = _overlap_tail(cur, overlap), False
    if cur:
        chunks.append(cur)
    return chunks


def parse_seed_header(text: str, filename: str) -> tuple:
    """Dong dau '[LOAI] Tieu de' -> (title, document_type).
    Thieu/khong nhan dang -> (ten file, 'guideline')."""
    first = ""
    for line in (text or "").splitlines():
        if line.strip():
            first = line.strip()
            break
    m = re.match(r"^\[(.+?)\]\s*(.*)$", first)
    if not m:
        fallback = os.path.splitext(os.path.basename(filename))[0].replace("-", " ").replace("_", " ")
        return fallback, DEFAULT_DOC_TYPE
    raw_type = _ascii_upper(m.group(1))
    title = m.group(2).strip()
    if not title:
        title = os.path.splitext(os.path.basename(filename))[0].replace("-", " ").replace("_", " ")
    return title, TYPE_MAP.get(raw_type, DEFAULT_DOC_TYPE)


def _new_client():
    import chromadb
    return chromadb.PersistentClient(path=CHROMA_DB_DIR)


def _embedding_fn():
    from chromadb.utils import embedding_functions
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)


def get_collection(create: bool = False, client=None):
    """Lay collection Chroma (import lazy de module import duoc khi thieu lib)."""
    if create:
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    if not os.path.exists(CHROMA_DB_DIR) and not create:
        return None
    client = client or _new_client()
    ef = _embedding_fn()
    if create:
        return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)
    try:
        return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
    except Exception as e:
        print(f"Error connecting to ChromaDB: {e}")
        return None


def collection_has_legacy_int_doc_id(collection, sample: int = 5) -> bool:
    """Phat hien vector cu (doc_id kieu int, truoc quy uoc 4.1.2)."""
    try:
        got = collection.get(limit=sample, include=["metadatas"])
        for meta in (got.get("metadatas") or []):
            if isinstance((meta or {}).get("doc_id"), int):
                return True
    except Exception:
        pass
    return False


def backup_before_rebuild(collection=None, db_path="garage.db",
                           chroma_dir=None, backup_root="backup"):
    """Backup garage.db + chroma truoc --rebuild ra backup/YYYY-MM-DD/.
    Tra (backup_dir, chunks_before)."""
    import shutil
    from datetime import date

    chroma_dir = chroma_dir or CHROMA_DB_DIR
    dest = os.path.join(backup_root, date.today().strftime("%Y-%m-%d"))
    chunks_before = None
    try:
        if collection is not None:
            chunks_before = collection.count()
    except Exception:
        pass
    if os.path.exists(db_path):
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(db_path, os.path.join(dest, os.path.basename(db_path)))
    if os.path.isdir(chroma_dir):
        shutil.copytree(chroma_dir, os.path.join(dest, "chroma_db"),
                        dirs_exist_ok=True)
    print(f"Backup truoc rebuild: {dest} (chunks truoc: {chunks_before}).")
    return dest, chunks_before


def check_ingest_complete(chunks_before, chunks_after, backup_dir) -> bool:
    """Doi chieu so chunk truoc/sau rebuild de phat hien ingest hut.
    Tra True neu du, False neu hut (kem canh bao + vi tri backup)."""
    if chunks_before is None or chunks_after is None:
        print(f"Khong doi chieu duoc (truoc={chunks_before}, sau={chunks_after}).")
        return True
    if chunks_after < chunks_before:
        print(f"CANH BAO ingest hut: truoc {chunks_before} -> sau {chunks_after} "
              f"(mat {chunks_before - chunks_after} chunks). "
              f"Kiem tra backup {backup_dir}.")
        return False
    print(f"Doi chieu backup: truoc {chunks_before} -> sau {chunks_after} (OK).")
    return True


def rebuild_collection():
    """Xoa + tao lai collection (dung 1 lan de chuyen doc_id int -> str)."""
    client = _new_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    rag_service.reload()
    return get_collection(create=True, client=client)


def ensure_current_collection(collection):
    """Neu collection con vector legacy (doc_id int) -> rebuild + reset flag
    toan bo doc ve 0 de nap lai. Tra (collection, rebuilt)."""
    from app.models.models import GarageDocument
    from app.database import SessionLocal

    if collection is not None and collection_has_legacy_int_doc_id(collection):
        print("Phat hien metadata cu (doc_id int) -> rebuild collection theo 4.1.2.")
        collection = rebuild_collection()
        db = SessionLocal()
        try:
            db.query(GarageDocument).update({GarageDocument.is_ingested: 0})
            db.commit()
        finally:
            db.close()
        return collection, True
    return collection, False


def sync_seeds_to_db(db):
    """Nap file seed vao garage_documents (lan dau). Tra (inserted, skipped).
    DB la source of truth: trung title -> giu ban DB (chi backfill 'source'
    neu thieu); document_type luon ep ve 4 loai chuan."""
    from app.models.models import GarageDocument

    files = sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.txt")))
    if not files:
        print(f"Khong tim thay file .txt nao trong {KNOWLEDGE_DIR}!")
        return 0, 0
    inserted, skipped = 0, 0
    for path in files:
        basename = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            skipped += 1
            continue
        title, doc_type = parse_seed_header(content, path)
        doc_type = normalize_doc_type(doc_type)
        exists = db.query(GarageDocument).filter(GarageDocument.title == title).first()
        if exists:
            if not getattr(exists, "source", None):
                exists.source = basename
            if exists.document_type not in VALID_DOC_TYPES:
                exists.document_type = normalize_doc_type(exists.document_type)
            skipped += 1
            continue
        db.add(GarageDocument(title=title, content=content,
                              document_type=doc_type, source=basename,
                              is_ingested=0))
        inserted += 1
    db.commit()
    print(f"Sync seed -> DB: them {inserted}, giu ban DB (bo qua) {skipped}.")
    return inserted, skipped


def _doc_uid(doc) -> str:
    """Id logic cua doc trong Chroma: basename voi doc tu seed (on dinh
    qua moi lan tao lai DB), str(id) voi doc tao tu form (khong file)."""
    return getattr(doc, "source", None) or str(doc.id)


def _build_payload(content, source, doc_id, doc_type, chunk_size=800, overlap=100):
    """Dung chung: chunk -> (documents, metadatas, ids).
    Metadata chuan 4.1.2 + ids on dinh [f"doc{doc_id}_c{i}"]."""
    sid = str(doc_id)
    dtype = normalize_doc_type(doc_type)
    chunks = [c for c in chunk_text(content or "", chunk_size, overlap) if c.strip()]
    documents, metadatas, ids = [], [], []
    for i, chunk in enumerate(chunks):
        documents.append(chunk)
        metadatas.append({"source": source, "chunk_index": i,
                          "doc_id": sid, "document_type": dtype})
        ids.append(f"doc{sid}_c{i}")
    return documents, metadatas, ids


def ingest_text(content, source, doc_id, doc_type, collection=None,
                chunk_size=800, overlap=100) -> int:
    """Core nap 1 van ban vao Chroma (4.2.2): chunk -> build
    ids=[f"doc{doc_id}_c{i}"] (on dinh, khong trung) -> upsert.
    collection=None thi tu tao. Tra so chunk (rong -> 0)."""
    if collection is None:
        collection = get_collection(create=True)
    documents, metadatas, ids = _build_payload(
        content, source, doc_id, doc_type, chunk_size, overlap)
    if documents:
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        # Handle search dang cache o cung process thay du lieu moi ngay.
        rag_service.reload()
    return len(documents)


def build_doc_payload(doc):
    """Chia 1 GarageDocument -> (documents, metadatas, ids) de upsert.
    Metadata chuan 4.1.2: {source: basename, chunk_index, doc_id: str,
    document_type}; doc form (khong file) lay source = title, doc_id = str(id)."""
    source = getattr(doc, "source", None) or doc.title
    return _build_payload(doc.content, source, _doc_uid(doc), doc.document_type)


def ingest_document(db, doc, collection) -> int:
    """Nap 1 doc vao Chroma: xoa vector cu (where doc_id) -> upsert moi
    (qua core ingest_text), danh dau is_ingested=1. Tra so chunk."""
    source = getattr(doc, "source", None) or doc.title
    uid = _doc_uid(doc)
    try:
        collection.delete(where={"doc_id": uid})
    except Exception:
        pass
    n = ingest_text(doc.content, source, uid, doc.document_type, collection)
    doc.is_ingested = 1
    db.commit()
    return n


def ingest_document_by_id(db, doc_id, collection=None) -> int:
    """Dung cho manager upload (tai su dung session san co):
    nap 1 doc vua tao (collection tu tao neu thieu)."""
    from app.models.models import GarageDocument

    doc = db.query(GarageDocument).filter(GarageDocument.id == doc_id).first()
    if not doc:
        return 0
    if collection is None:
        collection = get_collection(create=True)
    return ingest_document(db, doc, collection)


def ingest_db_document(doc_id, collection=None) -> int:
    """Nap 1 GarageDocument tu garage.db (tu mo/dong session):
    doc(id, title, content, document_type)
    -> ingest_text(doc.content, doc.title, doc.id, doc.document_type);
    xong doc.is_ingested=1 + commit; loi -> giu 0.
    Tra so chunk (doc khong ton tai -> 0)."""
    from app.database import SessionLocal
    from app.models.models import GarageDocument

    db = SessionLocal()
    try:
        doc = db.query(GarageDocument).filter(GarageDocument.id == doc_id).first()
        if not doc:
            return 0
        if collection is None:
            collection = get_collection(create=True)
        n = ingest_text(doc.content, doc.title, doc.id, doc.document_type,
                        collection)
        doc.is_ingested = 1
        db.commit()
        return n
    except Exception as e:
        db.rollback()
        try:
            doc = db.query(GarageDocument).filter(GarageDocument.id == doc_id).first()
            if doc is not None:
                doc.is_ingested = 0
                db.commit()
        except Exception:
            db.rollback()
        print(f"ingest_db_document #{doc_id} loi, giu is_ingested=0: {e}")
        return 0
    finally:
        db.close()


def ingest_files(pattern: str = "*.txt", collection=None) -> int:
    """Nap truc tiep file txt trong KNOWLEDGE_DIR (vong glob cu), moi file
    -> ingest_text(content, source=basename, doc_id=basename, doc_type).
    Cung output voi flow DB (seed doc dung basename lam doc_id) nen khong
    trung lap khi chay kem ingest_pending. Luon chay offline voi
    all-MiniLM-L6-v2 (EMBEDDING_MODEL). Tra tong so chunk."""
    assert EMBEDDING_MODEL == "all-MiniLM-L6-v2", "chi chay offline all-MiniLM-L6-v2"
    if collection is None:
        collection = get_collection(create=True)
    total = 0
    for path in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, pattern))):
        basename = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            continue
        _, doc_type = parse_seed_header(content, path)
        n = ingest_text(content, basename, basename, doc_type, collection)
        print(f"Ingest file: {basename} ({doc_type}) -> {n} chunks")
        total += n
    return total


def ingest_pending(db, collection, force: bool = False) -> tuple:
    """Nap doc chua ingest (is_ingested=0); force=True nap lai tat ca
    (dung khi doi tham so chunk). Tra (tong chunks, so docs)."""
    from app.models.models import GarageDocument

    if force:
        db.query(GarageDocument).update({GarageDocument.is_ingested: 0})
        db.commit()
    pending = db.query(GarageDocument).filter(GarageDocument.is_ingested == 0).all()
    total = 0
    for doc in pending:
        print(f"Ingest doc #{doc.id}: {doc.title} ({doc.document_type})")
        total += ingest_document(db, doc, collection)
    return total, len(pending)


def ingest_documents(force: bool = False, rebuild: bool = False):
    """Flow chuan: migrate schema -> sync seed -> DB, roi nap doc chua
    ingest vao Chroma (rebuild 1 lan neu con metadata cu doc_id int).
    force=True nap lai toan bo (VD sau khi doi chunk_size/overlap).
    rebuild=True xoa sach collection truoc (VD sau khi doi scheme id)."""
    from app.database import SessionLocal
    from app.database import Base
    from app.database import engine
    from app.models import models as _models  # noqa: F401 (dang ky metadata)

    print("Bat dau dong bo seed + ingest RAG...")
    Base.metadata.create_all(bind=engine)
    ensure_source_column(engine)
    db = SessionLocal()
    try:
        sync_seeds_to_db(db)
        collection = get_collection(create=True)
        backup_dir, chunks_before = None, None
        if rebuild:
            print("Rebuild: backup truoc, xoa sach collection + nap lai toan bo.")
            backup_dir, chunks_before = backup_before_rebuild(collection)
            collection = rebuild_collection()
            force = True
        else:
            collection, _ = ensure_current_collection(collection)
        total, n_docs = ingest_pending(db, collection, force=force)
        try:
            chunks_after = collection.count()
        except Exception:
            chunks_after = None
        print(f"Hoan tat: luu {total} chunks tu {n_docs} docs vao Vector Database.")
        if rebuild:
            check_ingest_complete(chunks_before, chunks_after, backup_dir)
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    ingest_documents(force="--force" in args, rebuild="--rebuild" in args)
