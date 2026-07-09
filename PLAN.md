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

## Meilenstein B — Mehr Formate & Quellen
Ziel: mehr Bücher abdecken, bessere Treffer.

- [ ] Weitere Formate: **FB2**, **CBZ/CBR** (Comics), optional DjVu.
- [ ] Zusätzliche Metadatenquelle **Deutsche Nationalbibliothek (DNB/SRU)** –
      besonders gut für deutschsprachige Titel.
- [ ] **Spracherkennung** (`langdetect`) auf der Textprobe → gezieltere Suche
      und automatisches Setzen von `language`.
- [ ] **Trefferbewertung**: Vorschläge nach Ähnlichkeit zu Datei-Metadaten
      sortieren (Titel/Autor-Fuzzy-Score) statt nur Provider-Reihenfolge.

## Meilenstein C — GUI-Komfort
Ziel: schnelleres, angenehmeres Arbeiten.

- [ ] **Bibliotheks-Ansicht** als Cover-Grid mit Filter/Suche statt reiner Liste.
- [ ] **Vorschläge vergleichen**: mehrere Treffer nebeneinander, Felder einzeln
      übernehmen (nicht nur „ganzer Vorschlag").
- [ ] **Inline-Cover-Editor**: zuschneiden/drehen vor dem Einbetten.
- [ ] **Einstellungen-Dialog** (SMTP, Kindle-Adresse, Standard-Zielordner,
      Anreicherungs-Optionen) – ersetzt manuelle Umgebungsvariablen.
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

Meilenstein A ist abgeschlossen. Als Nächstes bietet sich **Meilenstein C**
an – konkret die **Bibliotheks-Ansicht als Cover-Grid** und der
**Einstellungen-Dialog** (SMTP/Kindle-Adresse), da die Datenbasis (SQLite +
`config.Settings`) dafür bereits steht. Alternativ **Meilenstein B**
(Spracherkennung + Trefferbewertung) für spürbar bessere Anreicherungs-Treffer.
