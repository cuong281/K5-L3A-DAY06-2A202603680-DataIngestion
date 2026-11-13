"""Day 06 pipeline: ingest -> chunk -> embed -> store -> retrieve top-3 -> evaluate.

Run from starter/ (Docker pgvector up, .env present):
    python -m src.run --split dev     # ingest/refresh indexes, run dev, apply the pre-registered rule
    python -m src.run --split test    # refused until results/selection.json exists (chosen on dev)

Strategies (same corpus, model, store, metric, benchmark):
    A: fixed-size 500 chars, overlap 50, no filter
    B: paragraph/heading chunks <= 1000 chars, no filter
    C: exactly B's index + article_id filter, applied only when a question provides one
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

from . import corpus
from .chunking import by_paragraph, fixed_size
from .embeddings import BgeM3Embedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pdf
from .store import PgVectorStore

RESULTS = corpus.REPO_DIR / "results"
QUESTIONS = corpus.REPO_DIR / "benchmark" / "questions.json"
MANIFEST = corpus.REPO_DIR / "data" / "manifest.json"
VERIFICATION = RESULTS / "benchmark_verification.json"
SELECTION = RESULTS / "selection.json"
TOP_K = 3

INDEXES = {
    "A": {"chunking": "fixed_size", "size": 500, "overlap": 50},
    "B": {"chunking": "by_paragraph", "max_size": 1000},
}
STRATEGIES = {
    "A": {"index": "A", "use_filter": False, "description": "fixed-size 500/50, không lọc"},
    "B": {"index": "B", "use_filter": False, "description": "theo đoạn/heading <= 1000, không lọc"},
    "C": {"index": "B", "use_filter": True, "description": "index của B + lọc article_id khi câu hỏi có filter"},
}
SELECTION_RULE = ("Chọn trên dev: (1) Evidence Hit@3 cao nhất; (2) các chiến lược kém tốt nhất <= 1 câu "
                  "được so tiếp bằng Hit@1; (3) nếu vẫn hòa: ít chunk hơn, rồi không cần filter hơn "
                  "(benchmark/README.md, chốt trước khi chạy).")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_corpus() -> list:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = sha256_file(corpus.LOCAL_PDF)
    if actual != manifest["sha256"]:
        sys.exit(f"PDF hash {actual[:12]} != manifest {manifest['sha256'][:12]}; rerun scripts.build_manifest")
    if manifest["counted_page_count"] < 30:
        sys.exit(f"manifest counts only {manifest['counted_page_count']} content pages (< 30)")
    pages = load_pdf(corpus.LOCAL_PDF, corpus.DOCUMENT_ID, corpus.SOURCE_URL)
    for page in pages:
        article = corpus.article_for_page(page.page)
        page.metadata.update(article_id=article["article_id"], article_title=article["title"])
    return [p for p in pages if p.text]  # empty pages are logged in the manifest, nothing to chunk


def build_chunks(pages: list) -> dict[str, list]:
    out = {}
    for name, cfg in INDEXES.items():
        if cfg["chunking"] == "fixed_size":
            out[name] = [c for p in pages for c in fixed_size(p, cfg["size"], cfg["overlap"])]
        else:
            out[name] = [c for p in pages for c in by_paragraph(p, cfg["max_size"])]
    return out


def chunk_stats(chunks: list, tokenizer) -> dict:
    lengths = [len(c.text) for c in chunks]
    tokens = [len(tokenizer(c.text, add_special_tokens=False)["input_ids"]) for c in chunks]
    return {
        "chunks": len(chunks), "chars_total": sum(lengths),
        "chars_min": min(lengths), "chars_median": statistics.median(lengths),
        "chars_mean": round(statistics.mean(lengths), 1), "chars_max": max(lengths),
        "tokens_total": sum(tokens), "tokens_max": max(tokens),
        "pages_covered": len({c.page for c in chunks}),
    }


def ingest(store: PgVectorStore, embedder, name: str, chunks: list) -> dict:
    """Embed only new/changed chunks, upsert, delete obsolete; then prove a re-run changes nothing."""
    existing = store.existing_hashes(name)
    changed = [c for c in chunks if existing.get(c.chunk_id) != store.content_hash(c)]
    started = time.perf_counter()
    vectors = embedder.embed_documents([c.text for c in changed])
    embed_seconds = time.perf_counter() - started
    stats = store.upsert(name, changed, vectors, keep_ids={c.chunk_id for c in chunks})
    rows_after = store.count(name)
    # Re-ingestion check with the same source version: nothing should need re-embedding or writing.
    recheck = store.existing_hashes(name)
    pending = sum(recheck.get(c.chunk_id) != store.content_hash(c) for c in chunks)
    rerun = store.upsert(name, [], [], keep_ids={c.chunk_id for c in chunks})
    return {
        "index": name, "chunks_current": len(chunks), "embedded_now": len(changed),
        "embed_seconds": round(embed_seconds, 2), **stats, "rows_after": rows_after,
        "reingest_check": {"pending_after_ingest": pending, "deleted_on_rerun": rerun["deleted"],
                           "rows_after_rerun": store.count(name),
                           "no_duplicates": rows_after == len(chunks) == store.count(name) and pending == 0},
    }


def select_strategy(summary: dict, stats: dict) -> dict:
    """Apply the rule pre-registered in benchmark/README.md to dev metrics only."""
    dev = {s: summary[s]["dev"] for s in STRATEGIES}
    best = max(m["hit@3"] for m in dev.values())
    step1 = [s for s, m in dev.items() if m["hit@3"] >= best - 1]
    best_h1 = max(dev[s]["hit@1"] for s in step1)
    step2 = [s for s in step1 if dev[s]["hit@1"] == best_h1]
    n_chunks = {s: stats[STRATEGIES[s]["index"]]["chunks"] for s in STRATEGIES}
    chosen = sorted(step2, key=lambda s: (n_chunks[s], STRATEGIES[s]["use_filter"]))[0]
    return {"rule": SELECTION_RULE, "decided_at": now(),
            "dev_metrics": {s: {k: dev[s][k] for k in ("N", "hit@1", "hit@3")} | {"chunks": n_chunks[s]} for s in dev},
            "after_step1_hit3": step1, "after_step2_hit1": step2, "chosen": chosen,
            "chosen_config": STRATEGIES[chosen] | {"index_config": INDEXES[STRATEGIES[chosen]["index"]]}}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    args = parser.parse_args(argv)

    load_dotenv(corpus.STARTER_DIR / ".env")
    verification = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    questions_hash = sha256_file(QUESTIONS)
    if verification["errors"] or verification["summary"]["questions_sha256"] != questions_hash:
        sys.exit("benchmark/questions.json changed since verification (or has errors): run scripts.verify_benchmark")
    if args.split == "test" and not SELECTION.exists():
        sys.exit("Refusing to run test: choose the strategy on dev first (results/selection.json missing)")
    questions = [q for q in json.loads(QUESTIONS.read_text(encoding="utf-8")) if q["split"] == args.split]

    run_started = now()
    pages = load_corpus()
    chunks = build_chunks(pages)
    t0 = time.perf_counter()
    embedder = BgeM3Embedder()
    model_load_seconds = round(time.perf_counter() - t0, 2)
    store = PgVectorStore(os.getenv("DATABASE_URL", ""), embedder.dimensions, embedder.model_name)
    store.create_schema()
    ingest_log = [ingest(store, embedder, name, items) for name, items in chunks.items()]
    stats = {name: chunk_stats(items, embedder._model.tokenizer) for name, items in chunks.items()}

    traces = []
    query_vectors = {}
    for strategy, cfg in STRATEGIES.items():
        for q in questions:
            if q["id"] not in query_vectors:
                query_vectors[q["id"]] = embedder.embed_query(q["question"])
            applied = q["filter"] if (cfg["use_filter"] and q["filter"]) else None
            started = time.perf_counter()
            hits = store.search(cfg["index"], query_vectors[q["id"]], TOP_K, applied)
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            traces.append({
                "strategy": strategy, "index": cfg["index"], "split": q["split"], "id": q["id"],
                "type": q["type"], "question": q["question"], "filter_requested": q["filter"],
                "filter_applied": applied, "gold_page": q["gold_page"],
                "alternative_pages": [a["gold_page"] for a in q.get("alternatives", [])],
                "evidence_quote": q["evidence_quote"], "search_ms": latency_ms,
                "result": evaluate_query(q, hits),
            })

    summary = summarize(traces)
    with (RESULTS / f"traces_{args.split}.jsonl").open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace, ensure_ascii=False) + "\n")
    with psycopg_version(store) as db:
        environment = {
            "python": platform.python_version(), "os": platform.platform(), "cpu": platform.processor(),
            "packages": {p: version(p) for p in ("torch", "sentence-transformers", "transformers",
                                                  "pymupdf", "psycopg")},
            "database": db,
        }
    write_json(RESULTS / f"metrics_{args.split}.json", {
        "split": args.split, "run_started": run_started, "run_finished": now(),
        "questions_sha256": questions_hash, "pdf_sha256": sha256_file(corpus.LOCAL_PDF),
        "model": {"name": embedder.model_name, "revision": embedder.revision, "dimensions": embedder.dimensions,
                  "device": "cpu", "normalize": True, "query_instruction": None, "load_seconds": model_load_seconds},
        "store": {"backend": "PostgreSQL + pgvector", "table": "day6_chunks", "metric": "cosine (<=>)",
                  "search": "exact (no ANN index)", "top_k": TOP_K},
        "cost_usd": 0, "environment": environment,
        "indexes": INDEXES, "strategies": STRATEGIES, "chunk_stats": stats, "ingest": ingest_log,
        "summary": summary,
    })
    with (RESULTS / "ingest_runs.jsonl").open("a", encoding="utf-8") as handle:  # history, never overwritten
        handle.write(json.dumps({"run_started": run_started, "split": args.split,
                                 "model_load_seconds": model_load_seconds, "ingest": ingest_log},
                                ensure_ascii=False) + "\n")
    if args.split == "dev" and not SELECTION.exists():  # decided once, on the first dev run
        write_json(SELECTION, select_strategy(summary, stats))

    print(f"[{args.split}] questions={len(questions)} model={embedder.model_name}@{embedder.revision[:8]}")
    for log in ingest_log:
        print(f"  index {log['index']}: chunks={log['chunks_current']} embedded_now={log['embedded_now']} "
              f"({log['embed_seconds']}s) ins/upd/del={log['inserted']}/{log['updated']}/{log['deleted']} "
              f"rows={log['rows_after']} no_duplicates={log['reingest_check']['no_duplicates']}")
    for strategy in STRATEGIES:
        m = summary[strategy][args.split]
        flt = f" filter {m['filter_compliant']}/{m['filter_questions']}" if m["filter_questions"] else ""
        print(f"  {strategy}: Hit@1 {m['hit@1']}/{m['N']}  Hit@3 {m['hit@3']}/{m['N']}  "
              f"split={m['evidence_split_cases']}{flt}  missed={m['missed_ids']}")
    if args.split == "dev":
        print(f"  selected (pre-registered rule): {json.loads(SELECTION.read_text(encoding='utf-8'))['chosen']}")


class psycopg_version:
    """Context helper returning PostgreSQL and pgvector versions for the run record."""

    def __init__(self, store: PgVectorStore) -> None:
        self.store = store

    def __enter__(self) -> dict:
        with self.store._connect() as conn:
            pg = conn.execute("SELECT current_setting('server_version')").fetchone()[0]
            vec = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
        return {"postgresql": pg, "pgvector": vec}

    def __exit__(self, *exc) -> None:
        return None


if __name__ == "__main__":
    main()
