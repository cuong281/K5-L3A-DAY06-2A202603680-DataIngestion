"""Aggregate the HUMAN labels in results/audit/*.csv into results/audit_summary.json.

Run from starter/ after filling the label columns:  python -m scripts.summarize_audit
Refuses to summarize while any label is missing or invalid, and lists the offending rows.
- Coherence: mean of 0/1/2 labels per strategy (/2). C reuses B's chunks, so C = B by construction.
- Metadata: records whose source, page AND article_id are all marked 'y' / records checked;
  filter compliance (top-3 all inside the requested article) / questions with a filter, or N/A.
- Grounding: count of labels 0/1/2 and mean (/2) per strategy; Evidence Hit@3 shown only as a proxy.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict

from src import corpus

AUDIT = corpus.REPO_DIR / "results" / "audit"


def read(name: str) -> list[dict]:
    with (AUDIT / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    problems: list[str] = []
    coherence = read("coherence_labels.csv")
    metadata = read("metadata_audit.csv")
    grounding = read("grounding_labels.csv")

    for r in coherence:
        if r["label_0_1_2"].strip() not in {"0", "1", "2"} or not r["reason"].strip():
            problems.append(f"coherence {r['position_id']} {r['strategy']}: need label 0/1/2 and reason")
    for r in metadata:
        if any(r[k].strip().lower() not in {"y", "n"} for k in ("source_ok_y_n", "page_ok_y_n", "article_ok_y_n")):
            problems.append(f"metadata {r['strategy']} {r['question_id']} #{r['rank']}: mark y/n in the 3 *_ok columns")
    for r in grounding:
        if r["label_0_1_2"].strip() not in {"0", "1", "2"} or not r["reason"].strip():
            problems.append(f"grounding {r['strategy']} {r['question_id']}: need label 0/1/2 and reason")
    if problems:
        print(f"{len(problems)} label(s) missing/invalid; nothing summarized:", *problems[:30], sep="\n  ")
        sys.exit(1)

    out: dict = {}
    by = defaultdict(list)
    for r in coherence:
        by[r["strategy"]].append(int(r["label_0_1_2"]))
    by["C"] = list(by["B"])  # identical chunks (C reuses B's index)
    out["coherence"] = {s: {"n": len(v), "mean_of_2": round(sum(v) / len(v), 2), "counts": dict(Counter(v))}
                        for s, v in sorted(by.items())}

    out["metadata"] = {}
    for s in sorted({r["strategy"] for r in metadata}):
        rows = [r for r in metadata if r["strategy"] == s]
        ok = sum(all(r[k].strip().lower() == "y" for k in ("source_ok_y_n", "page_ok_y_n", "article_ok_y_n"))
                 for r in rows)
        per_q = defaultdict(list)
        for r in rows:
            requested = json.loads(r["filter_requested"]) if r["filter_requested"] else None
            if requested:
                per_q[r["question_id"]].append(r["article_id"] == requested["article_id"])
        compliant = sum(all(v) for v in per_q.values())
        out["metadata"][s] = {
            "records_full_and_correct": ok, "records_checked": len(rows),
            "filter_compliant": compliant if per_q else None,
            "filter_questions": len(per_q) if per_q else "N/A",
            "errors": [f"{r['question_id']} #{r['rank']} {r['chunk_id']}: {r['notes']}" for r in rows
                       if not all(r[k].strip().lower() == "y" for k in ("source_ok_y_n", "page_ok_y_n", "article_ok_y_n"))],
        }

    out["grounding"] = {}
    for s in sorted({r["strategy"] for r in grounding}):
        labels = [int(r["label_0_1_2"]) for r in grounding if r["strategy"] == s]
        proxy = sum(r["auto_evidence_hit@3_proxy"] == "yes" for r in grounding if r["strategy"] == s)
        out["grounding"][s] = {"n": len(labels), "count_0": labels.count(0), "count_1": labels.count(1),
                               "count_2": labels.count(2), "mean_of_2": round(sum(labels) / len(labels), 2),
                               "evidence_hit@3_proxy": f"{proxy}/{len(labels)}"}
    out["labeler"] = "Tác giả (tự chấm) - có nguy cơ thiên lệch, xem báo cáo"
    path = corpus.REPO_DIR / "results" / "audit_summary.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
