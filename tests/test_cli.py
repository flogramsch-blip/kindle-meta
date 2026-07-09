"""Tests für die Kommandozeile (End-to-End über cli.main)."""

import pytest

from kindle_meta import cli, providers
from kindle_meta.models import BookMetadata


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KINDLE_META_HOME", str(tmp_path / "home"))


@pytest.fixture
def no_network(monkeypatch):
    """Provider durch feste Vorschläge ersetzen (keine echten Requests)."""
    monkeypatch.setattr(
        providers, "search",
        lambda q, **k: [BookMetadata(title="Online", authors=["Autor"], publisher="V")],
    )
    monkeypatch.setattr(providers, "search_by_isbn", lambda i, **k: None)


def test_cli_info(sample_epub, capsys):
    assert cli.main(["info", sample_epub]) == 0
    out = capsys.readouterr().out
    assert "Der Testtitel" in out


def test_cli_apply_and_undo(sample_epub, capsys):
    # In-Place mit Backup, dann rückgängig.
    assert cli.main(["apply", sample_epub, "--title", "Geändert", "--author", "A"]) == 0
    from kindle_meta.readers import read_metadata
    assert read_metadata(sample_epub).title == "Geändert"

    assert cli.main(["undo", sample_epub]) == 0
    assert read_metadata(sample_epub).title == "Der Testtitel"


def test_cli_library_after_apply(sample_epub, capsys):
    cli.main(["apply", sample_epub, "--series", "Reihe", "--series-index", "1"])
    capsys.readouterr()
    assert cli.main(["library"]) == 0
    out = capsys.readouterr().out
    assert "Reihe" in out


def test_cli_batch_dry_run(sample_epub, no_network, capsys):
    assert cli.main(["batch", sample_epub, "--no-llm"]) == 0
    out = capsys.readouterr().out
    assert "Trockenlauf" in out


def test_cli_send_without_config_errors(sample_epub, capsys):
    rc = cli.main(["send", sample_epub, "--to", "x@kindle.com"])
    assert rc == 1
    assert "SMTP nicht konfiguriert" in capsys.readouterr().err


def test_cli_unsupported_format_errors(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    assert cli.main(["info", str(f)]) == 1
