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
- [ ] Weitere Formate: **CBZ/CBR** (Comics, ComicInfo.xml), optional DjVu.
- [ ] `langRestrict`/Sprachfilter in der Online-Suche nutzen.

## Meilenstein C — GUI-Komfort (teilweise umgesetzt)
Ziel: schnelleres, angenehmeres Arbeiten.

- [x] **Bibliotheks-Ansicht** als Cover-Grid mit Such-/Filterfeld (eigener Tab,
      Thumbnails aus der SQLite-Bibliothek, Doppelklick öffnet im Editor).
- [x] **Inline-Cover-Editor**: Drehen (↺/↻) direkt im Editor; Zuschnitt-Helfer
      (`covers.crop`) vorhanden.
- [x] **Einstellungen-Dialog** (SMTP, Kindle-Adresse, Absender) – Werte aus
      `config.Settings`, Send-to-Kindle nutzt sie automatisch.
- [ ] **Vorschläge vergleichen**: mehrere Treffer nebeneinander, Felder einzeln
      übernehmen (nicht nur „ganzer Vorschlag").
- [ ] **Interaktiver Cover-Zuschnitt** (Auswahlrechteck) statt nur Funktion.
- [ ] **Mehrfachauswahl** in der Liste + Sammelaktionen (löschen, senden).

## Meilenstein D — Automatisierung & Verteilung
Ziel: weniger Handarbeit, einfache Installation.

- [ ] **Watch-Ordner**: neue Downloads automatisch einlesen und anreichern.
- [ ] **Anreicherungs-Profile**: konfigurieren, welche Felder überschrieben
      werden dürfen (z. B. „Cover nie überschreiben").
- [ ] **Packaging** mit PyInstaller → Ein-Klick-Apps für Windows/macOS/Linux
      ohne separate Python-Installation.
- [ ] **CI (GitHub Actions)**: Tests + Lint (ruff) bei jedem Push/PR.

---

## Empfohlener nächster Schritt

Meilenstein A ist abgeschlossen; die Kerne von B (Spracherkennung, DNB,
Fuzzy-Ranking, FB2) und C (Bibliotheks-Grid, Einstellungen, Cover-Drehen)
ebenfalls. Als Nächstes bietet sich **Meilenstein D** an – zuerst **CI mit
GitHub Actions** (Tests bei jedem Push absichern) und **Packaging** mit
PyInstaller (Ein-Klick-App ohne Python). Alternativ die restlichen
Komfort-Punkte aus C (Vorschläge feldweise übernehmen, Mehrfachauswahl).
