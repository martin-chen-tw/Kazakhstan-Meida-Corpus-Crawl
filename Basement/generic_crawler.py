from __future__ import annotations
import os, re, xml.etree.ElementTree as ET
from datetime import date
from .config import get_source_config
from .http import get_text, links_from_html
from .models import ArticleMeta
from .parsing import date_from_url, extract_article_parts, in_range, slug_title

def _locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
        return [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    except Exception:
        return re.findall(r"<loc>(.*?)</loc>", xml_text, re.I | re.S)

def _candidate_sitemaps(cfg) -> list[str]:
    if cfg.sitemaps: return cfg.sitemaps
    bases = [cfg.article_base_url.rstrip('/'), cfg.base_url.rstrip('/')]
    return [b + "/sitemap.xml" for b in dict.fromkeys(b for b in bases if b)]

def _article_like(url: str, cfg) -> bool:
    bad = (".jpg", ".png", ".pdf", ".xml", "/tag/", "/category/", "#")
    if any(x in url.lower() for x in bad): return False
    contains = cfg.extra.get("article_url_contains")
    if contains and not any(x in url for x in contains): return False
    return cfg.article_base_url.rstrip('/') in url or cfg.base_url.split('/')[2] in url

def _row_date(row: dict[str, str]) -> date:
    try:
        return date.fromisoformat(str(row.get("date", ""))[:10])
    except Exception:
        return date.max

def _sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for _, row in sorted(enumerate(rows), key=lambda item: (_row_date(item[1]), item[0]))]

def crawling_table(newspaper: str, lang: str, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, str]]:
    cfg = get_source_config(newspaper, lang)
    target_limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    urls: list[str] = []
    for sm in _candidate_sitemaps(cfg):
        try:
            locs = _locs(get_text(sm))
            child_maps = [x for x in locs if x.endswith('.xml')]
            if start_date is None and end_date is None:
                child_maps = list(reversed(child_maps))
            for child in child_maps:
                try:
                    urls.extend(x for x in _locs(get_text(child)) if _article_like(x, cfg))
                except Exception: pass
            urls.extend(x for x in locs if _article_like(x, cfg))
        except Exception:
            pass
    if not urls and cfg.base_url:
        try: urls = [u for u in links_from_html(cfg.base_url, get_text(cfg.base_url)) if _article_like(u, cfg)]
        except Exception: urls = []
    if not urls and cfg.article_base_url:
        urls = [cfg.article_base_url.rstrip("/")]
    rows: list[dict[str, str]] = []
    for url in dict.fromkeys(urls):
        d = date_from_url(url)
        if not in_range(d, start_date, end_date): continue
        rows.append({"newspaper": cfg.newspaper, "lang": lang, "url": url, "title": slug_title(url), "date": d, "author": ""})
    rows = _sort_rows(rows)
    return rows[:target_limit] if target_limit else rows

def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    parts = extract_article_parts(html)
    body = parts.get("body", "")
    if not with_metadata:
        return body
    return {
        "body": body,
        "rowdata": html,
        "title": parts.get("title", ""),
        "date": parts.get("date", ""),
        "author": parts.get("author", ""),
    }

def article_metadata(url: str) -> dict[str, str]:
    html = get_text(str(url))
    parts = extract_article_parts(html)
    data = {k: parts.get(k, "") for k in ("title", "date", "author")}
    data["rowdata"] = html
    return data

