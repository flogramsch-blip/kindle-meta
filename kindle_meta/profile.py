"""Anreicherungs-Profile: welche Felder beim Anreichern geschützt sind.

Ein geschütztes Feld behält beim Übernehmen eines Online-Vorschlags seinen
vorhandenen Wert aus der Datei (z. B. „Cover nie überschreiben"). Die Auswahl
wird als kommagetrennte Liste in den Einstellungen gespeichert.
"""

from __future__ import annotations

from typing import Optional

# Felder, die sinnvoll geschützt werden können.
PROTECTABLE_FIELDS = {
    "title", "authors", "publisher", "published", "language",
    "isbn", "description", "series", "series_index", "subjects", "cover",
}

_SETTINGS_KEY = "protected_fields"


def parse_protected(text: Optional[str]) -> set[str]:
    """Wandelt ``"cover, title"`` in ein validiertes Feld-Set um.

    Unbekannte Feldnamen werden ignoriert; ``cover`` schützt auch ``cover_mime``.
    """
    if not text:
        return set()
    fields = {p.strip().lower() for p in text.split(",") if p.strip()}
    valid = fields & PROTECTABLE_FIELDS
    if "cover" in valid:
        valid = valid | {"cover_mime"}
    return valid


def load_protected(settings=None) -> set[str]:
    """Lädt die geschützten Felder aus den Einstellungen."""
    if settings is None:
        from .config import Settings

        settings = Settings()
    return parse_protected(settings.get(_SETTINGS_KEY))


def save_protected(fields: set[str], settings=None) -> None:
    if settings is None:
        from .config import Settings

        settings = Settings()
    cleaned = sorted(f for f in fields if f in PROTECTABLE_FIELDS)
    settings.set(_SETTINGS_KEY, ", ".join(cleaned) or None)
