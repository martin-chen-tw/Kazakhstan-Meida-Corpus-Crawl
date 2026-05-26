from __future__ import annotations

import os
import re
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from Basement.parsing import in_range

NEWSPAPER = __name__.split(".")[-2]
SECTION = {"ru": "novosti", "kz": "vlast-qazaqsha", "en": "english"}


def _links(html: str, base: str, lang: str) -> list[str]:
    section = SECTION.get(lang, SECTION["ru"])
    urls = []
    for href in re.findall(r'href="([^"]+\.html)"', html):
        url = urljoin(base, href)
        path = urlparse(url).path
        if path.startswith(f"/{section}/"):
            urls.append(url)
    return list(dict.fromkeys(urls))


def _last_page(html: str, section: str) -> int:
    match = re.search(rf'href="/{re.escape(section)}/(\d+)/\?archive=1"\s+rel="last"', html)
    return int(match.group(1)) if match else 1


def _get(url: str) -> tuple[str, int]:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    response.encoding = response.apparent_encoding
    return response.text, response.status_code


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    section = SECTION.get(lang, SECTION["ru"])
    base = f"https://vlast.kz/{section}/"
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    misses = 0
    first_url = f"{base}?archive=1"
    try:
        first_html, first_status = _get(first_url)
    except Exception:
        first_html, first_status = "", 0
    max_page = _last_page(first_html, section) if first_status < 400 else 1

    for page in range(1, max_page + 1):
        if limit and len(rows) >= limit:
            break
        url = f"{base}{page}/?archive=1" if page > 1 else first_url
        try:
            if page == 1 and first_html:
                html, status = first_html, first_status
            else:
                html, status = _get(url)
            if status >= 400:
                raise RuntimeError(status)
            links = _links(html, base, lang)
        except Exception:
            misses += 1
            if misses >= 3:
                break
            continue
        if not links:
            misses += 1
            if misses >= 3:
                break
            continue
        misses = 0
        for item in links:
            if item in seen:
                continue
            seen.add(item)
            day = ""
            if in_range(day, start_date, end_date):
                rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": item, "title": "", "date": day, "time": "", "author": ""})
    selected = rows[:limit] if limit else rows
    return selected if with_metadata else [row["url"] for row in selected]
