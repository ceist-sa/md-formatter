"""md2pdf — turn a Notion Markdown export into a branded PDF."""

from __future__ import annotations

import argparse
from pathlib import Path

from .common import add_document_options, ensure_homebrew_fontconfig, safe_filename, write_pdf


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        ensure_homebrew_fontconfig("md_formatter")

    parser = argparse.ArgumentParser(
        prog="md2pdf", description="Convert a Notion Markdown export into a formatted PDF."
    )
    parser.add_argument("input", type=Path, help="Markdown file exported from Notion")
    parser.add_argument("-o", "--output", type=Path, help="output PDF (default: next to the input, Notion id removed)")
    add_document_options(parser)
    args = parser.parse_args(argv)

    from . import render

    src: Path = args.input
    if not src.is_file():
        parser.error(f"file not found: {src}")

    out: Path = args.output or src.with_name(safe_filename(render.clean_title_from_filename(src)) + ".pdf")
    write_pdf(render.parse(src), args, out, base_url=src.resolve())
    print(out)
    return 0
