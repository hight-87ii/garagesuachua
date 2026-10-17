import os

CHROMA_DB_DIR = "data/chroma_db"

# Nguong khoang cach cosine: chunk xa hon thi loai (giam nhieu RAG).
MAX_DISTANCE = 1.2

# Gon prompt (giam latency): chi lay 2 chunk, moi chunk cat 800 ky tu.
RAG_N_RESULTS = 2
RAG_CHUNK_TRUNCATE = 800

# Khởi tạo client tĩnh (chỉ tạo 1 lần khi app chạy)
client = None
sentence_transformer_ef = None
collection = None

def reload():
    """Reset handle Chroma da cache de lan search sau thay du lieu moi nhat.
    Goi sau moi ingest -> khong can restart uvicorn (ap dung ingest trong
    cung process, VD route upload/reingest cua manager).
    Chi reset client/collection (co the stale sau upsert/delete_collection);
    giu embedding function (stateless theo du lieu, tai lai ton vai giay)."""
    global client, collection
    client = None
    collection = None

def get_chroma_collection():
    global client, sentence_transformer_ef, collection
    if not os.path.exists(CHROMA_DB_DIR):
        return None

    if collection is None:
        try:
            # Import lười để ứng dụng vẫn chạy khi chưa cài chromadb
            import chromadb
            from chromadb.utils import embedding_functions

            client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
            sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            collection = client.get_or_create_collection(
                name="garage_knowledge",
                embedding_function=sentence_transformer_ef
            )
        except Exception as e:
            print(f"Error connecting to ChromaDB: {e}")
            return None
    return collection

def search_knowledge_base(query: str, n_results: int = RAG_N_RESULTS) -> str:
    """
    Nhận câu hỏi của người dùng, tìm kiếm trong Vector DB và trả về đoạn text phù hợp.
    """
    col = get_chroma_collection()
    if not col:
        return ""
    try:
        if col.count() == 0:
            return ""
    except Exception:
        pass

    try:
        results = col.query(
            query_texts=[query],
            n_results=n_results
        )

        docs = (results.get('documents') or [[]])[0] or []
        metas = (results.get('metadatas') or [[]])[0] or []
        dists = (results.get('distances') or [[]])[0] or []
        if not docs:
            return ""

        # Noi cac doan tai lieu tim duoc lai voi nhau, kem citation day du
        # metadata {source, chunk_index, doc_id, document_type}.
        # Loc: bo chunk qua xa (distance > MAX_DISTANCE) + chunk rong.
        context_texts = []
        for i, doc in enumerate(docs):
            if not (doc or "").strip():
                continue
            if i < len(dists) and dists[i] is not None and dists[i] > MAX_DISTANCE:
                continue
            meta = (metas[i] if i < len(metas) else None) or {}
            source = meta.get("source", "Tài liệu nội bộ")
            cidx = meta.get("chunk_index", "?")
            # Gon prompt: moi chunk toi da 800 ky tu (citation giu nguyen).
            context_texts.append(f"[Trích từ {source}#{cidx}]:\n{doc[:RAG_CHUNK_TRUNCATE]}")
            
        return "\n\n".join(context_texts)
    except Exception as e:
        print(f"Lỗi khi search ChromaDB: {e}")
        return ""
