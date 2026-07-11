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


def test_compare_dialog_combines_fields(qapp):
    from kindle_meta.gui.app import CompareDialog
    from kindle_meta.models import BookMetadata

    orig = BookMetadata(title="Datei", authors=["Alt"], source_path="/x/y.epub")
    sugg = [BookMetadata(title="Online", authors=["Neu"], publisher="V")]
    dlg = CompareDialog(orig, sugg)
    dlg._boxes["title"].setCurrentText("Datei")     # aus der Datei
    dlg._boxes["authors"].setCurrentText("Neu")     # aus dem Vorschlag
    dlg._boxes["publisher"].setCurrentText("V")
    res = dlg.result_metadata()
    assert res.title == "Datei"
    assert res.authors == ["Neu"]
    assert res.publisher == "V"
    assert res.source_path == "/x/y.epub"           # Herkunft bleibt erhalten


def test_crop_dialog_produces_cover(qapp):
    import io

    from PIL import Image
    from PySide6.QtCore import QRect

    from kindle_meta.gui.app import CropDialog

    buf = io.BytesIO()
    Image.new("RGB", (300, 450), (50, 80, 120)).save(buf, "PNG")
    dlg = CropDialog(buf.getvalue())
    dlg.image.selection = QRect(10, 10, 120, 160)
    dlg._crop()
    assert dlg.result_cover and dlg.result_cover[:2] == b"\xff\xd8"  # JPEG


def test_multiselect_remove(qapp):
    w = _make_window(qapp)
    w._add_file("/x/a.epub")
    w._add_file("/x/b.epub")
    w.file_list.selectAll()
    assert len(w._selected_paths()) == 2
    w._remove_selected()
    assert w.file_list.count() == 0


def test_ai_result_added_as_marked_suggestion(qapp, sample_epub):
    from kindle_meta.models import BookMetadata
    from kindle_meta.readers import read_metadata

    w = _make_window(qapp)
    w._on_meta_loaded(read_metadata(sample_epub))

    ki = BookMetadata(title="KI Titel", authors=["KI Autor"], publisher="KI Verlag")
    w._on_ai_result(ki)

    # KI-Ergebnis steht als erster Vorschlag und ist markiert.
    assert w._suggestions[0] is ki
    assert id(ki) in w._ai_ids
    assert w.compare_btn.isEnabled()
    assert "🤖 KI:" in w.suggestion_box.itemText(1)  # Eintrag 0 ist der Platzhalter
