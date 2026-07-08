"""Kommandozeilen-Interface – nützlich zum Testen der Kern-Logik ohne GUI.

Beispiele:
    python -m kindle_meta.cli info buch.epub
    python -m kindle_meta.cli enrich buch.pdf
    python -m kindle_meta.cli apply buch.epub --title "..." --author "..."
"""

from __future__ import annotations

import argparse
import sys

from .enrich import enrich_batch, enrich_file
from .models import BookMetadata
from .readers import read_metadata
from .writers import write_metadata


def _print_meta(meta: BookMetadata, prefix: str = "") -> None:
    print(f"{prefix}Titel:      {meta.title or '-'}")
    print(f"{prefix}Autor(en):  {meta.author_str or '-'}")
    print(f"{prefix}Verlag:     {meta.publisher or '-'}")
    print(f"{prefix}Datum:      {meta.published or '-'}")
    print(f"{prefix}ISBN:       {meta.isbn or '-'}")
    print(f"{prefix}Sprache:    {meta.language or '-'}")
    print(f"{prefix}Seiten:     {meta.page_count or '-'}")
    print(f"{prefix}Cover:      {'ja' if meta.has_cover() else 'nein'}")


def cmd_info(args) -> int:
    meta = read_metadata(args.path)
    _print_meta(meta)
    return 0


def cmd_enrich(args) -> int:
    result = enrich_file(args.path, use_llm=not args.no_llm)
    print("== Aus Datei ==")
    _print_meta(result.original)
    if result.used_llm:
        print("\n(KI wurde zum Ergänzen von Titel/Autor genutzt)")
    print(f"\n== {len(result.suggestions)} Vorschlag/Vorschläge ==")
    for i, sug in enumerate(result.suggestions):
        print(f"\n[{i}]")
        _print_meta(sug, prefix="  ")
    return 0


def cmd_apply(args) -> int:
    meta = read_metadata(args.path)
    if args.title:
        meta.title = args.title
    if args.author:
        meta.authors = [a.strip() for a in args.author.split(",")]
    if args.publisher:
        meta.publisher = args.publisher
    if args.date:
        meta.published = args.date
    if args.isbn:
        meta.isbn = args.isbn
    out = write_metadata(meta, args.out, optimize_cover=args.optimize_cover)
    print(f"Geschrieben: {out}")
    return 0


def cmd_batch(args) -> int:
    def progress(i, total, path, outcome):
        mark = "✓" if outcome.ok else "✗"
        print(f"  [{i + 1}/{total}] {mark} {path.rsplit('/', 1)[-1]}")

    outcomes = enrich_batch(
        args.paths,
        apply=args.apply,
        out_dir=args.out_dir,
        use_llm=not args.no_llm,
        optimize_cover=args.optimize_cover,
        progress=progress,
    )
    written = 0
    for oc in outcomes:
        name = oc.path.rsplit("/", 1)[-1]
        if not oc.ok:
            print(f"✗ {name}: {oc.error}")
            continue
        best = oc.result.best
        line = f"• {name}: {best.title or '?'} — {best.author_str or '?'}"
        if best.published:
            line += f" ({best.published})"
        if oc.written_to:
            line += f"  → geschrieben: {oc.written_to}"
            written += 1
        elif args.apply:
            line += "  (kein Vorschlag – übersprungen)"
        print(line)
    if args.apply:
        print(f"\n{written}/{len(outcomes)} Datei(en) geschrieben.")
    else:
        print(f"\nTrockenlauf – mit --apply schreiben. {len(outcomes)} Datei(en) geprüft.")
    return 0


def cmd_convert(args) -> int:
    from . import calibre

    out = calibre.convert(args.path, args.to)
    print(f"Konvertiert: {out}")
    return 0


def cmd_send(args) -> int:
    from .sendmail import send_to_kindle

    send_to_kindle(args.path, args.to)
    print(f"An Kindle gesendet: {args.to}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kindle-meta", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="Metadaten einer Datei anzeigen")
    p_info.add_argument("path")
    p_info.set_defaults(func=cmd_info)

    p_enrich = sub.add_parser("enrich", help="Online/KI-Vorschläge anzeigen")
    p_enrich.add_argument("path")
    p_enrich.add_argument("--no-llm", action="store_true", help="KI-Fallback deaktivieren")
    p_enrich.set_defaults(func=cmd_enrich)

    p_apply = sub.add_parser("apply", help="Metadaten in Datei schreiben")
    p_apply.add_argument("path")
    p_apply.add_argument("--out", help="Ausgabedatei (sonst wird Original überschrieben)")
    p_apply.add_argument("--title")
    p_apply.add_argument("--author", help="mehrere durch Komma trennen")
    p_apply.add_argument("--publisher")
    p_apply.add_argument("--date")
    p_apply.add_argument("--isbn")
    p_apply.add_argument(
        "--optimize-cover", action="store_true", help="Cover für Kindle skalieren/komprimieren"
    )
    p_apply.set_defaults(func=cmd_apply)

    p_batch = sub.add_parser("batch", help="Mehrere Dateien anreichern (Trockenlauf oder --apply)")
    p_batch.add_argument("paths", nargs="+", help="mehrere Dateien")
    p_batch.add_argument("--apply", action="store_true", help="besten Vorschlag schreiben")
    p_batch.add_argument("--out-dir", help="Zielordner (sonst Originale überschreiben)")
    p_batch.add_argument("--no-llm", action="store_true", help="KI-Fallback deaktivieren")
    p_batch.add_argument(
        "--optimize-cover", action="store_true", help="Cover für Kindle skalieren/komprimieren"
    )
    p_batch.set_defaults(func=cmd_batch)

    p_convert = sub.add_parser("convert", help="Format via Calibre konvertieren (z. B. nach azw3)")
    p_convert.add_argument("path")
    p_convert.add_argument("--to", default="azw3", help="Zielformat: azw3/mobi/epub (Standard: azw3)")
    p_convert.set_defaults(func=cmd_convert)

    p_send = sub.add_parser("send", help="Datei per Send-to-Kindle an @kindle.com-Adresse mailen")
    p_send.add_argument("path")
    p_send.add_argument("--to", required=True, help="Kindle-Adresse, z. B. name@kindle.com")
    p_send.set_defaults(func=cmd_send)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # bekannte App-Fehler sauber melden
        # kindle-meta-eigene Ausnahmen tragen sprechende Meldungen.
        if exc.__class__.__module__.startswith("kindle_meta"):
            print(f"Fehler: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
