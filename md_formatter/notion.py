"""Minimal Notion API client: list a database's pages and fetch a page as Markdown."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .render import format_date

API = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
UUID = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}", re.I)


class NotionError(Exception):
    pass


def extract_id(url_or_id: str) -> str:
    """Accept a database URL (https://www.notion.so/…/Name-<id>?v=…) or a bare id."""
    path = url_or_id.split("?", 1)[0]
    ids = UUID.findall(path)
    if not ids:
        raise NotionError(f"no Notion id found in {url_or_id!r}")
    return ids[-1].replace("-", "")


class Notion:
    def __init__(self, token: str):
        self.token = token

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            API + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(float(e.headers.get("Retry-After", 1)))
                    continue
                try:
                    message = json.load(e).get("message", "")
                except ValueError:
                    message = ""
                raise NotionError(f"Notion API {e.code}: {message or e.reason}") from None
            except urllib.error.URLError as e:
                raise NotionError(f"could not reach Notion: {e.reason}") from None
        raise NotionError("Notion API rate limit: try again in a moment")

    def data_source_id(self, database_id: str) -> str:
        """Databases hold one or more data sources; pages are queried from a data source."""
        try:
            db = self._request("GET", f"/databases/{database_id}")
        except NotionError as e:
            if "404" not in str(e):
                raise
            # The id may already be a data source id.
            return self._request("GET", f"/data_sources/{database_id}")["id"]
        sources = db.get("data_sources") or []
        if not sources:
            raise NotionError("this database has no data sources")
        return sources[0]["id"]

    def list_pages(self, data_source_id: str) -> list[dict]:
        pages, cursor = [], None
        while True:
            body = {"page_size": 100, "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}]}
            if cursor:
                body["start_cursor"] = cursor
            resp = self._request("POST", f"/data_sources/{data_source_id}/query", body)
            pages += [p for p in resp["results"] if p.get("object") == "page"]
            if not resp.get("has_more"):
                return pages
            cursor = resp["next_cursor"]

    def page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}")

    def page_markdown(self, page_id: str) -> str:
        resp = self._request("GET", f"/pages/{page_id}/markdown")
        if resp.get("truncated"):
            raise NotionError("page is too large for the Notion markdown API (content was truncated)")
        return resp["markdown"]


def _plain(rich_text: list[dict]) -> str:
    return "".join(t.get("plain_text", "") for t in rich_text or [])


def page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return _plain(prop["title"]).strip()
    return ""


def _date(value: dict | None) -> str:
    if not value or not value.get("start"):
        return ""
    text = format_date(value["start"])
    if value.get("end"):
        text += f" – {format_date(value['end'])}"
    return text


def _number(n: float) -> str:
    return (f"{n:,.2f}" if n != int(n) else f"{int(n):,}").replace(",", " ").replace(".", ",")


def format_property(prop: dict) -> str:
    """A page property as display text; "" when empty or not meaningful in print."""
    kind = prop.get("type")
    value = prop.get(kind)
    if value is None:
        return ""
    if kind == "rich_text":
        return _plain(value)
    if kind == "number":
        return _number(value)
    if kind in ("select", "status"):
        return value.get("name", "")
    if kind == "multi_select":
        return ", ".join(o["name"] for o in value)
    if kind == "date":
        return _date(value)
    if kind == "people":
        return ", ".join(p.get("name", "") for p in value if p.get("name"))
    if kind == "checkbox":
        return "Sim" if value else "Não"
    if kind in ("url", "email", "phone_number"):
        return value
    if kind in ("created_time", "last_edited_time"):
        return format_date(value)
    if kind in ("created_by", "last_edited_by"):
        return value.get("name", "")
    if kind == "unique_id":
        return f"{value.get('prefix') + '-' if value.get('prefix') else ''}{value.get('number', '')}"
    if kind == "formula":
        return format_property(value)
    if kind == "rollup":
        if value.get("type") == "array":
            return ", ".join(filter(None, (format_property(v) for v in value["array"])))
        return format_property(value)
    return ""  # relation, files, button, …: ids or links that mean nothing on paper


def page_properties(page: dict) -> list[tuple[str, str]]:
    """Non-empty properties other than the title, in Notion's order."""
    out = []
    for name, prop in page.get("properties", {}).items():
        if prop.get("type") == "title":
            continue
        text = format_property(prop).strip()
        if text:
            out.append((name, text))
    return out
