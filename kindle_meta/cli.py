"""Kommandozeilen-Interface – nützlich zum Testen der Kern-Logik ohne GUI.

Beispiele:
    python -m kindle_meta.cli info buch.epub
    python -m kindle_meta.cli enrich buch.pdf
    python -m kindle_meta.cli apply buch.epub --title "..." --author "..."
"""

from __future__ import annotations

import argparse
import sys

from .enrich import enrich_file
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
    out = write_metadata(meta, args.out)
    print(f"Geschrieben: {out}")
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
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
