"""Online-Anreicherung der Metadaten über Google Books und Open Library.

Beide Provider liefern ``BookMetadata``-Kandidaten zu einer Such-Query oder
ISBN. Netzwerkzugriffe sind über ``requests`` gekapselt und geben bei Fehlern
leere Ergebnisse zurück, statt die App abstürzen zu lassen.
"""

from __future__ import annotations

from typing import Optional

from .models import BookMetadata

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPENLIBRARY_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

_TIMEOUT = 15


def search(query: str, *, max_results: int = 5, fetch_covers: bool = True) -> list[BookMetadata]:
    """Sucht bei allen Providern und liefert eine kombinierte Kandidatenliste.

    Google-Books-Treffer stehen vorn (meist die reichhaltigsten Metadaten),
    danach Open Library als Ergänzung.
    """
    results: list[BookMetadata] = []
    results.extend(search_google_books(query, max_results=max_results, fetch_covers=fetch_covers))
    results.extend(search_openlibrary(query, max_results=max_results, fetch_covers=fetch_covers))
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
def search_google_books(query: str, *, max_results: int = 5, fetch_covers: bool = True) -> list[BookMetadata]:
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
def search_openlibrary(query: str, *, max_results: int = 5, fetch_covers: bool = True) -> list[BookMetadata]:
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
