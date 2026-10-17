"""Eval RAG P6-03 (4.4.1): 10 query co dinh, doi hoi pass >= 8/10.

Moi query assert 2 dieu kien:
  1. source ky vong co trong result cua search_knowledge_base (top-3).
  2. distance[0] (top-1) < 1.2.

Chay: python test_rag.py (exit 0 = dat, exit 1 = rot).
Yeu cau: data/chroma_db da ingest (python ingest_knowledge.py).
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

QUERIES = [
    # 4 cau goc: hut ga / loi / PCV / ap bom xang
    ("xe hụt ga C200", "sample_guide.txt"),
    ("mã lỗi P0171", "sample_guide.txt"),
    ("van PCV kêu rít", "sample_guide.txt"),
    ("áp bơm xăng C200", "sample_guide.txt"),
    # 6 cau tu 4 file moi: bao-duong (2), phanh-lop (2), dieu-hoa (1), bao-gia (1)
    ("lịch bảo dưỡng định kỳ bao nhiêu km", "bao-duong-dinh-ky.txt"),
    ("bảo dưỡng lớn 40000km", "bao-duong-dinh-ky.txt"),
    ("má phanh mòn kêu ken két", "phanh-lop.txt"),
    ("dầu phanh DOT4 khi nào thay", "phanh-lop.txt"),
    ("thiếu gas điều hòa", "dieu-hoa-dien.txt"),
    ("báo giá VAT công thợ", "bao-gia-chinh-sach.txt"),
]
MAX_DISTANCE = 1.2
PASS_MIN = 8


def main() -> int:
    from app.services.rag_service import get_chroma_collection, search_knowledge_base

    col = get_chroma_collection()
    if col is None:
        print("FAIL: chua ingest (thieu data/chroma_db). Chay python ingest_knowledge.py truoc.")
        return 1

    passed = 0
    for q, exp in QUERIES:
        r = col.query(query_texts=[q], n_results=3)
        d0 = r["distances"][0][0]
        top1 = r["metadatas"][0][0].get("source", "?")
        result = search_knowledge_base(q)
        ok_src = exp in result
        ok_dist = d0 is not None and d0 < MAX_DISTANCE
        ok = ok_src and ok_dist
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} {q!r} "
              f"(top1={top1} d0={d0:.3f} src_in_result={ok_src})")

    print(f"{passed}/{len(QUERIES)} (can >= {PASS_MIN})")
    return 0 if passed >= PASS_MIN else 1


if __name__ == "__main__":
    sys.exit(main())
