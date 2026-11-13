"""Score retrieved evidence and keep full per-query traces.

Definition (GUIDE §4.1): a retrieved chunk is a HIT when it comes from the gold source and a
gold page (primary or any documented alternative) AND contains the WHOLE evidence quote.
Comparison uses the pipeline normalization and ignores line breaks. Hit@1 = top-1 is a hit;
Hit@3 = at least one hit in top-3. Partial evidence is never counted; it is flagged as
``evidence_split`` for error analysis. Human labels (coherence, grounding) are NOT inferred
here from string matching; they are collected separately in results/audit/.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .ingestion import normalize_text

PARTIAL_PROBE = 40  # characters from each end of the quote used to detect a cut


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(text)).strip()


def gold_list(question: dict[str, Any]) -> list[dict[str, Any]]:
    primary = {"gold_page": question["gold_page"], "evidence_quote": question["evidence_quote"]}
    return [primary, *question.get("alternatives", [])]


def _match(question: dict[str, Any], hit: dict[str, Any]) -> tuple[bool, bool]:
    """Return (full evidence present, only part of it present) for one retrieved chunk."""
    text = flat(hit["text"])
    full = partial = False
    for gold in gold_list(question):
        if hit["document_id"] != question["gold_source_id"] or hit["page"] != gold["gold_page"]:
            continue
        quote = flat(gold["evidence_quote"])
        if quote in text:
            full = True
        elif quote[:PARTIAL_PROBE] in text or quote[-PARTIAL_PROBE:] in text:
            partial = True
    return full, partial and not full


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a trace with hit@1/hit@3, per-hit match flags and filter compliance."""
    ranked = []
    for hit in sorted(hits, key=lambda h: h["rank"]):
        full, partial = _match(question, hit)
        ranked.append({
            "rank": hit["rank"], "chunk_id": hit["chunk_id"], "score": round(float(hit["score"]), 6),
            "document_id": hit["document_id"], "source": hit["source"], "page": hit["page"],
            "article_id": hit["article_id"], "text": hit["text"],
            "evidence_full": full, "evidence_partial": partial,
        })
    top3 = ranked[:3]
    expected = (question.get("filter") or {}).get("article_id")
    return {
        "hit@1": bool(top3) and top3[0]["evidence_full"],
        "hit@3": any(h["evidence_full"] for h in top3),
        "evidence_split": not any(h["evidence_full"] for h in top3) and any(h["evidence_partial"] for h in top3),
        "gold_pages_in_top3": any(h["page"] in {g["gold_page"] for g in gold_list(question)} for h in top3),
        "filter_compliant": None if expected is None else all(h["article_id"] == expected for h in top3),
        "hits": ranked,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 (as n/N) by strategy and split."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        groups[(trace["strategy"], trace["split"])].append(trace)
    summary: dict[str, Any] = {}
    for (strategy, split), items in sorted(groups.items()):
        n = len(items)
        filtered = [t for t in items if t["result"]["filter_compliant"] is not None]
        hit1 = sum(t["result"]["hit@1"] for t in items)
        hit3 = sum(t["result"]["hit@3"] for t in items)
        summary.setdefault(strategy, {})[split] = {
            "N": n,
            "hit@1": hit1, "hit@1_rate": round(hit1 / n, 4),
            "hit@3": hit3, "hit@3_rate": round(hit3 / n, 4),
            "evidence_split_cases": sum(t["result"]["evidence_split"] for t in items),
            "filter_questions": len(filtered),
            "filter_compliant": sum(t["result"]["filter_compliant"] for t in filtered) if filtered else None,
            "missed_ids": [t["id"] for t in items if not t["result"]["hit@3"]],
        }
    return summary
