"""notion2pdf — pick a page from a Notion database and turn it into a branded PDF."""

from __future__ import annotations

import argparse
import datetime
import getpass
import json
import os
import sys
from pathlib import Path

from .common import add_document_options, ensure_homebrew_fontconfig, safe_filename, write_pdf

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "notion2pdf" / "config.json"


def load_config() -> dict:
    config = {}
    if CONFIG_PATH.is_file():
        config = json.loads(CONFIG_PATH.read_text())
    if os.environ.get("NOTION_TOKEN"):
        config["token"] = os.environ["NOTION_TOKEN"]
    if os.environ.get("NOTION_DATABASE_ID"):
        config["database"] = os.environ["NOTION_DATABASE_ID"]
    return config


def save_config(updates: dict) -> None:
    """Merge updates into the config file (never the environment overrides), readable only by the user."""
    config = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.is_file() else {}
    config.update(updates)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.touch(mode=0o600, exist_ok=True)
    CONFIG_PATH.chmod(0o600)
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))


def setup() -> int:
    from .notion import Notion, NotionError, extract_id

    print("Notion setup. Create an internal integration at https://www.notion.so/profile/integrations,")
    print("give it 'Read content' access, and share the database with it (••• → Connections).\n")
    token = getpass.getpass("Integration secret (input hidden): ").strip()
    database = input("Database link or id: ").strip()
    try:
        database_id = extract_id(database)
        client = Notion(token)
        pages = client.list_pages(client.data_source_id(database_id))
    except NotionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    save_config({"token": token, "database": database_id})
    print(f"\nConnected: {len(pages)} pages found. Saved to {CONFIG_PATH}")
    return 0


def _edited(page: dict) -> str:
    stamp = datetime.datetime.fromisoformat(page["last_edited_time"].replace("Z", "+00:00"))
    return stamp.astimezone().strftime("%d/%m/%Y")


def choose_page(pages: list[dict]) -> dict | None:
    import questionary

    from .notion import page_title

    width = max(len(page_title(p) or "Sem título") for p in pages)
    choices = [
        questionary.Choice(title=f"{(page_title(p) or 'Sem título').ljust(width)}   {_edited(p)}", value=p)
        for p in pages
    ]
    return questionary.select(
        "Which document? (type to filter, ↑↓ to move, Enter to choose)",
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        use_shortcuts=False,
        instruction=" ",
    ).ask()


class Cancelled(Exception):
    pass


def _ask(question):
    """Run a questionary prompt; Ctrl-C (None) cancels the whole run."""
    answer = question.ask()
    if answer is None:
        raise Cancelled
    return answer


def _signer_label(signer: dict) -> str:
    return ", ".join(filter(None, (signer.get("name"), signer.get("role")))) or "(blank line)"


def ask_signoff(args: argparse.Namespace, config: dict) -> None:
    """Ask for signatures and the place/date line, filling args.sign / place / sign_date.
    Signers and the place are remembered in the config for next time."""
    import questionary

    if not _ask(questionary.confirm("Add signature lines?", default=False)):
        return

    saved: list[dict] = config.get("signers", [])
    chosen: list[dict] = []
    if saved:
        chosen = _ask(
            questionary.checkbox(
                "Who signs? (space to select, Enter to confirm)",
                choices=[questionary.Choice(_signer_label(s), value=s) for s in saved],
            )
        )
    new: list[dict] = []

    def add_signer() -> None:
        name = _ask(questionary.text("Name (leave empty for none):")).strip()
        role = _ask(questionary.text("Role (optional):")).strip()
        new.append({"name": name, "role": role})

    if not chosen:
        add_signer()
    while _ask(questionary.confirm("Add someone else?", default=False)):
        add_signer()
    signers = chosen + new
    args.sign = [f"{s['name']}, {s['role']}" for s in signers]

    kind = _ask(
        questionary.select(
            "Place and date line above the signatures?",
            choices=[
                questionary.Choice("Yes, date left blank to fill in by hand", "blank"),
                questionary.Choice("Yes, with today's date", "today"),
                questionary.Choice("Yes, with another date", "other"),
                questionary.Choice("No", "none"),
            ],
        )
    )
    place = config.get("place", "Lisboa")
    if kind != "none":
        place = _ask(questionary.text("Place:", default=place)).strip()
        args.place = place or None
        if kind == "today":
            args.sign_date = "hoje"
        elif kind == "other":
            args.sign_date = _ask(questionary.text("Date (YYYY-MM-DD or as it should be written):")).strip()
        else:
            args.sign_date = ""

    # Most recently used first; people with a name only, blank lines aren't worth remembering.
    remembered = [s for s in signers if s["name"]]
    remembered += [s for s in saved if s not in remembered]
    save_config({"signers": remembered[:20], "place": place})


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        ensure_homebrew_fontconfig("md_formatter.notion_cli")

    parser = argparse.ArgumentParser(
        prog="notion2pdf", description="Pick a page from the Notion database and turn it into a formatted PDF."
    )
    parser.add_argument("--setup", action="store_true", help="save the Notion integration secret and database")
    parser.add_argument("-o", "--output", type=Path, help="output PDF or folder (default: current folder, named after the page)")
    parser.add_argument("--no-properties", action="store_true", help="leave out the page properties under the title")
    add_document_options(parser)
    args = parser.parse_args(argv)

    if args.setup:
        return setup()

    from . import render
    from .notion import Notion, NotionError, page_properties, page_title
    from .notion_md import to_markdown

    config = load_config()
    if not config.get("token") or not config.get("database"):
        parser.error("not set up yet: run `notion2pdf --setup`")

    client = Notion(config["token"])
    try:
        print("Loading documents from Notion…", file=sys.stderr)
        pages = client.list_pages(client.data_source_id(config["database"]))
        if not pages:
            print("The database has no pages.", file=sys.stderr)
            return 1
        page = choose_page(pages)
        if page is None:
            return 1
        title = page_title(page) or "Sem título"
        if not (args.sign or args.place or args.sign_date is not None) and sys.stdin.isatty():
            ask_signoff(args, config)
        print(f"Fetching “{title}”…", file=sys.stderr)
        body = to_markdown(client.page_markdown(page["id"]), title=title)
    except NotionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Cancelled:
        return 1

    doc = render.Document(
        title=title,
        body_html=render.render_body(body),
        properties=[] if args.no_properties else page_properties(page),
    )
    out: Path = args.output or Path(safe_filename(title) + ".pdf")
    if out.is_dir():
        out = out / (safe_filename(title) + ".pdf")
    write_pdf(doc, args, out, base_url=Path.cwd())
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
