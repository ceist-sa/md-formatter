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
```

| Option | Description |
| --- | --- |
| `-o, --output` | Output path. By default the PDF goes next to the input, with Notion's id removed from the name. |
| `--date` | A date or subtitle shown under the title. |
| `--org` | Organization name in the footer. |
| `--lang` | Document language, used for hyphenation. Default: `pt`. |
| `--html` | Also write the intermediate HTML, for debugging. |

## What it handles

- The first `# Title` becomes the title block under the logo. Notion property lines right below it (`Data: …`) become a metadata row.
- Tables: number and currency columns are right-aligned, with consistent `€` spacing and real minus signs. A last row starting with *Total* or *Saldo final* is set as a total.
- Notion callouts (`<aside>`), checklists, quotes, code, images and links.

Styling lives in `md_formatter/style.css`. Logos and fonts are bundled in `md_formatter/assets/`.
