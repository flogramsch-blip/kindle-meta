"""KI-Fallback: Titel und Autor aus einer Textprobe erkennen.

Nutzt die Anthropic-API (Claude), falls installiert und ein API-Key gesetzt
ist. Wird verwendet, wenn eine Datei keine brauchbaren Metadaten enthält –
Claude schätzt Titel/Autor aus den ersten Seiten, damit anschließend online
gesucht werden kann.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .models import BookMetadata

MODEL = "claude-opus-4-8"

_PROMPT = (
    "Du bekommst den Anfangstext eines E-Books (evtl. Titelseite, Impressum, "
    "erste Kapitel). Extrahiere die bibliografischen Metadaten, soweit sie im "
    "Text belegt sind. Rate NICHT bei fehlenden Angaben – gib dann null zurück. "
    "Antworte ausschließlich mit JSON dieser Form:\n"
    '{"title": string|null, "authors": [string], "publisher": string|null, '
    '"published": string|null, "isbn": string|null, "language": string|null}\n\n'
    "Textprobe:\n\n"
)


def available() -> bool:
    """True, wenn SDK installiert und API-Key vorhanden ist."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def guess_metadata(sample_text: str, *, model: str = MODEL) -> Optional[BookMetadata]:
    """Lässt Claude Titel/Autor/… aus der Textprobe schätzen.

    Gibt ``None`` zurück, wenn die KI nicht verfügbar ist oder die Antwort
    nicht als JSON verwertbar war.
    """
    if not sample_text or not available():
        return None

    import anthropic

    client = anthropic.Anthropic()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": _PROMPT + sample_text[:6000]}],
        )
        raw = "".join(block.text for block in message.content if block.type == "text")
        data = _extract_json(raw)
    except Exception:
        return None
    if not data:
        return None

    return BookMetadata(
        title=data.get("title") or None,
        authors=[a for a in (data.get("authors") or []) if a],
        publisher=data.get("publisher") or None,
        published=data.get("published") or None,
        isbn=data.get("isbn") or None,
        language=data.get("language") or None,
    )


_RESEARCH_PROMPT = (
    "Du bist ein bibliografischer Rechercheassistent. Identifiziere anhand der "
    "folgenden Angaben (Titel/Autor und/oder Anfangstext) das Buch und gib die "
    "dir bekannten bibliografischen Metadaten zurück – hier darfst du dein "
    "Wissen nutzen, nicht nur den Text. Wenn du dir bei einem Feld unsicher "
    "bist, gib null zurück (lieber null als falsch). Erfinde keine ISBN.\n"
    "Antworte ausschließlich mit JSON dieser Form:\n"
    '{"title": string|null, "authors": [string], "publisher": string|null, '
    '"published": string|null, "isbn": string|null, "language": string|null, '
    '"description": string|null, "subjects": [string], "series": string|null, '
    '"series_index": number|null}\n\n'
)


def research_metadata(known: BookMetadata, *, model: str = MODEL) -> Optional[BookMetadata]:
    """Manuelle KI-Recherche: identifiziert das Buch und liefert bekannte Metadaten.

    Anders als ``guess_metadata`` (nur Text-Extraktion) darf Claude hier sein
    eigenes Wissen einsetzen, um Verlag, Datum, Beschreibung, Serie usw. zu
    ergänzen. Das Ergebnis ist als KI-Vorschlag zu verstehen und vom Nutzer zu
    prüfen. Gibt ``None`` zurück, wenn die KI nicht verfügbar/verwertbar ist.
    """
    if not available():
        return None

    context_parts = []
    if known.title:
        context_parts.append(f"Titel: {known.title}")
    if known.authors:
        context_parts.append(f"Autor(en): {known.author_str}")
    if known.isbn:
        context_parts.append(f"ISBN: {known.isbn}")
    if known.sample_text:
        context_parts.append("Anfangstext:\n" + known.sample_text[:4000])
    context = "\n".join(context_parts)
    if not context.strip():
        return None

    import anthropic

    client = anthropic.Anthropic()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": _RESEARCH_PROMPT + context}],
        )
        raw = "".join(block.text for block in message.content if block.type == "text")
        data = _extract_json(raw)
    except Exception:
        return None
    if not data:
        return None

    idx = data.get("series_index")
    try:
        idx = float(idx) if idx is not None else None
    except (TypeError, ValueError):
        idx = None
    return BookMetadata(
        title=data.get("title") or None,
        authors=[a for a in (data.get("authors") or []) if a],
        publisher=data.get("publisher") or None,
        published=data.get("published") or None,
        isbn=data.get("isbn") or None,
        language=data.get("language") or None,
        description=data.get("description") or None,
        subjects=[s for s in (data.get("subjects") or []) if s],
        series=data.get("series") or None,
        series_index=idx,
    )


def _extract_json(raw: str) -> Optional[dict]:
    raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
