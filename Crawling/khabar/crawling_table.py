from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

from Basement.config import get_source_config
from Basement.http import absolute, get_text, links_from_html
from Basement.parsing import in_range


NEWSPAPER = __name__.split(".")[-2]
def _date_from_url_or_text(url: str) -> str:
    match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", url)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else ""


def _article_like(url: str, lang: str) -> bool:
    prefix = "/ru/news/" if lang == "ru" else "/kk/news/"
    return url.startswith("https://khabar.kz" + prefix) and re.search(r"/\d{5,}-", url) is not None


def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    except Exception:
        return [x.strip() for x in re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)]


def _sitemap_url(lang: str) -> str:
    return f"https://khabar.kz/{'ru' if lang == 'ru' else 'kk'}/xml-karta"


def _row(url: str, lang: str) -> dict[str, str]:
    return {
        "newspaper": NEWSPAPER,
        "lang": lang,
        "url": url,
        "title": "",
        "date": _date_from_url_or_text(url),
        "time": "",
        "author": "",
    }


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    cfg = get_source_config(NEWSPAPER, lang)
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        for url in _locs(get_text(_sitemap_url(lang), retries=1, timeout=15)):
            if url in seen or not _article_like(url, lang):
                continue
            day = _date_from_url_or_text(url)
            if not in_range(day, start_date, end_date):
                continue
            seen.add(url)
            rows.append(_row(url, lang))
            if limit and len(rows) >= limit:
                return rows if with_metadata else [row["url"] for row in rows]
    except Exception:
        pass

    start = len(rows)
    while True:
        page_url = cfg.base_url + str(start)
        try:
            html = get_text(page_url, retries=1, timeout=15)
        except Exception:
            break
        added = 0
        candidates = 0
        for url in links_from_html(page_url, html):
            url = absolute(page_url, url)
            if not _article_like(url, lang):
                continue
            candidates += 1
            if url in seen:
                continue
            day = _date_from_url_or_text(url)
            if not in_range(day, start_date, end_date):
                continue
            seen.add(url)
            rows.append(_row(url, lang))
            added += 1
            if limit and len(rows) >= limit:
                return rows if with_metadata else [row["url"] for row in rows]
        if candidates == 0:
            break
        start += 20
    return rows if with_metadata else [row["url"] for row in rows]
