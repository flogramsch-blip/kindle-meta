"""Leichte, abhängigkeitsfreie Spracherkennung über Stoppwörter.

Reicht, um die Sprache eines Buches grob zu bestimmen (de/en/fr/es/it/nl/pt),
damit ``language`` gesetzt und die Online-Suche gezielter werden kann. Bewusst
ohne externe Bibliothek – deterministisch und gut testbar.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

# Häufige Funktionswörter je Sprache (kleine, disjunkte Auswahl).
_STOPWORDS: dict[str, set[str]] = {
    "de": {"der", "die", "und", "das", "ist", "nicht", "ein", "eine", "mit",
           "auch", "sich", "auf", "für", "von", "dass", "war", "wird", "aber"},
    "en": {"the", "and", "of", "to", "in", "is", "that", "it", "was", "for",
           "with", "as", "his", "he", "on", "are", "this", "which"},
    "fr": {"le", "la", "les", "des", "une", "et", "est", "que", "qui", "dans",
           "pour", "pas", "sur", "avec", "plus", "son", "ses", "mais"},
    "es": {"el", "la", "los", "las", "una", "que", "de", "en", "por", "con",
           "para", "como", "más", "pero", "sus", "este", "esta", "muy"},
    "it": {"il", "la", "che", "di", "una", "per", "con", "non", "del", "sono",
           "come", "più", "sua", "suo", "questo", "questa", "ma", "anche"},
    "nl": {"de", "het", "een", "en", "van", "dat", "die", "niet", "met", "is",
           "op", "voor", "aan", "zijn", "maar", "ook", "als", "door"},
    "pt": {"de", "que", "uma", "para", "com", "não", "por", "mais", "como",
           "mas", "seu", "sua", "este", "esta", "muito", "quando", "onde"},
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-ZäöüÄÖÜßàâçéèêëîïôûùüÿñáíóú']+", text.lower())


def detect(text: Optional[str], *, min_tokens: int = 20) -> Optional[str]:
    """Erkennt die Sprache als ISO-639-1-Code (z. B. ``de``) oder ``None``.

    Zählt Stoppwort-Treffer pro Sprache; die Sprache mit den meisten Treffern
    gewinnt. Bei zu wenig Text oder Gleichstand/ohne Treffer → ``None``.
    """
    if not text:
        return None
    tokens = _tokens(text)
    if len(tokens) < min_tokens:
        return None
    token_set = Counter(tokens)

    scores: dict[str, int] = {}
    for lang, words in _STOPWORDS.items():
        scores[lang] = sum(token_set[w] for w in words)

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return None
    # Klarer Vorsprung nötig (sonst uneindeutig).
    ordered = sorted(scores.values(), reverse=True)
    if len(ordered) > 1 and ordered[0] == ordered[1]:
        return None
    return best
