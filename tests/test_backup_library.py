"""Tests für Backup, Bibliothek und Einstellungen (mit temporärem App-Home)."""

from dataclasses import replace

import pytest

from kindle_meta import backup
from kindle_meta.config import Settings
from kindle_meta.library import STATUS_WRITTEN, Library
from kindle_meta.models import BookMetadata


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    """Leitet das App-Verzeichnis in einen Temp-Ordner um."""
    monkeypatch.setenv("KINDLE_META_HOME", str(tmp_path / "home"))
    yield


def test_backup_and_restore(tmp_path):
    f = tmp_path / "buch.epub"
    f.write_bytes(b"ORIGINAL")
    b1 = backup.create_backup(str(f))
    assert backup.list_backups(str(f)) == [b1]

    f.write_bytes(b"GEAENDERT")
    backup.restore_latest(str(f))
    assert f.read_bytes() == b"ORIGINAL"


def test_restore_without_backup_raises(tmp_path):
    f = tmp_path / "ohne.epub"
    f.write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        backup.restore_latest(str(f))


def test_library_upsert_and_get(tmp_path):
    meta = BookMetadata(
        title="Buch A", authors=["Autor A"], isbn="9783161484100",
        series="Reihe", series_index=2.0, source_path=str(tmp_path / "a.epub"),
    )
    with Library() as lib:
        lib.upsert(meta, status=STATUS_WRITTEN)
        assert lib.count() == 1
        got = lib.get(meta.source_path)
        assert got.title == "Buch A"
        assert got.authors == ["Autor A"]
        assert got.series == "Reihe"
        assert lib.get_status(meta.source_path) == STATUS_WRITTEN

        # Upsert aktualisiert statt zu duplizieren.
        lib.upsert(replace(meta, title="Buch A neu"))
        assert lib.count() == 1
        assert lib.get(meta.source_path).title == "Buch A neu"


def _png(width=400, height=600) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (20, 40, 60)).save(buf, "PNG")
    return buf.getvalue()


def test_library_stores_thumbnail(tmp_path):
    meta = BookMetadata(
        title="Mit Cover", source_path=str(tmp_path / "c.epub"),
        cover=_png(), cover_mime="image/png",
    )
    with Library() as lib:
        lib.upsert(meta)
        thumb = lib.get_thumbnail(meta.source_path)
        assert thumb and thumb[:2] == b"\xff\xd8"  # JPEG-Signatur


def test_library_migration_adds_thumbnail_column(tmp_path):
    """Alte DB ohne thumbnail-Spalte wird beim Öffnen migriert."""
    import sqlite3

    db = str(tmp_path / "old.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE books (path TEXT PRIMARY KEY, title TEXT)")
    con.execute("INSERT INTO books (path, title) VALUES ('p', 't')")
    con.commit()
    con.close()

    with Library(db) as lib:  # sollte migrieren, nicht crashen
        cols = {r[1] for r in lib.conn.execute("PRAGMA table_info(books)")}
        assert "thumbnail" in cols


def test_settings_roundtrip():
    s = Settings()
    s.set("kindle_addr", "dev@kindle.com")
    assert Settings().get("kindle_addr") == "dev@kindle.com"
    # Geheimnis wird gespeichert (Datei-Fallback ohne keyring) und wieder gelesen.
    s.set("smtp_pass", "geheim")
    assert Settings().get("smtp_pass") == "geheim"
