from __future__ import annotations

import re

from Basement.http import get_text, strip_tags
from Basement.parsing import clean_text, description_from_html, metadata_date


MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _date(text: str) -> str:
    match = re.search(r"(\d{1,2})\s+([а-я]+)\s+(20\d{2})", text.lower())
    if not match:
        return ""
    day, month_name, year = match.groups()
    month = MONTHS.get(month_name)
    return f"{year}-{month:02d}-{int(day):02d}" if month else ""


def _body(html: str) -> str:
    match = re.search(r'(?is)<div[^>]+class=["\'][^"\']*article__body[^"\']*["\'][^>]*>(.*?)<div[^>]+class=["\'][^"\']*article__tags', html)
    if not match:
        match = re.search(r"(?is)<article[^>]*>(.*?)</article>", html)
    if not match:
        return ""
    text = strip_tags(match.group(1)).replace("<>", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("Фото:", "#")) and "Kazpravda.kz" not in line:
            lines.append(line)
    return clean_text("\n".join(lines))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url), retries=1, timeout=15)
    body = _body(html)
    if not with_metadata:
        return body
    title = _first(r'<h1[^>]+class=["\'][^"\']*article__title[^"\']*["\'][^>]*>(.*?)</h1>', html)
    return {
        "body": body or description_from_html(html) or title,
        "rowdata": html,
        "author": "",
        "title": title,
        "date": metadata_date(html, str(url)) or _date(_first(r'<time[^>]+class=["\'][^"\']*article__date[^"\']*["\'][^>]*>(.*?)</time>', html)),
    }
