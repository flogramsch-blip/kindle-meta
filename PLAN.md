# Update-Pläne für kindle-meta

Stand: Aufbauend auf dem aktuellen Funktionsumfang – EPUB/PDF nativ,
MOBI/AZW3 via Calibre, Anreicherung (Google Books + Open Library + KI),
Cover-Auswahl & -Optimierung, Stapelverarbeitung mit Fortschritt/Abbruch,
Send-to-Kindle, CLI + PySide6-GUI, 27 Tests.

Die Ausbaustufen sind nach Nutzen/Aufwand in Meilensteine gruppiert. Jede
Aufgabe ist einzeln umsetzbar; Reihenfolge innerhalb eines Meilensteins ist
flexibel.

---

## Meilenstein A — Robustheit & Datenhaltung ✅ (umgesetzt)
Ziel: verlässlicher Alltagsbetrieb, nichts geht verloren.

- [x] **Automatisches Backup** der Originaldatei vor dem In-Place-Schreiben
      (`backup.py`) + „Rückgängig"-Funktion (`kindle-meta undo`).
- [x] **Persistente Bibliothek (SQLite)** (`library.py`): bearbeitete Bücher +
      Status; Anzeige über `kindle-meta library`.
- [x] **Einstellungen speichern** (`config.py`): Schlüsselbund via `keyring`,
      sonst Datei-Fallback; App-Home unter `~/.kindle-meta`.
- [x] **Serien-Metadaten** (`series`/`series_index`) in EPUB (calibre:series)
      und via Calibre (`--series`/`--index`); GUI-Felder ergänzt.
- [x] **Bessere ISBN-Erkennung** (`isbn.py`): ISBN aus Text per Regex +
      Prüfziffer; wird beim Anreichern automatisch genutzt.

## Meilenstein B — Mehr Formate & Quellen (teilweise umgesetzt)
Ziel: mehr Bücher abdecken, bessere Treffer.

- [x] Format **FB2** (FictionBook) lesen inkl. Cover (`readers._read_fb2`).
- [x] Zusätzliche Metadatenquelle **Deutsche Nationalbibliothek (DNB/SRU)**
      (`providers.search_dnb`), mit ISBN-Validierung und Rollen-Bereinigung.
- [x] **Spracherkennung** (`lang.py`, stoppwortbasiert, ohne Abhängigkeit) →
      setzt `language` automatisch beim Anreichern.
- [x] **Trefferbewertung** (`matching.py`): Vorschläge nach Ähnlichkeit
      (Titel/Autor/ISBN) sortiert, bester zuerst.
- [x] Weitere Formate: **CBZ/CBR** (Comics) lesen inkl. ComicInfo.xml + Cover
      (CBR benötigt optionales `rarfile`).
- [x] **Sprachfilter** in der Online-Suche (Google Books `langRestrict`).
- [ ] Optional: DjVu-Format.

## Meilenstein C — GUI-Komfort (teilweise umgesetzt)
Ziel: schnelleres, angenehmeres Arbeiten.

- [x] **Bibliotheks-Ansicht** als Cover-Grid mit Such-/Filterfeld (eigener Tab,
      Thumbnails aus der SQLite-Bibliothek, Doppelklick öffnet im Editor).
- [x] **Inline-Cover-Editor**: Drehen (↺/↻) direkt im Editor; Zuschnitt-Helfer
      (`covers.crop`) vorhanden.
- [x] **Einstellungen-Dialog** (SMTP, Kindle-Adresse, Absender) – Werte aus
      `config.Settings`, Send-to-Kindle nutzt sie automatisch.
- [x] **Vorschläge vergleichen** (`CompareDialog`): Felder aus mehreren Treffern
      frei kombinieren.
- [x] **Interaktiver Cover-Zuschnitt** (`CropDialog` mit Auswahlrechteck).
- [x] **Mehrfachauswahl** in der Liste + Sammelaktionen (entfernen, senden).

## Meilenstein D — Automatisierung & Verteilung ✅ (umgesetzt)
Ziel: weniger Handarbeit, einfache Installation.

- [x] **Watch-Ordner** (`watch.py`): neue Dateien automatisch einlesen und
      anreichern; CLI `kindle-meta watch`.
- [x] **Anreicherungs-Profile** (`profile.py`): geschützte Felder, die beim
      Anreichern nicht überschrieben werden; CLI `--protect`, GUI-Einstellung.
- [x] **Packaging** mit PyInstaller (`packaging/kindle-meta.spec`) → Ein-Datei-App.
- [x] **CI (GitHub Actions)**: Lint (ruff) + Tests auf Python 3.10–3.12.

---

## Status

Meilensteine **A, B, C und D** sind umgesetzt. Zusätzlich abgeschlossen:
Coverage-Messung (`pytest --cov`, in der CI aktiv) und ein Calibre-
Integrationstest, der sich ohne installiertes Calibre überspringt.

## Verbleibende Ideen (optional)

- **DjVu**-Format lesen.
- Comic-Metadaten (ComicInfo.xml) auch **schreiben** (aktuell nur lesen).
- Automatische **Sammlungen** auf dem Kindle über Serien-Metadaten prüfen/optimieren.
- Übersetzungen der Oberfläche (i18n), aktuell Deutsch.
- Optionales **Cloud-Backup** der Bibliothek/Einstellungen.
