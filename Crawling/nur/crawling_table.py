from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import date

from Basement.http import get_text
from Basement.parsing import in_range

NEWSPAPER = __name__.split(".")[-2]
HOST = {"ru": "https://www.nur.kz", "kz": "https://kaz.nur.kz"}


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


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    base = HOST.get(lang, HOST["ru"])
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    child_maps = _locs(get_text(f"{base}/article-index-sitemap.xml"))
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for sitemap in child_maps:
        if limit and len(rows) >= limit:
            break
        try:
            items = _url_items(get_text(sitemap))
        except Exception:
            continue
        for item in items:
            url = item["url"]
            day = item.get("date", "")
            if not url.startswith(base + "/") or url in seen or not in_range(day, start_date, end_date):
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
