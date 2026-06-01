from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from Basement.config import get_root_config
from Basement.parsing import in_range
from Basement.sql_tmp_db import read_tmp_urls

NEWSPAPER = __name__.split(".")[-2]
SECTION = {"ru": "novosti", "kz": "vlast-qazaqsha", "en": "english"}
TABLE_WORKERS = 10


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
    headers = {"User-Agent": "Mozilla/5.0", "Connection": "close"}
    with requests.get(url, headers=headers, timeout=10) as response:
        response.encoding = response.apparent_encoding
        return response.text, response.status_code


def _staged_urls() -> set[str]:
    path = os.environ.get("NCCU_STAGED_URL_DB")
    return read_tmp_urls(Path(path)) if path else set()


def _page_links(page: int, first_html: str, first_status: int, base: str, section: str, lang: str) -> tuple[int, list[str]]:
    url = f"{base}{page}/?archive=1" if page > 1 else f"{base}?archive=1"
    try:
        if page == 1 and first_html:
            html, status = first_html, first_status
        else:
            html, status = _get(url)
        if status >= 400:
            return page, []
        return page, _links(html, base, lang)
    except Exception:
        return page, []


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
    seen: set[str] = _staged_urls()
    misses = 0
    workers = int(get_root_config("concurrency", "threads_per_newspaper", default=TABLE_WORKERS) or TABLE_WORKERS)
    first_url = f"{base}?archive=1"
    try:
        first_html, first_status = _get(first_url)
    except Exception:
        first_html, first_status = "", 0
    max_page = _last_page(first_html, section) if first_status < 400 else 1

    for batch_start in range(1, max_page + 1, max(1, workers)):
        if limit and len(rows) >= limit:
            break
        pages = list(range(batch_start, min(batch_start + max(1, workers), max_page + 1)))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            page_results = list(executor.map(lambda page: _page_links(page, first_html, first_status, base, section, lang), pages))
        for _, links in page_results:
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
                    if limit and len(rows) >= limit:
                        break
            if limit and len(rows) >= limit:
                break
        if misses >= 3:
            break
    selected = rows[:limit] if limit else rows
    return selected if with_metadata else [row["url"] for row in selected]
