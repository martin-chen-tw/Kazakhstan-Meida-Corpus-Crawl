from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from Basement.config import get_root_config
from Basement.final_sqlite_db import read_urls
from Basement.http import get_text
from Basement.parsing import date_from_url, in_range

NEWSPAPER = __name__.split(".")[-2]
HOST = {"ru": "https://ru.sputnik.kz", "kz": "https://sputnik.kz"}
TABLE_WORKERS = 10


def _locs(xml_text: str) -> list[str]:
    return re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)


def _article_links(html: str, base: str, archive_day: str) -> list[str]:
    urls = []
    for href in re.findall(r'href="([^"]+\.html)"', html):
        url = urljoin(base, href)
        if url.startswith(base + "/20") and date_from_url(url) == archive_day:
            urls.append(url)
    return list(dict.fromkeys(urls))


def _existing_urls() -> set[str]:
    path = os.environ.get("NCCU_OUTPUT_URL_DB")
    return read_urls(Path(path)) if path else set()


def _archive_links(archive: str, base: str) -> tuple[str, list[str]]:
    day = date_from_url(archive)
    try:
        return day, _article_links(get_text(archive), base, day)
    except Exception:
        return day, []


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    base = HOST.get(lang, HOST["kz"])
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    archives = list(reversed(_locs(get_text(base + "/sitemap_archive.xml"))))
    if start_date is None and end_date is None:
        archives = list(reversed(archives))
    rows: list[dict[str, str]] = []
    seen: set[str] = _existing_urls()
    workers = int(get_root_config("concurrency", "threads_per_newspaper", default=TABLE_WORKERS) or TABLE_WORKERS)
    for batch_start in range(0, len(archives), max(1, workers)):
        if limit and len(rows) >= limit:
            break
        batch = [archive for archive in archives[batch_start:batch_start + max(1, workers)] if in_range(date_from_url(archive), start_date, end_date)]
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            for day, links in executor.map(lambda archive: _archive_links(archive, base), batch):
                for url in links:
                    if url in seen:
                        continue
                    seen.add(url)
                    rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": "", "date": date_from_url(url) or day, "time": "", "author": ""})
                    if limit and len(rows) >= limit:
                        break
                if limit and len(rows) >= limit:
                    break
    return rows if with_metadata else [row["url"] for row in rows]
