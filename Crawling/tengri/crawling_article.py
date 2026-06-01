from __future__ import annotations
import re
from Basement.http import get_text, meta_content, strip_tags
from Basement.parsing import clean_text, extract_article_parts


def _author(html: str) -> str:
    author = meta_content(html, ["author", "article:author"])
    if author:
        return author
    patterns = [
        r'(?is)<[^>]+class=["\'][^"\']*(?:author|article-author)[^"\']*["\'][^>]*>(.*?)</[^>]+>',
        r'(?is)\bAuthor\s*:?\s*(?:</?[^>]*>\s*)?([^<\n]+)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return clean_text(strip_tags(m.group(1)))
    return ""


def _body(html: str) -> str:
    m = re.search(r'(?is)<div[^>]+class=["\'][^"\']*content_main_text[^"\']*["\'][^>]*>(.*?)(?:<div\s+id=["\']comm["\']|<div[^>]+class=["\'][^"\']*content_main_text_tags)', html)
    if not m:
        return ""
    return clean_text("\n".join(line for line in strip_tags(m.group(1)).splitlines()
                                if line.strip() != "<>" and "Google News" not in line and line.strip() not in {"Подписаться", "Subscribe"}))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    parts = extract_article_parts(html)
    body = _body(html) or parts.get("body", "")
    if not with_metadata:
        return body
    return {"body": body, "rowdata": html, "author": parts.get("author") or _author(html),
            "title": parts.get("title", ""), "date": parts.get("date", "")}
