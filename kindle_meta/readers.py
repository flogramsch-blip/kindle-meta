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
    elif ext == ".fb2":
        meta = _read_fb2(path)
    elif ext in (".cbz", ".cbr"):
        meta = _read_comic(path, ext)
    elif ext in _CALIBRE_EXTENSIONS:
        from . import calibre  # lazy, damit Calibre optional bleibt

        meta = calibre.read_metadata(path)
    else:
        raise UnsupportedFormat(
            f"Kein Reader für '{ext}' (unterstützt: .epub, .pdf, .fb2, .cbz, .cbr, "
            ".mobi, .azw3, .azw)"
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
    for _value, attrs in book.get_metadata("OPF", "meta"):
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
# FB2 (FictionBook) – XML-Format
# --------------------------------------------------------------------------- #
def _read_fb2(path: str) -> BookMetadata:
    import base64
    import xml.etree.ElementTree as ET

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    root = ET.parse(path).getroot()

    def find_first(parent, name):
        for el in parent.iter():
            if local(el.tag) == name:
                return el
        return None

    meta = BookMetadata()
    title_info = find_first(root, "title-info")
    if title_info is not None:
        for el in title_info:
            name = local(el.tag)
            if name == "book-title" and el.text:
                meta.title = el.text.strip()
            elif name == "author":
                parts = [
                    (c.text or "").strip()
                    for c in el
                    if local(c.tag) in ("first-name", "middle-name", "last-name")
                ]
                full = " ".join(p for p in parts if p)
                if full:
                    meta.authors.append(full)
            elif name == "lang" and el.text:
                meta.language = el.text.strip()
            elif name == "genre" and el.text:
                meta.subjects.append(el.text.strip())
            elif name == "annotation":
                text = " ".join(t.strip() for t in el.itertext() if t.strip())
                if text:
                    meta.description = text

    publish_info = find_first(root, "publish-info")
    if publish_info is not None:
        for el in publish_info:
            name = local(el.tag)
            if name == "publisher" and el.text:
                meta.publisher = el.text.strip()
            elif name == "year" and el.text:
                meta.published = el.text.strip()
            elif name == "isbn" and el.text:
                meta.isbn = _clean_isbn(el.text)

    # Cover: <coverpage><image href="#id"/></coverpage> -> <binary id="id">.
    cover_id = _fb2_cover_id(root, local)
    if cover_id:
        for el in root.iter():
            if local(el.tag) == "binary" and el.get("id") == cover_id:
                try:
                    meta.cover = base64.b64decode((el.text or "").strip())
                    meta.cover_mime = el.get("content-type", "image/jpeg")
                except Exception:
                    pass
                break

    # Textprobe aus dem <body>.
    body = find_first(root, "body")
    if body is not None:
        text = " ".join(t.strip() for t in body.itertext() if t.strip())
        meta.sample_text = text[:SAMPLE_CHARS]
    return meta


# --------------------------------------------------------------------------- #
# Comics: CBZ (ZIP) und CBR (RAR)
# --------------------------------------------------------------------------- #
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _read_comic(path: str, ext: str) -> BookMetadata:
    """Liest CBZ/CBR: ComicInfo.xml (falls vorhanden) + erstes Bild als Cover."""
    if ext == ".cbz":
        names, opener = _cbz_entries(path)
    else:
        names, opener = _cbr_entries(path)

    meta = BookMetadata()
    # ComicInfo.xml -> Metadaten.
    for name in names:
        if name.lower().endswith("comicinfo.xml"):
            _parse_comicinfo(opener(name), meta)
            break

    # Erstes Bild (alphabetisch) als Cover.
    images = sorted(n for n in names if n.lower().endswith(_IMAGE_EXTS))
    if images:
        data = opener(images[0])
        if data:
            meta.cover = data
            meta.cover_mime = _image_mime(images[0])
    return meta


def _cbz_entries(path: str):
    import zipfile

    zf = zipfile.ZipFile(path)
    names = zf.namelist()

    def opener(name: str) -> bytes:
        with zf.open(name) as fh:
            return fh.read()

    return names, opener


def _cbr_entries(path: str):
    try:
        import rarfile
    except ImportError as exc:
        raise UnsupportedFormat(
            "CBR (RAR) benötigt das Paket 'rarfile' und ein entpacktes 'unrar'/'unar' "
            "im PATH. Alternativ das Comic als CBZ speichern."
        ) from exc

    rf = rarfile.RarFile(path)
    names = rf.namelist()

    def opener(name: str) -> bytes:
        with rf.open(name) as fh:
            return fh.read()

    return names, opener


def _parse_comicinfo(xml: bytes, meta: BookMetadata) -> None:
    import xml.etree.ElementTree as ET

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return
    fields = {local(el.tag): (el.text or "").strip() for el in root if el.text}

    meta.title = fields.get("Title") or meta.title
    meta.series = fields.get("Series") or meta.series
    if fields.get("Number"):
        try:
            meta.series_index = float(fields["Number"])
        except ValueError:
            pass
    writer = fields.get("Writer") or fields.get("Penciller")
    if writer:
        meta.authors = [a.strip() for a in writer.split(",") if a.strip()]
    meta.publisher = fields.get("Publisher") or meta.publisher
    meta.published = fields.get("Year") or meta.published
    meta.description = fields.get("Summary") or meta.description
    meta.language = fields.get("LanguageISO") or meta.language
    if fields.get("Genre"):
        meta.subjects = [g.strip() for g in fields["Genre"].split(",") if g.strip()]


def _image_mime(name: str) -> str:
    n = name.lower()
    if n.endswith(".png"):
        return "image/png"
    if n.endswith(".webp"):
        return "image/webp"
    if n.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _fb2_cover_id(root, local) -> Optional[str]:
    for el in root.iter():
        if local(el.tag) == "coverpage":
            for img in el.iter():
                if local(img.tag) == "image":
                    for key, val in img.attrib.items():
                        if local(key) == "href" and val:
                            return val.lstrip("#")
    return None


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
