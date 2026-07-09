"""Ähnlichkeitsbewertung von Anreicherungs-Vorschlägen.

Sortiert Online-Treffer danach, wie gut sie zu den bekannten Datei-Metadaten
passen (Titel + Autor), damit der beste Vorschlag oben steht – statt sich nur
auf die Reihenfolge der Provider zu verlassen. Nutzt ``difflib`` (Standardlib).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import BookMetadata


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    """Ähnlichkeit zweier Strings in [0, 1] (0 = leer/unbekannt)."""
    a, b = _normalize(a or ""), _normalize(b or "")
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def score(reference: BookMetadata, candidate: BookMetadata) -> float:
    """Bewertet ``candidate`` gegen die bekannten Werte in ``reference``.

    Gewichtung: Titel 0,6, Autor 0,3, plus kleiner Bonus, wenn zusätzliche
    Felder (Verlag/Datum/ISBN) überhaupt vorhanden sind (reichhaltigerer Treffer).
    Fehlen Referenz-Titel und -Autor, zählt nur die Vollständigkeit.
    """
    title_sim = similarity(reference.title or "", candidate.title or "")
    author_sim = similarity(reference.author_str, candidate.author_str)

    have_ref = bool(reference.title) or bool(reference.authors)
    base = 0.6 * title_sim + 0.3 * author_sim if have_ref else 0.0

    completeness = sum(
        0.03 for v in (candidate.publisher, candidate.published, candidate.isbn,
                       candidate.cover, candidate.page_count) if v
    )
    # ISBN-Gleichheit ist ein starkes Signal.
    if reference.isbn and candidate.isbn and _digits(reference.isbn) == _digits(candidate.isbn):
        base += 0.5
    return round(base + completeness, 4)


def rank(reference: BookMetadata, candidates: list[BookMetadata]) -> list[BookMetadata]:
    """Sortiert Kandidaten absteigend nach Score (stabil bei Gleichstand)."""
    return sorted(candidates, key=lambda c: score(reference, c), reverse=True)


def _digits(isbn: str) -> str:
    return "".join(ch for ch in isbn if ch.isdigit())
