"""Sicherungskopien vor dem Überschreiben von Dateien.

Vor jedem In-Place-Schreibvorgang kann eine Kopie der Originaldatei angelegt
werden. So lässt sich ein ungewolltes Ergebnis rückgängig machen. Backups
liegen unter ``<app_home>/backups`` mit Zeitstempel im Namen.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import backups_dir


def _backup_name(path: str, when: Optional[datetime] = None) -> str:
    when = when or datetime.now()
    stamp = when.strftime("%Y%m%d-%H%M%S-%f")
    return f"{stamp}__{os.path.basename(path)}"


def create_backup(path: str, backup_dir: Optional[str] = None) -> str:
    """Legt eine Sicherungskopie von ``path`` an und gibt den Backup-Pfad zurück."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    dest_dir = Path(backup_dir) if backup_dir else backups_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _backup_name(path)
    shutil.copy2(path, dest)
    return str(dest)


def list_backups(path: str, backup_dir: Optional[str] = None) -> list[str]:
    """Alle Backups zu einer Datei, neuestes zuerst (Zuordnung über Dateinamen)."""
    dest_dir = Path(backup_dir) if backup_dir else backups_dir()
    if not dest_dir.exists():
        return []
    base = os.path.basename(path)
    hits = [str(p) for p in dest_dir.iterdir() if p.name.endswith(f"__{base}")]
    # Dateinamen beginnen mit sortierbarem Zeitstempel -> umgekehrt = neueste zuerst.
    return sorted(hits, reverse=True)


def restore_latest(path: str, backup_dir: Optional[str] = None) -> str:
    """Stellt das neueste Backup einer Datei wieder her. Gibt ``path`` zurück."""
    backups = list_backups(path, backup_dir)
    if not backups:
        raise FileNotFoundError(f"Kein Backup für {os.path.basename(path)} gefunden.")
    shutil.copy2(backups[0], path)
    return path
