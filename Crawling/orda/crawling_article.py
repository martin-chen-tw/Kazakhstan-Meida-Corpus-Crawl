from __future__ import annotations

import re

from Basement.http import get_text, meta_content, strip_tags, title_from_html
from Basement.parsing import clean_text, description_from_html, slug_title


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _date(raw: str) -> str:
    match = re.search(r"(20\d{2})[-/.]?(\d{2})[-/.]?(\d{2})", raw or "")
    return "-".join(match.groups()) if match else ""


def _clean_paragraph(raw: str) -> str:
    text = clean_text(strip_tags(raw))
    if "-->" in text:
        text = text.rsplit("-->", 1)[-1]
    text = re.sub(r"\s*\|\s*", " | ", text)
    return clean_text(text.replace("<>", " "))


def _body(html: str) -> str:
    paragraphs = [_clean_paragraph(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)]
    keep: list[str] = []
    for text in paragraphs:
        if len(text) < 40:
            continue
        lower = text.lower()
        if "certificate of registration" in lower or "куәлігі" in lower or "куәлік" in lower or "свидетельство" in lower:
            continue
        if "cookie" in lower or "құпиялылық саясат" in lower or "политику конфиденциальности" in lower:
            continue
        if lower.startswith(("ru | kz | en", "ордынка |", "society |", "news |")):
            continue
        keep.append(text.strip())
    return clean_text("\n".join(keep))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    title = _first(r"<h1[^>]*>(.*?)</h1>", html) or clean_text(strip_tags(title_from_html(html)))
    date = _date(meta_content(html, ["article:published_time", "datePublished", "publish_date", "date"]))
    if not date:
        date = _date(_first(r'<time[^>]+datetime=["\']([^"\']+)["\']', html) or _first(r"<time[^>]*>(.*?)</time>", html))
    author = meta_content(html, ["author", "article:author"])
    body = _body(html)
    if not title:
        title = slug_title(str(url))
    if not body:
        body = description_from_html(html) or title
    result = {"title": title, "date": date, "time": "", "author": author, "body": body, "rowdata": html}
    return result if with_metadata else body
