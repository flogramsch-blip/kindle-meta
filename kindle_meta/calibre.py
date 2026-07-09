"""Anbindung an Calibre für Kindle-Eigenformate (MOBI/AZW3/AZW).

EPUB und PDF bearbeiten wir nativ (ebooklib/pypdf). MOBI/AZW3 sind binäre
Kindle-Formate – hier ist Calibre das robusteste Werkzeug. Wir rufen die
Kommandozeilen-Tools ``ebook-meta`` (Metadaten lesen/schreiben) und
``ebook-convert`` (Formatkonvertierung) auf.

Ist Calibre nicht installiert, lösen die Funktionen ``CalibreNotFound`` aus –
die App bleibt für EPUB/PDF weiterhin voll funktionsfähig.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional

from .models import BookMetadata

CALIBRE_EXTENSIONS = (".mobi", ".azw3", ".azw")


class CalibreNotFound(Exception):
    """Calibre-Tools (ebook-meta/ebook-convert) sind nicht im PATH."""


def available() -> bool:
    return shutil.which("ebook-meta") is not None


def _require() -> None:
    if not available():
        raise CalibreNotFound(
            "Calibre (ebook-meta) nicht gefunden. Installiere Calibre von "
            "https://calibre-ebook.com/ und stelle sicher, dass 'ebook-meta' im PATH ist."
        )


# --------------------------------------------------------------------------- #
# Lesen
# --------------------------------------------------------------------------- #
def read_metadata(path: str) -> BookMetadata:
    """Liest Metadaten + Cover aus einer MOBI/AZW3-Datei via ``ebook-meta``."""
    _require()
    with tempfile.TemporaryDirectory() as tmp:
        cover_path = os.path.join(tmp, "cover.jpg")
        proc = subprocess.run(
            ["ebook-meta", path, "--get-cover", cover_path],
            check=True,
            capture_output=True,
            text=True,
        )
        meta = parse_ebook_meta_output(proc.stdout)
        if os.path.exists(cover_path) and os.path.getsize(cover_path) > 0:
            with open(cover_path, "rb") as fh:
                meta.cover = fh.read()
            meta.cover_mime = "image/jpeg"
    meta.source_path = path
    return meta


def parse_ebook_meta_output(text: str) -> BookMetadata:
    """Parst die ``key : value``-Ausgabe von ``ebook-meta``.

    Ausgelagert und rein textbasiert, damit es ohne installiertes Calibre
    getestet werden kann.
    """
    fields: dict[str, str] = {}
    key = None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z()#/ .]+?)\s*:\s(.*)$", line)
        if m and not line.startswith(" "):
            key = m.group(1).strip().lower()
            fields[key] = m.group(2).strip()
        elif key and line.startswith(" ") and line.strip():
            # Fortsetzungszeile (z. B. mehrzeilige Comments).
            fields[key] += " " + line.strip()

    meta = BookMetadata()
    meta.title = fields.get("title") or None
    meta.authors = _parse_authors(fields.get("author(s)") or fields.get("authors") or "")
    meta.publisher = fields.get("publisher") or None
    meta.language = _first_lang(fields.get("languages"))
    meta.description = fields.get("comments") or None
    published = fields.get("published")
    if published:
        # Calibre gibt oft ISO-Timestamps aus – nur das Datum behalten.
        meta.published = published.split("T")[0]
    if fields.get("tags"):
        meta.subjects = [t.strip() for t in fields["tags"].split(",") if t.strip()]
    ident = fields.get("identifiers", "")
    m = re.search(r"isbn:([0-9Xx-]+)", ident)
    if m:
        meta.isbn = m.group(1).replace("-", "")
    # Serie: "Meine Reihe [2]" oder "Meine Reihe #2".
    series = fields.get("series")
    if series:
        sm = re.match(r"^(.*?)\s*[\[#]\s*([\d.]+)\]?\s*$", series)
        if sm:
            meta.series = sm.group(1).strip()
            try:
                meta.series_index = float(sm.group(2))
            except ValueError:
                pass
        else:
            meta.series = series
    return meta


def _parse_authors(value: str) -> list[str]:
    if not value:
        return []
    # "Vorname Nachname [Sortname]" -> Sortname-Klammern entfernen.
    value = re.sub(r"\[[^\]]*\]", "", value)
    parts = re.split(r"\s*&\s*|\s*;\s*", value)
    return [p.strip() for p in parts if p.strip()]


def _first_lang(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.split(",")[0].strip() or None


# --------------------------------------------------------------------------- #
# Schreiben
# --------------------------------------------------------------------------- #
def write_metadata(meta: BookMetadata, path: str) -> None:
    """Schreibt Metadaten + Cover via ``ebook-meta`` in eine MOBI/AZW3-Datei."""
    _require()
    args = ["ebook-meta", path]
    args += build_write_args(meta)

    cover_tmp = None
    if meta.cover:
        suffix = ".png" if (meta.cover_mime or "").endswith("png") else ".jpg"
        fd, cover_tmp = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as fh:
            fh.write(meta.cover)
        args += ["--cover", cover_tmp]

    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    finally:
        if cover_tmp and os.path.exists(cover_tmp):
            os.remove(cover_tmp)


def build_write_args(meta: BookMetadata) -> list[str]:
    """Baut die ``ebook-meta``-Argumente (ohne Cover) – rein & testbar."""
    args: list[str] = []
    if meta.title:
        args += ["--title", meta.title]
    if meta.authors:
        args += ["--authors", " & ".join(meta.authors)]
    if meta.publisher:
        args += ["--publisher", meta.publisher]
    if meta.published:
        args += ["--date", meta.published]
    if meta.language:
        args += ["--language", meta.language]
    if meta.description:
        args += ["--comments", meta.description]
    if meta.subjects:
        args += ["--tags", ", ".join(meta.subjects)]
    if meta.isbn:
        args += ["--identifier", f"isbn:{meta.isbn}"]
    if meta.series:
        args += ["--series", meta.series]
        if meta.series_index is not None:
            idx = meta.series_index
            args += ["--index", str(int(idx)) if float(idx).is_integer() else str(idx)]
    return args


# --------------------------------------------------------------------------- #
# Konvertierung
# --------------------------------------------------------------------------- #
def convert(src: str, out_ext: str = "azw3") -> str:
    """Konvertiert ``src`` nach ``out_ext`` (azw3/mobi/epub …) via ``ebook-convert``."""
    if shutil.which("ebook-convert") is None:
        raise CalibreNotFound("ebook-convert nicht gefunden (Calibre installieren).")
    out = os.path.splitext(src)[0] + f".{out_ext.lstrip('.')}"
    subprocess.run(["ebook-convert", src, out], check=True, capture_output=True, text=True)
    return out
