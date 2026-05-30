from __future__ import annotations

import json
import re
from html import unescape

from Basement.http import get_text, meta_content, strip_tags, title_from_html
from Basement.parsing import clean_text


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _date(raw: str) -> str:
    match = re.search(r"(20\d{2})[-/.]?(\d{2})[-/.]?(\d{2})", raw or "")
    return "-".join(match.groups()) if match else ""


def _jsonld_values(html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in re.findall(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html):
        try:
            data = json.loads(unescape(raw))
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if isinstance(node.get("@graph"), list):
                nodes.extend(item for item in node["@graph"] if isinstance(item, dict))
            for key in ("headline", "articleBody", "datePublished", "dateModified"):
                if key in node and node[key] and key not in values:
                    values[key] = clean_text(str(node[key]))
            author = node.get("author")
            if "author" not in values and isinstance(author, list) and author and isinstance(author[0], dict):
                values["author"] = clean_text(str(author[0].get("name", "")))
            elif "author" not in values and isinstance(author, dict):
                values["author"] = clean_text(str(author.get("name", "")))
    return values


def _author_from_targeting(html: str) -> str:
    match = re.search(r'"authors"\s*:\s*\[(.*?)\]', html, re.S)
    if not match:
        return ""
    authors = re.findall(r'"([^"]+)"', match.group(1))
    return clean_text(", ".join(authors))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    values = _jsonld_values(html)
    title = (
        values.get("headline", "")
        or _first(r"<h1[^>]*>(.*?)</h1>", html)
        or clean_text(strip_tags(title_from_html(html)))
    )
    date = _date(values.get("datePublished", "") or meta_content(html, ["article:published_time", "datePublished", "publish_date", "date"]))
    author = values.get("author", "") or meta_content(html, ["author", "article:author"]) or _author_from_targeting(html)
    body = values.get("articleBody", "")
    if not body:
        paragraphs = [clean_text(strip_tags(p)) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)]
        body = clean_text("\n".join(p for p in paragraphs if len(p) > 40 and "<>" not in p))
    result = {"title": title, "date": date, "time": "", "author": author, "body": body, "rowdata": html}
    return result if with_metadata else body
