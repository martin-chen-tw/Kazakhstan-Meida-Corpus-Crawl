from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

from Basement.config import get_source_config
from Basement.http import get_text
from Basement.parsing import in_range


NEWSPAPER = __name__.split(".")[-2]


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
    except Exception:
        rows = [{"url": url, "date": "", "time": ""} for url in _locs(xml_text)]
    return rows


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    cfg = get_source_config(NEWSPAPER, lang)
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    host = cfg.article_base_url.rstrip("/")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in _items(get_text(cfg.sitemaps[0], retries=1, timeout=20)):
        url = item["url"]
        if not url.startswith(f"{host}/article/") or url in seen:
            continue
        if not in_range(item.get("date", ""), start_date, end_date):
            continue
        seen.add(url)
        rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": "", "date": item.get("date", ""), "time": item.get("time", ""), "author": ""})
        if limit and len(rows) >= limit:
            break
    return rows if with_metadata else [row["url"] for row in rows]
