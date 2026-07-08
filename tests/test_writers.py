"""Tests für das Zurückschreiben von Metadaten (Roundtrip)."""

from dataclasses import replace

from kindle_meta.readers import read_metadata
from kindle_meta.writers import write_metadata


def test_epub_roundtrip(sample_epub, tmp_path):
    meta = read_metadata(sample_epub)
    updated = replace(
        meta,
        title="Neuer Titel",
        authors=["Anna Autorin", "Ben Beispiel"],
        publisher="Neuverlag",
        published="2024-05-01",
        isbn="9781234567897",
    )
    out = str(tmp_path / "out.epub")
    write_metadata(updated, out)

    reread = read_metadata(out)
    assert reread.title == "Neuer Titel"
    assert reread.authors == ["Anna Autorin", "Ben Beispiel"]
    assert reread.publisher == "Neuverlag"
    assert reread.published == "2024-05-01"
    assert reread.has_cover()  # Cover bleibt erhalten


def test_pdf_roundtrip(sample_pdf, tmp_path):
    meta = read_metadata(sample_pdf)
    updated = replace(meta, title="Geändert", authors=["Neue Autorin"])
    out = str(tmp_path / "out.pdf")
    write_metadata(updated, out)

    reread = read_metadata(out)
    assert reread.title == "Geändert"
    assert reread.authors == ["Neue Autorin"]


def test_write_to_copy_keeps_original(sample_epub, tmp_path):
    meta = read_metadata(sample_epub)
    out = str(tmp_path / "copy.epub")
    write_metadata(replace(meta, title="Kopie-Titel"), out)

    assert read_metadata(sample_epub).title == "Der Testtitel"  # Original unverändert
    assert read_metadata(out).title == "Kopie-Titel"
