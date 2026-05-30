from __future__ import annotations

import re

from Basement.http import strip_tags
from Basement.parsing import clean_text

from .crawling_table import _get, _parse_day


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _body(html: str) -> str:
    marker = re.search(r'(?is)<h1[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>.*?</h1>', html)
    if not marker:
        return ""
    start = marker.end()
    end = html.find('<div class="right', start)
    chunk = html[start:end if end != -1 else len(html)]
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", chunk)
    text = "\n".join(strip_tags(p) for p in paragraphs) if paragraphs else strip_tags(chunk)
    lines = []
    for line in text.replace("<>", "").splitlines():
        line = line.strip()
        if line and not line.startswith(("Фото", "Сурет")):
            lines.append(line)
    return clean_text("\n".join(lines))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = _get(str(url))
    body = _body(html)
    if not with_metadata:
        return body
    return {
        "body": body,
        "rowdata": html,
        "author": "",
        "title": _first(r'<h1[^>]+class=["\'][^"\']*title[^"\']*["\'][^>]*>(.*?)</h1>', html),
        "date": _parse_day(_first(r'<i[^>]+class=["\'][^"\']*clock[^"\']*["\'][^>]*>.*?</i>\s*<span>(.*?)</span>', html)),
    }
