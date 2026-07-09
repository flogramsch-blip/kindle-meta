"""Tests für Serien-Metadaten (EPUB-Roundtrip) und Calibre-Parsing."""

from dataclasses import replace

from kindle_meta import calibre
from kindle_meta.readers import read_metadata
from kindle_meta.writers import write_metadata


def test_epub_series_roundtrip(sample_epub, tmp_path):
    meta = read_metadata(sample_epub)
    updated = replace(meta, series="Die Chroniken", series_index=3.0)
    out = str(tmp_path / "s.epub")
    write_metadata(updated, out)

    reread = read_metadata(out)
    assert reread.series == "Die Chroniken"
    assert reread.series_index == 3.0


def test_calibre_series_parsing():
    meta = calibre.parse_ebook_meta_output(
        "Title               : X\nSeries              : Meine Reihe [2]\n"
    )
    assert meta.series == "Meine Reihe"
    assert meta.series_index == 2.0


def test_calibre_series_write_args():
    from kindle_meta.models import BookMetadata

    args = calibre.build_write_args(
        BookMetadata(title="T", series="Reihe", series_index=2.0)
    )
    assert "--series" in args and "Reihe" in args
    assert "--index" in args and "2" in args
