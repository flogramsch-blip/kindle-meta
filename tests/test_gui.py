"""Leichter Offscreen-Smoke-Test der GUI.

Überspringt sich, wenn PySide6 (oder die nötigen Qt-Systembibliotheken) fehlen –
so bleibt die Test-Suite auch ohne GUI-Umgebung grün.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # pragma: no cover
        pytest.skip("PySide6 nicht importierbar")
    app = QApplication.instance() or QApplication([])
    try:
        yield app
    finally:
        pass


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KINDLE_META_HOME", str(tmp_path / "home"))


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Verhindert, dass modale Dialoge den Headless-Testlauf blockieren."""
    from PySide6.QtWidgets import QMessageBox

    for name in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))


def _make_window(qapp):
    try:
        from kindle_meta.gui.app import MainWindow
        return MainWindow()
    except Exception as exc:  # z. B. fehlende libEGL
        pytest.skip(f"GUI nicht instanziierbar: {exc}")


def test_mainwindow_has_tabs(qapp):
    w = _make_window(qapp)
    tabs = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert tabs == ["Bearbeiten", "Bibliothek"]


def test_editor_loads_metadata_and_rotates_cover(qapp, sample_epub):
    from kindle_meta.readers import read_metadata

    w = _make_window(qapp)
    meta = read_metadata(sample_epub)
    w._on_meta_loaded(meta)
    assert w.f_title.text() == "Der Testtitel"
    assert w._collect_form().title == "Der Testtitel"

    before = w._current_meta.cover
    w._rotate_cover(90)
    assert w._current_meta.cover != before  # Cover wurde verändert


def test_library_grid_and_filter(qapp, sample_epub):
    from kindle_meta.library import Library
    from kindle_meta.readers import read_metadata

    meta = read_metadata(sample_epub)
    with Library() as lib:
        lib.upsert(meta)

    w = _make_window(qapp)
    w._refresh_library()
    assert w.lib_grid.count() == 1
    w._filter_library("zzz")
    assert w.lib_grid.count() == 0
    w._filter_library("test")
    assert w.lib_grid.count() == 1


def test_settings_dialog_saves(qapp):
    from kindle_meta.config import Settings
    from kindle_meta.gui.app import SettingsDialog

    dlg = SettingsDialog()
    dlg.inputs["kindle_addr"].setText("me@kindle.com")
    dlg._save()
    assert Settings().get("kindle_addr") == "me@kindle.com"
