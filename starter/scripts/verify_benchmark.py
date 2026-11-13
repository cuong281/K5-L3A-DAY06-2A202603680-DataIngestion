"""Verify benchmark/questions.json against the normalized corpus BEFORE any retrieval run.

Run from starter/:  python -m scripts.verify_benchmark
Checks: required fields, >=20 questions, >=15 dev / >=5 test, >=3 filter questions with
>=1 in test, every evidence quote (primary and alternatives) is present on its gold page
after the same normalization the pipeline uses (whitespace-insensitive), and every filter
value exists and matches the article of each gold page. Writes results/benchmark_verification.json.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime

from src import corpus
from src.ingestion import load_pdf, normalize_text

REQUIRED = ("id", "split", "type", "question", "expected_answer", "gold_source_id", "gold_page", "evidence_quote", "filter")
QUESTIONS = corpus.REPO_DIR / "benchmark" / "questions.json"
OUT = corpus.REPO_DIR / "results" / "benchmark_verification.json"


def flat(text: str) -> str:
    """Normalize like the pipeline, then make the comparison insensitive to line breaks."""
    return re.sub(r"\s+", " ", normalize_text(text)).strip()


def main() -> None:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    pages = {p.page: flat(p.text) for p in load_pdf(corpus.LOCAL_PDF, corpus.DOCUMENT_ID, corpus.SOURCE_URL)}
    article_ids = {a["article_id"] for a in corpus.ARTICLES}
    errors, rows = [], []

    ids = Counter(q.get("id") for q in questions)
    errors += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for q in questions:
        qid = q.get("id", "?")
        missing = [f for f in REQUIRED if f not in q]
        if missing:
            errors.append(f"{qid}: missing fields {missing}")
            continue
        if q["split"] not in ("dev", "test"):
            errors.append(f"{qid}: split must be dev/test")
        if q["gold_source_id"] != corpus.DOCUMENT_ID:
            errors.append(f"{qid}: unknown gold_source_id {q['gold_source_id']}")
        golds = [{"gold_page": q["gold_page"], "evidence_quote": q["evidence_quote"]}] + q.get("alternatives", [])
        checked = []
        for gold in golds:
            page, quote = gold["gold_page"], gold["evidence_quote"]
            found = page in pages and flat(quote) in pages[page]
            other_pages = [n for n, text in pages.items() if n != page and flat(quote) in text]
            if not found:
                errors.append(f"{qid}: evidence not found on page {page}: {quote[:60]}...")
            article = corpus.article_for_page(page)["article_id"] if page in pages else None
            if q["filter"]:
                value = q["filter"].get("article_id")
                if value not in article_ids:
                    errors.append(f"{qid}: filter value {value!r} does not exist in corpus metadata")
                elif article != value:
                    errors.append(f"{qid}: gold page {page} is in {article}, not in filter {value}")
            checked.append({"gold_page": page, "article_id": article, "evidence_found": found,
                            "also_found_on_pages": other_pages})
        rows.append({"id": qid, "split": q["split"], "type": q["type"], "filter": q["filter"], "golds": checked})

    splits = Counter(q.get("split") for q in questions)
    filters = [q for q in questions if q.get("filter")]
    summary = {
        "questions": len(questions), "dev": splits["dev"], "test": splits["test"],
        "filter_questions": len(filters), "filter_questions_test": sum(q["split"] == "test" for q in filters),
        "types": dict(Counter(q.get("type") for q in questions)),
    }
    if summary["questions"] < 20: errors.append("need >= 20 questions")
    if summary["dev"] < 15: errors.append("need >= 15 dev questions")
    if summary["test"] < 5: errors.append("need >= 5 test questions")
    if summary["filter_questions"] < 3: errors.append("need >= 3 filter questions")
    if summary["filter_questions_test"] < 1: errors.append("need >= 1 filter question in test")

    summary["questions_sha256"] = hashlib.sha256(QUESTIONS.read_bytes()).hexdigest()
    summary["verified_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "errors": errors, "questions": rows},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    for row in rows:
        for g in row["golds"]:
            extra = f" (also on {g['also_found_on_pages']})" if g["also_found_on_pages"] else ""
            print(f"  {row['id']} {row['split']:4} p{g['gold_page']:02d} {g['article_id']:22} "
                  f"{'OK ' if g['evidence_found'] else 'MISSING'}{extra}")
    if errors:
        print("ERRORS:", *errors, sep="\n  ")
        sys.exit(1)
    print(f"All checks passed -> {OUT.relative_to(corpus.REPO_DIR)}")


if __name__ == "__main__":
    main()
