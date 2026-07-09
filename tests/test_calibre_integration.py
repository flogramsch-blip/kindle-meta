"""Integrationstest gegen echtes Calibre – überspringt sich, wenn nicht installiert.

Prüft den vollen MOBI/AZW3-Pfad (konvertieren, Metadaten schreiben, wieder
lesen), sobald 'ebook-convert' und 'ebook-meta' im PATH verfügbar sind (z. B.
lokal oder in einer CI mit installiertem Calibre).
"""

from dataclasses import replace

import pytest

from kindle_meta import calibre
from kindle_meta.readers import read_metadata
from kindle_meta.writers import write_metadata

pytestmark = pytest.mark.skipif(
    not (calibre.available() and calibre.calibre_available()),
    reason="Calibre (ebook-meta/ebook-convert) nicht installiert",
)


def test_convert_and_roundtrip_azw3(sample_epub, tmp_path):
    # EPUB -> AZW3 konvertieren.
    azw3 = calibre.convert(sample_epub, "azw3")
    assert azw3.endswith(".azw3")

    meta = read_metadata(azw3)
    assert meta.title  # aus dem EPUB übernommen

    # Metadaten schreiben und erneut lesen.
    updated = replace(meta, title="AZW3 Neu", authors=["Test Autor"], series="Reihe",
                      series_index=2.0)
    write_metadata(updated)
    reread = read_metadata(azw3)
    assert reread.title == "AZW3 Neu"
    assert reread.authors == ["Test Autor"]
    assert reread.series == "Reihe"
