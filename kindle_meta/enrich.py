"""Orchestrierung: Datei lesen → Query bilden → online/KI anreichern.

Der typische Ablauf:

1. ``read_metadata`` holt vorhandene Metadaten + Textprobe aus der Datei.
2. Fehlen Titel/Autor, versucht der KI-Fallback sie aus der Textprobe zu raten.
3. Mit ISBN oder Titel/Autor werden Online-Provider abgefragt.
4. Es entsteht eine Liste von Vorschlägen, die die GUI zur Bestätigung anzeigt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from . import isbn as isbn_mod
from . import lang, llm, matching, providers
from .models import BookMetadata
from .readers import read_metadata
from .writers import write_metadata


@dataclass
class EnrichmentResult:
    """Ergebnis der Anreicherung, das die GUI dem Nutzer präsentiert."""

    original: BookMetadata          # aus der Datei gelesen
    suggestions: list[BookMetadata] # Online-/KI-Kandidaten, bester zuerst
    used_llm: bool = False          # wurde die KI zum Raten genutzt?

    @property
    def best(self) -> BookMetadata:
        """Bester Vorschlag mit Datei-Werten als Fallback."""
        return self.best_with(None)

    def best_with(self, protect: Optional[set[str]]) -> BookMetadata:
        """Bester Vorschlag; ``protect`` schützt genannte Felder vor Überschreiben."""
        if self.suggestions:
            return self.original.merged_with(
                self.suggestions[0], prefer_other=True, protect=protect
            )
        return self.original

    @property
    def cover_candidates(self) -> list["CoverCandidate"]:
        """Alle verfügbaren Cover (Original + Vorschläge), dedupliziert.

        Für die GUI, damit der Nutzer aus mehreren Treffern das beste Cover
        auswählen kann.
        """
        seen: set[bytes] = set()
        out: list[CoverCandidate] = []
        if self.original.cover:
            out.append(CoverCandidate("Aus Datei", self.original.cover, self.original.cover_mime))
            seen.add(self.original.cover)
        for i, sug in enumerate(self.suggestions):
            if sug.cover and sug.cover not in seen:
                label = sug.title or f"Vorschlag {i + 1}"
                out.append(CoverCandidate(label, sug.cover, sug.cover_mime))
                seen.add(sug.cover)
        return out


@dataclass
class CoverCandidate:
    """Ein auswählbares Cover-Bild mit beschreibendem Label."""

    label: str
    data: bytes
    mime: str | None


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

    # ISBN aus dem Text ziehen, wenn die Datei keine trägt (präziseste Suche).
    if not working.isbn:
        found = isbn_mod.find_isbn(working.sample_text)
        if found:
            working = working.merged_with(BookMetadata(isbn=found), prefer_other=True)

    # Sprache erkennen, wenn nicht gesetzt (gezieltere Suche, korrektes Feld).
    if not working.language:
        detected = lang.detect(working.sample_text)
        if detected:
            working = working.merged_with(BookMetadata(language=detected), prefer_other=True)

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
        suggestions.extend(
            providers.search(query, max_results=max_results, language=working.language)
        )

    # Beste Treffer nach oben: nach Ähnlichkeit zu den bekannten Werten sortieren.
    suggestions = matching.rank(working, suggestions)

    return EnrichmentResult(original=original, suggestions=suggestions, used_llm=used_llm)


# --------------------------------------------------------------------------- #
# Stapelverarbeitung
# --------------------------------------------------------------------------- #
@dataclass
class BatchOutcome:
    """Ergebnis eines Buches im Stapellauf."""

    path: str
    result: EnrichmentResult | None = None
    written_to: str | None = None      # gesetzt, wenn geschrieben wurde
    error: str | None = None           # gesetzt bei Fehler

    @property
    def ok(self) -> bool:
        return self.error is None


# Fortschritts-Callback: (index_ab_0, gesamt, aktuelle_datei, ergebnis) -> None.
ProgressCallback = Callable[[int, int, str, "BatchOutcome"], None]
# Abbruch-Check: gibt True zurück, wenn der Lauf gestoppt werden soll.
CancelCheck = Callable[[], bool]


def enrich_batch(
    paths: list[str],
    *,
    apply: bool = False,
    out_dir: str | None = None,
    use_llm: bool = True,
    max_results: int = 5,
    optimize_cover: bool = False,
    backup: bool = False,
    protect: Optional[set[str]] = None,
    progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
) -> list[BatchOutcome]:
    """Reichert mehrere Dateien an und schreibt optional den besten Vorschlag.

    ``apply=False`` liefert nur Vorschläge (Trockenlauf). ``apply=True`` schreibt
    den besten Vorschlag pro Datei – nach ``out_dir`` kopiert, falls angegeben,
    sonst in die Originaldatei. Nur Dateien mit mindestens einem Vorschlag
    werden geschrieben; Fehler einzelner Dateien brechen den Lauf nicht ab.

    ``progress`` wird nach jeder Datei mit (Index, Gesamt, Pfad, Ergebnis)
    aufgerufen. ``should_cancel`` wird vor jeder Datei geprüft – liefert es
    ``True``, bricht der Lauf ab und gibt die bis dahin gesammelten Ergebnisse
    zurück. So kann die GUI Fortschritt anzeigen und abbrechen.
    """
    total = len(paths)
    outcomes: list[BatchOutcome] = []
    for index, path in enumerate(paths):
        if should_cancel and should_cancel():
            break
        outcome = BatchOutcome(path=path)
        try:
            result = enrich_file(path, use_llm=use_llm, max_results=max_results)
            outcome.result = result
            if apply and result.suggestions:
                out_path = _out_path_for(path, out_dir)
                outcome.written_to = write_metadata(
                    result.best_with(protect), out_path,
                    optimize_cover=optimize_cover, backup=backup,
                )
        except Exception as exc:  # einzelne Datei darf den Stapel nicht stoppen
            outcome.error = f"{type(exc).__name__}: {exc}"
        outcomes.append(outcome)
        if progress:
            progress(index, total, path, outcome)
    return outcomes


def _out_path_for(src: str, out_dir: str | None) -> str | None:
    if not out_dir:
        return None  # in-place
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, os.path.basename(src))
