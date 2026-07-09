"""Test für den FB2-Reader."""

import base64
import io

from kindle_meta.readers import read_metadata


def _make_fb2(tmp_path):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (10, 120, 30)).save(buf, "JPEG")
    cover_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
             xmlns:l="http://www.w3.org/1999/xlink">
  <description>
    <title-info>
      <genre>sf</genre>
      <author><first-name>Iwan</first-name><last-name>Autor</last-name></author>
      <book-title>Das FB2-Buch</book-title>
      <annotation><p>Eine kurze Beschreibung.</p></annotation>
      <lang>de</lang>
      <coverpage><image l:href="#cover.jpg"/></coverpage>
    </title-info>
    <publish-info>
      <publisher>FB2-Verlag</publisher>
      <year>2019</year>
      <isbn>978-3-16-148410-0</isbn>
    </publish-info>
  </description>
  <body><section><p>Erster Absatz des Buches.</p></section></body>
  <binary id="cover.jpg" content-type="image/jpeg">{cover_b64}</binary>
</FictionBook>
"""
    path = tmp_path / "buch.fb2"
    path.write_text(xml, encoding="utf-8")
    return str(path)


def test_read_fb2(tmp_path):
    meta = read_metadata(_make_fb2(tmp_path))
    assert meta.title == "Das FB2-Buch"
    assert meta.authors == ["Iwan Autor"]
    assert meta.publisher == "FB2-Verlag"
    assert meta.published == "2019"
    assert meta.language == "de"
    assert meta.isbn == "9783161484100"
    assert meta.has_cover()
    assert "Absatz" in (meta.sample_text or "")
    assert "Beschreibung" in (meta.description or "")
