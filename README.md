# md-formatter

Turns a Markdown file exported from Notion into a branded PDF, set in Lora.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Pango (a system library WeasyPrint needs):

```bash
brew install uv pango
uv tool install .             # puts `md2pdf` on your PATH
```

After changing the code, run `uv tool install --reinstall .` to update the command.
For development, `uv sync` creates `.venv` with the exact versions in `uv.lock`,
and `uv run md2pdf …` runs the code in the project folder directly.

## Usage

```bash
md2pdf "Meu documento 3de419a3db6c804a8555f2eea055d93e.md"
# → "Meu documento.pdf" next to the input

md2pdf input.md -o out.pdf --date "Setembro de 2026"

md2pdf input.md --sign "Ana Silva, Presidente" --sign "João Costa, Tesoureiro"

md2pdf input.md --place Lisboa --sign-date hoje --sign "Ana Silva, Presidente"
```

| Option | Description |
| --- | --- |
| `-o, --output` | Output path. By default the PDF goes next to the input, with Notion's id removed from the name. |
| `--date` | A date or subtitle shown under the title. |
| `--org` | Organization name in the footer. |
| `--lang` | Document language, used for hyphenation. Default: `pt`. |
| `--sign "NAME, ROLE"` | Adds a signature line at the end of the document. Repeat it for more signatures. Name and role are both optional: `--sign "Ana Silva"`, `--sign ", Tesoureiro"`, or `--sign` alone for a blank line. |
| `--place PLACE` | Adds a place and date line above the signatures ("Lisboa, ___ de ______ de ____"). Without `--sign-date`, the date is left blank to fill in by hand. |
| `--sign-date DATE` | Fills in that date: `hoje`/`today`, `YYYY-MM-DD` (written out as "2 de outubro de 2026"), or any text as written. With no value, adds a blank date line. |
| `--html` | Also write the intermediate HTML, for debugging. |

## What it handles

- The first `# Title` becomes the title block under the logo. Notion property lines right below it (`Data: …`) become a metadata row.
- Tables: number and currency columns are right-aligned, with consistent `€` spacing and real minus signs. A last row starting with *Total* or *Saldo final* is set as a total.
- Signatures are laid out two per row. Together with the place and date line, they are never split across pages or left alone on the last page.
- Notion callouts (`<aside>`), checklists, quotes, code, images and links.

Styling lives in `md_formatter/style.css`. Logos and fonts are bundled in `md_formatter/assets/`.
