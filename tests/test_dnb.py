"""Tests für den DNB-oai_dc-Parser (ohne Netzwerk)."""

from kindle_meta import providers

SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
  <numberOfRecords>1</numberOfRecords>
  <records>
    <record>
      <recordData>
        <dc xmlns="http://www.openarchives.org/OAI/2.0/oai_dc/"
            xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Der Steppenwolf</dc:title>
          <dc:creator>Hesse, Hermann</dc:creator>
          <dc:publisher>Suhrkamp</dc:publisher>
          <dc:date>1974</dc:date>
          <dc:language>ger</dc:language>
          <dc:identifier>ISBN 978-3-518-03171-1</dc:identifier>
          <dc:subject>Roman</dc:subject>
        </dc>
      </recordData>
    </record>
  </records>
</searchRetrieveResponse>
"""


def test_parse_dnb_oai_dc():
    results = providers.parse_dnb_oai_dc(SAMPLE)
    assert len(results) == 1
    m = results[0]
    assert m.title == "Der Steppenwolf"
    assert m.authors == ["Hesse, Hermann"]
    assert m.publisher == "Suhrkamp"
    assert m.published == "1974"
    assert m.language == "ger"
    assert m.isbn == "9783518031711"
    assert m.subjects == ["Roman"]


def test_parse_dnb_empty():
    assert providers.parse_dnb_oai_dc(b"<garbage") == []
    assert providers.parse_dnb_oai_dc(b"<x/>") == []


def test_parse_dnb_rejects_non_isbn_identifier_and_strips_roles():
    xml = b"""<?xml version="1.0"?>
    <searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
      <records><record><recordData>
        <dc xmlns="http://www.openarchives.org/OAI/2.0/oai_dc/"
            xmlns:dc="http://purl.org/dc/elements/1.1/">
          <dc:title>Ein Buch</dc:title>
          <dc:creator>Muster, Erika [Verfasser]</dc:creator>
          <dc:identifier>1160959677</dc:identifier>
        </dc>
      </recordData></record></records>
    </searchRetrieveResponse>"""
    m = providers.parse_dnb_oai_dc(xml)[0]
    assert m.authors == ["Muster, Erika"]   # Rollen-Zusatz entfernt
    assert m.isbn is None                    # interne Nummer, keine gültige ISBN
