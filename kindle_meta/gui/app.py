"""PySide6-Desktop-Oberfläche für kindle-meta.

Ablauf in der GUI:
  1. Dateien per Button/Drag&Drop zur Liste hinzufügen.
  2. Datei auswählen → vorhandene Metadaten + Cover erscheinen im Formular.
  3. "Online suchen" holt Vorschläge (Google Books / Open Library, KI-Fallback).
     Ein Vorschlag lässt sich anwenden; Felder bleiben manuell editierbar.
  4. "Speichern" schreibt die Metadaten (inkl. Cover) zurück in die Datei –
     Kindle-tauglich eingebettet.

Die eigentliche Arbeit (Lesen/Anreichern/Schreiben) läuft in Worker-Threads,
damit die Oberfläche nicht einfriert. Netzwerk-lastige Anreicherung wird über
``QThreadPool`` ausgeführt.
"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import replace

from PySide6.QtCore import QObject, QPoint, QRect, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRubberBand,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..enrich import CoverCandidate, EnrichmentResult, enrich_batch, enrich_metadata
from ..models import BookMetadata
from ..readers import read_metadata
from ..writers import write_metadata

SUPPORTED = (".epub", ".pdf")


# --------------------------------------------------------------------------- #
# Worker-Infrastruktur (damit die GUI nicht blockiert)
# --------------------------------------------------------------------------- #
class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.result.emit(self.fn(*self.args, **self.kwargs))
        except Exception:
            self.signals.error.emit(traceback.format_exc())


class BatchSignals(QObject):
    progress = Signal(int, int, str)  # index, total, dateiname
    done = Signal(object)             # list[BatchOutcome]
    error = Signal(str)


class BatchWorker(QRunnable):
    """Führt einen Stapellauf im Hintergrund aus – mit Fortschritt & Abbruch."""

    def __init__(self, paths, *, out_dir, use_llm, optimize_cover, backup, protect=None):
        super().__init__()
        self.paths = paths
        self.out_dir = out_dir
        self.use_llm = use_llm
        self.optimize_cover = optimize_cover
        self.backup = backup
        self.protect = protect
        self.signals = BatchSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            outcomes = enrich_batch(
                self.paths,
                apply=True,
                out_dir=self.out_dir,
                use_llm=self.use_llm,
                optimize_cover=self.optimize_cover,
                backup=self.backup,
                protect=self.protect,
                progress=lambda i, total, path, oc: self.signals.progress.emit(
                    i, total, path.rsplit("/", 1)[-1]
                ),
                should_cancel=lambda: self._cancelled,
            )
            self.signals.done.emit(outcomes)
        except Exception:
            self.signals.error.emit(traceback.format_exc())


# --------------------------------------------------------------------------- #
# Hauptfenster
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kindle-meta – E-Book-Metadaten für Kindle")
        self.resize(920, 620)
        self.pool = QThreadPool.globalInstance()

        # Zustand
        self._current_meta: BookMetadata | None = None
        self._suggestions: list[BookMetadata] = []
        self._cover_candidates: list[CoverCandidate] = []
        self._batch_worker: BatchWorker | None = None
        self._kindle_addr: str = ""

        self._build_ui()
        self.setAcceptDrops(True)

    # -- UI-Aufbau ---------------------------------------------------------- #
    def _build_ui(self) -> None:
        self._build_menu()
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_editor_tab(), "Bearbeiten")
        self.tabs.addTab(self._build_library_tab(), "Bibliothek")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&Datei")
        act_settings = menu.addAction("Einstellungen …")
        act_settings.triggered.connect(self._open_settings)
        act_quit = menu.addAction("Beenden")
        act_quit.triggered.connect(self.close)

    def _build_editor_tab(self) -> QWidget:
        central = QWidget()
        root = QHBoxLayout(central)

        # Linke Spalte: Dateiliste
        left = QVBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.currentItemChanged.connect(self._on_select_file)
        add_btn = QPushButton("Dateien hinzufügen …")
        add_btn.clicked.connect(self._add_files_dialog)
        left.addWidget(QLabel("Bücher (Drag & Drop, Mehrfachauswahl)"))
        left.addWidget(self.file_list, 1)
        left.addWidget(add_btn)

        # Sammelaktionen für die (mehrfache) Auswahl.
        sel_row = QHBoxLayout()
        remove_btn = QPushButton("Ausgewählte entfernen")
        remove_btn.clicked.connect(self._remove_selected)
        send_sel_btn = QPushButton("Ausgewählte senden")
        send_sel_btn.clicked.connect(self._send_selected)
        sel_row.addWidget(remove_btn)
        sel_row.addWidget(send_sel_btn)
        left.addLayout(sel_row)

        # Stapelverarbeitung
        left.addWidget(QLabel("Stapelverarbeitung"))
        self.batch_optimize = QCheckBox("Cover für Kindle optimieren")
        left.addWidget(self.batch_optimize)
        self.batch_btn = QPushButton("Alle anreichern & speichern …")
        self.batch_btn.clicked.connect(self._run_batch)
        left.addWidget(self.batch_btn)
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.clicked.connect(self._cancel_batch)
        self.cancel_btn.hide()
        left.addWidget(self.cancel_btn)
        self.progress = QProgressBar()
        self.progress.hide()
        left.addWidget(self.progress)

        root.addLayout(left, 1)

        # Rechte Spalte: Cover + Formular
        right = QVBoxLayout()

        self.cover_label = QLabel("Kein Cover")
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setMinimumSize(180, 240)
        self.cover_label.setStyleSheet("border: 1px solid #888; color: #888;")
        cover_btn = QPushButton("Cover ersetzen …")
        cover_btn.clicked.connect(self._replace_cover)

        # Inline-Cover-Editor: drehen.
        rotate_row = QHBoxLayout()
        self.rotate_left_btn = QPushButton("↺")
        self.rotate_left_btn.setToolTip("90° gegen den Uhrzeigersinn drehen")
        self.rotate_left_btn.clicked.connect(lambda: self._rotate_cover(-90))
        self.rotate_right_btn = QPushButton("↻")
        self.rotate_right_btn.setToolTip("90° im Uhrzeigersinn drehen")
        self.rotate_right_btn.clicked.connect(lambda: self._rotate_cover(90))
        self.crop_btn = QPushButton("Zuschneiden …")
        self.crop_btn.setToolTip("Cover interaktiv zuschneiden")
        self.crop_btn.clicked.connect(self._crop_cover)
        rotate_row.addWidget(self.rotate_left_btn)
        rotate_row.addWidget(self.rotate_right_btn)

        cover_box = QVBoxLayout()
        cover_box.addWidget(self.cover_label)
        cover_box.addWidget(cover_btn)
        cover_box.addLayout(rotate_row)
        cover_box.addWidget(self.crop_btn)

        form = QFormLayout()
        self.f_title = QLineEdit()
        self.f_author = QLineEdit()
        self.f_publisher = QLineEdit()
        self.f_date = QLineEdit()
        self.f_isbn = QLineEdit()
        self.f_language = QLineEdit()
        self.f_series = QLineEdit()
        self.f_series_index = QLineEdit()
        self.f_series_index.setPlaceholderText("z. B. 2")
        self.f_desc = QTextEdit()
        self.f_desc.setMaximumHeight(90)
        form.addRow("Titel", self.f_title)
        form.addRow("Autor(en)", self.f_author)
        form.addRow("Verlag", self.f_publisher)
        form.addRow("Datum", self.f_date)
        form.addRow("ISBN", self.f_isbn)
        form.addRow("Sprache", self.f_language)
        form.addRow("Serie", self.f_series)
        form.addRow("Serien-Nr.", self.f_series_index)
        form.addRow("Beschreibung", self.f_desc)

        top = QHBoxLayout()
        top.addLayout(cover_box)
        top.addLayout(form, 1)
        right.addLayout(top)

        # Cover-Auswahl: klickbare Thumbnails aus mehreren Treffern.
        self.cover_picker = QListWidget()
        self.cover_picker.setFlow(QListWidget.LeftToRight)
        self.cover_picker.setWrapping(False)
        self.cover_picker.setFixedHeight(120)
        self.cover_picker.setIconSize(QSize(70, 96))
        self.cover_picker.setSpacing(6)
        self.cover_picker.itemClicked.connect(self._on_pick_cover)
        self.cover_picker.hide()
        right.addWidget(QLabel("Cover-Auswahl (nach der Suche):"))
        right.addWidget(self.cover_picker)

        # Vorschläge + Aktionen
        self.suggestion_box = QComboBox()
        self.suggestion_box.setEnabled(False)
        self.suggestion_box.currentIndexChanged.connect(self._apply_suggestion)

        self.search_btn = QPushButton("Online suchen / anreichern")
        self.search_btn.clicked.connect(self._enrich)
        self.compare_btn = QPushButton("Vergleichen …")
        self.compare_btn.setToolTip("Vorschläge feldweise vergleichen und kombinieren")
        self.compare_btn.clicked.connect(self._compare_suggestions)
        self.compare_btn.setEnabled(False)
        self.save_btn = QPushButton("Speichern (in Datei schreiben)")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Vorschläge:"))
        actions.addWidget(self.suggestion_box, 1)
        actions.addWidget(self.search_btn)
        actions.addWidget(self.compare_btn)
        right.addLayout(actions)

        opts_row = QHBoxLayout()
        self.optimize_cover_cb = QCheckBox("Cover beim Speichern für Kindle optimieren")
        self.backup_cb = QCheckBox("Backup vor Überschreiben")
        self.backup_cb.setChecked(True)
        opts_row.addWidget(self.optimize_cover_cb)
        opts_row.addWidget(self.backup_cb)
        opts_row.addStretch(1)
        right.addLayout(opts_row)

        save_row = QHBoxLayout()
        save_row.addWidget(self.save_btn, 1)
        self.send_btn = QPushButton("An Kindle senden …")
        self.send_btn.clicked.connect(self._send_to_kindle)
        self.send_btn.setEnabled(False)
        save_row.addWidget(self.send_btn)
        right.addLayout(save_row)

        self.status = QLabel("Bereit.")
        self.status.setStyleSheet("color: #555;")
        right.addWidget(self.status)

        root.addLayout(right, 2)
        self._set_form_enabled(False)
        return central

    def _build_library_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        top = QHBoxLayout()
        self.lib_search = QLineEdit()
        self.lib_search.setPlaceholderText("Suchen (Titel/Autor/Serie) …")
        self.lib_search.textChanged.connect(self._filter_library)
        refresh_btn = QPushButton("Aktualisieren")
        refresh_btn.clicked.connect(self._refresh_library)
        top.addWidget(QLabel("Bibliothek:"))
        top.addWidget(self.lib_search, 1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.lib_grid = QListWidget()
        self.lib_grid.setViewMode(QListWidget.IconMode)
        self.lib_grid.setIconSize(QSize(120, 170))
        self.lib_grid.setGridSize(QSize(160, 230))
        self.lib_grid.setResizeMode(QListWidget.Adjust)
        self.lib_grid.setMovement(QListWidget.Static)
        self.lib_grid.setSpacing(10)
        self.lib_grid.setWordWrap(True)
        self.lib_grid.itemDoubleClicked.connect(self._open_library_item)
        layout.addWidget(self.lib_grid, 1)

        self.lib_status = QLabel("")
        self.lib_status.setStyleSheet("color: #555;")
        layout.addWidget(self.lib_status)
        return widget

    # -- Datei-Handling ----------------------------------------------------- #
    def _add_files_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "E-Books auswählen", "", "E-Books (*.epub *.pdf)"
        )
        for p in paths:
            self._add_file(p)

    def _add_file(self, path: str) -> None:
        if not path.lower().endswith(SUPPORTED):
            return
        # Duplikate vermeiden.
        for i in range(self.file_list.count()):
            if self.file_list.item(i).data(Qt.UserRole) == path:
                return
        item = QListWidgetItem(path.rsplit("/", 1)[-1])
        item.setData(Qt.UserRole, path)
        self.file_list.addItem(item)

    def dragEnterEvent(self, event):  # noqa: N802 (Qt-Namenskonvention)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        for url in event.mimeData().urls():
            self._add_file(url.toLocalFile())

    def _on_select_file(self, current, _previous) -> None:
        if current is None:
            return
        path = current.data(Qt.UserRole)
        self.status.setText("Lese Datei …")
        worker = Worker(read_metadata, path)
        worker.signals.result.connect(self._on_meta_loaded)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_meta_loaded(self, meta: BookMetadata) -> None:
        self._current_meta = meta
        self._suggestions = []
        self._cover_candidates = []
        self.cover_picker.clear()
        self.cover_picker.hide()
        self.suggestion_box.clear()
        self.suggestion_box.setEnabled(False)
        self.compare_btn.setEnabled(False)
        self._fill_form(meta)
        self._set_form_enabled(True)
        self.save_btn.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.status.setText("Datei gelesen. Optional online anreichern.")

    # -- Formular <-> Modell ------------------------------------------------ #
    def _fill_form(self, meta: BookMetadata) -> None:
        self.f_title.setText(meta.title or "")
        self.f_author.setText(meta.author_str)
        self.f_publisher.setText(meta.publisher or "")
        self.f_date.setText(meta.published or "")
        self.f_isbn.setText(meta.isbn or "")
        self.f_language.setText(meta.language or "")
        self.f_series.setText(meta.series or "")
        idx = meta.series_index
        self.f_series_index.setText("" if idx is None else _fmt_index(idx))
        self.f_desc.setPlainText(meta.description or "")
        self._show_cover(meta)

    def _collect_form(self) -> BookMetadata:
        assert self._current_meta is not None
        authors = [a.strip() for a in self.f_author.text().split(",") if a.strip()]
        index_text = self.f_series_index.text().strip().replace(",", ".")
        try:
            series_index = float(index_text) if index_text else None
        except ValueError:
            series_index = None
        return replace(
            self._current_meta,
            title=self.f_title.text().strip() or None,
            authors=authors,
            publisher=self.f_publisher.text().strip() or None,
            published=self.f_date.text().strip() or None,
            isbn=self.f_isbn.text().strip() or None,
            language=self.f_language.text().strip() or None,
            series=self.f_series.text().strip() or None,
            series_index=series_index,
            description=self.f_desc.toPlainText().strip() or None,
        )

    def _show_cover(self, meta: BookMetadata) -> None:
        if meta.cover:
            pix = QPixmap()
            if pix.loadFromData(meta.cover):
                self.cover_label.setPixmap(
                    pix.scaled(180, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        self.cover_label.setPixmap(QPixmap())
        self.cover_label.setText("Kein Cover")

    def _replace_cover(self) -> None:
        if self._current_meta is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Cover-Bild wählen", "", "Bilder (*.jpg *.jpeg *.png)"
        )
        if not path:
            return
        with open(path, "rb") as fh:
            data = fh.read()
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        self._current_meta = replace(self._current_meta, cover=data, cover_mime=mime)
        self._show_cover(self._current_meta)

    def _rotate_cover(self, degrees: int) -> None:
        if self._current_meta is None or not self._current_meta.cover:
            return
        try:
            from .. import covers

            data, mime = covers.rotate(self._current_meta.cover, degrees)
        except Exception as exc:
            QMessageBox.warning(self, "Cover drehen", str(exc))
            return
        self._current_meta = replace(self._current_meta, cover=data, cover_mime=mime)
        self._show_cover(self._current_meta)
        self.status.setText("Cover gedreht.")

    # -- Anreicherung ------------------------------------------------------- #
    def _enrich(self) -> None:
        if self._current_meta is None:
            return
        self.status.setText("Suche online (Google Books / Open Library) …")
        self.search_btn.setEnabled(False)
        base = self._collect_form()
        worker = Worker(enrich_metadata, base)
        worker.signals.result.connect(self._on_enriched)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_enriched(self, result: EnrichmentResult) -> None:
        self.search_btn.setEnabled(True)
        self._suggestions = result.suggestions
        self.suggestion_box.blockSignals(True)
        self.suggestion_box.clear()
        self.suggestion_box.addItem("— Vorschlag wählen —")
        for sug in result.suggestions:
            label = f"{sug.title or '?'} — {sug.author_str or '?'}"
            if sug.published:
                label += f" ({sug.published})"
            self.suggestion_box.addItem(label)
        self.suggestion_box.setEnabled(bool(result.suggestions))
        self.suggestion_box.blockSignals(False)
        self.compare_btn.setEnabled(bool(result.suggestions))

        # Cover-Auswahl befüllen.
        self._cover_candidates = result.cover_candidates
        self.cover_picker.clear()
        for cand in self._cover_candidates:
            pix = QPixmap()
            if not pix.loadFromData(cand.data):
                continue
            item = QListWidgetItem(QIcon(pix), cand.label)
            item.setToolTip(cand.label)
            item.setData(Qt.UserRole, cand)
            self.cover_picker.addItem(item)
        self.cover_picker.setVisible(self.cover_picker.count() > 0)

        note = " (KI half beim Erkennen)" if result.used_llm else ""
        n_covers = self.cover_picker.count()
        covers = f", {n_covers} Cover zur Auswahl" if n_covers else ""
        self.status.setText(
            f"{len(result.suggestions)} Vorschlag/Vorschläge gefunden{note}{covers}."
        )

    def _apply_suggestion(self, index: int) -> None:
        if index <= 0 or index - 1 >= len(self._suggestions):
            return
        sug = self._suggestions[index - 1]
        # Vorschlag über die aktuellen (evtl. editierten) Werte legen.
        merged = self._collect_form().merged_with(sug, prefer_other=True)
        self._current_meta = merged
        self._fill_form(merged)
        self.status.setText("Vorschlag übernommen – bitte prüfen und speichern.")

    def _on_pick_cover(self, item: QListWidgetItem) -> None:
        if self._current_meta is None:
            return
        cand: CoverCandidate = item.data(Qt.UserRole)
        self._current_meta = replace(
            self._current_meta, cover=cand.data, cover_mime=cand.mime
        )
        self._show_cover(self._current_meta)
        self.status.setText(f"Cover übernommen: {cand.label}")

    def _compare_suggestions(self) -> None:
        if self._current_meta is None or not self._suggestions:
            return
        dlg = CompareDialog(self._collect_form(), self._suggestions, self)
        if dlg.exec() == QDialog.Accepted:
            merged = dlg.result_metadata()
            self._current_meta = merged
            self._fill_form(merged)
            self.status.setText("Felder aus Vergleich übernommen – bitte prüfen und speichern.")

    def _crop_cover(self) -> None:
        if self._current_meta is None or not self._current_meta.cover:
            QMessageBox.information(self, "Zuschneiden", "Kein Cover vorhanden.")
            return
        dlg = CropDialog(self._current_meta.cover, self)
        if dlg.exec() == QDialog.Accepted and dlg.result_cover:
            self._current_meta = replace(
                self._current_meta, cover=dlg.result_cover, cover_mime=dlg.result_mime
            )
            self._show_cover(self._current_meta)
            self.status.setText("Cover zugeschnitten.")

    # -- Sammelaktionen für die Auswahl ------------------------------------- #
    def _selected_paths(self) -> list[str]:
        return [item.data(Qt.UserRole) for item in self.file_list.selectedItems()]

    def _remove_selected(self) -> None:
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def _send_selected(self) -> None:
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "Senden", "Bitte Bücher in der Liste auswählen.")
            return
        default = self._kindle_addr or (_load_settings().get("kindle_addr") or "")
        addr, ok = QInputDialog.getText(
            self, "Ausgewählte an Kindle senden",
            "Kindle-E-Mail-Adresse (…@kindle.com):", text=default,
        )
        if not ok or not addr.strip():
            return
        self._kindle_addr = addr.strip()
        _load_settings().set("kindle_addr", self._kindle_addr)

        def _send_all():
            from ..sendmail import send_to_kindle
            for p in paths:
                send_to_kindle(p, self._kindle_addr)
            return len(paths)

        self.status.setText(f"Sende {len(paths)} Buch/Bücher an Kindle …")
        worker = Worker(_send_all)
        worker.signals.result.connect(
            lambda n: self.status.setText(f"{n} Buch/Bücher an Kindle gesendet.")
        )
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    # -- Speichern ---------------------------------------------------------- #
    def _save(self) -> None:
        if self._current_meta is None:
            return
        meta = self._collect_form()
        self.status.setText("Schreibe Datei …")
        self.save_btn.setEnabled(False)
        worker = Worker(
            write_metadata,
            meta,
            optimize_cover=self.optimize_cover_cb.isChecked(),
            backup=self.backup_cb.isChecked(),
        )
        worker.signals.result.connect(self._on_saved)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_saved(self, out_path: str) -> None:
        self.save_btn.setEnabled(True)
        self.status.setText(f"Gespeichert: {out_path}")
        _record_library(out_path)
        QMessageBox.information(self, "Fertig", f"Metadaten geschrieben:\n{out_path}")

    # -- Stapelverarbeitung ------------------------------------------------- #
    def _run_batch(self) -> None:
        paths = [
            self.file_list.item(i).data(Qt.UserRole)
            for i in range(self.file_list.count())
        ]
        if not paths:
            QMessageBox.information(self, "Stapel", "Bitte zuerst Dateien hinzufügen.")
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, "Zielordner wählen (Abbrechen = Originale überschreiben)"
        )
        if not out_dir:
            confirm = QMessageBox.question(
                self, "Originale überschreiben?",
                "Ohne Zielordner werden die Originaldateien überschrieben. Fortfahren?",
            )
            if confirm != QMessageBox.Yes:
                return
            out_dir = None

        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.batch_btn.setEnabled(False)

        from ..profile import load_protected

        worker = BatchWorker(
            paths,
            out_dir=out_dir,
            use_llm=True,
            optimize_cover=self.batch_optimize.isChecked(),
            backup=self.backup_cb.isChecked(),
            protect=load_protected(),
        )
        worker.signals.progress.connect(self._on_batch_progress)
        worker.signals.done.connect(self._on_batch_done)
        worker.signals.error.connect(self._on_error)
        self._batch_worker = worker
        self.pool.start(worker)

    def _cancel_batch(self) -> None:
        if self._batch_worker:
            self._batch_worker.cancel()
            self.status.setText("Abbruch angefordert – laufende Datei wird noch beendet …")

    def _on_batch_progress(self, index: int, total: int, name: str) -> None:
        self.progress.setValue(index + 1)
        self.status.setText(f"Stapel: {index + 1}/{total} – {name}")

    def _on_batch_done(self, outcomes) -> None:
        self.progress.hide()
        self.cancel_btn.hide()
        self.batch_btn.setEnabled(True)
        self._batch_worker = None
        written = sum(1 for o in outcomes if o.written_to)
        for o in outcomes:
            if o.written_to:
                _record_library(o.written_to)
        errors = [o for o in outcomes if not o.ok]
        msg = f"{written} von {len(outcomes)} Datei(en) geschrieben."
        if errors:
            msg += f"\n{len(errors)} Fehler:\n" + "\n".join(
                f"• {e.path.rsplit('/', 1)[-1]}: {e.error}" for e in errors[:10]
            )
        self.status.setText(f"Stapel fertig: {msg.splitlines()[0]}")
        QMessageBox.information(self, "Stapel fertig", msg)

    # -- Send to Kindle ----------------------------------------------------- #
    def _send_to_kindle(self) -> None:
        if self._current_meta is None or not self._current_meta.source_path:
            return
        default = self._kindle_addr or (_load_settings().get("kindle_addr") or "")
        addr, ok = QInputDialog.getText(
            self, "An Kindle senden",
            "Kindle-E-Mail-Adresse (…@kindle.com):", text=default,
        )
        if not ok or not addr.strip():
            return
        self._kindle_addr = addr.strip()
        _load_settings().set("kindle_addr", self._kindle_addr)

        def _send():
            from ..sendmail import send_to_kindle
            send_to_kindle(self._current_meta.source_path, self._kindle_addr)
            return self._kindle_addr

        self.status.setText("Sende an Kindle …")
        self.send_btn.setEnabled(False)
        worker = Worker(_send)
        worker.signals.result.connect(self._on_sent)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_sent(self, addr: str) -> None:
        self.send_btn.setEnabled(True)
        self.status.setText(f"An Kindle gesendet: {addr}")
        QMessageBox.information(self, "Gesendet", f"Buch an {addr} gesendet.")

    # -- Bibliotheks-Tab ---------------------------------------------------- #
    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "Bibliothek":
            self._refresh_library()

    def _refresh_library(self) -> None:
        try:
            from ..library import Library

            with Library() as lib:
                self._lib_books = lib.all()
                self._lib_thumbs = {
                    m.source_path: lib.get_thumbnail(m.source_path) for m in self._lib_books
                }
        except Exception as exc:
            self.lib_status.setText(f"Bibliothek nicht ladbar: {exc}")
            return
        self._render_library(self._lib_books)
        self.lib_status.setText(f"{len(self._lib_books)} Buch/Bücher.")

    def _render_library(self, books) -> None:
        self.lib_grid.clear()
        for meta in books:
            label = meta.title or "?"
            if meta.authors:
                label += f"\n{meta.author_str}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, meta.source_path)
            item.setToolTip(meta.source_path or "")
            thumb = getattr(self, "_lib_thumbs", {}).get(meta.source_path)
            if thumb:
                pix = QPixmap()
                if pix.loadFromData(thumb):
                    item.setIcon(QIcon(pix))
            self.lib_grid.addItem(item)

    def _filter_library(self, text: str) -> None:
        text = text.strip().lower()
        books = getattr(self, "_lib_books", [])
        if not text:
            self._render_library(books)
            return
        filtered = [
            m for m in books
            if text in (m.title or "").lower()
            or text in m.author_str.lower()
            or text in (m.series or "").lower()
        ]
        self._render_library(filtered)

    def _open_library_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Bibliothek", "Datei nicht gefunden:\n" + str(path))
            return
        self._add_file(path)
        self.tabs.setCurrentIndex(0)  # zum Bearbeiten-Tab
        # In der Liste auswählen -> lädt Metadaten.
        for i in range(self.file_list.count()):
            if self.file_list.item(i).data(Qt.UserRole) == path:
                self.file_list.setCurrentRow(i)
                break

    # -- Einstellungen ------------------------------------------------------ #
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.status.setText("Einstellungen gespeichert.")

    # -- Hilfen ------------------------------------------------------------- #
    def _on_error(self, tb: str) -> None:
        has_meta = self._current_meta is not None
        self.search_btn.setEnabled(True)
        self.save_btn.setEnabled(has_meta)
        self.send_btn.setEnabled(has_meta)
        # Falls ein Stapellauf lief, Bedienelemente zurücksetzen.
        self.batch_btn.setEnabled(True)
        self.cancel_btn.hide()
        self.progress.hide()
        self._batch_worker = None
        self.status.setText("Fehler – siehe Dialog.")
        QMessageBox.critical(self, "Fehler", tb)

    def _set_form_enabled(self, enabled: bool) -> None:
        for w in (
            self.f_title, self.f_author, self.f_publisher, self.f_date,
            self.f_isbn, self.f_language, self.f_series, self.f_series_index,
            self.f_desc, self.search_btn,
        ):
            w.setEnabled(enabled)


def _fmt_index(value: float) -> str:
    """Serien-Index ohne unnötige Nachkommastelle (1 statt 1.0)."""
    return str(int(value)) if float(value).is_integer() else str(value)


class CompareDialog(QDialog):
    """Vergleicht Datei-Werte mit mehreren Vorschlägen – feldweise übernehmbar.

    Für jedes Feld gibt es eine (editierbare) Auswahl aller Kandidatenwerte
    (Datei + Vorschläge). Beim Bestätigen entsteht ein zusammengesetztes
    ``BookMetadata`` – man kann so Titel von A und Autor von B kombinieren.
    """

    # (Attribut, Label). Cover wird separat über die Cover-Auswahl gewählt.
    FIELDS = [
        ("title", "Titel"),
        ("authors", "Autor(en)"),
        ("publisher", "Verlag"),
        ("published", "Datum"),
        ("isbn", "ISBN"),
        ("language", "Sprache"),
        ("series", "Serie"),
        ("series_index", "Serien-Nr."),
        ("description", "Beschreibung"),
    ]

    def __init__(self, original: BookMetadata, suggestions: list[BookMetadata], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vorschläge vergleichen")
        self.resize(640, 400)
        self.original = original
        self._boxes: dict[str, QComboBox] = {}

        form = QFormLayout()
        sources = [("Datei", original)] + [
            (s.title or f"Vorschlag {i + 1}", s) for i, s in enumerate(suggestions)
        ]
        for attr, label in self.FIELDS:
            box = QComboBox()
            box.setEditable(True)
            seen = set()
            for _src_label, meta in sources:
                val = self._field_str(meta, attr)
                if val and val not in seen:
                    box.addItem(val)
                    seen.add(val)
            # aktuellen Wert der Datei vorwählen
            current = self._field_str(original, attr)
            box.setCurrentText(current)
            self._boxes[attr] = box
            form.addRow(label, box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("Pro Feld einen Wert wählen (oder frei eintippen). "
                      "Werte lassen sich aus verschiedenen Vorschlägen kombinieren.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _field_str(meta: BookMetadata, attr: str) -> str:
        if attr == "authors":
            return meta.author_str
        val = getattr(meta, attr)
        if val is None:
            return ""
        if attr == "series_index":
            return _fmt_index(val)
        return str(val)

    def result_metadata(self) -> BookMetadata:
        """Baut aus den ausgewählten Werten ein zusammengesetztes BookMetadata."""
        def val(attr):
            return self._boxes[attr].currentText().strip()

        authors = [a.strip() for a in val("authors").split(",") if a.strip()]
        idx_text = val("series_index").replace(",", ".")
        try:
            idx = float(idx_text) if idx_text else None
        except ValueError:
            idx = None
        return replace(
            self.original,
            title=val("title") or None,
            authors=authors,
            publisher=val("publisher") or None,
            published=val("published") or None,
            isbn=val("isbn") or None,
            language=val("language") or None,
            series=val("series") or None,
            series_index=idx,
            description=val("description") or None,
        )


class _CropLabel(QLabel):
    """Bild-Label mit aufziehbarem Auswahlrechteck (für den Cover-Zuschnitt)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self._origin = QPoint()
        self.selection = QRect()

    def mousePressEvent(self, event):  # noqa: N802
        self._origin = event.position().toPoint()
        self._rubber.setGeometry(QRect(self._origin, QSize()))
        self._rubber.show()

    def mouseMoveEvent(self, event):  # noqa: N802
        if not self._origin.isNull():
            self._rubber.setGeometry(QRect(self._origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):  # noqa: N802
        self.selection = self._rubber.geometry()


class CropDialog(QDialog):
    """Interaktiver Cover-Zuschnitt: Rechteck aufziehen, dann zuschneiden."""

    def __init__(self, cover: bytes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cover zuschneiden")
        self.cover = cover
        self.result_cover: bytes | None = None
        self.result_mime: str | None = None

        self._pix = QPixmap()
        self._pix.loadFromData(cover)
        self._display = self._pix.scaled(
            360, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        self.image = _CropLabel()
        self.image.setPixmap(self._display)
        self.image.setFixedSize(self._display.size())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._crop)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("Auswahlrechteck aufziehen und mit OK bestätigen.")
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)
        layout.addWidget(self.image, alignment=Qt.AlignCenter)
        layout.addWidget(buttons)

    def _crop(self) -> None:
        sel = self.image.selection
        if sel.width() < 5 or sel.height() < 5:
            self.reject()
            return
        # Anzeige-Koordinaten auf Originalbild hochrechnen.
        sx = self._pix.width() / self._display.width()
        sy = self._pix.height() / self._display.height()
        box = (
            max(0, int(sel.left() * sx)),
            max(0, int(sel.top() * sy)),
            min(self._pix.width(), int(sel.right() * sx)),
            min(self._pix.height(), int(sel.bottom() * sy)),
        )
        try:
            from .. import covers

            self.result_cover, self.result_mime = covers.crop(self.cover, box)
        except Exception as exc:
            QMessageBox.warning(self, "Zuschneiden", str(exc))
            return
        self.accept()


def _load_settings():
    from ..config import Settings

    return Settings()


def _record_library(path: str) -> None:
    """Geschriebenes Buch in der Bibliothek vermerken (Fehler ignorieren)."""
    try:
        from ..library import STATUS_WRITTEN, Library
        from ..readers import read_metadata

        meta = read_metadata(path)
        with Library() as lib:
            lib.upsert(meta, status=STATUS_WRITTEN)
    except Exception:
        pass


class SettingsDialog(QDialog):
    """Dialog zum Bearbeiten von Kindle-Adresse und SMTP-Zugang."""

    # (Einstellungs-Schlüssel, Anzeigelabel, Passwort?)
    FIELDS = [
        ("kindle_addr", "Kindle-Adresse (…@kindle.com)", False),
        ("smtp_host", "SMTP-Host", False),
        ("smtp_port", "SMTP-Port (587/465)", False),
        ("smtp_user", "SMTP-Benutzer", False),
        ("smtp_pass", "SMTP-Passwort", True),
        ("smtp_from", "Absender (optional)", False),
        ("protected_fields", "Geschützte Felder (z. B. cover,title)", False),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.settings = _load_settings()

        form = QFormLayout()
        self.inputs: dict[str, QLineEdit] = {}
        for key, label, is_secret in self.FIELDS:
            edit = QLineEdit(self.settings.get(key, "") or "")
            if is_secret:
                edit.setEchoMode(QLineEdit.Password)
            self.inputs[key] = edit
            form.addRow(label, edit)

        note = QLabel(
            "Geheimnisse werden im System-Schlüsselbund gespeichert, falls "
            "'keyring' installiert ist – sonst in der Konfigdatei.\n"
            "Die Absenderadresse muss bei Amazon als genehmigt hinterlegt sein."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _save(self) -> None:
        for key, _label, _secret in self.FIELDS:
            value = self.inputs[key].text().strip()
            self.settings.set(key, value or None)
        self.accept()


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
