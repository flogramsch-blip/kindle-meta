"""Tests für den Comic-Reader (CBZ) und den Sprachfilter der Suche."""

import io
import zipfile

from kindle_meta import providers
from kindle_meta.readers import read_metadata

COMICINFO = """<?xml version="1.0"?>
<ComicInfo>
  <Title>Heft 1</Title>
  <Series>Meine Comics</Series>
  <Number>1</Number>
  <Writer>Jane Zeichner</Writer>
  <Publisher>Comicverlag</Publisher>
  <Year>2018</Year>
  <Summary>Ein spannendes Heft.</Summary>
  <LanguageISO>de</LanguageISO>
  <Genre>Abenteuer</Genre>
</ComicInfo>
"""


def _jpeg(width=50, height=70) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 100, 50)).save(buf, "JPEG")
    return buf.getvalue()


def test_read_cbz(tmp_path):
    path = tmp_path / "comic.cbz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ComicInfo.xml", COMICINFO)
        zf.writestr("002.jpg", _jpeg())
        zf.writestr("001.jpg", _jpeg())  # kommt alphabetisch zuerst -> Cover

    meta = read_metadata(str(path))
    assert meta.title == "Heft 1"
    assert meta.series == "Meine Comics"
    assert meta.series_index == 1.0
    assert meta.authors == ["Jane Zeichner"]
    assert meta.publisher == "Comicverlag"
    assert meta.published == "2018"
    assert meta.language == "de"
    assert meta.subjects == ["Abenteuer"]
    assert meta.has_cover()


def test_read_cbz_without_comicinfo(tmp_path):
    path = tmp_path / "plain.cbz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("page1.png", _jpeg())
    meta = read_metadata(str(path))
    assert meta.has_cover()          # Cover aus erstem Bild
    assert meta.title is None        # keine Metadaten vorhanden


def test_lang2_mapping():
    assert providers._lang2("de") == "de"
    assert providers._lang2("ger") == "de"
    assert providers._lang2("eng") == "en"
    assert providers._lang2(None) is None
    assert providers._lang2("xyz") is None


def test_search_google_books_passes_langrestrict(monkeypatch):
    """Die Funktion importiert 'requests' lazy -> Modul in sys.modules ersetzen."""
    import sys

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": []}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return FakeResp()

    fake_requests = type("M", (), {"get": staticmethod(fake_get)})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    providers.search_google_books("Titel", language="ger")
    assert captured["params"].get("langRestrict") == "de"
