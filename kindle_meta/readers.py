"""Einlesen vorhandener Metadaten und einer Textprobe aus E-Book-Dateien.

Unterstützt EPUB (über ``ebooklib``) und PDF (über ``pypdf``). Beide
Abhängigkeiten werden lazy importiert, damit das Paket auch ohne sie
importierbar bleibt (z. B. in Tests der reinen Datenlogik).
"""

from __future__ import annotations

import os
from typing import Optional

from .models import BookMetadata

# Wie viel Text aus den ersten Seiten wir als Probe für Suche/KI mitnehmen.
SAMPLE_CHARS = 4000


class UnsupportedFormat(Exception):
    """Wird ausgelöst, wenn kein Reader für die Dateiendung existiert."""


def read_metadata(path: str) -> BookMetadata:
    """Liest Metadaten + Textprobe aus einer Datei anhand ihrer Endung."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        meta = _read_epub(path)
    elif ext == ".pdf":
        meta = _read_pdf(path)
    elif ext in _CALIBRE_EXTENSIONS:
        from . import calibre  # lazy, damit Calibre optional bleibt

        meta = calibre.read_metadata(path)
    else:
        raise UnsupportedFormat(
            f"Kein Reader für '{ext}' (unterstützt: .epub, .pdf, .mobi, .azw3, .azw)"
        )
    meta.source_path = path
    return meta


# Kindle-Eigenformate laufen über Calibre (siehe kindle_meta.calibre).
_CALIBRE_EXTENSIONS = (".mobi", ".azw3", ".azw")


# --------------------------------------------------------------------------- #
# EPUB
# --------------------------------------------------------------------------- #
def _read_epub(path: str) -> BookMetadata:
    from ebooklib import epub  # lazy

    book = epub.read_epub(path)
    meta = BookMetadata()

    def first(namespace: str, name: str) -> Optional[str]:
        items = book.get_metadata(namespace, name)
        if items:
            return items[0][0]
        return None

    meta.title = first("DC", "title")
    meta.authors = [v[0] for v in book.get_metadata("DC", "creator")]
    meta.publisher = first("DC", "publisher")
    meta.published = first("DC", "date")
    meta.language = first("DC", "language")
    meta.description = first("DC", "description")
    meta.subjects = [v[0] for v in book.get_metadata("DC", "subject")]

    ident = book.get_metadata("DC", "identifier")
    for value, attrs in ident:
        scheme = (attrs or {}).get("scheme", "").lower()
        if "isbn" in scheme or _looks_like_isbn(value):
            meta.isbn = _clean_isbn(value)
            break

    # Serien-Angaben (Calibre-Konvention) für Kindle-Sammlungen.
    for value, attrs in book.get_metadata("OPF", "meta"):
        name = (attrs or {}).get("name")
        content = (attrs or {}).get("content")
        if name == "calibre:series":
            meta.series = content
        elif name == "calibre:series_index" and content:
            try:
                meta.series_index = float(content)
            except ValueError:
                pass

    meta.cover, meta.cover_mime = _extract_epub_cover(book)
    meta.sample_text = _extract_epub_text(book)
    return meta


def _extract_epub_cover(book) -> tuple[Optional[bytes], Optional[str]]:
    from ebooklib import ITEM_COVER, ITEM_IMAGE

    # 1) Explizit als Cover markiertes Item.
    for item in book.get_items_of_type(ITEM_COVER):
        return item.get_content(), item.media_type

    # 2) Cover über <meta name="cover"> referenziert.
    cover_meta = book.get_metadata("OPF", "cover")
    if cover_meta:
        cover_id = (cover_meta[0][1] or {}).get("content")
        if cover_id:
            item = book.get_item_with_id(cover_id)
            if item:
                return item.get_content(), item.media_type

    # 3) Fallback: erstes Bild mit "cover" im Namen.
    for item in book.get_items_of_type(ITEM_IMAGE):
        if "cover" in item.get_name().lower():
            return item.get_content(), item.media_type
    return None, None


def _extract_epub_text(book) -> str:
    from ebooklib import ITEM_DOCUMENT

    chunks: list[str] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        text = _strip_html(item.get_content().decode("utf-8", errors="ignore"))
        if text.strip():
            chunks.append(text)
        if sum(len(c) for c in chunks) >= SAMPLE_CHARS:
            break
    return " ".join(chunks)[:SAMPLE_CHARS].strip()


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _read_pdf(path: str) -> BookMetadata:
    from pypdf import PdfReader  # lazy

    reader = PdfReader(path)
    meta = BookMetadata()

    info = reader.metadata or {}
    meta.title = _pdf_str(info.get("/Title"))
    author = _pdf_str(info.get("/Author"))
    if author:
        # Autoren in PDFs sind oft "Nachname, Vorname" oder mit ";"/"&" getrennt.
        meta.authors = _split_authors(author)
    meta.published = _pdf_str(info.get("/CreationDate"))
    meta.page_count = len(reader.pages)

    # Textprobe der ersten Seiten für Suche/KI.
    sample: list[str] = []
    for page in reader.pages[:5]:
        try:
            sample.append(page.extract_text() or "")
        except Exception:  # pragma: no cover - defensiv gegen kaputte PDFs
            continue
        if sum(len(s) for s in sample) >= SAMPLE_CHARS:
            break
    meta.sample_text = " ".join(" ".join(sample).split())[:SAMPLE_CHARS]
    return meta


def _pdf_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def _split_authors(value: str) -> list[str]:
    import re

    parts = re.split(r"\s*[;&]\s*|\s+and\s+|\s+und\s+", value)
    return [p.strip() for p in parts if p.strip()]


def _clean_isbn(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit() or ch in "Xx").upper()


def _looks_like_isbn(value: str) -> bool:
    digits = _clean_isbn(value)
    return len(digits) in (10, 13)
