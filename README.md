# kindle-meta

Eine Desktop-App, um aus dem Internet geladene **E-Books (EPUB/PDF)** einzulesen,
ihre Metadaten anzureichern und **Kindle-tauglich zurückzuschreiben** – mit
richtigem Cover, Autor, Verlag, Erscheinungsdatum und ISBN. So werden Bücher auf
einem **Kindle Paperwhite** sauber mit Cover und korrekten Angaben angezeigt.

## Warum das nötig ist

Ein Kindle zeigt Cover und Metadaten nur zuverlässig an, wenn sie **in der Datei
eingebettet** sind – die Datei umzubenennen reicht nicht. `kindle-meta` schreibt
die Metadaten direkt in die Datei (EPUB: OPF/DC + Cover-Item, PDF: Info-Dictionary).

## Funktionen

- **Lesen**: EPUB & PDF nativ, **MOBI/AZW3/AZW** via Calibre – vorhandene
  Metadaten + Textprobe der ersten Seiten.
- **Anreichern** aus drei Quellen:
  1. **Online-Datenbanken** – Google Books & Open Library (Cover, Verlag, Datum, ISBN, Seiten).
  2. **KI-Fallback** – Claude erkennt Titel/Autor aus dem Text, wenn Metadaten fehlen.
  3. **Manuell** – jeder Vorschlag ist editierbar und wird vor dem Schreiben bestätigt.
- **Cover-Auswahl**: Aus mehreren Treffern das beste Cover per Klick wählen.
- **Stapelverarbeitung**: Ganze Ordner in einem Durchgang anreichern (`batch`).
- **Schreiben**: Metadaten + Cover eingebettet zurück in die Datei.
- **Konvertierung** nach AZW3/MOBI via Calibre (für ältere Kindles).

## Installation

```bash
# Kern + GUI
pip install -e ".[gui]"

# optional: KI-Fallback (Claude)
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=sk-...
```

Für die Konvertierung nach AZW3/MOBI zusätzlich [Calibre](https://calibre-ebook.com/)
installieren (liefert `ebook-convert`). Für die GUI wird `PySide6` benötigt.

## Nutzung

### Grafische Oberfläche

```bash
kindle-meta-gui
```

1. Bücher per Button oder **Drag & Drop** hinzufügen.
2. Buch auswählen → vorhandene Metadaten + Cover erscheinen.
3. **„Online suchen / anreichern"** → Vorschläge wählen (oder Felder manuell füllen).
4. **„Speichern"** → Metadaten werden in die Datei geschrieben.

### Kommandozeile

```bash
kindle-meta info    buch.epub               # vorhandene Metadaten anzeigen
kindle-meta enrich  buch.pdf                # Online-/KI-Vorschläge anzeigen
kindle-meta apply   buch.epub \
    --title "Der Steppenwolf" \
    --author "Hermann Hesse" \
    --publisher "Suhrkamp" --date 1927 \
    --out fertig.epub                       # schreiben (Original bleibt erhalten)

# Stapelverarbeitung: erst Trockenlauf, dann schreiben
kindle-meta batch *.epub                    # nur Vorschläge anzeigen
kindle-meta batch *.epub --apply --out-dir fertig/   # besten Vorschlag schreiben

# Kindle-Eigenformate (erfordert Calibre)
kindle-meta info    buch.azw3
kindle-meta convert fertig.epub --to azw3   # für ältere Kindles
```

## Auf den Kindle bringen

Moderne Paperwhites nehmen **EPUB** direkt an (Send-to-Kindle per E-Mail, App
oder USB). Für ältere Geräte nach AZW3 konvertieren:

```python
from kindle_meta.writers import convert_with_calibre
convert_with_calibre("fertig.epub", "azw3")   # erfordert Calibre
```

## Architektur

| Modul | Aufgabe |
|-------|---------|
| `kindle_meta/models.py`   | `BookMetadata` – zentrales Datenmodell + Merge-Logik |
| `kindle_meta/readers.py`  | EPUB/PDF einlesen (Metadaten + Textprobe) |
| `kindle_meta/calibre.py`  | MOBI/AZW3 lesen/schreiben & Konvertierung via Calibre |
| `kindle_meta/providers.py`| Google Books & Open Library abfragen |
| `kindle_meta/llm.py`      | Claude-Fallback für Titel/Autor aus Text |
| `kindle_meta/enrich.py`   | Orchestrierung: lesen → anreichern → Vorschläge, Stapellauf |
| `kindle_meta/writers.py`  | Metadaten + Cover zurückschreiben |
| `kindle_meta/gui/app.py`  | PySide6-Desktop-Oberfläche mit Cover-Auswahl |
| `kindle_meta/cli.py`      | Kommandozeile (info/enrich/apply/batch/convert) |

Die **Kern-Logik ist von der GUI getrennt** und über `tests/` abgedeckt.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- Cover-Zuschnitt/Optimierung für die Kindle-Anzeige.
- Fortschrittsanzeige & Abbrechen im Stapellauf (GUI).
- Direkter Send-to-Kindle-Versand per E-Mail aus der App.

## Lizenz

MIT
