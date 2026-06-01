from __future__ import annotations

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from Basement.config import get_root_config, get_source_config
from Basement.http import absolute, get_text, strip_tags
from Basement.parsing import clean_text, in_range

NEWSPAPER = __name__.split(".")[-2]

LOAD_MORE_HOSTS = {
    "ru": "https://www.zakon.kz",
    "kz": "https://kaz.zakon.kz",
}
DEFAULT_MAX_PAGE = 10000
CONSECUTIVE_EMPTY_STOP = 2
CONSECUTIVE_DUPLICATE_STOP = 2
TABLE_WORKERS = 10
_PAGE_CACHE: dict[tuple[str, int], str] = {}


def _load_more_url(lang: str, page: int) -> str:
    host = LOAD_MORE_HOSTS[lang]
    return f"{host}/news/?handler=LoadMoreNews&p={page}&type=list"


def _valid_day(raw: str) -> str:
    try:
        day = date.fromisoformat(raw[:10])
    except Exception:
        return ""
    return raw[:10] if 1900 <= day.year <= 2100 else ""


def _article_like(url: str, lang: str) -> bool:
    if not url.endswith(".html"):
        return False
    if lang == "kz" and "://kaz.zakon.kz/" not in url:
        return False
    if lang == "ru" and "://www.zakon.kz/" not in url:
        return False
    return not any(part in url for part in ("/pbf/", "/special/", "special.zakon.kz"))


def _sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for _, row in sorted(
            enumerate(rows),
            key=lambda item: (item[1].get("date") or "9999-12-31", item[1].get("time") or "", item[0]),
        )
    ]


def _page_text(lang: str, page: int) -> str:
    key = (lang, page)
    if key not in _PAGE_CACHE:
        _PAGE_CACHE[key] = _bounded_get_text(_load_more_url(lang, page))
    return _PAGE_CACHE[key]


def _bounded_get_text(url: str) -> str:
    try:
        proc = subprocess.run(
            [
                "curl",
                "-L",
                "--silent",
                "--show-error",
                "--compressed",
                "--connect-timeout",
                "5",
                "--max-time",
                "15",
                "--user-agent",
                "Mozilla/5.0",
                "--header",
                "Connection: close",
                "--fail",
                url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=17,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except Exception:
        pass
    return get_text(url, retries=1, timeout=12)


def _response_html(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        return text
    chunks: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, str) and "<" in value:
            chunks.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return "\n".join(chunks)


def _items_from_page_html(html: str, lang: str) -> list[dict[str, str]]:
    host = LOAD_MORE_HOSTS[lang]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    anchor_re = re.compile(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>')
    for match in anchor_re.finditer(html):
        href, label_html = match.groups()
        url = absolute(host, href)
        if url in seen or not _article_like(url, lang):
            continue
        seen.add(url)
        context = html[max(0, match.start() - 500): min(len(html), match.end() + 500)]
        title = clean_text(strip_tags(label_html))
        raw_date = _first_date(context)
        rows.append({
            "url": url,
            "title": title,
            "date": raw_date,
            "time": "",
        })
    return rows


def _items_from_page(lang: str, page: int) -> list[dict[str, str]]:
    return _items_from_page_html(_response_html(_page_text(lang, page)), lang)


def _safe_items_from_page(lang: str, page: int) -> list[dict[str, str]]:
    try:
        return _items_from_page(lang, page)
    except Exception:
        return []


def _first_date(text: str) -> str:
    patterns = [
        r"(20\d{2})[-/.](\d{2})[-/.](\d{2})",
        r"(\d{2})[.](\d{2})[.](20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        groups = match.groups()
        if groups[0].startswith("20"):
            return _valid_day("-".join(groups))
        return _valid_day(f"{groups[2]}-{groups[1]}-{groups[0]}")
    return ""


def _all_known_dates_older(rows: list[dict[str, str]], start_date: date | None) -> bool:
    if start_date is None or not rows:
        return False
    dates = []
    for row in rows:
        day = row.get("date", "")
        if not day:
            return False
        try:
            dates.append(date.fromisoformat(day[:10]))
        except Exception:
            return False
    return bool(dates) and max(dates) < start_date


def _max_page(cfg) -> int:
    raw = cfg.extra.get("max_load_more_page", DEFAULT_MAX_PAGE)
    try:
        return max(1, min(DEFAULT_MAX_PAGE, int(raw)))
    except Exception:
        return DEFAULT_MAX_PAGE


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
    consecutive_empty = 0
    consecutive_duplicate = 0
    workers = int(get_root_config("concurrency", "threads_per_newspaper", default=TABLE_WORKERS) or TABLE_WORKERS)
    max_page = _max_page(cfg)
    stop = False

    for batch_start in range(1, max_page + 1, max(1, workers)):
        pages = list(range(batch_start, min(batch_start + max(1, workers), max_page + 1)))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            batch_items = list(executor.map(lambda page: _safe_items_from_page(lang, page), pages))
        for items in batch_items:
            if not items:
                consecutive_empty += 1
                if consecutive_empty >= CONSECUTIVE_EMPTY_STOP:
                    stop = True
                    break
                continue
            consecutive_empty = 0
            if _all_known_dates_older(items, start_date):
                stop = True
                break
            added = 0
            for item in items:
                url = item["url"]
                if url in seen or not in_range(item.get("date", ""), start_date, end_date):
                    continue
                seen.add(url)
                rows.append({
                    "newspaper": NEWSPAPER,
                    "lang": lang,
                    "url": url,
                    "title": item.get("title", ""),
                    "date": item.get("date", ""),
                    "time": item.get("time", ""),
                    "author": "",
                })
                added += 1
            if added == 0:
                consecutive_duplicate += 1
                if consecutive_duplicate >= CONSECUTIVE_DUPLICATE_STOP:
                    stop = True
                    break
            else:
                consecutive_duplicate = 0
            if limit and len(rows) >= limit:
                stop = True
                break
        if stop:
            break

    sorted_rows = _sort_rows(rows)
    if limit:
        sorted_rows = sorted_rows[:limit]
    return sorted_rows if with_metadata else [row["url"] for row in sorted_rows]
