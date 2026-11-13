"""Build data/manifest.json: source, permission, hash, per-page stats and the page-counting rule.

Run from starter/:  python -m scripts.build_manifest
The PDF itself is not committed (see LICENSE_OR_PERMISSION in src/corpus.py); this
manifest lets a grader download the same file, verify its SHA-256 and re-derive counts.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from importlib.metadata import version

from src import corpus
from src.ingestion import load_pdf

MIN_CONTENT_CHARS = 1500  # non-whitespace characters after normalization
REFERENCE_HEADING = re.compile(r"(TÀI LIỆU THAM KHẢO|Tài liệu và thông tin tham khảo)\s*\n", re.IGNORECASE)
REFERENCE_SHARE = 0.5
COUNTING_RULE = (
    f"Một trang vật lý được tính là trang nội dung khi: (1) không phải trang bìa; "
    f"(2) phần sau tiêu đề tài liệu tham khảo chiếm < {REFERENCE_SHARE:.0%} số ký tự của trang; "
    f"(3) có >= {MIN_CONTENT_CHARS} ký tự không phải khoảng trắng sau chuẩn hóa (NFC, gộp khoảng trắng, "
    "bỏ số trang). Trang không đạt vẫn được ingest nhưng không tính vào ngưỡng 30 trang. "
    "Nội dung nằm trong ảnh (bảng/hình) không trích xuất được và không được tính."
)


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def nonspace(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def main() -> None:
    pages = load_pdf(corpus.LOCAL_PDF, corpus.DOCUMENT_ID, corpus.SOURCE_URL)
    errors: list[str] = []

    # Article boundaries must be supported by the text itself.
    by_number = {p.page: p for p in pages}
    for article in corpus.ARTICLES:
        start = by_number.get(article["start_page"])
        if start is None or article["marker"].lower() not in start.text.lower():
            errors.append(f"marker '{article['marker']}' not found on page {article['start_page']} "
                          f"({article['article_id']})")
    covered = {n for a in corpus.ARTICLES for n in range(a["start_page"], a["end_page"] + 1)}
    if covered != set(by_number):
        errors.append(f"article page ranges do not cover all pages exactly: {sorted(set(by_number) ^ covered)}")

    rows = []
    for page in pages:
        article = corpus.article_for_page(page.page)
        chars = nonspace(page.text)
        reason = None
        if article["article_id"] == "cover":
            reason = "trang bìa"
        else:
            match = REFERENCE_HEADING.search(page.text)
            if match and nonspace(page.text[match.start():]) >= REFERENCE_SHARE * chars:
                reason = "chủ yếu là tài liệu tham khảo"
            elif chars < MIN_CONTENT_CHARS:
                reason = f"dưới {MIN_CONTENT_CHARS} ký tự nội dung"
        rows.append({
            "page_id": f"{corpus.DOCUMENT_ID}:p{page.page:02d}",
            "page": page.page,
            "article_id": article["article_id"],
            "chars_total": len(page.text),
            "chars_nonspace": chars,
            "counted": reason is None,
            "exclusion_reason": reason,
            "image_count": page.metadata["image_count"],
            "empty": page.metadata["empty"],
            "warnings": page.metadata["warnings"],
        })

    counted = [r["page"] for r in rows if r["counted"]]
    manifest = {
        "source_id": corpus.DOCUMENT_ID,
        "title": corpus.TITLE,
        "publisher": corpus.PUBLISHER,
        "published_date": corpus.PUBLISHED_DATE,
        "source_path_or_url": corpus.SOURCE_URL,
        "local_path": corpus.LOCAL_PDF.relative_to(corpus.REPO_DIR).as_posix(),
        "sha256": sha256(corpus.LOCAL_PDF),
        "license_or_permission": corpus.LICENSE_OR_PERMISSION,
        "accessed_at": corpus.ACCESSED_AT,
        "snapshot_or_version": "Bản PDF tải từ URL trên; xác minh bằng sha256",
        "language": "vi",
        "extractor": f"PyMuPDF {version('pymupdf')} (text layer, không OCR)",
        "physical_pages": len(pages),
        "counting_rule": COUNTING_RULE,
        "counted_page_count": len(counted),
        "counted_pages": counted,
        "chars_nonspace_counted_pages": sum(r["chars_nonspace"] for r in rows if r["counted"]),
        "chars_nonspace_all_pages": sum(r["chars_nonspace"] for r in rows),
        "filter_field": {
            "name": "article_id",
            "type": "string (categorical)",
            "value_source": "tiêu đề + dòng nguồn/tác giả in ở trang đầu mỗi bài; marker được kiểm tra tự động",
            "values": corpus.ARTICLES,
        },
        "pages": rows,
        "validation_errors": errors,
    }

    out = corpus.REPO_DIR / "data" / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out.relative_to(corpus.REPO_DIR)}")
    print(f"Physical pages: {len(pages)} | counted content pages: {len(counted)}")
    for r in rows:
        if not r["counted"]:
            print(f"  excluded p{r['page']:02d} ({r['chars_nonspace']} chars): {r['exclusion_reason']}")
    for r in rows:
        for w in r["warnings"]:
            print(f"  warning p{r['page']:02d}: {w}")
    if errors:
        print("VALIDATION ERRORS:", *errors, sep="\n  ")
        sys.exit(1)
    if len(counted) < 30:
        sys.exit(f"Only {len(counted)} counted pages; at least 30 are required.")


if __name__ == "__main__":
    main()
