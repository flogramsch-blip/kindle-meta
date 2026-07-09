"""Tests für ISBN-Erkennung und -Validierung."""

from kindle_meta import isbn


def test_valid_isbn13():
    assert isbn.is_valid("978-3-16-148410-0")
    assert isbn.is_valid("9783161484100")


def test_valid_isbn10_with_x():
    assert isbn.is_valid("0-8044-2957-X")


def test_invalid_checksum():
    assert not isbn.is_valid("9783161484101")  # falsche Prüfziffer
    assert not isbn.is_valid("1234567890")     # ISBN-10 mit falscher Prüfziffer


def test_find_isbn_in_text_prefers_isbn13():
    text = "Impressum. ISBN-10: 3161484100 und ISBN-13: 978-3-16-148410-0. Verlag."
    assert isbn.find_isbn(text) == "9783161484100"


def test_find_isbn_none():
    assert isbn.find_isbn("kein code hier 12345") is None
    assert isbn.find_isbn(None) is None


def test_find_isbn_standalone():
    assert isbn.find_isbn("Buch, ISBN 3-16-148410-X, Seite 1") == "316148410X"
