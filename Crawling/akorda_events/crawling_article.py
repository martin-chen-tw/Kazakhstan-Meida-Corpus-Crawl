from __future__ import annotations

import re

from Basement.http import get_text, strip_tags
from Basement.parsing import clean_text, description_from_html, extract_article_parts

from .crawling_table import _parse_day


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _body(html: str) -> str:
    match = re.search(r"(?is)<article[^>]*>(.*?)</article>", html)
    if not match:
        return ""
    text = strip_tags(match.group(1)).replace("\xa0", " ").replace("<>", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line in {"Go back", "Back"} or "akorda.kz" in line.lower():
            continue
        lines.append(line)
    return clean_text("\n".join(lines))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url), retries=1, timeout=12)
    parts = extract_article_parts(html)
    title = _first(r"<h2[^>]*class=[\"'][^\"']*mt-5[^\"']*[\"'][^>]*>(.*?)</h2>", html) or parts.get("title", "")
    body = _body(html) or parts.get("body", "") or description_from_html(html) or title
    if not with_metadata:
        return body
    return {
        "body": body,
        "author": parts.get("author", ""),
        "title": title,
        "date": _parse_day(_first(r"<h2[^>]*class=[\"'][^\"']*mt-5[^\"']*[\"'][^>]*>.*?</h2>\s*<h5[^>]*>(.*?)</h5>", html)) or parts.get("date", "") or _parse_day(title),
    }
