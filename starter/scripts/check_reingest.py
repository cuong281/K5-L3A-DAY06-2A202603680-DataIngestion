"""Demonstrate how the store handles a CHANGED source document (GUIDE §3).

Run from starter/:  python -m scripts.check_reingest
Uses real bge-m3 vectors on 4 real chunks of page 11 under a temporary strategy name, then:
  1. ingest v1                        -> 4 inserted
  2. re-ingest v1 unchanged           -> 0 embedded, 0 written, 0 deleted (no duplicates)
  3. ingest v2: 1 chunk edited, 1 removed -> 1 re-embedded/updated, 1 obsolete chunk deleted
The temporary rows are removed at the end. Output: results/reingest_check.json
"""
from __future__ import annotations

import json
import os
from dataclasses import replace

from dotenv import load_dotenv

from src import corpus
from src.chunking import by_paragraph
from src.embeddings import BgeM3Embedder
from src.ingestion import load_pdf
from src.store import TABLE, PgVectorStore

STRATEGY = "_reingest_check"


def sync(store: PgVectorStore, embedder: BgeM3Embedder, chunks: list) -> dict:
    existing = store.existing_hashes(STRATEGY)
    changed = [c for c in chunks if existing.get(c.chunk_id) != store.content_hash(c)]
    stats = store.upsert(STRATEGY, changed, embedder.embed_documents([c.text for c in changed]),
                         keep_ids={c.chunk_id for c in chunks})
    return {"embedded": len(changed), **stats, "rows": store.count(STRATEGY)}


def main() -> None:
    load_dotenv(corpus.STARTER_DIR / ".env")
    page = load_pdf(corpus.LOCAL_PDF, corpus.DOCUMENT_ID, corpus.SOURCE_URL)[10]  # page 11: 5 B-chunks
    page.metadata.update(article_id="a3_camnang_btttt", article_title="test")
    v1 = by_paragraph(page, 1000)[:4]
    assert len(v1) == 4, "test page must yield at least 4 chunks"
    v2 = [replace(v1[0], text=v1[0].text + " (đoạn được sửa ở phiên bản 2)"), *v1[1:3]]  # edit #0, drop #3

    embedder = BgeM3Embedder()
    store = PgVectorStore(os.getenv("DATABASE_URL", ""), embedder.dimensions, embedder.model_name)
    store.create_schema()
    try:
        steps = {
            "1_ingest_v1": sync(store, embedder, v1),
            "2_reingest_v1_unchanged": sync(store, embedder, v1),
            "3_ingest_v2_edit1_drop1": sync(store, embedder, v2),
        }
    finally:
        with store._connect() as conn:
            conn.execute(f"DELETE FROM {TABLE} WHERE strategy = %s", (STRATEGY,))
    expected = {"1_ingest_v1": (4, 4, 0, 0, 4), "2_reingest_v1_unchanged": (0, 0, 0, 0, 4),
                "3_ingest_v2_edit1_drop1": (1, 0, 1, 1, 3)}
    result = {"steps": steps, "passed": all(
        (s["embedded"], s["inserted"], s["updated"], s["deleted"], s["rows"]) == expected[k] for k, s in steps.items())}
    out = corpus.REPO_DIR / "results" / "reingest_check.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
