"""Tests für die Merge-Logik des Datenmodells."""

from kindle_meta.models import BookMetadata


def test_merge_prefers_other_but_keeps_existing():
    base = BookMetadata(title="Alt", authors=["A"], publisher="Verlag A")
    other = BookMetadata(title="Neu", authors=[], publisher=None, isbn="123")

    merged = base.merged_with(other, prefer_other=True)
    assert merged.title == "Neu"          # other gewinnt bei gesetztem Wert
    assert merged.authors == ["A"]        # leere Liste überschreibt nicht
    assert merged.publisher == "Verlag A" # None überschreibt nicht
    assert merged.isbn == "123"           # neu ergänzt


def test_merge_prefer_self():
    base = BookMetadata(title="Datei")
    other = BookMetadata(title="Online", publisher="V")
    merged = base.merged_with(other, prefer_other=False)
    assert merged.title == "Datei"   # self gewinnt
    assert merged.publisher == "V"   # aber Lücken werden gefüllt


def test_author_str():
    assert BookMetadata(authors=["A", "B"]).author_str == "A, B"
