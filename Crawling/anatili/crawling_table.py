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
EMPTY_PAGE_LIMIT = 2
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


def _last_news_url(lang: str, page: int) -> str:
    suffix = f"/last-news?page={page}"
    return f"{BASE}{suffix}&ln=lat" if lang == "qazaq" else f"{BASE}{suffix}"


def _main_list_block(html: str) -> str:
    match = re.search(
        r'(?is)<div class=["\']col-xl-9 col-lg-8 col-md-7["\'][^>]*>(.*?)<nav>\s*<ul class=["\']pagination["\']',
        html,
    )
    return match.group(1) if match else html


def _last_page(html: str) -> int | None:
    pages = [int(value) for value in re.findall(r"last-news\?page=(\d+)", html)]
    return max(pages) if pages else None


def _rows_from_page(lang: str, page: int) -> tuple[list[dict[str, str]], int | None]:
    html = _get(_last_news_url(lang, page))
    block = _main_list_block(html)
    rows: list[dict[str, str]] = []
    for match in re.finditer(r'(?is)<a\s+href=["\'](/news/\d+)["\'][^>]*>(.*?)</a>', block):
        url = urljoin(BASE, match.group(1))
        if lang == "qazaq":
            url += "?ln=lat"
        chunk = match.group(2)
        title_match = re.search(r"(?is)<h2[^>]*>(.*?)</h2>", chunk)
        date_match = re.search(r"(?is)<span>(\d{1,2}\s+[^<]+?\s+20\d{2})</span>", chunk)
        title = clean_text(strip_tags(title_match.group(1))) if title_match else ""
        day = _parse_day(date_match.group(1)) if date_match else ""
        if title:
            rows.append({"newspaper": NEWSPAPER, "lang": lang, "url": url, "title": title, "date": day, "time": "", "author": ""})
    return rows, _last_page(html)


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
    max_page: int | None = None
    empty_pages = 0
    while True:
        page_rows, discovered_last_page = _rows_from_page(lang, page)
        max_page = max_page or discovered_last_page
        if not page_rows:
            empty_pages += 1
            if empty_pages >= EMPTY_PAGE_LIMIT:
                break
        else:
            empty_pages = 0
        for row in page_rows:
            url = row["url"]
            if url in seen or not in_range(row.get("date", ""), start_date, end_date):
                continue
            seen.add(url)
            rows.append(row)
            if limit and len(rows) >= limit:
                return rows if with_metadata else [item["url"] for item in rows]
        if max_page and page >= max_page:
            break
        page += 1
    return rows if with_metadata else [row["url"] for row in rows]
