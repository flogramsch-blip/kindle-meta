# Update-Pläne für kindle-meta

Stand: Aufbauend auf dem aktuellen Funktionsumfang – EPUB/PDF nativ,
MOBI/AZW3 via Calibre, Anreicherung (Google Books + Open Library + KI),
Cover-Auswahl & -Optimierung, Stapelverarbeitung mit Fortschritt/Abbruch,
Send-to-Kindle, CLI + PySide6-GUI, 27 Tests.

Die Ausbaustufen sind nach Nutzen/Aufwand in Meilensteine gruppiert. Jede
Aufgabe ist einzeln umsetzbar; Reihenfolge innerhalb eines Meilensteins ist
flexibel.

---

## Meilenstein A — Robustheit & Datenhaltung
Ziel: verlässlicher Alltagsbetrieb, nichts geht verloren.

- [ ] **Automatisches Backup** der Originaldatei vor jedem Schreibvorgang
      (`.bak` oder Papierkorb-Ordner) + „Rückgängig"-Funktion.
- [ ] **Persistente Bibliothek (SQLite)**: importierte Bücher, letzter Status,
      gewählte Vorschläge und die zuletzt genutzte Kindle-Adresse merken.
- [ ] **Einstellungen sicher speichern**: SMTP-Zugang & Kindle-Adresse im
      System-Schlüsselbund (`keyring`) statt nur Umgebungsvariablen.
- [ ] **Serien-Metadaten** (`series`/`series_index`) für Kindle-Sammlungen
      korrekt in EPUB (calibre:series-Meta) und via Calibre schreiben.
- [ ] **Bessere ISBN-Erkennung**: ISBN aus Impressum/Text per Regex + Prüfziffer.

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

**Meilenstein A zuerst** – konkret die Kombination aus **Backup vor dem
Schreiben** und **persistenter Bibliothek (SQLite)**. Beides erhöht die
Alltagstauglichkeit sofort spürbar (nichts geht verloren, Wiederaufnahme
möglich) und schafft die Datenbasis, auf der die GUI-Komfortfeatures aus
Meilenstein C später aufsetzen.
