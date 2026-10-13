"""Check local links in generated HTML without requesting any external URL."""

from __future__ import annotations

import argparse
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


def validate_site(site_dir: Path, base_path: str = "/MinxiongHydroCast/") -> list[str]:
    root = site_dir.resolve()
    pages: dict[Path, PageLinks] = {}
    for path in root.rglob("*.html"):
        parser = PageLinks()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[path] = parser
    if root / "index.html" not in pages:
        return ["Site has no index.html"]
    errors: list[str] = []
    for page, parser in pages.items():
        for link in parser.links:
            parts = urlsplit(link)
            if parts.scheme or parts.netloc:
                continue
            path = unquote(parts.path)
            if path.startswith("/"):
                if not path.startswith(base_path):
                    errors.append(f"{page.relative_to(root)}: outside site prefix: {link}")
                    continue
                target = root / path[len(base_path):]
            else:
                target = page.parent / path if path else page
            target = target.resolve()
            if not target.is_relative_to(root):
                errors.append(f"{page.relative_to(root)}: outside site directory: {link}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"{page.relative_to(root)}: missing target: {link}")
            elif parts.fragment and target in pages:
                if unquote(parts.fragment) not in pages[target].ids:
                    errors.append(f"{page.relative_to(root)}: missing anchor: {link}")
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
    print("[OK] generated local links, assets, and HTML anchors resolve")


if __name__ == "__main__":
    main()
