from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

from Basement.http import get_text
from Basement.parsing import in_range

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


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    base = HOST.get(lang, HOST["ru"])
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    misses = 0

    for page in range(1, 1000):
        if limit and len(rows) >= limit:
            break
        try:
            items = _url_items(get_text(f"{base}/sitemap/sitemap_news{page}.xml"))
        except Exception:
            misses += 1
            if misses >= 3:
                break
            continue
        if not items:
            misses += 1
            if misses >= 3:
                break
            continue
        misses = 0
        for item in items:
            url = item["url"]
            day = item.get("date", "")
            if not _usable_article_url(url, base) or url in seen or not in_range(day, start_date, end_date):
                continue
            seen.add(url)
            rows.append({
                "newspaper": NEWSPAPER,
                "lang": lang,
                "url": url,
                "title": item.get("title", ""),
                "date": day,
                "time": item.get("time", ""),
                "author": item.get("author", ""),
            })
            if limit and len(rows) >= limit:
                break

    return rows if with_metadata else [row["url"] for row in rows]
