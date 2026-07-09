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
- **Cover-Optimierung**: Cover für die Kindle-Anzeige skalieren/zuschneiden (Pillow).
- **Stapelverarbeitung**: Ganze Ordner in einem Durchgang anreichern – mit
  Fortschrittsanzeige und Abbrechen in der GUI (`batch`).
- **Schreiben**: Metadaten + Cover eingebettet zurück in die Datei.
- **Send-to-Kindle**: fertige Bücher direkt an die `@kindle.com`-Adresse mailen.
- **Serien-Metadaten**: `series`/`series_index` für Kindle-Sammlungen (EPUB & Calibre).
- **Backup & Undo**: automatische Sicherung vor dem Überschreiben, Wiederherstellung per `undo`.
- **Bibliothek (SQLite)**: bearbeitete Bücher + Status bleiben über Sitzungen erhalten.
- **ISBN-Erkennung**: gültige ISBN aus dem Text (Impressum) automatisch ziehen.
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
kindle-meta batch *.epub --apply --out-dir fertig/ --optimize-cover

# Cover optimieren + Serie setzen (Backup automatisch beim In-Place-Schreiben)
kindle-meta apply buch.epub --optimize-cover --series "Die Chroniken" --series-index 2
kindle-meta undo    buch.epub               # letztes Backup wiederherstellen
kindle-meta library                         # bearbeitete Bücher auflisten

# Kindle-Eigenformate (erfordert Calibre)
kindle-meta info    buch.azw3
kindle-meta convert fertig.epub --to azw3   # für ältere Kindles

# Per Send-to-Kindle verschicken (SMTP-Config als Umgebungsvariablen, s. u.)
kindle-meta send fertig.epub --to deingeraet@kindle.com
```

### Send-to-Kindle einrichten

Amazon vergibt pro Gerät eine `@kindle.com`-Adresse. Die **Absenderadresse muss
in den Amazon-Kontoeinstellungen als „genehmigte E-Mail" hinterlegt** sein. Die
SMTP-Zugangsdaten kommen aus Umgebungsvariablen (keine Geheimnisse im Code):

```bash
export KINDLE_SMTP_HOST=smtp.gmail.com
export KINDLE_SMTP_PORT=587          # 587 = STARTTLS, 465 = SSL
export KINDLE_SMTP_USER=ich@gmail.com
export KINDLE_SMTP_PASS=app-passwort # bei Gmail: App-Passwort
export KINDLE_FROM=ich@gmail.com     # optional, Standard = KINDLE_SMTP_USER
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
| `kindle_meta/covers.py`   | Cover für die Kindle-Anzeige optimieren (Pillow) |
| `kindle_meta/sendmail.py` | Send-to-Kindle per SMTP-E-Mail |
| `kindle_meta/isbn.py`     | ISBN aus Text erkennen & validieren |
| `kindle_meta/backup.py`   | Sicherungskopien anlegen/wiederherstellen |
| `kindle_meta/library.py`  | SQLite-Bibliothek: bearbeitete Bücher + Status |
| `kindle_meta/config.py`   | App-Verzeichnis & Einstellungen (keyring optional) |
| `kindle_meta/enrich.py`   | Orchestrierung: lesen → anreichern → Vorschläge, Stapellauf |
| `kindle_meta/writers.py`  | Metadaten + Cover + Serie zurückschreiben |
| `kindle_meta/gui/app.py`  | PySide6-Desktop-Oberfläche (Cover-Auswahl, Stapel, Send) |
| `kindle_meta/cli.py`      | Kommandozeile (info/enrich/apply/batch/convert/send/undo/library) |

Die **Kern-Logik ist von der GUI getrennt** und über `tests/` abgedeckt.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

Siehe [PLAN.md](PLAN.md) für die geplanten nächsten Ausbaustufen.

## Lizenz

MIT
