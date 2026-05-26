from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests

from Basement.config import get_root_config
from Basement.http import get_text
from Basement.parsing import in_range
from Basement.sql_tmp_db import read_tmp_urls

NEWSPAPER = __name__.split(".")[-2]
HOST = {"ru": "https://orda.kz", "en": "https://en.orda.kz", "kz": "https://kaz.orda.kz"}
BAD_PATH_MARKERS = (
    "__trashed",
    "%ef%bf%bc",
    "\ufffc",
    "%ef%b8%8f",
    "\ufe0f",
)
BAD_PATHS = {
    "/ruhani-zha%d2%a3%d2%93yru-czentr-molodezh-i-penthaus-kak-skolotil-sostoyanie-otecz-bajbeka-chast-3/",
}
_HEADERS = {"User-Agent": get_root_config("crawling", "user_agent", default="NCCUCorpusCrawler/2.0")}
TABLE_WORKERS = 10


def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [node.text.strip() for node in root.iter() if node.tag.endswith("loc") and node.text]
    except Exception:
        return re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)


def _url_items(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        rows: list[dict[str, str]] = []
        for node in root.iter():
            if not node.tag.endswith("url"):
                continue
            loc = ""
            lastmod = ""
            for child in node:
                if child.tag.endswith("loc") and child.text:
                    loc = child.text.strip()
                if child.tag.endswith("lastmod") and child.text:
                    lastmod = child.text.strip()
            if loc:
                rows.append({"url": loc, "date": lastmod[:10], "time": lastmod, "title": "", "author": ""})
        return rows
    except Exception:
        return [{"url": url, "date": "", "time": "", "title": "", "author": ""} for url in _locs(xml_text)]


def _usable_article_url(url: str, base: str) -> bool:
    if not url.startswith(base + "/"):
        return False
    path = url.split(base, 1)[1].lower()
    if path in BAD_PATHS:
        return False
    return not any(marker in path for marker in BAD_PATH_MARKERS)


def _reachable_article_url(url: str) -> bool:
    timeout = int(get_root_config("crawling", "request_timeout", default=20))
    try:
        response = requests.head(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if response.status_code == 405:
            response = requests.get(url, headers=_HEADERS, timeout=timeout, stream=True)
            response.close()
    except requests.RequestException:
        return True
    return response.status_code not in {404, 410}


def _reachable_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    with ThreadPoolExecutor(max_workers=TABLE_WORKERS) as executor:
        reachable = executor.map(_reachable_article_url, [row["url"] for row in rows])
    return [row for row, ok in zip(rows, reachable) if ok]


def _staged_urls() -> set[str]:
    path = os.environ.get("NCCU_STAGED_URL_DB")
    return read_tmp_urls(Path(path)) if path else set()


def _page_items(base: str, page: int) -> list[dict[str, str]] | None:
    try:
        return _url_items(get_text(f"{base}/sitemap/sitemap_news{page}.xml"))
    except Exception:
        return None


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    base = HOST.get(lang, HOST["ru"])
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    rows: list[dict[str, str]] = []
    seen: set[str] = _staged_urls()
    misses = 0

    for batch_start in range(1, 1000, TABLE_WORKERS):
        if limit and len(rows) >= limit:
            break
        pages = list(range(batch_start, min(batch_start + TABLE_WORKERS, 1000)))
        with ThreadPoolExecutor(max_workers=TABLE_WORKERS) as executor:
            batch_items = list(executor.map(lambda page: _page_items(base, page), pages))
        for items in batch_items:
            if limit and len(rows) >= limit:
                break
            if not items:
                misses += 1
                if misses >= 3:
                    break
                continue
            misses = 0
            candidates: list[dict[str, str]] = []
            candidate_urls: set[str] = set()
            for item in items:
                url = item["url"]
                day = item.get("date", "")
                if (
                    not _usable_article_url(url, base)
                    or url in seen
                    or url in candidate_urls
                    or not in_range(day, start_date, end_date)
                ):
                    continue
                candidate_urls.add(url)
                candidates.append({
                    "newspaper": NEWSPAPER,
                    "lang": lang,
                    "url": url,
                    "title": item.get("title", ""),
                    "date": day,
                    "time": item.get("time", ""),
                    "author": item.get("author", ""),
                })
            for row in _reachable_rows(candidates):
                seen.add(row["url"])
                rows.append(row)
                if limit and len(rows) >= limit:
                    break
        if misses >= 3:
            break

    return rows if with_metadata else [row["url"] for row in rows]
