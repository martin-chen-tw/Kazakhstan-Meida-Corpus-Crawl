from __future__ import annotations

import re

from Basement.http import get_text, strip_tags
from Basement.parsing import clean_text, description_from_html, metadata_date


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _meta(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def _body(html: str) -> str:
    match = re.search(
        r'(?is)<(?:main|div)[^>]+class=["\'][^"\']*single-body[^"\']*["\'][^>]*>(.*?)(?:<div[^>]+class=["\'][^"\']*(?:single-footer|single-read-also)|<section|</main>)',
        html,
    )
    body_html = match.group(1) if match else ""
    if not body_html:
        match = re.search(r'(?is)<div[^>]+class=["\'][^"\']*single-content[^"\']*["\'][^>]*>(.*?)(?:<aside|<footer|</article>|</main>)', html)
        body_html = match.group(1) if match else ""
    if not body_html:
        return description_from_html(html)
    text = strip_tags(body_html).replace("<>", "")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("Фото:", "Читайте также")):
            lines.append(line)
    return clean_text("\n".join(lines))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url), retries=1, timeout=15)
    body = _body(html)
    if not with_metadata:
        return body
    title = (
        _first(r'<h1[^>]+class=["\'][^"\']*single-header__title[^"\']*["\'][^>]*>(.*?)</h1>', html)
        or _first(r'<article[^>]+class=["\'][^"\']*subcat-article[^"\']*["\'][^>]*>.*?<h1[^>]*>(.*?)</h1>', html)
        or _meta(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html)
    )
    return {
        "body": body or title,
        "rowdata": html,
        "author": _first(r'<div[^>]+class=["\'][^"\']*author-card__name[^"\']*["\'][^>]*>\s*<a[^>]*>(.*?)</a>', html)
        or _first(r'<div[^>]+class=["\'][^"\']*subcat-article__header__author-info[^"\']*["\'][^>]*>.*?<p[^>]*>(.*?)</p>', html),
        "title": title,
        "date": metadata_date(html, str(url)) or (
            _first(r'<time[^>]+class=["\'][^"\']*single-publishing-time__date[^"\']*["\'][^>]+datetime=["\']([^"\']+)', html)[:10]
            or _first(r'<div[^>]+class=["\'][^"\']*subcat-article__header__date[^"\']*["\'][^>]*>.*?<p[^>]*>(.*?)</p>', html)
        ),
    }
