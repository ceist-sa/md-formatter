"""Convert Notion's "enhanced markdown" (from the page markdown API) to the Markdown that
render.py understands.

Enhanced markdown nests child blocks with tabs and uses XML-like tags for callouts, toggles,
columns, tables and mentions: https://developers.notion.com/guides/data-apis/enhanced-markdown
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .render import format_date

# {color="blue"} / {toggle="true" color="red"} at the end of a block's first line.
ATTR_LIST = re.compile(r'\s*(?<!\\)\{(?:[\w-]+="[^"]*"\s*)+\}\s*$')
LIST_ITEM = re.compile(r"^(- \[[ xX]\] |[-*+] |\d+[.)] )")
SPAN = re.compile(r"<span([^>]*)>((?:(?!<span).)*?)</span>", re.S)
MENTION = re.compile(r"<mention-([\w-]+)([^>]*?)(?:/>|>(.*?)</mention-\1>)", re.S)
CITATION = re.compile(r"\[\^[^\]]+\]")
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
# Tags that only group their (indented) children.
CONTAINERS = ("<columns", "<column", "<synced_block", "<synced_block_reference")
CLOSERS = ("</columns>", "</column>", "</synced_block>", "</synced_block_reference>")
# Blocks with nothing to print.
SKIPPED = ("<empty-block", "<table_of_contents", "<unknown", "<database", "<page ", "<page>")
MEDIA = re.compile(r"^<(audio|video|file|pdf)\b[^>]*>(.*?)</\1>$")


@dataclass
class Block:
    kind: str  # "ul"/"ol" for list items (consecutive items of one kind form a list)
    text: str


def _mention(m: re.Match) -> str:
    kind, attrs, label = m.group(1), dict(ATTR.findall(m.group(2))), m.group(3)
    if kind == "date":
        text = format_date(attrs.get("start", ""))
        if attrs.get("end"):
            text += f" – {format_date(attrs['end'])}"
        return text
    return label or ""


def inline(text: str) -> str:
    """Rich text: drop block attributes, colors, mentions and citations; keep underline."""
    text = ATTR_LIST.sub("", text)
    while True:
        new = SPAN.sub(lambda m: f"<u>{m.group(2)}</u>" if 'underline="true"' in m.group(1) else m.group(2), text)
        if new == text:
            break
        text = new
    text = MENTION.sub(_mention, text)
    return CITATION.sub("", text)


def _depth(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


def _children(lines: list[str], i: int) -> tuple[list[str], int]:
    """Lines indented under line i (dedented by one tab), and the index after them."""
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or _depth(lines[j]) > 0):
        j += 1
    # Trailing blank lines belong to whatever comes next.
    while j > i + 1 and not lines[j - 1].strip():
        j -= 1
    return [line[1:] if line.startswith("\t") else line for line in lines[i + 1 : j]], j


def _until(lines: list[str], i: int, closer: str) -> tuple[list[str], int]:
    """Lines between line i and the closing tag at the same depth (dedented by one tab)."""
    j = i + 1
    while j < len(lines) and not (lines[j].strip() == closer and _depth(lines[j]) == 0):
        j += 1
    return [line[1:] if line.startswith("\t") else line for line in lines[i + 1 : j]], j + 1


def _table(lines: list[str]) -> str:
    source = "\n".join(lines)
    opening = dict(ATTR.findall(source.split(">", 1)[0]))
    rows = [
        [inline(c).strip().replace("|", "\\|").replace("\n", "<br>") for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", source, re.S)
    ]
    rows = [r for r in rows if r]
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    # Pipe tables need a header row; an empty one is hidden when rendering.
    header = rows.pop(0) if opening.get("header-row") == "true" else [""] * ncols
    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * ncols]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _indent(text: str, width: int) -> str:
    pad = " " * width
    return "\n".join(pad + line if line.strip() else "" for line in text.split("\n"))


def _join(blocks: list[Block]) -> str:
    out = ""
    for k, block in enumerate(blocks):
        if k:
            out += "\n" if block.kind in ("ul", "ol") and block.kind == blocks[k - 1].kind else "\n\n"
        out += block.text
    return out


def convert_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i].lstrip("\t")
        s = line.strip()
        if not s:
            i += 1
            continue

        if s.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            code = [l[_depth(lines[i]):] for l in lines[i : j + 1]]
            blocks.append(Block("code", "\n".join(code)))
            i = j + 1
        elif s == "$$":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "$$":
                j += 1
            blocks.append(Block("code", "```\n" + "\n".join(l.strip() for l in lines[i + 1 : j]) + "\n```"))
            i = j + 1
        elif re.match(r"<table[\s>]", s):
            j = i
            while j < len(lines) and lines[j].strip() != "</table>":
                j += 1
            blocks.append(Block("table", _table(lines[i : j + 1])))
            i = j + 1
        elif s.startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            blocks.append(Block("table", "\n".join(inline(l.strip()) for l in lines[i:j])))
            i = j
        elif s.startswith("<callout"):
            icon = dict(ATTR.findall(s)).get("icon", "")
            inner, i = _until(lines, i, "</callout>")
            body = _join(convert_blocks(inner))
            # render.py treats a leading emoji inside <aside> as the callout's icon.
            icon = icon if icon and not icon.isascii() else ""
            blocks.append(Block("callout", f"<aside>\n{icon} {body}\n</aside>" if icon else f"<aside>\n{body}\n</aside>"))
        elif s.startswith("<details"):
            inner, i = _until(lines, i, "</details>")
            summary = ""
            if inner and (m := re.match(r"\s*<summary>(.*?)</summary>\s*$", inner[0])):
                summary, inner = m.group(1), inner[1:]
            if summary.strip():
                blocks.append(Block("p", f"**{inline(summary).strip()}**"))
            blocks += convert_blocks(inner)
        elif s.startswith(CONTAINERS):
            children, i = _children(lines, i)
            blocks += convert_blocks(children)
        elif s.startswith(CLOSERS):
            i += 1
        elif s.startswith(SKIPPED):
            _, i = _children(lines, i)
        elif m := MEDIA.match(s):
            caption = inline(m.group(2)).strip()
            if caption:
                blocks.append(Block("p", f"*{caption}*"))
            _, i = _children(lines, i)
        elif m := LIST_ITEM.match(s):
            width = 2 if s.startswith("- [") else len(m.group(1))
            children, i = _children(lines, i)
            item = inline(s)
            child_blocks = convert_blocks(children)
            for k, child in enumerate(child_blocks):
                tight = child.kind in ("ul", "ol") and (k == 0 or child_blocks[k - 1].kind == child.kind)
                item += ("\n" if tight else "\n\n") + _indent(child.text, width)
            blocks.append(Block("ol" if s[0].isdigit() else "ul", item))
        else:
            kind = "hr" if s == "---" else "p"
            blocks.append(Block(kind, inline(s)))
            children, i = _children(lines, i)
            blocks += convert_blocks(children)
    return blocks


def to_markdown(enhanced: str, title: str | None = None) -> str:
    """Convert enhanced markdown to plain Markdown, dropping a leading H1 that repeats the title."""
    blocks = convert_blocks(enhanced.replace("\r\n", "\n").split("\n"))
    if blocks and title and blocks[0].text.lstrip("# ").strip() == title.strip() and blocks[0].text.startswith("# "):
        blocks.pop(0)
    return _join(blocks) + "\n"
