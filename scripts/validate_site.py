"""Check local links in generated HTML without requesting any external URL."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        identifier = attributes.get("id")
        if identifier:
            self.ids.add(identifier)
        for key in ("href", "src"):
            value = attributes.get(key)
            if value:
                self.links.append(value)


def read_pages(root: Path) -> dict[Path, PageLinks]:
    pages: dict[Path, PageLinks] = {}
    for path in root.rglob("*.html"):
        parser = PageLinks()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path] = parser
    return pages


def link_error(
    root: Path, page: Path, link: str, pages: dict[Path, PageLinks], base_path: str
) -> str | None:
    parts = urlsplit(link)
    if parts.scheme or parts.netloc:
        return None
    path = unquote(parts.path)
    if path.startswith("/"):
        if not path.startswith(base_path):
            return "outside site prefix"
        target = root / path[len(base_path):]
    else:
        target = page.parent / path if path else page
    target = target.resolve()
    if not target.is_relative_to(root):
        return "outside site directory"
    if target.is_dir():
        target /= "index.html"
    if not target.is_file():
        return "missing target"
    if parts.fragment and target in pages and unquote(parts.fragment) not in pages[target].ids:
        return "missing anchor"
    return None


def validate_site(site_dir: Path, base_path: str = "/MinxiongHydroCast/") -> list[str]:
    root = site_dir.resolve()
    pages = read_pages(root)
    if root / "index.html" not in pages:
        return ["Site has no index.html"]
    search_index = root / "search" / "search_index.json"
    if search_index.is_file():
        data = json.loads(search_index.read_text(encoding="utf-8"))
        pages[root / "index.html"].links.extend(entry["location"] for entry in data["docs"])
    errors: list[str] = []
    for page, parser in pages.items():
        for link in parser.links:
            reason = link_error(root, page, link, pages, base_path)
            if reason:
                errors.append(f"{page.relative_to(root)}: {reason}: {link}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_dir", type=Path)
    args = parser.parse_args()
    errors = validate_site(args.site_dir)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        raise SystemExit(1)
    print("[OK] generated links, assets, HTML anchors, and search targets resolve")


if __name__ == "__main__":
    main()
