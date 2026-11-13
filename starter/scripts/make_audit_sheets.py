"""Create the manual-audit sheets in results/audit/ (labels are left EMPTY for the human grader).

Run from starter/ after `python -m src.run --split test`:  python -m scripts.make_audit_sheets
Sheets (UTF-8 with BOM so Excel shows Vietnamese correctly):
  coherence_labels.csv  10 fixed source positions x strategies A, B (C reuses B's chunks -> same label)
  metadata_audit.csv    test questions x top-3 x A/B/C: check source/page/article_id against the PDF
  grounding_labels.csv  test questions x A/B/C: is the top-3 evidence enough to answer and trace?
Positions for coherence are fixed by rule, before looking at any label: the midpoint of the flat text
of the first 10 counted pages in page order (manifest.counted_pages[:10]).
Existing sheets are never overwritten (labels may already be filled in); delete one to regenerate it.
"""
from __future__ import annotations

import csv
import json

from src import corpus
from src.chunking import by_paragraph, fixed_size, flat_text
from src.evaluation import flat
from src.ingestion import load_pdf
from src.run import INDEXES

AUDIT = corpus.REPO_DIR / "results" / "audit"
CONTEXT = 60


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    path = AUDIT / name
    if path.exists():
        print(f"skip {path.relative_to(corpus.REPO_DIR)} (exists; delete it to regenerate)")
        return
    AUDIT.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"wrote {path.relative_to(corpus.REPO_DIR)} ({len(rows)} rows)")


def coherence_sheet(pages: dict) -> None:
    manifest = json.loads((corpus.REPO_DIR / "data" / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for n, page_no in enumerate(manifest["counted_pages"][:10], start=1):
        page = pages[page_no]
        text = flat_text(page)
        offset = len(text) // 2
        context = text[max(0, offset - CONTEXT):offset + CONTEXT]
        builders = {"A": fixed_size(page, INDEXES["A"]["size"], INDEXES["A"]["overlap"]),
                    "B": by_paragraph(page, INDEXES["B"]["max_size"])}
        for strategy, chunks in builders.items():
            chunk = next(c for c in chunks if c.metadata["char_start"] <= offset < c.metadata["char_end"])
            rows.append([f"pos{n:02d}", page_no, offset, context, strategy, chunk.chunk_id,
                         len(chunk.text), chunk.text, "", ""])
    write_csv("coherence_labels.csv",
              ["position_id", "page", "char_offset", "source_context", "strategy", "chunk_id",
               "chunk_chars", "chunk_text", "label_0_1_2", "reason"], rows)


def metadata_sheet(pages: dict, traces: list) -> None:
    rows = []
    for t in traces:
        for h in t["result"]["hits"]:
            on_page = flat(h["text"]) in flat_text(pages[h["page"]])
            expected_article = corpus.article_for_page(h["page"])["article_id"]
            rows.append([t["strategy"], t["id"], h["rank"], h["chunk_id"], h["source"], h["page"],
                         h["article_id"], json.dumps(t["filter_requested"], ensure_ascii=False),
                         json.dumps(t["filter_applied"], ensure_ascii=False),
                         "yes" if on_page else "NO", "yes" if expected_article == h["article_id"] else "NO",
                         h["text"], "", "", "", ""])
    write_csv("metadata_audit.csv",
              ["strategy", "question_id", "rank", "chunk_id", "source", "page", "article_id",
               "filter_requested", "filter_applied", "auto_text_found_on_page", "auto_article_matches_page",
               "chunk_text", "source_ok_y_n", "page_ok_y_n", "article_ok_y_n", "notes"], rows)


def grounding_sheet(traces: list, questions: dict) -> None:
    rows = []
    for t in traces:
        q = questions[t["id"]]
        top3 = "\n\n".join(f"[#{h['rank']} p{h['page']} {h['article_id']}] {h['text']}" for h in t["result"]["hits"])
        rows.append([t["strategy"], t["id"], q["question"], json.dumps(q["filter"], ensure_ascii=False),
                     q["expected_answer"], q["gold_page"], q["evidence_quote"],
                     "yes" if t["result"]["hit@3"] else "no", top3, "", ""])
    write_csv("grounding_labels.csv",
              ["strategy", "question_id", "question", "filter", "expected_answer", "gold_page", "evidence_quote",
               "auto_evidence_hit@3_proxy", "top3_chunks", "label_0_1_2", "reason"], rows)


def main() -> None:
    pages = {p.page: p for p in load_pdf(corpus.LOCAL_PDF, corpus.DOCUMENT_ID, corpus.SOURCE_URL)}
    traces_path = corpus.REPO_DIR / "results" / "traces_test.jsonl"
    if not traces_path.exists():
        raise SystemExit("results/traces_test.jsonl missing: run `python -m src.run --split test` first")
    traces = [json.loads(line) for line in traces_path.open(encoding="utf-8")]
    questions = {q["id"]: q for q in json.loads((corpus.REPO_DIR / "benchmark" / "questions.json")
                                                .read_text(encoding="utf-8"))}
    coherence_sheet(pages)
    metadata_sheet(pages, traces)
    grounding_sheet(traces, questions)


if __name__ == "__main__":
    main()
