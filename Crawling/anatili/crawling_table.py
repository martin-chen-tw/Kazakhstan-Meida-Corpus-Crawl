from __future__ import annotations

import os
import re
from datetime import date
from urllib.parse import urljoin

import requests

from Basement.config import get_source_config
from Basement.http import strip_tags
from Basement.parsing import clean_text, in_range


NEWSPAPER = __name__.split(".")[-2]
BASE = "https://anatili.kazgazeta.kz"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
MONTHS = {
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
}


def _get(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def _parse_day(text: str) -> str:
    text = clean_text(strip_tags(text)).replace(",", " ").lower()
    match = re.search(r"(\d{1,2})\s+([а-яәіңғүұқөһ]+)\s+(20\d{2})", text, re.I)
    if not match:
        return ""
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name)
    if not month:
        return ""
    try:
        return date(int(year), month, int(day)).isoformat()
    except ValueError:
        return ""


def _clean_title(text: str) -> str:
    text = text.replace("<>", "\n")
    date_re = re.compile(r"\d{1,2}\s+[А-Яа-яӘәІіҢңҒғҮүҰұҚқӨөҺһ]+\s+20\d{2}")
    for line in text.splitlines():
        line = clean_text(line)
        if line and not date_re.search(line) and not line.isdigit():
            return line
    return clean_text(date_re.split(text, 1)[0])


def crawling_table(
    lang: str,
    start_date: date | None = None,
    end_date: date | None = None,
    with_metadata: bool = True,
) -> list[dict[str, str]] | list[str]:
    get_source_config(NEWSPAPER, lang)
    limit = int(os.environ.get("NCCU_CRAWL_LIMIT", "0") or 0)
    html = _get(f"{BASE}/?ln=lat" if lang == "qazaq" else BASE)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(r'(?is)<a[^>]+href=["\'](/news/\d+)["\'][^>]*>(.*?)</a>')
    for match in pattern.finditer(html):
        url = urljoin(BASE, match.group(1))
        if lang == "qazaq":
            url += "?ln=lat"
        if url in seen:
            continue
        text = clean_text(strip_tags(match.group(2)))
        title = _clean_title(text)
        day = _parse_day(text)
        if not title or not in_range(day, start_date, end_date):
            continue
        seen.add(url)
        rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": title, "date": day, "time": "", "author": ""})
        if limit and len(rows) >= limit:
            break
    return rows if with_metadata else [row["url"] for row in rows]
