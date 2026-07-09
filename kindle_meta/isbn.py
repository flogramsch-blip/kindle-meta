"""ISBN-Erkennung und -Validierung aus Freitext (z. B. Impressum).

Findet ISBN-10 und ISBN-13 in einem Text, prüft die Prüfziffer und gibt die
erste gültige zurück. Wird beim Anreichern genutzt, wenn die Datei selbst keine
ISBN in den Metadaten trägt.
"""

from __future__ import annotations

import re
from typing import Optional

# Kandidaten: "ISBN" optional, dann 10–13 Ziffern mit Bindestrichen/Leerzeichen.
_CANDIDATE = re.compile(
    r"(?:ISBN(?:-1[03])?:?\s*)?((?:97[89][-\s]?)?(?:\d[-\s]?){9}[\dXx])",
    re.IGNORECASE,
)


def normalize(raw: str) -> str:
    """Entfernt Bindestriche/Leerzeichen, macht X groß."""
    return re.sub(r"[-\s]", "", raw).upper()


def is_valid_isbn10(isbn: str) -> bool:
    isbn = normalize(isbn)
    if len(isbn) != 10 or not re.fullmatch(r"\d{9}[\dX]", isbn):
        return False
    total = 0
    for i, ch in enumerate(isbn):
        val = 10 if ch == "X" else int(ch)
        total += val * (10 - i)
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    isbn = normalize(isbn)
    if len(isbn) != 13 or not isbn.isdigit():
        return False
    total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(isbn))
    return total % 10 == 0


def is_valid(isbn: str) -> bool:
    isbn = normalize(isbn)
    return is_valid_isbn13(isbn) if len(isbn) == 13 else is_valid_isbn10(isbn)


def find_isbn(text: Optional[str]) -> Optional[str]:
    """Erste gültige ISBN im Text (normalisiert) oder ``None``.

    ISBN-13 werden bevorzugt (moderner, eindeutiger).
    """
    if not text:
        return None
    found: list[str] = []
    for match in _CANDIDATE.finditer(text):
        candidate = normalize(match.group(1))
        if is_valid(candidate):
            found.append(candidate)
    if not found:
        return None
    # ISBN-13 bevorzugen.
    for f in found:
        if len(f) == 13:
            return f
    return found[0]
