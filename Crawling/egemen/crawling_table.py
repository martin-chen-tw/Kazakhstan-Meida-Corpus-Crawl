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


def _sample_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    if not items:
        return []
    indexes = {0, len(items) // 4, len(items) // 2, (len(items) * 3) // 4, len(items) - 1}
    return [items[i] for i in sorted(indexes)]


def _looks_like_broken_sitemap(items: list[dict[str, str]], lang: str) -> bool:
    sampled = _sample_items(items)
    if len(sampled) < 3:
        return False
    checked = 0
    for item in sampled:
        try:
            get_text(item["url"], retries=0, timeout=10)
            return False
        except Exception as exc:
            text = str(exc)
            if "404 Client Error" not in text and "status code: 404" not in text:
                return False
            checked += 1
    print(f"[WARN] egemen {lang}: sitemap article URLs sampled as 404; skipping broken sitemap list")
    return checked == len(sampled)


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
    candidates = []
    for item in _items(get_text(cfg.sitemaps[0], retries=1, timeout=20)):
        url = item["url"]
        if not url.startswith(f"{host}/article/") or url in seen:
            continue
        if not in_range(item.get("date", ""), start_date, end_date):
            continue
        seen.add(url)
        candidates.append(item)
        if limit and len(candidates) >= limit:
            break
    if _looks_like_broken_sitemap(candidates, lang):
        return rows if with_metadata else []
    for item in candidates:
        url = item["url"]
        rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": "", "date": item.get("date", ""), "time": item.get("time", ""), "author": ""})
        if limit and len(rows) >= limit:
            break
    return rows if with_metadata else [row["url"] for row in rows]
