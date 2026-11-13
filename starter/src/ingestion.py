"""Read and normalize source PDFs page by page, keeping a link back to the source page.

Extractor: PyMuPDF. pypdf was tested first on this corpus and split about 0.8% of
Vietnamese tokens into fragments (e.g. "nghiệ p"); PyMuPDF produced none
(see report). Only the text layer is read; this module does no OCR. Pages without
extractable text are kept, flagged with ``empty=True`` and a warning, so that the
caller can log them instead of silently dropping them.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pymupdf

from .models import DocumentPage

# Space-like characters that PDF text layers commonly emit instead of U+0020.
_SPACE_CHARS = dict.fromkeys(map(ord, "        "
                                      "      　\t"), " ")
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)
_MULTI_SPACE = re.compile(r" {2,}")
_MULTI_BLANK = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT = re.compile(r" +([,.;:!?)\]”’])")


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while keeping structure.

    - Unicode NFC, so precomposed Vietnamese letters compare equal everywhere.
    - Exotic spaces/tabs become a normal space; zero-width characters are removed.
    - Runs of spaces collapse to one; spaces before closing punctuation are removed.
    - Each line is stripped. Single newlines (line breaks inside a paragraph) and
      blank lines (paragraph breaks) are kept; 3+ newlines collapse to one blank line.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_SPACE_CHARS).translate(_ZERO_WIDTH)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = _MULTI_SPACE.sub(" ", line).strip()
        line = _SPACE_BEFORE_PUNCT.sub(r"\1", line)
        lines.append(line)
    text = "\n".join(lines)
    return _MULTI_BLANK.sub("\n\n", text).strip()


def _page_blocks(page: "pymupdf.Page", page_number: int) -> tuple[list[str], list[str]]:
    """Return text blocks in stream order, dropping blank and page-number-only blocks."""
    blocks, removed = [], []
    for block in page.get_text("blocks"):
        if block[6] != 0:  # 1 = image block; images carry no text layer
            continue
        text = block[4].strip()
        if not text:
            continue
        if text == str(page_number):
            removed.append(text)
            continue
        blocks.append(text)
    return blocks, removed


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract every physical page with its 1-based page number and source.

    Paragraph-like blocks are separated by a blank line; line breaks inside a block
    are kept. ``metadata`` records diagnostics used by the manifest and error log:
    ``image_count``, ``page_number_removed``, ``empty`` and ``warnings``.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Source PDF not found: {path}")
    pages: list[DocumentPage] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            page_number = index + 1
            blocks, removed = _page_blocks(page, page_number)
            text = normalize_text("\n\n".join(blocks))
            image_count = len(page.get_images())
            warnings = []
            if not text:
                warnings.append("no extractable text (scan/image-only page; OCR not applied)")
            if image_count:
                warnings.append(f"{image_count} embedded image(s); any text inside them is not extracted")
            pages.append(DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                text=text,
                metadata={
                    "image_count": image_count,
                    "page_number_removed": bool(removed),
                    "empty": not text,
                    "warnings": warnings,
                },
            ))
    return pages
