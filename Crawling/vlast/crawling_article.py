from __future__ import annotations

import re
import subprocess

from Basement.http import get_text, meta_content, strip_tags, title_from_html
from Basement.parsing import clean_text, description_from_html, metadata_date


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _get_article_html(url: str) -> str:
    try:
        proc = subprocess.run(
            [
                "curl",
                "-L",
                "--silent",
                "--show-error",
                "--compressed",
                "--connect-timeout",
                "5",
                "--max-time",
                "15",
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
            timeout=17,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    except Exception:
        pass
    return get_text(str(url), retries=1, timeout=12)


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = _get_article_html(str(url))
    title = _first(r"<h1[^>]*>(.*?)</h1>", html) or clean_text(strip_tags(title_from_html(html)))
    date = metadata_date(html, str(url))
    author = meta_content(html, ["author", "article:author"])
    paragraphs = [strip_tags(p) for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)]
    body = clean_text("\n".join(p for p in paragraphs if len(p.strip()) > 30)) or description_from_html(html)
    result = {"title": title, "date": date, "time": "", "author": author, "body": body, "rowdata": html}
    return result if with_metadata else body
