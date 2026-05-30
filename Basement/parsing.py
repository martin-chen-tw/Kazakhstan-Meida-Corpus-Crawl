from __future__ import annotations
import json, re
from datetime import date
from urllib.parse import urlparse
from .http import meta_content, strip_tags, title_from_html

def clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())

def date_from_url(url: str) -> str:
    pats = [r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", r"/(20\d{2})(\d{2})(\d{2})/"]
    for pat in pats:
        m = re.search(pat, url)
        if m:
            y, mo, d = map(int, m.groups())
            try:
                return date(y, mo, d).isoformat()
            except ValueError:
                pass
    return ""

def in_range(date_text: str, start: date | None, end: date | None) -> bool:
    if not date_text or (start is None and end is None):
        return True
    try:
        d = date.fromisoformat(date_text[:10])
    except Exception:
        return True
    return (start is None or d >= start) and (end is None or d <= end)

def slug_title(url: str) -> str:
    slug = urlparse(url).path.rstrip('/').split('/')[-1]
    return re.sub(r"[-_]+", " ", re.sub(r"\.html?$", "", slug)).strip()

def json_ld_value(html: str, key: str) -> str:
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"'
    match = re.search(pattern, html, re.I | re.S)
    if not match:
        return ""
    try:
        return str(json.loads(f'"{match.group(1)}"')).strip()
    except Exception:
        return match.group(1).strip()

def first_date_text(raw: str) -> str:
    match = re.search(r"(20\d{2})[-/.]?(\d{2})[-/.]?(\d{2})", raw or "")
    if match:
        return "-".join(match.groups())
    match = re.search(r"(20\d{2})(\d{2})(\d{2})T", raw or "")
    if match:
        return "-".join(match.groups())
    return ""

def metadata_date(html: str, url: str = "") -> str:
    raw = (
        json_ld_value(html, "datePublished")
        or meta_content(html, ["article:published_time", "datePublished", "publish_date", "date", "pubdate"])
    )
    return first_date_text(raw) or date_from_url(url)

def description_from_html(html: str) -> str:
    return clean_text(strip_tags(
        meta_content(html, ["og:description", "twitter:description", "description"])
        or json_ld_value(html, "description")
    ))

def required_text(*values: str) -> str:
    for value in values:
        text = clean_text(strip_tags(str(value or "")))
        if text:
            return text
    return ""

def extract_article_parts(html: str) -> dict[str, str]:
    title = title_from_html(html)
    date_text = metadata_date(html)
    author = meta_content(html, ["article:author", "author"])
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", html)
    body_html = m.group(1) if m else html
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", body_html)
    body = clean_text("\n".join(strip_tags(p) for p in paragraphs) if paragraphs else strip_tags(body_html))
    return {"title": clean_text(strip_tags(title)), "date": date_text[:10], "author": author, "body": body}
