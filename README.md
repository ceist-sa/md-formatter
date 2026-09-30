# md-formatter

Turns Notion pages into branded PDFs, set in Lora. Two commands:

- **`notion2pdf`** shows a menu of the pages in a Notion database and turns the chosen one into a PDF.
- **`md2pdf`** converts a Markdown file exported from Notion.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Pango (a system library WeasyPrint needs):

```bash
brew install uv pango
uv tool install .             # puts `md2pdf` and `notion2pdf` on your PATH
```

After changing the code, run `uv tool install --reinstall .` to update the commands.
For development, `uv sync` creates `.venv` with the exact versions in `uv.lock`,
and `uv run md2pdf …` runs the code in the project folder directly.

### Connecting to Notion (once)

1. Create an internal integration at <https://www.notion.so/profile/integrations>. Under *Capabilities*, it only needs **Read content**.
2. Open the database in Notion, click **•••** → **Connections**, and add the integration.
3. Run `notion2pdf --setup`, paste the integration secret and the database link.

The secret and database are saved in `~/.config/notion2pdf/config.json`, readable only by you.
The `NOTION_TOKEN` and `NOTION_DATABASE_ID` environment variables override it.

## Usage

```bash
notion2pdf
# → menu of the database's pages, most recently edited first; type to filter, Enter to choose
# → "<page title>.pdf" in the current folder

notion2pdf --place Lisboa --sign "Ana Silva, Presidente" --sign "João Costa, Tesoureiro"

md2pdf "Meu documento 3de419a3db6c804a8555f2eea055d93e.md"
# → "Meu documento.pdf" next to the input

md2pdf input.md --place Lisboa --sign-date hoje --sign "Ana Silva, Presidente"
```

Options for both commands:

| Option | Description |
| --- | --- |
| `-o, --output` | Output path. `md2pdf` puts the PDF next to the input by default; `notion2pdf` in the current folder (it also accepts a folder). |
| `--date` | A date or subtitle shown under the title. |
| `--org` | Organization name in the footer. |
| `--lang` | Document language, used for hyphenation. Default: `pt`. |
| `--sign "NAME, ROLE"` | Adds a signature line at the end of the document. Repeat it for more signatures. Name and role are both optional: `--sign "Ana Silva"`, `--sign ", Tesoureiro"`, or `--sign` alone for a blank line. |
| `--place PLACE` | Adds a place and date line above the signatures ("Lisboa, ___ de ______ de ____"). Without `--sign-date`, the date is left blank to fill in by hand. |
| `--sign-date DATE` | Fills in that date: `hoje`/`today`, `YYYY-MM-DD` (written out as "2 de outubro de 2026"), or any text as written. With no value, adds a blank date line. |
| `--html` | Also write the intermediate HTML, for debugging. |

`notion2pdf` only:

| Option | Description |
| --- | --- |
| `--setup` | Save the Notion integration secret and database. |
| `--no-properties` | Leave out the page's properties (Data, Estado, …) under the title. |

## What it handles

- The page title becomes the title block under the logo. Page properties (`Data: …`) become a row of details below it.
- Tables: number and currency columns are right-aligned, with consistent `€` spacing and real minus signs. A last row starting with *Total* or *Saldo final* is set as a total.
- Signatures are laid out two per row. Together with the place and date line, they are never split across pages or left alone on the last page.
- Callouts, checklists, quotes, code, images and links. From Notion directly, also toggles (printed open), columns (printed one after another) and mentions. Bookmarks, embeds, child pages and linked databases are left out.

Styling lives in `md_formatter/style.css`. Logos and fonts are bundled in `md_formatter/assets/`.
