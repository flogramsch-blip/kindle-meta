"""Tests für die manuelle KI-Recherche (Anthropic-Client gemockt)."""

import sys
import types

from kindle_meta import llm
from kindle_meta.models import BookMetadata


def _install_fake_anthropic(monkeypatch, reply: str):
    """Baut ein Fake-'anthropic'-Modul, dessen Client 'reply' zurückgibt."""
    block = types.SimpleNamespace(type="text", text=reply)
    message = types.SimpleNamespace(content=[block])

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        class messages:  # noqa: N801 - imitiert client.messages.create
            pass

        def _create(self, *a, **k):
            return message

    client = FakeClient()
    client.messages = types.SimpleNamespace(create=lambda *a, **k: message)

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda *a, **k: client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


def test_research_metadata_parses_reply(monkeypatch):
    reply = (
        'Hier die Daten: {"title": "Der Steppenwolf", "authors": ["Hermann Hesse"], '
        '"publisher": "Suhrkamp", "published": "1927", "isbn": null, '
        '"language": "de", "description": "Ein Roman.", "subjects": ["Klassiker"], '
        '"series": null, "series_index": null}'
    )
    _install_fake_anthropic(monkeypatch, reply)

    res = llm.research_metadata(BookMetadata(title="Steppenwolf", authors=["Hesse"]))
    assert res is not None
    assert res.title == "Der Steppenwolf"
    assert res.authors == ["Hermann Hesse"]
    assert res.publisher == "Suhrkamp"
    assert res.description == "Ein Roman."
    assert res.subjects == ["Klassiker"]


def test_research_metadata_none_without_context(monkeypatch):
    _install_fake_anthropic(monkeypatch, "{}")
    # Weder Titel/Autor/ISBN noch Textprobe -> kein Kontext, keine Anfrage.
    assert llm.research_metadata(BookMetadata()) is None


def test_research_metadata_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.research_metadata(BookMetadata(title="X")) is None
