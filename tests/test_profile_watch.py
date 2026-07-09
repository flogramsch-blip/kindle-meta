"""Tests für Anreicherungs-Profile und Ordner-Überwachung."""


from kindle_meta import profile
from kindle_meta.models import BookMetadata
from kindle_meta.watch import FolderWatcher


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #
def test_parse_protected_validates_and_expands_cover():
    fields = profile.parse_protected("cover, title, quatsch")
    assert "title" in fields
    assert "cover" in fields and "cover_mime" in fields  # Cover erweitert
    assert "quatsch" not in fields


def test_parse_protected_empty():
    assert profile.parse_protected("") == set()
    assert profile.parse_protected(None) == set()


def test_merged_with_protect_keeps_own_value():
    original = BookMetadata(title="Datei-Titel", cover=b"orig", cover_mime="image/png")
    suggestion = BookMetadata(title="Online-Titel", cover=b"neu", cover_mime="image/jpeg")

    merged = original.merged_with(suggestion, prefer_other=True, protect={"cover", "cover_mime"})
    assert merged.title == "Online-Titel"   # nicht geschützt -> überschrieben
    assert merged.cover == b"orig"          # geschützt -> Datei-Wert bleibt


def test_merged_with_protect_but_own_empty_takes_other():
    original = BookMetadata(title="T")  # kein Cover
    suggestion = BookMetadata(title="T", cover=b"neu", cover_mime="image/jpeg")
    merged = original.merged_with(suggestion, prefer_other=True, protect={"cover"})
    assert merged.cover == b"neu"  # nichts zu schützen -> Vorschlag greift


def test_save_and_load_protected(tmp_path, monkeypatch):
    monkeypatch.setenv("KINDLE_META_HOME", str(tmp_path / "home"))
    from kindle_meta.config import Settings

    profile.save_protected({"cover", "title"}, Settings())
    loaded = profile.load_protected(Settings())
    assert "cover" in loaded and "title" in loaded


# --------------------------------------------------------------------------- #
# Watch
# --------------------------------------------------------------------------- #
def test_watcher_detects_new_files(tmp_path):
    w = FolderWatcher(str(tmp_path))
    assert w.scan() == []  # leer

    (tmp_path / "a.epub").write_bytes(b"x")
    (tmp_path / "ignore.txt").write_text("no")
    new = w.scan()
    assert len(new) == 1 and new[0].endswith("a.epub")

    # Zweiter Scan ohne Änderung -> nichts Neues.
    assert w.scan() == []

    (tmp_path / "b.pdf").write_bytes(b"x")
    assert len(w.scan()) == 1


def test_watcher_prime_ignores_existing(tmp_path):
    (tmp_path / "old.epub").write_bytes(b"x")
    w = FolderWatcher(str(tmp_path))
    w.prime()
    assert w.scan() == []  # Bestand wird ignoriert
    (tmp_path / "new.epub").write_bytes(b"x")
    assert len(w.scan()) == 1


def test_watcher_run_iterations(tmp_path):
    (tmp_path / "seen.epub").write_bytes(b"x")
    w = FolderWatcher(str(tmp_path))
    collected = []
    (tmp_path / "fresh.epub").write_bytes(b"x")
    # process_existing=False -> "seen.epub" schon geprimt; nur neue zählen.
    w.prime()
    (tmp_path / "later.epub").write_bytes(b"x")
    w.run(collected.append, interval=0, iterations=1, process_existing=True)
    assert any(p.endswith("later.epub") for p in collected)
