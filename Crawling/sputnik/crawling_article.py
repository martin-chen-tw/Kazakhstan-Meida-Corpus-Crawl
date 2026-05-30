from __future__ import annotations

import re

from Basement.http import get_text, meta_content, strip_tags, title_from_html
from Basement.parsing import clean_text, description_from_html, metadata_date


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    title = _first(r"<h1[^>]*>(.*?)</h1>", html) or clean_text(strip_tags(title_from_html(html)))
    date = metadata_date(html, str(url))
    author = meta_content(html, ["author", "article:author"])
    blocks = re.findall(r'(?is)<div[^>]+class="[^"]*article__text[^"]*"[^>]*>(.*?)</div>', html)
    if not blocks:
        blocks = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    body = clean_text("\n".join(strip_tags(block) for block in blocks)) or description_from_html(html) or title
    result = {"title": title, "date": date, "time": "", "author": author, "body": body}
    return result if with_metadata else body
