"""Tests für Stapelverarbeitung und Cover-Auswahl (Provider gemockt)."""

from dataclasses import replace

import pytest

from kindle_meta import enrich, providers
from kindle_meta.enrich import EnrichmentResult, enrich_batch
from kindle_meta.models import BookMetadata
from kindle_meta.readers import read_metadata


@pytest.fixture
def mock_providers(monkeypatch):
    """Ersetzt Netzwerk-Provider durch feste Vorschläge (mit Cover)."""
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c6360000002000154a24f0f0000000049454e44ae426082"
    )
    suggestion = BookMetadata(
        title="Angereicherter Titel",
        authors=["Online Autor"],
        publisher="Online Verlag",
        published="2020",
        cover=png,
        cover_mime="image/png",
    )
    monkeypatch.setattr(providers, "search", lambda q, **k: [suggestion])
    monkeypatch.setattr(providers, "search_by_isbn", lambda i, **k: None)
    return suggestion


def test_batch_dry_run_does_not_write(sample_epub, mock_providers):
    outcomes = enrich_batch([sample_epub], apply=False, use_llm=False)
    assert len(outcomes) == 1
    assert outcomes[0].ok
    assert outcomes[0].written_to is None
    # Original bleibt unverändert.
    assert read_metadata(sample_epub).title == "Der Testtitel"


def test_batch_apply_writes_best(sample_epub, mock_providers, tmp_path):
    out_dir = str(tmp_path / "out")
    outcomes = enrich_batch([sample_epub], apply=True, out_dir=out_dir, use_llm=False)
    oc = outcomes[0]
    assert oc.written_to is not None
    reread = read_metadata(oc.written_to)
    assert reread.title == "Angereicherter Titel"
    assert reread.publisher == "Online Verlag"


def test_batch_continues_on_error(sample_epub, mock_providers):
    outcomes = enrich_batch([sample_epub, "/does/not/exist.epub"], apply=False, use_llm=False)
    assert outcomes[0].ok
    assert not outcomes[1].ok
    assert outcomes[1].error


def test_cover_candidates_dedup(mock_providers):
    original = BookMetadata(title="X")
    result = EnrichmentResult(original=original, suggestions=[mock_providers, mock_providers])
    cands = result.cover_candidates
    # Beide Vorschläge teilen dasselbe Cover -> nur einmal.
    assert len(cands) == 1
    assert cands[0].data == mock_providers.cover
