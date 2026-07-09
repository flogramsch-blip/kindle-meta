"""Persistente Bibliothek über SQLite.

Merkt sich importierte Bücher samt Metadaten und Status, damit die App über
Sitzungen hinweg weiß, was schon bearbeitet/geschrieben/gesendet wurde. Cover
werden nicht gespeichert (nur ein Flag), um die DB klein zu halten – das Cover
liegt ohnehin in der Datei.

Die Datenbank liegt standardmäßig unter ``<app_home>/library.db``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from .config import library_path
from .models import BookMetadata

# Bearbeitungsstatus eines Buches.
STATUS_IMPORTED = "imported"
STATUS_ENRICHED = "enriched"
STATUS_WRITTEN = "written"
STATUS_SENT = "sent"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    path         TEXT PRIMARY KEY,
    title        TEXT,
    authors      TEXT,   -- JSON-Liste
    publisher    TEXT,
    published    TEXT,
    isbn         TEXT,
    language     TEXT,
    series       TEXT,
    series_index REAL,
    page_count   INTEGER,
    has_cover    INTEGER DEFAULT 0,
    thumbnail    BLOB,
    status       TEXT,
    updated_at   TEXT
);
"""


class Library:
    """Kleine SQLite-Bibliothek. Als Kontextmanager nutzbar."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(library_path())
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Fügt fehlende Spalten in bestehenden Datenbanken nachträglich hinzu."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(books)")}
        if "thumbnail" not in cols:
            self.conn.execute("ALTER TABLE books ADD COLUMN thumbnail BLOB")

    def __enter__(self) -> "Library":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    # -- Schreiben ---------------------------------------------------------- #
    def upsert(self, meta: BookMetadata, status: Optional[str] = None) -> None:
        """Fügt ein Buch ein oder aktualisiert es (Schlüssel: source_path).

        Ist ein Cover vorhanden, wird daraus ein kleines Vorschaubild für die
        Bibliotheks-Ansicht abgeleitet (falls Pillow verfügbar ist).
        """
        if not meta.source_path:
            raise ValueError("meta.source_path muss gesetzt sein")
        thumb = _make_thumbnail(meta.cover)
        row = {
            "path": meta.source_path,
            "title": meta.title,
            "authors": json.dumps(meta.authors, ensure_ascii=False),
            "publisher": meta.publisher,
            "published": meta.published,
            "isbn": meta.isbn,
            "language": meta.language,
            "series": meta.series,
            "series_index": meta.series_index,
            "page_count": meta.page_count,
            "has_cover": 1 if meta.has_cover() else 0,
            "thumbnail": thumb,
            "status": status or STATUS_IMPORTED,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.conn.execute(
            """
            INSERT INTO books (path, title, authors, publisher, published, isbn,
                               language, series, series_index, page_count,
                               has_cover, thumbnail, status, updated_at)
            VALUES (:path, :title, :authors, :publisher, :published, :isbn,
                    :language, :series, :series_index, :page_count,
                    :has_cover, :thumbnail, :status, :updated_at)
            ON CONFLICT(path) DO UPDATE SET
                title=excluded.title, authors=excluded.authors,
                publisher=excluded.publisher, published=excluded.published,
                isbn=excluded.isbn, language=excluded.language,
                series=excluded.series, series_index=excluded.series_index,
                page_count=excluded.page_count, has_cover=excluded.has_cover,
                thumbnail=COALESCE(excluded.thumbnail, books.thumbnail),
                status=excluded.status, updated_at=excluded.updated_at
            """,
            row,
        )
        self.conn.commit()

    def set_status(self, path: str, status: str) -> None:
        self.conn.execute(
            "UPDATE books SET status=?, updated_at=? WHERE path=?",
            (status, datetime.now().isoformat(timespec="seconds"), path),
        )
        self.conn.commit()

    def remove(self, path: str) -> None:
        self.conn.execute("DELETE FROM books WHERE path=?", (path,))
        self.conn.commit()

    # -- Lesen -------------------------------------------------------------- #
    def get(self, path: str) -> Optional[BookMetadata]:
        cur = self.conn.execute("SELECT * FROM books WHERE path=?", (path,))
        row = cur.fetchone()
        return _row_to_meta(row) if row else None

    def get_status(self, path: str) -> Optional[str]:
        cur = self.conn.execute("SELECT status FROM books WHERE path=?", (path,))
        row = cur.fetchone()
        return row["status"] if row else None

    def all(self) -> list[BookMetadata]:
        cur = self.conn.execute("SELECT * FROM books ORDER BY updated_at DESC")
        return [_row_to_meta(r) for r in cur.fetchall()]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]

    def get_thumbnail(self, path: str) -> Optional[bytes]:
        cur = self.conn.execute("SELECT thumbnail FROM books WHERE path=?", (path,))
        row = cur.fetchone()
        return row["thumbnail"] if row and row["thumbnail"] else None


def _make_thumbnail(cover: Optional[bytes]) -> Optional[bytes]:
    """Kleines JPEG-Vorschaubild aus Cover-Daten – ohne Pillow einfach ``None``."""
    if not cover:
        return None
    try:
        from . import covers

        thumb, _ = covers.thumbnail(cover)
        return thumb
    except Exception:
        return None


def _row_to_meta(row: sqlite3.Row) -> BookMetadata:
    return BookMetadata(
        title=row["title"],
        authors=json.loads(row["authors"]) if row["authors"] else [],
        publisher=row["publisher"],
        published=row["published"],
        isbn=row["isbn"],
        language=row["language"],
        series=row["series"],
        series_index=row["series_index"],
        page_count=row["page_count"],
        source_path=row["path"],
    )
