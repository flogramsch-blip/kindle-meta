"""Online-Anreicherung der Metadaten über Google Books, Open Library und DNB.

Alle Provider liefern ``BookMetadata``-Kandidaten zu einer Such-Query oder
ISBN. Netzwerkzugriffe sind über ``requests`` gekapselt und geben bei Fehlern
leere Ergebnisse zurück, statt die App abstürzen zu lassen.
"""

from __future__ import annotations

import re
from typing import Optional

from . import isbn as isbn_mod
from .models import BookMetadata


def _is_isbn(value: str) -> bool:
    return isbn_mod.is_valid(value)

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPENLIBRARY_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
DNB_SRU_URL = "https://services.dnb.de/sru/dnb"

_TIMEOUT = 15


def search(query: str, *, max_results: int = 5, fetch_covers: bool = True) -> list[BookMetadata]:
    """Sucht bei allen Providern und liefert eine kombinierte Kandidatenliste.

    Google-Books-Treffer stehen vorn (meist die reichhaltigsten Metadaten),
    danach Open Library als Ergänzung.
    """
    results: list[BookMetadata] = []
    results.extend(search_google_books(query, max_results=max_results, fetch_covers=fetch_covers))
    results.extend(search_openlibrary(query, max_results=max_results, fetch_covers=fetch_covers))
    results.extend(search_dnb(query, max_results=max_results))
    return results


def search_by_isbn(isbn: str, *, fetch_covers: bool = True) -> Optional[BookMetadata]:
    """Präzise Suche über ISBN – liefert den besten Einzeltreffer oder ``None``."""
    hits = search_google_books(f"isbn:{isbn}", max_results=1, fetch_covers=fetch_covers)
    if hits:
        return hits[0]
    hits = search_openlibrary(f"isbn:{isbn}", max_results=1, fetch_covers=fetch_covers)
    return hits[0] if hits else None


# --------------------------------------------------------------------------- #
# Google Books
# --------------------------------------------------------------------------- #
def search_google_books(
    query: str, *, max_results: int = 5, fetch_covers: bool = True
) -> list[BookMetadata]:
    import requests

    try:
        resp = requests.get(
            GOOGLE_BOOKS_URL,
            params={"q": query, "maxResults": max_results},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    out: list[BookMetadata] = []
    for item in data.get("items", []):
        info = item.get("volumeInfo", {})
        meta = BookMetadata(
            title=info.get("title"),
            authors=list(info.get("authors", [])),
            publisher=info.get("publisher"),
            published=info.get("publishedDate"),
            language=info.get("language"),
            description=info.get("description"),
            page_count=info.get("pageCount"),
            subjects=list(info.get("categories", [])),
        )
        for ident in info.get("industryIdentifiers", []):
            if ident.get("type") in ("ISBN_13", "ISBN_10"):
                meta.isbn = ident.get("identifier")
                if ident.get("type") == "ISBN_13":
                    break
        if fetch_covers:
            link = (info.get("imageLinks") or {}).get("thumbnail")
            if link:
                meta.cover, meta.cover_mime = _download(link.replace("http://", "https://"))
        out.append(meta)
    return out


# --------------------------------------------------------------------------- #
# Open Library
# --------------------------------------------------------------------------- #
def search_openlibrary(
    query: str, *, max_results: int = 5, fetch_covers: bool = True
) -> list[BookMetadata]:
    import requests

    try:
        resp = requests.get(
            OPENLIBRARY_SEARCH_URL,
            params={"q": query, "limit": max_results},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    out: list[BookMetadata] = []
    for doc in data.get("docs", [])[:max_results]:
        meta = BookMetadata(
            title=doc.get("title"),
            authors=list(doc.get("author_name", [])),
            publisher=(doc.get("publisher") or [None])[0],
            published=str(doc["first_publish_year"]) if doc.get("first_publish_year") else None,
            language=(doc.get("language") or [None])[0],
            page_count=doc.get("number_of_pages_median"),
            isbn=(doc.get("isbn") or [None])[0],
            subjects=list(doc.get("subject", [])[:10]),
        )
        if fetch_covers and doc.get("cover_i"):
            meta.cover, meta.cover_mime = _download(
                OPENLIBRARY_COVER_URL.format(cover_id=doc["cover_i"])
            )
        out.append(meta)
    return out


# --------------------------------------------------------------------------- #
# Deutsche Nationalbibliothek (DNB) – SRU-Schnittstelle
# --------------------------------------------------------------------------- #
def search_dnb(query: str, *, max_results: int = 5) -> list[BookMetadata]:
    """Sucht in der DNB via SRU (Dublin-Core-Schema). Ohne Cover.

    Besonders stark bei deutschsprachigen Titeln. Fehler (Netzwerk, ungültige
    Antwort) führen zu einer leeren Liste, nicht zum Absturz.
    """
    import requests

    # CQL: WOE = Wörter aus Titel und Beteiligten (allgemeine Stichwortsuche).
    cql = f'WOE="{query}"'
    try:
        resp = requests.get(
            DNB_SRU_URL,
            params={
                "version": "1.1",
                "operation": "searchRetrieve",
                "query": cql,
                "recordSchema": "oai_dc",
                "maximumRecords": max_results,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return parse_dnb_oai_dc(resp.content, max_results=max_results)
    except Exception:
        return []


def parse_dnb_oai_dc(xml: bytes, *, max_results: int = 5) -> list[BookMetadata]:
    """Parst eine SRU-Antwort im oai_dc-Schema – separat testbar."""
    import xml.etree.ElementTree as ET

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    out: list[BookMetadata] = []
    # Jeder <dc>-Container entspricht einem Datensatz.
    for dc in root.iter():
        if local(dc.tag) != "dc":
            continue
        meta = BookMetadata()
        for child in dc:
            name = local(child.tag)
            value = (child.text or "").strip()
            if not value:
                continue
            if name == "title" and not meta.title:
                meta.title = value
            elif name == "creator":
                # Rollen-Zusätze wie "[Verfasser]" / "[Übersetzer]" entfernen.
                author = re.sub(r"\s*\[[^\]]*\]", "", value).strip()
                if author:
                    meta.authors.append(author)
            elif name == "publisher" and not meta.publisher:
                meta.publisher = value
            elif name == "date" and not meta.published:
                meta.published = value
            elif name == "language" and not meta.language:
                meta.language = value
            elif name == "identifier" and not meta.isbn:
                digits = "".join(c for c in value if c.isdigit() or c in "Xx").upper()
                # Nur echte ISBN übernehmen (DNB mischt interne IDN-Nummern ein).
                if _is_isbn(digits):
                    meta.isbn = digits
            elif name == "subject":
                meta.subjects.append(value)
        if meta.title:
            out.append(meta)
        if len(out) >= max_results:
            break
    return out


# --------------------------------------------------------------------------- #
# Hilfsfunktion
# --------------------------------------------------------------------------- #
def _download(url: str) -> tuple[Optional[bytes], Optional[str]]:
    import requests

    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        content = resp.content
        if not content:
            return None, None
        mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        return content, mime
    except Exception:
        return None, None
