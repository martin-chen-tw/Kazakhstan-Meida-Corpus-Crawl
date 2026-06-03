from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

from Basement.config import get_source_config
from Basement.http import get_text
from Basement.parsing import in_range


NEWSPAPER = __name__.split(".")[-2]
ROOTS = {
    "ru": "https://kz.kursiv.media/sitemaps/ru/sitemap.xml",
    "kz": "https://kz.kursiv.media/sitemaps/kk/sitemap.xml",
    "en": "https://kz.kursiv.media/sitemaps/en/sitemap.xml",
}


def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]
    except Exception:
        return re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)


def _items(xml_text: str) -> list[dict[str, str]]:
    rows = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        for node in [e for e in root.iter() if e.tag.endswith("url")]:
            loc = last = ""
            for child in node:
                if child.tag.endswith("loc") and child.text:
                    loc = child.text.strip()
                if child.tag.endswith("lastmod") and child.text:
                    last = child.text.strip()
            if loc:
                rows.append({"url": loc, "date": last[:10], "time": last})
        if not rows:
            rows = [{"url": url, "date": "", "time": ""} for url in _locs(xml_text)]
    except Exception:
        rows = [{"url": url, "date": "", "time": ""} for url in _locs(xml_text)]
    return rows


def _article_like(url: str, lang: str) -> bool:
    if not url.startswith("https://kz.kursiv.media/") or "/sitemaps/" in url:
        return False
    if lang == "kz" and "/kk/" not in url:
        return False
    if lang == "en" and "/en/" not in url:
        return False
    if lang == "ru" and ("/kk/" in url or "/en/" in url):
        return False
    return re.search(r"/20\d{2}-\d{2}-\d{2}/", url) is not None


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    get_source_config(NEWSPAPER, lang)
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    child_maps = [url for url in _locs(get_text(ROOTS[lang], retries=1, timeout=15)) if url.endswith(".xml")]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for child in child_maps:
        xml = get_text(child, retries=1, timeout=20)
        nested = [item["url"] for item in _items(xml) if item["url"].endswith(".xml")]
        sitemap_items = nested or [child]
        for sitemap_url in sitemap_items:
            for item in _items(get_text(sitemap_url, retries=1, timeout=20)):
                url = item["url"]
                if url in seen or not _article_like(url, lang) or not in_range(item.get("date", ""), start_date, end_date):
                    continue
                seen.add(url)
                rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": "", "date": item.get("date", ""), "time": item.get("time", ""), "author": ""})
                if limit and len(rows) >= limit:
                    return rows if with_metadata else [row["url"] for row in rows]
    return rows if with_metadata else [row["url"] for row in rows]
