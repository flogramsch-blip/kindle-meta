"""Zentrale Pfade und Einstellungen der App.

Alles landet unter einem App-Verzeichnis (Standard ``~/.kindle-meta``,
überschreibbar per Umgebungsvariable ``KINDLE_META_HOME``): Bibliothek-DB,
Backups und Einstellungen.

Geheimnisse (SMTP-Passwort) werden – falls ``keyring`` installiert ist – im
System-Schlüsselbund gespeichert, sonst als Fallback in der Konfigdatei
(mit Warnung, da dann im Klartext).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

APP_NAME = "kindle-meta"
_KEYRING_SERVICE = "kindle-meta"
_SECRET_KEYS = {"smtp_pass"}


def app_home() -> Path:
    """App-Basisverzeichnis; wird bei Bedarf angelegt."""
    home = os.environ.get("KINDLE_META_HOME")
    base = Path(home) if home else Path.home() / ".kindle-meta"
    base.mkdir(parents=True, exist_ok=True)
    return base


def backups_dir() -> Path:
    d = app_home() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def library_path() -> Path:
    return app_home() / "library.db"


def _settings_file() -> Path:
    return app_home() / "settings.json"


class Settings:
    """Einfacher Schlüssel/Wert-Speicher für Einstellungen.

    Nicht-geheime Werte liegen in ``settings.json``. Geheime Werte
    (``_SECRET_KEYS``) werden im Schlüsselbund abgelegt, wenn ``keyring``
    verfügbar ist – andernfalls ebenfalls in der Datei (Klartext-Fallback).
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        path = _settings_file()
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        _settings_file().write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # -- öffentliche API ---------------------------------------------------- #
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if key in _SECRET_KEYS:
            secret = _keyring_get(key)
            if secret is not None:
                return secret
        return self._data.get(key, default)

    def set(self, key: str, value: Optional[str]) -> None:
        if key in _SECRET_KEYS and _keyring_set(key, value):
            # Erfolgreich im Schlüsselbund – nicht zusätzlich in Datei speichern.
            self._data.pop(key, None)
            self._save()
            return
        if value is None:
            self._data.pop(key, None)
        else:
            self._data[key] = value
        self._save()

    def as_dict(self) -> dict[str, Any]:
        """Nicht-geheime Einstellungen (für Anzeige/Debug)."""
        return {k: v for k, v in self._data.items() if k not in _SECRET_KEYS}


def keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
    except ImportError:
        return False
    return True


def _keyring_get(key: str) -> Optional[str]:
    if not keyring_available():
        return None
    import keyring

    try:
        return keyring.get_password(_KEYRING_SERVICE, key)
    except Exception:
        return None


def _keyring_set(key: str, value: Optional[str]) -> bool:
    if not keyring_available():
        return False
    import keyring

    try:
        if value is None:
            keyring.delete_password(_KEYRING_SERVICE, key)
        else:
            keyring.set_password(_KEYRING_SERVICE, key, value)
        return True
    except Exception:
        return False
