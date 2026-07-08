"""Datenmodell für Buch-Metadaten.

Ein einheitliches ``BookMetadata`` fließt durch die gesamte Anwendung:
Reader füllen es aus der Datei, Provider/LLM reichern es an, Writer schreiben
es zurück in die Datei.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional


@dataclass
class BookMetadata:
    """Metadaten eines Buches.

    Alle Felder sind optional, weil je nach Quelle (Datei, Online-DB, KI)
    unterschiedlich viel bekannt ist. ``cover`` enthält die rohen Bilddaten,
    ``cover_mime`` den passenden MIME-Typ (z. B. ``image/jpeg``).
    """

    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    publisher: Optional[str] = None
    published: Optional[str] = None  # ISO-Datum oder Jahr, z. B. "2021" / "2021-03-15"
    language: Optional[str] = None
    isbn: Optional[str] = None
    description: Optional[str] = None
    page_count: Optional[int] = None
    series: Optional[str] = None
    series_index: Optional[float] = None
    subjects: list[str] = field(default_factory=list)

    cover: Optional[bytes] = None
    cover_mime: Optional[str] = None

    # Textprobe der ersten Seiten – dient als Grundlage für Online-Suche & KI.
    sample_text: Optional[str] = None
    # Herkunft der Datei, damit Writer die richtige Strategie wählen können.
    source_path: Optional[str] = None

    @property
    def author_str(self) -> str:
        """Autoren als ein String, z. B. für Anzeige und Suche."""
        return ", ".join(self.authors)

    def has_cover(self) -> bool:
        return bool(self.cover)

    def merged_with(self, other: "BookMetadata", *, prefer_other: bool = True) -> "BookMetadata":
        """Kombiniert zwei Metadaten-Sätze.

        Standardmäßig gewinnen die Werte aus ``other`` (z. B. eine Online-DB),
        aber nur wenn sie tatsächlich gesetzt sind – leere Felder überschreiben
        nie vorhandene Werte.
        """
        primary, secondary = (other, self) if prefer_other else (self, other)

        def pick(field_name: str):
            pval = getattr(primary, field_name)
            sval = getattr(secondary, field_name)
            if isinstance(pval, list):
                return pval or sval
            return pval if pval not in (None, "") else sval

        return replace(
            self,
            title=pick("title"),
            authors=pick("authors"),
            publisher=pick("publisher"),
            published=pick("published"),
            language=pick("language"),
            isbn=pick("isbn"),
            description=pick("description"),
            page_count=pick("page_count"),
            series=pick("series"),
            series_index=pick("series_index"),
            subjects=pick("subjects"),
            cover=pick("cover"),
            cover_mime=pick("cover_mime"),
            sample_text=self.sample_text or other.sample_text,
            source_path=self.source_path or other.source_path,
        )
