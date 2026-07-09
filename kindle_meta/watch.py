"""Ordner überwachen und neue E-Books automatisch anreichern.

Einfacher Polling-Ansatz (ohne Zusatz-Abhängigkeit): In festen Abständen wird
der Ordner gescannt; neu aufgetauchte Dateien werden gemeldet. Die Scan-Logik
ist von der Endlosschleife getrennt und dadurch gut testbar.
"""

from __future__ import annotations

import os
import time
from typing import Callable, Iterable, Optional

# Von der App unterstützte Endungen.
SUPPORTED_EXTS = (".epub", ".pdf", ".fb2", ".mobi", ".azw3", ".azw")


class FolderWatcher:
    def __init__(self, folder: str, *, extensions: Iterable[str] = SUPPORTED_EXTS):
        self.folder = folder
        self.extensions = tuple(e.lower() for e in extensions)
        self._seen: set[str] = set()

    def _current_files(self) -> set[str]:
        if not os.path.isdir(self.folder):
            return set()
        out = set()
        for name in os.listdir(self.folder):
            if name.lower().endswith(self.extensions):
                out.add(os.path.join(self.folder, name))
        return out

    def prime(self) -> None:
        """Merkt sich die aktuell vorhandenen Dateien, ohne sie zu melden.

        So werden beim Start nur *neue* Dateien verarbeitet, nicht der Bestand.
        """
        self._seen = self._current_files()

    def scan(self) -> list[str]:
        """Gibt seit dem letzten Scan neu hinzugekommene Dateien zurück."""
        current = self._current_files()
        new = current - self._seen
        self._seen = current
        return sorted(new)

    def run(
        self,
        callback: Callable[[str], None],
        *,
        interval: float = 5.0,
        iterations: Optional[int] = None,
        process_existing: bool = False,
    ) -> None:
        """Überwacht den Ordner und ruft ``callback(pfad)`` für neue Dateien.

        ``iterations`` begrenzt die Zahl der Durchläufe (für Tests/Skripte);
        ``None`` läuft endlos. ``process_existing=False`` ignoriert den
        Anfangsbestand.
        """
        if not process_existing:
            self.prime()
        count = 0
        while iterations is None or count < iterations:
            for path in self.scan():
                callback(path)
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval)
