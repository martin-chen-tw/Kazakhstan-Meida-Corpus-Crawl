from __future__ import annotations
import os, re, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from Basement.config import get_source_config
from Basement.http import get_text
from Basement.parsing import in_range

SiteMapDict = {
    "ru": "https://tengrinews.kz/sitemap-index.xml",
    "en": "https://en.tengrinews.kz/en-sitemap-index.xml",
    "kz": "https://kaz.tengrinews.kz/kk-sitemap-index.xml",
}

def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]
    except Exception:
        return re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)

def _url_items(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        rows=[]
        for u in [e for e in root.iter() if e.tag.endswith("url")]:
            loc=last=""
            for c in u:
                if c.tag.endswith("loc") and c.text: loc=c.text.strip()
                if c.tag.endswith("lastmod") and c.text: last=c.text.strip()
            day = _valid_day(last[:10])
            if loc: rows.append({"url": loc, "time": last if day else "", "date": day})
        return rows
    except Exception:
        return [{"url": u, "time": "", "date": ""} for u in _locs(xml_text)]

def _valid_day(raw: str) -> str:
    try:
        day = date.fromisoformat(raw)
    except Exception:
        return ""
    return raw if 1900 <= day.year <= 2100 else ""

def _sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for _, row in sorted(enumerate(rows), key=lambda item: (
        item[1].get("date") or "9999-12-31", item[1].get("time") or "", item[0]))]

def _items_from_sitemap(url: str) -> list[dict[str, str]]:
    try:
        return _url_items(get_text(url))
    except Exception:
        return []

def crawling_table(lang: str, start_date: date | None = None, end_date: date | None = None,
                   with_metadata: bool = True) -> list[dict[str, str]] | list[str]:
    cfg = get_source_config("tengri", lang)
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    index_url = SiteMapDict.get(lang, cfg.sitemaps[0])
    child_maps = [u for u in _locs(get_text(index_url)) if "sitemap-news" in u]
    if start_date is None and end_date is None:
        child_maps = list(reversed(child_maps))
    rows=[]; seen=set()
    with ThreadPoolExecutor(max_workers=12) as ex:
        sitemap_items = ex.map(_items_from_sitemap, child_maps)
        for items in sitemap_items:
            for item in items:
                if not in_range(item.get("date", ""), start_date, end_date): continue
                if item["url"] in seen: continue
                seen.add(item["url"])
                row = {"newspaper": "tengri", "lang": lang, "url": item["url"],
                       "title": "", "date": item.get("date", ""),
                       "time": item.get("time", ""), "author": ""}
                rows.append(row)
    sorted_rows = _sort_rows(rows)
    if limit:
        sorted_rows = sorted_rows[:limit]
    return sorted_rows if with_metadata else [row["url"] for row in sorted_rows]
