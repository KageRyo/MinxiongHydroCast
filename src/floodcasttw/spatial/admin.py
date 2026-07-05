"""Administrative-area parsing helpers."""

from __future__ import annotations

import re

COUNTY_RE = re.compile(r"([^\s,，]{1,8}[縣市])")
TOWNSHIP_RE = re.compile(r"([^\s,，]{1,8}[鄉鎮市區])")
VILLAGE_RE = re.compile(r"([^\s,，]{1,12}[村里])")


def extract_admin_parts(text: str) -> dict[str, str]:
    source = text or ""
    county = COUNTY_RE.search(source)
    after_county = source[county.end() :] if county else source
    township = TOWNSHIP_RE.search(after_county)
    after_township = after_county[township.end() :] if township else after_county
    village = VILLAGE_RE.search(after_township)
    return {
        "county": county.group(1) if county else "",
        "township": township.group(1) if township else "",
        "village": village.group(1) if village else "",
    }


def admin_unit_key(county: str = "", township: str = "", village: str = "") -> str:
    parts = [part.strip() for part in (county, township, village) if part.strip()]
    return "|".join(parts)
