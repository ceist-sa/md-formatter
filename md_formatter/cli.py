"""md2pdf — turn a Notion Markdown export into a branded PDF."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_ORG = "Camerata de Estudantes do Instituto Superior Técnico"
_REEXEC_FLAG = "MD_FORMATTER_REEXEC"


def _ensure_homebrew_fontconfig() -> None:
    """On macOS, a stale libfontconfig in /usr/local/lib can shadow Homebrew's copy and
    break WeasyPrint. DYLD_LIBRARY_PATH must be set before the process starts, so re-exec."""
    if sys.platform != "darwin" or os.environ.get(_REEXEC_FLAG):
        return
    for prefix in ("/opt/homebrew", "/usr/local"):
        libdir = Path(prefix) / "opt" / "fontconfig" / "lib"
        if libdir.is_dir():
            env = dict(os.environ, **{_REEXEC_FLAG: "1"})
            env["DYLD_LIBRARY_PATH"] = os.pathsep.join(
                p for p in (str(libdir), env.get("DYLD_LIBRARY_PATH")) if p
            )
            os.execve(sys.executable, [sys.executable, "-m", "md_formatter", *sys.argv[1:]], env)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        _ensure_homebrew_fontconfig()

    parser = argparse.ArgumentParser(
        prog="md2pdf", description="Convert a Notion Markdown export into a formatted PDF."
    )
    parser.add_argument("input", type=Path, help="Markdown file exported from Notion")
    parser.add_argument("-o", "--output", type=Path, help="output PDF (default: next to the input, Notion id removed)")
    parser.add_argument("--org", default=DEFAULT_ORG, help="organization name shown in the footer")
    parser.add_argument("--date", help="date or subtitle shown under the title")
    parser.add_argument("--lang", default="pt", help="document language, used for hyphenation (default: pt)")
    parser.add_argument(
        "--sign",
        metavar='"NAME, ROLE"',
        nargs="?",
        const="",
        action="append",
        default=[],
        help='add a signature line at the end; repeat for more. Name and role are optional: '
        '"Ana Silva, Presidente", "Ana Silva", ", Tesoureiro", or no value for a blank line',
    )
    parser.add_argument("--place", help='place for the line above the signatures, e.g. "Lisboa"')
    parser.add_argument(
        "--sign-date",
        metavar="DATE",
        nargs="?",
        const="",
        help='date for the line above the signatures: "hoje", YYYY-MM-DD, or any text. '
        "With no value (or with only --place), blanks are left to fill in by hand",
    )
    parser.add_argument("--html", action="store_true", help="also write the intermediate HTML (for debugging)")
    args = parser.parse_args(argv)

    from . import render

    src: Path = args.input
    if not src.is_file():
        parser.error(f"file not found: {src}")

    out: Path = args.output or src.with_name(render.clean_title_from_filename(src).replace("/", "-") + ".pdf")

    doc = render.parse(src)
    html_str = render.build_html(
        doc,
        organization=args.org,
        lang=args.lang,
        date=args.date,
        signatures=[render.parse_signature(s) for s in args.sign],
        place=args.place,
        sign_date=render.format_sign_date(args.sign_date) if args.sign_date else args.sign_date,
    )
    if args.html:
        out.with_suffix(".html").write_text(html_str, encoding="utf-8")
    render.render_pdf(html_str, out, base_url=src.resolve())
    print(out)
    return 0
