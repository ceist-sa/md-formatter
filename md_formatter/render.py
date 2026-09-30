"""Convert a Notion-exported Markdown file into a styled HTML document and PDF."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

ASSETS = Path(__file__).parent / "assets"

# Notion appends a 32-char hex id to exported file names.
NOTION_ID = re.compile(r"\s+[0-9a-f]{32}$")
# Notion writes page properties as "Key: value" lines right below the title.
PROPERTY_LINE = re.compile(r"^([^\s:#|>*-][^:]{0,40}):\s+(.+)$")
# Cells that look like amounts, percentages, dates or plain numbers.
NUMERIC_CELL = re.compile(
    r"^[\s(]*[+\-−–]?\s*[€$£]?\s*\d[\d\s.,]*\s*(%|€|\$|£|[A-Z]{3})?[)\s]*(\(.*\))?\s*$"
)
TOTAL_ROW = re.compile(r"^\s*(total|subtotal|saldo final|balance|grand total)\b", re.I)


@dataclass
class Document:
    title: str
    body_html: str
    properties: list[tuple[str, str]] = field(default_factory=list)


def clean_title_from_filename(path: Path) -> str:
    return NOTION_ID.sub("", path.stem).strip()


def _split_title_and_properties(text: str) -> tuple[str | None, list[tuple[str, str]], str]:
    """Pull the leading H1 and any Notion property lines off the top of the document."""
    lines = text.lstrip("﻿").splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not lines[i].startswith("# "):
        return None, [], text

    title = lines[i][2:].strip()
    i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1

    properties = []
    while i < len(lines) and (m := PROPERTY_LINE.match(lines[i].strip())):
        properties.append((m.group(1).strip(), m.group(2).strip()))
        i += 1

    return title, properties, "\n".join(lines[i:])


def _render_asides(text: str, md: MarkdownIt) -> str:
    """Notion exports callouts as <aside> blocks whose contents are raw Markdown."""

    def repl(m: re.Match) -> str:
        inner = m.group(1).strip()
        icon = ""
        # A leading emoji is the callout's icon.
        if inner and not inner[0].isascii() and not inner[0].isalnum():
            icon, inner = inner[0], inner[1:].lstrip("️").strip()
        icon_html = f'<span class="callout-icon">{icon}</span>' if icon else ""
        return f'\n<aside class="callout">{icon_html}<div>{md.render(inner)}</div></aside>\n'

    return re.sub(r"<aside>\s*(.*?)\s*</aside>", repl, text, flags=re.S)


def _normalize_amount(inline) -> None:
    """Consistent spacing before currency symbols and a real minus sign in amounts."""
    for child in inline.children or []:
        if child.type == "text":
            text = re.sub(r"(\d)\s*([€$£%])", "\\1\u00a0\\2", child.content)
            child.content = re.sub(r"(^|[\s(])-(?=\s*\d)", "\\1\u2212", text)


def _annotate_tables(md: MarkdownIt) -> None:
    """Right-align numeric columns and highlight total rows."""

    def core_rule(state) -> None:
        tokens = state.tokens
        i = 0
        while i < len(tokens):
            if tokens[i].type != "table_open":
                i += 1
                continue
            end = next(j for j in range(i, len(tokens)) if tokens[j].type == "table_close")

            # Collect (row_index, col_index, cell_open_token, text) for body cells.
            rows: list[list[tuple]] = []
            in_body = False
            for j in range(i, end):
                t = tokens[j]
                if t.type == "tbody_open":
                    in_body = True
                elif t.type == "tr_open":
                    rows.append([])
                elif t.type in ("td_open", "th_open"):
                    rows[-1].append((t, tokens[j + 1].content, in_body, j))

            body = [r for r in rows if r and r[0][2]]
            ncols = max((len(r) for r in rows), default=0)
            for c in range(ncols):
                values = [r[c][1] for r in body if c < len(r) and r[c][1].strip()]
                numeric = values and sum(bool(NUMERIC_CELL.match(v.replace("*", ""))) for v in values) >= 0.6 * len(values)
                if numeric and c > 0:
                    for r in rows:
                        if c < len(r):
                            r[c][0].attrJoin("class", "num")
                            _normalize_amount(tokens[r[c][3] + 1])

            if body and TOTAL_ROW.match(body[-1][0][1].replace("*", "")):
                tr = next(k for k in range(body[-1][0][3], i, -1) if tokens[k].type == "tr_open")
                tokens[tr].attrJoin("class", "total")

            tokens[i].attrJoin("class", "data")
            i = end + 1

    md.core.ruler.push("annotate_tables", core_rule)


def _markdown() -> MarkdownIt:
    md = (
        MarkdownIt("commonmark", {"html": True, "typographer": True, "linkify": False})
        .enable(["table", "strikethrough"])
        .use(tasklists_plugin)
    )
    _annotate_tables(md)
    return md


def parse(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    md = _markdown()
    title, properties, body = _split_title_and_properties(text)
    body = _render_asides(body, md)
    body_html = re.sub(
        r'<input class="task-list-item-checkbox"( checked="checked")?[^>]*>',
        lambda m: f'<span class="checkbox{" checked" if m.group(1) else ""}"></span>',
        md.render(body),
    )
    return Document(
        title=title or clean_title_from_filename(path),
        body_html=body_html,
        properties=properties,
    )


def _font_faces() -> str:
    weights = {
        "Regular": (400, "normal"),
        "Italic": (400, "italic"),
        "Medium": (500, "normal"),
        "SemiBold": (600, "normal"),
        "SemiBoldItalic": (600, "italic"),
        "Bold": (700, "normal"),
        "BoldItalic": (700, "italic"),
    }
    return "\n".join(
        f"@font-face {{ font-family: 'Lora'; src: url('{(ASSETS / 'fonts' / f'Lora-{name}.ttf').as_uri()}');"
        f" font-weight: {w}; font-style: {s}; }}"
        for name, (w, s) in weights.items()
    )


def parse_signature(spec: str) -> tuple[str, str]:
    """"Name, Role" -> (name, role). Either part may be empty; the role may contain commas."""
    name, _, role = spec.partition(",")
    return name.strip(), role.strip()


def _signatures_html(signatures: list[tuple[str, str]]) -> str:
    if not signatures:
        return ""
    blocks = "".join(
        '<div class="signature"><div class="signature-line"></div>'
        + (f'<div class="signature-name">{html.escape(name)}</div>' if name else "")
        + (f'<div class="signature-role">{html.escape(role)}</div>' if role else "")
        + "</div>"
        for name, role in signatures
    )
    return f'<section class="signatures">{blocks}</section>'


def build_html(
    doc: Document,
    *,
    organization: str,
    lang: str,
    date: str | None,
    signatures: list[tuple[str, str]] = (),
) -> str:
    css = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
    logo = (ASSETS / "logo-dark.png").as_uri()
    icon = (ASSETS / "icon-dark.png").as_uri()

    meta_items = list(doc.properties)
    if date:
        meta_items.insert(0, ("", date))
    meta_html = ""
    if meta_items:
        meta_html = '<dl class="meta">' + "".join(
            (f"<dt>{html.escape(k)}</dt>" if k else "") + f"<dd>{html.escape(v)}</dd>"
            for k, v in meta_items
        ) + "</dl>"

    title = html.escape(doc.title)
    org = html.escape(organization)
    return f"""<!doctype html>
<html lang="{html.escape(lang)}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="author" content="{org}">
<style>
{_font_faces()}
{css}
</style>
</head>
<body>
<div class="running-header"><img src="{icon}" alt=""><span>{title}</span></div>
<div class="running-footer">{org}</div>
<header class="title-block">
  <img class="logo" src="{logo}" alt="{org}">
  <h1>{title}</h1>
  {meta_html}
</header>
<main>
{doc.body_html}
{_signatures_html(list(signatures))}
</main>
</body>
</html>
"""


def render_pdf(html_str: str, output: Path, base_url: Path) -> None:
    from weasyprint import HTML

    HTML(string=html_str, base_url=str(base_url)).write_pdf(output)
