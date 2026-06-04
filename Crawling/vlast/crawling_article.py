from __future__ import annotations

import os
import re
import subprocess

from Basement.http import get_text, meta_content, strip_tags, title_from_html
from Basement.config import get_root_config
from Basement.parsing import clean_text, description_from_html, json_ld_value, metadata_date


def _article_timeout() -> int:
    configured = int(get_root_config("crawling", "request_timeout", default=20) or 20)
    return int(os.environ.get("NCCU_VLAST_ARTICLE_TIMEOUT", max(configured, 45)))


def _article_retries() -> int:
    return int(os.environ.get("NCCU_VLAST_ARTICLE_RETRIES", 3))


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _published_time(html: str) -> str:
    raw = (
        json_ld_value(html, "datePublished")
        or _first(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", html)
        or meta_content(html, ["article:published_time", "datePublished", "publish_date", "date", "pubdate"])
    )
    match = re.search(r"(?:T|\s)(\d{1,2}:\d{2}(?::\d{2})?)", raw or "")
    if not match:
        match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", raw or "")
    if not match:
        return ""
    parts = match.group(1).split(":")
    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2]) if len(parts) > 2 else 0
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _clean_paragraph(raw: str) -> str:
    text = strip_tags(raw)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"[<>\s]+", line):
            continue
        lines.append(line)
    return clean_text("\n".join(lines))


def _body(html: str) -> str:
    paragraphs = [_clean_paragraph(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)]
    return clean_text("\n".join(p for p in paragraphs if len(p.strip()) > 30))


def _get_article_html(url: str) -> str:
    timeout = _article_timeout()
    try:
        proc = subprocess.run(
            [
                "curl",
                "-L",
                "--silent",
                "--show-error",
                "--compressed",
                "--connect-timeout",
                str(max(5, min(timeout // 3, 15))),
                "--max-time",
                str(timeout),
                "--user-agent",
                "Mozilla/5.0",
                "--header",
                "Connection: close",
                "--fail",
                str(url),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 3,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except Exception:
        pass
    return get_text(str(url), retries=_article_retries(), timeout=timeout)


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = _get_article_html(str(url))
    title = _first(r"<h1[^>]*>(.*?)</h1>", html) or clean_text(strip_tags(title_from_html(html)))
    date = metadata_date(html, str(url))
    time = _published_time(html)
    author = meta_content(html, ["author", "article:author"])
    body = _body(html) or description_from_html(html)
    result = {"title": title, "date": date, "time": time, "author": author, "body": body, "rowdata": html}
    return result if with_metadata else body
