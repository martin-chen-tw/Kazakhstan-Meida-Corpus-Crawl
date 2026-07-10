from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

from Basement.config import get_source_config
from Basement.http import absolute, get_text, links_from_html
from Basement.parsing import in_range


NEWSPAPER = __name__.split(".")[-2]
INDEX = "https://kazpravda.kz/sitemap.xml"


def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [item.text.strip() for item in root.iter() if item.tag.endswith("loc") and item.text]
    except Exception:
        return re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)


def _url_items(xml_text: str) -> list[dict[str, str]]:
    rows = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        for node in [item for item in root.iter() if item.tag.endswith("url")]:
            loc = last = ""
            for child in node:
                if child.tag.endswith("loc") and child.text:
                    loc = child.text.strip()
                if child.tag.endswith("lastmod") and child.text:
                    last = child.text.strip()
            if loc:
                rows.append({"url": loc, "date": last[:10], "time": last})
    except Exception:
        rows = [{"url": url, "date": "", "time": ""} for url in _locs(xml_text)]
    return rows


def _article_prefix(lang: str) -> str:
    return {"en": "/en/n/", "qaz": "/kk/n/"}.get(lang, "/n/")


def _article_like(url: str, lang: str) -> bool:
    return url.startswith("https://kazpravda.kz" + _article_prefix(lang)) and url.endswith("/")


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

    if lang != "ru":
        for url in links_from_html(cfg.base_url, get_text(cfg.base_url, retries=1, timeout=15)):
            url = absolute(cfg.base_url, url)
            if url in seen or not _article_like(url, lang):
                continue
            seen.add(url)
            rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": "", "date": "", "time": "", "author": ""})
            if limit and len(rows) >= limit:
                return rows if with_metadata else [row["url"] for row in rows]
        return rows if with_metadata else [row["url"] for row in rows]

    child_maps = [url for url in _locs(get_text(INDEX, retries=1, timeout=15)) if url.endswith(".xml")]
    for child in child_maps:
        for item in _url_items(get_text(child, retries=1, timeout=20)):
            url = item["url"]
            if url in seen or not _article_like(url, lang) or not in_range(item.get("date", ""), start_date, end_date):
                continue
            seen.add(url)
            rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": "", "date": item.get("date", ""), "time": item.get("time", ""), "author": ""})
            if limit and len(rows) >= limit:
                return rows if with_metadata else [row["url"] for row in rows]
    return rows if with_metadata else [row["url"] for row in rows]
