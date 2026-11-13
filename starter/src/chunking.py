"""Fixed-size (strategy A) and structure-aware (strategy B) chunking, one page at a time.

Both strategies chunk the same representation: the page's normalized lines joined by
single spaces ("flat" text). ``char_start``/``char_end`` in chunk metadata are offsets in
that flat text, so chunks of different strategies can be compared on the same source
position (used by the coherence audit). Chunks never cross a page boundary, which keeps
``page`` exact for tracing; the cost is that a sentence continuing onto the next page is
cut (true for both strategies, reported as a limitation).
"""
from __future__ import annotations

import re

from .models import Chunk, DocumentPage

# Page diagnostics stay in the manifest/logs, not on every chunk.
_PAGE_ONLY_KEYS = {"warnings", "image_count", "empty", "page_number_removed"}
# A numbered heading or list item at the start of a line: "2.Công nghệ số là gì?", "II.Chuyển đổi số",
# "B3. Khung năng lực", "1. Tập trung". (?!\d) rejects numbers such as "11.000" or "4.0".
HEADING = re.compile(r"^(?:\d{1,2}\.(?!\d)|[IVX]{1,4}\.|[A-E]\d?\.(?!\d))\s*\S")
SENTENCE_END = re.compile(r"(?<=[.!?…;])\s+")


def _lines(page: DocumentPage) -> list[tuple[str, bool]]:
    """Return (line, starts_paragraph) for every non-empty line of the page."""
    out, new_paragraph = [], True
    for raw in page.text.split("\n"):
        if not raw:
            new_paragraph = True
            continue
        out.append((raw, new_paragraph))
        new_paragraph = False
    return out


def flat_text(page: DocumentPage) -> str:
    return " ".join(line for line, _ in _lines(page))


def _chunk(page: DocumentPage, tag: str, index: int, text: str, start: int, params: dict) -> Chunk:
    metadata = {k: v for k, v in page.metadata.items() if k not in _PAGE_ONLY_KEYS}
    metadata.update(params, char_start=start, char_end=start + len(text))
    return Chunk(
        chunk_id=f"{page.document_id}:p{page.page:02d}:{tag}:{index:03d}",
        document_id=page.document_id, source=page.source, page=page.page,
        text=text, metadata=metadata,
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Strategy A: windows of ``size`` characters, consecutive windows share ``overlap`` characters."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("require size > 0 and 0 <= overlap < size")
    text = flat_text(page)
    tag, params = f"fixed{size}o{overlap}", {"chunking": "fixed_size", "chunk_size": size, "overlap": overlap}
    chunks, start, step = [], 0, size - overlap
    while start < len(text):
        piece = text[start:start + size]
        chunks.append(_chunk(page, tag, len(chunks), piece, start, params))
        if start + size >= len(text):
            break
        start += step
    return chunks


def _split_long(text: str, start: int, max_size: int) -> list[tuple[str, int]]:
    """Split an oversized unit at sentence ends; hard-split a single over-long sentence."""
    pieces, buf, buf_start, cursor = [], "", start, start
    for sentence in SENTENCE_END.split(text):
        s_start = text.index(sentence, cursor - start) + start
        cursor = s_start + len(sentence)
        while len(sentence) > max_size:  # no sentence boundary available: cut by characters
            if buf:
                pieces.append((buf, buf_start)); buf = ""
            pieces.append((sentence[:max_size], s_start))
            sentence, s_start = sentence[max_size:].lstrip(), s_start + max_size
        if buf and len(buf) + 1 + len(sentence) > max_size:
            pieces.append((buf, buf_start)); buf = ""
        if not buf:
            buf, buf_start = sentence, s_start
        else:
            buf = f"{buf} {sentence}"
    if buf:
        pieces.append((buf, buf_start))
    return pieces


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Strategy B: group whole paragraphs up to ``max_size`` characters.

    A unit is a paragraph (blank-line separated block) or a numbered heading/list item,
    which always starts a new chunk so that a heading stays with the text it introduces.
    Paragraphs longer than ``max_size`` are split at sentence ends.
    """
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    units: list[tuple[str, int, bool]] = []  # (text, flat offset, is_heading)
    offset = 0
    for line, starts_paragraph in _lines(page):
        is_heading = bool(HEADING.match(line))
        if starts_paragraph or is_heading or not units:
            units.append((line, offset, is_heading))
        else:
            text, start, heading = units[-1]
            units[-1] = (f"{text} {line}", start, heading)
        offset += len(line) + 1

    tag, params = f"para{max_size}", {"chunking": "by_paragraph", "chunk_size": max_size, "overlap": 0}
    chunks: list[Chunk] = []
    buf, buf_start = "", 0
    for text, start, is_heading in units:
        if len(text) > max_size:
            if buf:
                chunks.append(_chunk(page, tag, len(chunks), buf, buf_start, params)); buf = ""
            for piece, piece_start in _split_long(text, start, max_size):
                chunks.append(_chunk(page, tag, len(chunks), piece, piece_start, params))
            continue
        if buf and (is_heading or len(buf) + 1 + len(text) > max_size):
            chunks.append(_chunk(page, tag, len(chunks), buf, buf_start, params)); buf = ""
        if not buf:
            buf, buf_start = text, start
        else:
            buf = f"{buf} {text}"
    if buf:
        chunks.append(_chunk(page, tag, len(chunks), buf, buf_start, params))
    return chunks
