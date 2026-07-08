"""Tests für die Calibre-Anbindung – nur die reine Text-/Argument-Logik,
ohne installiertes Calibre."""

from kindle_meta import calibre
from kindle_meta.models import BookMetadata

SAMPLE_OUTPUT = """\
Title               : Der Steppenwolf
Author(s)           : Hermann Hesse [Hesse, Hermann]
Publisher           : Suhrkamp
Tags                : Fiction, Klassiker
Languages           : deu
Published           : 1927-01-01T00:00:00+00:00
Identifiers         : isbn:9783518031711
Comments            : Ein Roman über
                      den Steppenwolf.
"""


def test_parse_ebook_meta_output():
    meta = calibre.parse_ebook_meta_output(SAMPLE_OUTPUT)
    assert meta.title == "Der Steppenwolf"
    assert meta.authors == ["Hermann Hesse"]
    assert meta.publisher == "Suhrkamp"
    assert meta.language == "deu"
    assert meta.published == "1927-01-01"
    assert meta.isbn == "9783518031711"
    assert meta.subjects == ["Fiction", "Klassiker"]
    assert "Steppenwolf" in meta.description


def test_parse_multiple_authors():
    meta = calibre.parse_ebook_meta_output(
        "Author(s)           : Jane Doe [Doe, Jane] & John Roe [Roe, John]\n"
    )
    assert meta.authors == ["Jane Doe", "John Roe"]


def test_build_write_args():
    meta = BookMetadata(
        title="T", authors=["A", "B"], publisher="P",
        published="2021", isbn="123", subjects=["x", "y"],
    )
    args = calibre.build_write_args(meta)
    assert "--title" in args and "T" in args
    assert "A & B" in args
    assert "--identifier" in args and "isbn:123" in args
    assert "--tags" in args


def test_available_is_bool():
    assert isinstance(calibre.available(), bool)
