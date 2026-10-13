"""Keep MkDocs' translation locale separate from each page's HTML language."""

from typing import Any


def on_post_page(output: str, *, page: Any, **kwargs: Any) -> str:
    language = page.meta.get("lang", "en")
    return output.replace('<html lang="zh_TW"', f'<html lang="{language}"', 1)
