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

import sys
import traceback
from dataclasses import replace

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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

    def __init__(self, paths, *, out_dir, use_llm, optimize_cover):
        super().__init__()
        self.paths = paths
        self.out_dir = out_dir
        self.use_llm = use_llm
        self.optimize_cover = optimize_cover
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
        central = QWidget()
        root = QHBoxLayout(central)

        # Linke Spalte: Dateiliste
        left = QVBoxLayout()
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self._on_select_file)
        add_btn = QPushButton("Dateien hinzufügen …")
        add_btn.clicked.connect(self._add_files_dialog)
        left.addWidget(QLabel("Bücher (Drag & Drop möglich)"))
        left.addWidget(self.file_list, 1)
        left.addWidget(add_btn)

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

        cover_box = QVBoxLayout()
        cover_box.addWidget(self.cover_label)
        cover_box.addWidget(cover_btn)

        form = QFormLayout()
        self.f_title = QLineEdit()
        self.f_author = QLineEdit()
        self.f_publisher = QLineEdit()
        self.f_date = QLineEdit()
        self.f_isbn = QLineEdit()
        self.f_language = QLineEdit()
        self.f_desc = QTextEdit()
        self.f_desc.setMaximumHeight(90)
        form.addRow("Titel", self.f_title)
        form.addRow("Autor(en)", self.f_author)
        form.addRow("Verlag", self.f_publisher)
        form.addRow("Datum", self.f_date)
        form.addRow("ISBN", self.f_isbn)
        form.addRow("Sprache", self.f_language)
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
        self.save_btn = QPushButton("Speichern (in Datei schreiben)")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Vorschläge:"))
        actions.addWidget(self.suggestion_box, 1)
        actions.addWidget(self.search_btn)
        right.addLayout(actions)

        self.optimize_cover_cb = QCheckBox("Cover beim Speichern für Kindle optimieren")
        right.addWidget(self.optimize_cover_cb)

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
        self.setCentralWidget(central)
        self._set_form_enabled(False)

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
        self.f_desc.setPlainText(meta.description or "")
        self._show_cover(meta)

    def _collect_form(self) -> BookMetadata:
        assert self._current_meta is not None
        authors = [a.strip() for a in self.f_author.text().split(",") if a.strip()]
        return replace(
            self._current_meta,
            title=self.f_title.text().strip() or None,
            authors=authors,
            publisher=self.f_publisher.text().strip() or None,
            published=self.f_date.text().strip() or None,
            isbn=self.f_isbn.text().strip() or None,
            language=self.f_language.text().strip() or None,
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
        covers = f", {self.cover_picker.count()} Cover zur Auswahl" if self.cover_picker.count() else ""
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

    # -- Speichern ---------------------------------------------------------- #
    def _save(self) -> None:
        if self._current_meta is None:
            return
        meta = self._collect_form()
        self.status.setText("Schreibe Datei …")
        self.save_btn.setEnabled(False)
        worker = Worker(write_metadata, meta, optimize_cover=self.optimize_cover_cb.isChecked())
        worker.signals.result.connect(self._on_saved)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_saved(self, out_path: str) -> None:
        self.save_btn.setEnabled(True)
        self.status.setText(f"Gespeichert: {out_path}")
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

        worker = BatchWorker(
            paths,
            out_dir=out_dir,
            use_llm=True,
            optimize_cover=self.batch_optimize.isChecked(),
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
        addr, ok = QInputDialog.getText(
            self, "An Kindle senden",
            "Kindle-E-Mail-Adresse (…@kindle.com):", text=self._kindle_addr,
        )
        if not ok or not addr.strip():
            return
        self._kindle_addr = addr.strip()

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
            self.f_isbn, self.f_language, self.f_desc, self.search_btn,
        ):
            w.setEnabled(enabled)


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
