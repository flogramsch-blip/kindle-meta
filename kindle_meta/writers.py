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
    meta: BookMetadata,
    out_path: Optional[str] = None,
    *,
    optimize_cover: bool = False,
    backup: bool = False,
) -> str:
    """Schreibt ``meta`` in die Datei ``meta.source_path``.

    Wenn ``out_path`` angegeben ist, wird die Originaldatei zuerst dorthin
    kopiert und die Kopie bearbeitet (Original bleibt unverändert). Gibt den
    Pfad der geschriebenen Datei zurück.

    Mit ``optimize_cover=True`` wird ein vorhandenes Cover vor dem Schreiben
    für die Kindle-Anzeige skaliert/komprimiert (benötigt Pillow).

    Mit ``backup=True`` wird vor einem In-Place-Überschreiben eine
    Sicherungskopie angelegt (siehe ``kindle_meta.backup``).
    """
    if not meta.source_path:
        raise WriteError("meta.source_path ist nicht gesetzt")

    src = meta.source_path
    writes_in_place = not out_path or os.path.abspath(out_path) == os.path.abspath(src)
    if backup and writes_in_place and os.path.exists(src):
        from . import backup as _backup  # lazy

        _backup.create_backup(src)

    if optimize_cover and meta.cover:
        from dataclasses import replace as _replace

        from . import covers  # lazy, damit Pillow optional bleibt

        opt_bytes, opt_mime = covers.optimize_for_kindle(meta.cover)
        meta = _replace(meta, cover=opt_bytes, cover_mime=opt_mime)

    target = out_path or src
    if not writes_in_place:
        shutil.copy2(src, target)

    ext = os.path.splitext(target)[1].lower()
    if ext == ".epub":
        _write_epub(meta, target)
    elif ext == ".pdf":
        _write_pdf(meta, target)
    elif ext in (".mobi", ".azw3", ".azw"):
        from . import calibre  # lazy, damit Calibre optional bleibt

        calibre.write_metadata(meta, target)
    elif ext == ".fb2":
        raise WriteError(
            "FB2 kann gelesen, aber nicht direkt geschrieben werden. Konvertiere "
            "es für den Kindle zuerst nach EPUB/AZW3 (z. B. 'kindle-meta convert')."
        )
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

    # Serien-Angaben (Calibre-Konvention) – für Kindle-Sammlungen.
    _set_calibre_meta(book, "calibre:series", meta.series)
    if meta.series_index is not None:
        # Ganzzahlen ohne Nachkommastelle darstellen (1 statt 1.0).
        idx = meta.series_index
        idx_str = str(int(idx)) if float(idx).is_integer() else str(idx)
        _set_calibre_meta(book, "calibre:series_index", idx_str)
    else:
        _set_calibre_meta(book, "calibre:series_index", None)

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


_NS_OPF = "http://www.idpf.org/2007/opf"


def _set_calibre_meta(book, name: str, value: Optional[str]) -> None:
    """Setzt/entfernt ein ``<meta name=… content=…>`` im OPF (Calibre-Stil)."""
    opf = book.metadata.setdefault(_NS_OPF, {})
    entries = opf.get("meta", [])
    # Vorhandene Einträge mit diesem Namen entfernen.
    entries = [
        (val, attrs) for val, attrs in entries if (attrs or {}).get("name") != name
    ]
    if value:
        entries.append((None, {"name": name, "content": value}))
    opf["meta"] = entries


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
