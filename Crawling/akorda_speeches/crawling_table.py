from __future__ import annotations

import os
import re
from datetime import date

from Basement.config import get_source_config
from Basement.http import absolute, get_text, strip_tags
from Basement.parsing import clean_text, in_range


NEWSPAPER = __name__.split(".")[-2]
CATEGORY = NEWSPAPER.removeprefix("akorda_")
BASE = "https://www.akorda.kz"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
}


def _parse_day(text: str) -> str:
    text = clean_text(strip_tags(text)).replace(",", " ").lower()
    patterns = [
        r"(\d{1,2})\s+([a-zа-яәіңғүұқөһ]+)\s+(20\d{2})",
        r"([a-zа-яәіңғүұқөһ]+)\s+(\d{1,2})\s+(20\d{2})",
        r"(20\d{2})\s+жылғы\s+(\d{1,2})\s+([a-zа-яәіңғүұқөһ]+)",
    ]
    match = next((m for p in patterns if (m := re.search(p, text, re.I))), None)
    if not match:
        return ""
    if match.re.pattern.startswith("(["):
        month_name, day, year = match.groups()
    elif match.re.pattern.startswith("(20"):
        year, day, month_name = match.groups()
    else:
        day, month_name, year = match.groups()
    month = MONTHS.get(month_name)
    if not month:
        return ""
    try:
        return date(int(year), month, int(day)).isoformat()
    except ValueError:
        return ""


def _page_url(lang: str, page: int) -> str:
    return f"{BASE}/{lang}/{CATEGORY}?page={page}"


def _article_like(url: str, lang: str) -> bool:
    if not url.startswith(f"{BASE}/{lang}/") or "?" in url or "#" in url:
        return False
    path = url.split(f"{BASE}/{lang}/", 1)[1].strip("/")
    if not path or path == CATEGORY or path.startswith((
        "republic_of_kazakhstan/", "president/", "official_documents/",
        "executive_office/", "secretary_of_state/", "security_council/",
    )):
        return False
    if CATEGORY == "addresses":
        return path.startswith(f"{CATEGORY}/") and len(path.split("/")) > 1
    if CATEGORY == "legal_acts" and lang == "en":
        return path.startswith("legal_acts/") and len(path.split("/")) > 1
    if CATEGORY == "legal_acts" and path.startswith("legal_acts/"):
        return len(path.split("/")) > 1
    return "/" not in path and re.search(r"-\d+$", path) is not None


def _rows_from_page(lang: str, page: int) -> list[dict[str, str]]:
    url = _page_url(lang, page)
    try:
        html = get_text(url, retries=1, timeout=12)
    except Exception:
        return []
    rows = []
    pattern = re.compile(r'(?is)<h3[^>]*>\s*<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>\s*</h3>')
    matches = list(pattern.finditer(html))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else match.end() + 1200
        segment = html[match.end():end]
        article_url = absolute(url, match.group(1))
        if not _article_like(article_url, lang):
            continue
        title = clean_text(strip_tags(match.group(2)))
        date_match = re.search(r"(?is)<h5[^>]*>(.*?)</h5>", segment)
        day = _parse_day(date_match.group(1) if date_match else segment)
        rows.append({
            "newspaper": NEWSPAPER, "lang": lang, "url": article_url,
            "title": title, "date": day, "time": "", "author": "",
        })
    return rows


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    get_source_config(NEWSPAPER, lang)
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    page = 1
    while True:
        page_rows = _rows_from_page(lang, page)
        added = 0
        for row in page_rows:
            if row["url"] in seen or not in_range(row.get("date", ""), start_date, end_date):
                continue
            seen.add(row["url"])
            rows.append(row)
            added += 1
            if limit and len(rows) >= limit:
                return rows if with_metadata else [item["url"] for item in rows]
        if not page_rows or added == 0:
            break
        page += 1
    return rows if with_metadata else [item["url"] for item in rows]
