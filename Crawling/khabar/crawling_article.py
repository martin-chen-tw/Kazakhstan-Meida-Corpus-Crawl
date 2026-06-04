from __future__ import annotations

import re

from Basement.http import get_text, strip_tags
from Basement.parsing import clean_text, description_from_html


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _date(text: str) -> str:
    match = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", text)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else ""


def _body(html: str) -> str:
    match = re.search(r'(?is)<div[^>]+class=["\'][^"\']*iq-blog-box[^"\']*["\'][^>]*>(.*?)(?:<div[^>]+class=["\'][^"\']*iq-blog-tag|</div>\s*</div>\s*</div>)', html)
    if not match:
        return ""
    text = strip_tags(match.group(1)).replace("<>", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not lines and re.fullmatch(r"\d+", line):
            continue
        if line and not re.match(r"^\d{2}\.\d{2}\.20\d{2}", line) and not line.startswith("#"):
            lines.append(line)
    return clean_text("\n".join(lines))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url), retries=1, timeout=15)
    title = _first(r'<h1[^>]+itemprop=["\']name["\'][^>]*>(.*?)</h1>', html)
    body = _body(html) or description_from_html(html) or title
    if not with_metadata:
        return body
    date_text = _first(r'<li[^>]*class=["\'][^"\']*border-gredient-left[^"\']*["\'][^>]*>.*?(\d{2}\.\d{2}\.20\d{2}[^<]*)</li>', html)
    return {
        "body": body,
        "rowdata": html,
        "author": "",
        "title": title,
        "date": _date(date_text),
    }
