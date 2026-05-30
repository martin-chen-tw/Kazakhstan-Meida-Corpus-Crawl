from __future__ import annotations

import re

from Basement.http import get_text, strip_tags
from Basement.parsing import clean_text, description_from_html, metadata_date, slug_title


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _body(html: str) -> str:
    match = re.search(r'(?is)<div[^>]+itemprop=["\']articleBody["\'][^>]*>(.*?)(?:<div[^>]+class=["\'][^"\']*top-news social-links|</article>)', html)
    if not match:
        return ""
    text = strip_tags(match.group(1)).replace("<>", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("Фото", "Сурет")):
            lines.append(line)
    return clean_text("\n".join(lines))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url), retries=1, timeout=15)
    body = _body(html)
    if not with_metadata:
        return body
    title = _first(r'<h1[^>]+class=["\'][^"\']*responsive_title[^"\']*["\'][^>]*>(.*?)</h1>', html) or slug_title(str(url))
    return {
        "body": body or description_from_html(html) or title,
        "author": _first(r'<div[^>]+class=["\'][^"\']*name-auth[^"\']*["\'][^>]*>\s*<h4>(.*?)</h4>', html),
        "title": title,
        "date": metadata_date(html, str(url)),
    }
