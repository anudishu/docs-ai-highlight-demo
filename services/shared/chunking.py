from __future__ import annotations

from dataclasses import dataclass

from shared.pdf_extract import ExtractedDocument, PageText


@dataclass
class TextChunk:
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int


def _page_for_offset(pages: list[PageText], offset: int) -> int:
    for page in pages:
        if page.char_start <= offset < page.char_end:
            return page.page_number
        if offset == page.char_end and page.text:
            return page.page_number
    if pages:
        return pages[-1].page_number
    return 1


def _break_window(text: str, start: int, end: int) -> int:
    window = text[start:end]
    for sep in ("\n\n", "\n", ". ", " "):
        pos = window.rfind(sep)
        if pos > len(window) * 0.4:
            return start + pos + len(sep)
    return end


def chunk_document(
    extracted: ExtractedDocument,
    chunk_size: int,
    chunk_overlap: int,
) -> list[TextChunk]:
    text = extracted.full_text
    pages = extracted.pages
    if not text.strip():
        return []

    chunks: list[TextChunk] = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            end = _break_window(text, start, end)

        piece = text[start:end].strip()
        if piece:
            chunks.append(
                TextChunk(
                    chunk_index=index,
                    text=piece,
                    page_start=_page_for_offset(pages, start),
                    page_end=_page_for_offset(pages, max(start, end - 1)),
                    char_start=start,
                    char_end=end,
                )
            )
            index += 1

        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)

    return chunks
