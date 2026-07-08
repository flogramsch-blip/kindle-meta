"""Metadaten (inkl. Cover) zurück in E-Book-Dateien schreiben.

Ziel: Ein Kindle Paperwhite zeigt Cover und Metadaten nur zuverlässig an,
wenn sie *in der Datei* eingebettet sind. Deshalb schreiben wir sie direkt in
EPUB (OPF/DC-Metadaten + Cover-Item) bzw. PDF (Info-Dictionary).

Hinweis zu Kindle: Moderne Paperwhites akzeptieren EPUB direkt (Send-to-Kindle).
Für ältere Geräte kann optional mit Calibre nach AZW3/MOBI konvertiert werden
(siehe ``convert_with_calibre``), falls Calibre installiert ist.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from .models import BookMetadata


class WriteError(Exception):
    pass


def write_metadata(
    meta: BookMetadata, out_path: Optional[str] = None, *, optimize_cover: bool = False
) -> str:
    """Schreibt ``meta`` in die Datei ``meta.source_path``.

    Wenn ``out_path`` angegeben ist, wird die Originaldatei zuerst dorthin
    kopiert und die Kopie bearbeitet (Original bleibt unverändert). Gibt den
    Pfad der geschriebenen Datei zurück.

    Mit ``optimize_cover=True`` wird ein vorhandenes Cover vor dem Schreiben
    für die Kindle-Anzeige skaliert/komprimiert (benötigt Pillow).
    """
    if not meta.source_path:
        raise WriteError("meta.source_path ist nicht gesetzt")

    if optimize_cover and meta.cover:
        from . import covers  # lazy, damit Pillow optional bleibt

        from dataclasses import replace as _replace

        opt_bytes, opt_mime = covers.optimize_for_kindle(meta.cover)
        meta = _replace(meta, cover=opt_bytes, cover_mime=opt_mime)

    src = meta.source_path
    target = out_path or src
    if out_path and os.path.abspath(out_path) != os.path.abspath(src):
        shutil.copy2(src, target)

    ext = os.path.splitext(target)[1].lower()
    if ext == ".epub":
        _write_epub(meta, target)
    elif ext == ".pdf":
        _write_pdf(meta, target)
    elif ext in (".mobi", ".azw3", ".azw"):
        from . import calibre  # lazy, damit Calibre optional bleibt

        calibre.write_metadata(meta, target)
    else:
        raise WriteError(f"Kein Writer für '{ext}' (unterstützt: .epub, .pdf, .mobi, .azw3, .azw)")
    return target


# --------------------------------------------------------------------------- #
# EPUB
# --------------------------------------------------------------------------- #
def _write_epub(meta: BookMetadata, path: str) -> None:
    from ebooklib import epub

    book = epub.read_epub(path)

    _reset_dc(book, "title", meta.title)
    _reset_creators(book, meta.authors)
    _reset_dc(book, "publisher", meta.publisher)
    _reset_dc(book, "date", meta.published)
    _reset_dc(book, "language", meta.language)
    _reset_dc(book, "description", meta.description)
    if meta.isbn:
        book.set_identifier(meta.isbn)
        _reset_dc(book, "identifier", meta.isbn, others={"id": "isbn", "scheme": "ISBN"})
    if meta.subjects:
        # Vorhandene Subjects ersetzen.
        book.metadata.setdefault(_NS_DC, {})["subject"] = []
        for subj in meta.subjects:
            book.add_metadata("DC", "subject", subj)

    if meta.cover:
        _remove_existing_cover(book)
        ext = "jpg" if (meta.cover_mime or "").endswith("jpeg") else "png"
        book.set_cover(f"cover.{ext}", meta.cover)

    # epub3_pages=False vermeidet einen ebooklib-Crash, wenn ein (Nav-)Dokument
    # beim erneuten Schreiben einen leeren Body hat.
    epub.write_epub(path, book, {"epub3_pages": False})


_NS_DC = "http://purl.org/dc/elements/1.1/"


def _reset_dc(book, name: str, value: Optional[str], *, others: Optional[dict] = None) -> None:
    """Ersetzt ein DC-Feld vollständig (löscht alte Werte, setzt neuen)."""
    ns_map = book.metadata.setdefault(_NS_DC, {})
    ns_map[name] = []
    if value:
        book.add_metadata("DC", name, value, others=others)


def _remove_existing_cover(book) -> None:
    """Entfernt vorhandene Cover-Items, damit ``set_cover`` keine Dubletten anlegt."""
    from ebooklib import ITEM_COVER

    keep = []
    for item in book.items:
        name = item.get_name().lower()
        is_cover = getattr(item, "get_type", lambda: None)() == ITEM_COVER
        if is_cover or name in ("cover.png", "cover.jpg", "cover.jpeg", "cover.xhtml"):
            continue
        keep.append(item)
    book.items = keep
    # Auch die <meta name="cover">-Referenz im OPF zurücksetzen.
    opf = book.metadata.get("OPF")
    if opf and "cover" in opf:
        opf["cover"] = []


def _reset_creators(book, authors: list[str]) -> None:
    ns_map = book.metadata.setdefault(_NS_DC, {})
    ns_map["creator"] = []
    for author in authors:
        book.add_metadata("DC", "creator", author)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def _write_pdf(meta: BookMetadata, path: str) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(path)
    writer = PdfWriter()
    writer.append(reader)

    info = {}
    if meta.title:
        info["/Title"] = meta.title
    if meta.authors:
        info["/Author"] = ", ".join(meta.authors)
    if meta.publisher:
        info["/Producer"] = meta.publisher
    if meta.subjects:
        info["/Keywords"] = ", ".join(meta.subjects)
    if meta.description:
        info["/Subject"] = meta.description
    writer.add_metadata(info)

    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        writer.write(fh)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Optional: Konvertierung für ältere Kindles via Calibre
# --------------------------------------------------------------------------- #
def calibre_available() -> bool:
    return shutil.which("ebook-convert") is not None


def convert_with_calibre(src: str, out_ext: str = "azw3") -> str:
    """Konvertiert ``src`` mit Calibre nach ``out_ext`` (z. B. azw3/mobi/epub).

    Erfordert ein installiertes Calibre. Metadaten/Cover werden dabei
    übernommen, wenn sie in ``src`` eingebettet sind.
    """
    if not calibre_available():
        raise WriteError("Calibre (ebook-convert) ist nicht installiert")
    out = os.path.splitext(src)[0] + f".{out_ext.lstrip('.')}"
    subprocess.run(["ebook-convert", src, out], check=True, capture_output=True)
    return out
