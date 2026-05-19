from __future__ import annotations

from dataclasses import dataclass

import fitz


@dataclass
class PageText:
    page_number: int
    text: str
    char_start: int
    char_end: int


@dataclass
class ExtractedDocument:
    pages: list[PageText]
    full_text: str

    @property
    def page_count(self) -> int:
        return len(self.pages)


def extract_text_from_pdf_bytes(data: bytes) -> ExtractedDocument:
    doc = fitz.open(stream=data, filetype="pdf")
    pages: list[PageText] = []
    parts: list[str] = []
    offset = 0

    for index in range(doc.page_count):
        page = doc.load_page(index)
        text = (page.get_text("text") or "").strip()
        page_number = index + 1
        if text:
            if parts:
                parts.append("\n\n")
                offset += 2
            char_start = offset
            parts.append(text)
            offset += len(text)
            pages.append(
                PageText(
                    page_number=page_number,
                    text=text,
                    char_start=char_start,
                    char_end=offset,
                )
            )
        else:
            pages.append(
                PageText(
                    page_number=page_number,
                    text="",
                    char_start=offset,
                    char_end=offset,
                )
            )

    doc.close()
    full_text = "".join(parts)
    return ExtractedDocument(pages=pages, full_text=full_text)
