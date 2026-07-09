"""Gemeinsame Test-Fixtures: erzeugt echte EPUB- und PDF-Dateien on the fly."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_epub(tmp_path):
    """Ein minimales, valides EPUB mit gesetzten Metadaten und Cover."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id-123")
    book.set_title("Der Testtitel")
    book.set_language("de")
    book.add_author("Erika Muster")
    book.add_metadata("DC", "publisher", "Testverlag")
    book.add_metadata("DC", "date", "2021")

    # Gültiges Cover-PNG via Pillow (kein manuell gehextes, evtl. defektes Bild).
    import io

    from PIL import Image

    _buf = io.BytesIO()
    Image.new("RGB", (60, 90), (120, 60, 30)).save(_buf, "PNG")
    book.set_cover("cover.png", _buf.getvalue())

    chapter = epub.EpubHtml(title="Kap 1", file_name="c1.xhtml", lang="de")
    chapter.content = "<html><body><h1>Kapitel</h1><p>Ein Satz Text.</p></body></html>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = tmp_path / "test.epub"
    epub.write_epub(str(path), book)
    return str(path)


@pytest.fixture
def sample_pdf(tmp_path):
    """Ein minimales PDF mit Titel/Autor im Info-Dictionary."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.add_metadata({"/Title": "PDF Titel", "/Author": "Max Mustermann"})
    path = tmp_path / "test.pdf"
    with open(path, "wb") as fh:
        writer.write(fh)
    return str(path)
