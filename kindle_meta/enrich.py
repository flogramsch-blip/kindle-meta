"""Orchestrierung: Datei lesen → Query bilden → online/KI anreichern.

Der typische Ablauf:

1. ``read_metadata`` holt vorhandene Metadaten + Textprobe aus der Datei.
2. Fehlen Titel/Autor, versucht der KI-Fallback sie aus der Textprobe zu raten.
3. Mit ISBN oder Titel/Autor werden Online-Provider abgefragt.
4. Es entsteht eine Liste von Vorschlägen, die die GUI zur Bestätigung anzeigt.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import llm, providers
from .models import BookMetadata
from .readers import read_metadata


@dataclass
class EnrichmentResult:
    """Ergebnis der Anreicherung, das die GUI dem Nutzer präsentiert."""

    original: BookMetadata          # aus der Datei gelesen
    suggestions: list[BookMetadata] # Online-/KI-Kandidaten, bester zuerst
    used_llm: bool = False          # wurde die KI zum Raten genutzt?

    @property
    def best(self) -> BookMetadata:
        """Bester Vorschlag mit Datei-Werten als Fallback."""
        if self.suggestions:
            return self.original.merged_with(self.suggestions[0], prefer_other=True)
        return self.original


def build_query(meta: BookMetadata) -> str:
    """Baut eine Suchanfrage aus Titel + Autor (Fallback: Textprobe)."""
    parts = []
    if meta.title:
        parts.append(meta.title)
    if meta.authors:
        parts.append(meta.authors[0])
    if parts:
        return " ".join(parts)
    if meta.sample_text:
        return " ".join(meta.sample_text.split()[:12])
    return ""


def enrich_file(path: str, *, use_llm: bool = True, max_results: int = 5) -> EnrichmentResult:
    """Kompletter Anreicherungslauf für eine Datei."""
    original = read_metadata(path)
    return enrich_metadata(original, use_llm=use_llm, max_results=max_results)


def enrich_metadata(
    original: BookMetadata, *, use_llm: bool = True, max_results: int = 5
) -> EnrichmentResult:
    """Reichert bereits gelesene Metadaten an (ohne erneut die Datei zu lesen)."""
    working = original
    used_llm = False

    # KI-Fallback nur wenn Titel oder Autor fehlt.
    if use_llm and (not working.title or not working.authors):
        guess = llm.guess_metadata(working.sample_text or "")
        if guess:
            working = working.merged_with(guess, prefer_other=False)
            used_llm = True

    suggestions: list[BookMetadata] = []
    if working.isbn:
        hit = providers.search_by_isbn(working.isbn)
        if hit:
            suggestions.append(hit)

    query = build_query(working)
    if query:
        suggestions.extend(providers.search(query, max_results=max_results))

    return EnrichmentResult(original=original, suggestions=suggestions, used_llm=used_llm)
