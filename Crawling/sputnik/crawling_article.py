from __future__ import annotations

import re

from Basement.http import get_text, meta_content, strip_tags, title_from_html
from Basement.parsing import clean_text, description_from_html, metadata_date


def _first(pattern: str, html: str) -> str:
    match = re.search(pattern, html, re.I | re.S)
    return clean_text(strip_tags(match.group(1))) if match else ""


def _article_html(html: str) -> str:
    patterns = [
        r'(?is)<div[^>]+class=["\'][^"\']*article__body[^"\']*["\'][^>]*>(.*?)(?:<div[^>]+class=["\'][^"\']*article__footer|<div[^>]+class=["\'][^"\']*article__tags|</article>)',
        r'(?is)<div[^>]+class=["\'][^"\']*article__text[^"\']*["\'][^>]*>(.*?)</div>',
        r"(?is)<article[^>]*>(.*?)</article>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return html


def _clean_body_block(raw: str) -> str:
    raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
    raw = re.sub(r"(?is)<(script|style|noscript|svg|button|form).*?</\1>", " ", raw)
    lines = []
    for line in strip_tags(raw).splitlines():
        line = re.sub(r"^(?:<>\s*)+", "", line.strip())
        if not line or re.fullmatch(r"[<>\s]+", line):
            continue
        lines.append(line)
    text = clean_text("\n".join(lines))
    if not text:
        return ""
    lower = text.lower()
    skip_fragments = [
        "подписывайтесь на sputnik",
        "sputnik казахстан",
        "sputnik қазақстан",
        "следите за последними новостями",
        "читайте также",
        "материалы по теме",
        "больше актуальных новостей",
        "telegram",
        "whatsapp",
    ]
    if any(fragment in lower for fragment in skip_fragments):
        return ""
    if re.fullmatch(r"[\W_]+", text):
        return ""
    return text


def _body(html: str) -> str:
    blocks = re.findall(
        r'(?is)<div[^>]+class=["\'][^"\']*article__text[^"\']*["\'][^>]*>(.*?)</div>',
        html,
    )
    if not blocks:
        blocks = re.findall(
            r'(?is)<div[^>]+class=["\'][^"\']*article__announce-text[^"\']*["\'][^>]*>(.*?)</div>',
            html,
        )
    if not blocks:
        article_html = _article_html(html)
        blocks = re.findall(r"(?is)<p[^>]*>(.*?)</p>", article_html)
        if not blocks:
            blocks = re.findall(
                r'(?is)<div[^>]+class=["\'][^"\']*article__body[^"\']*["\'][^>]*>(.*?)(?:<div[^>]+class=["\'][^"\']*article__footer|</article>)',
                html,
            )
    if not blocks and re.search(r"(?is)<article[^>]*>", html):
        blocks = [article_html]
    return clean_text("\n".join(text for block in blocks if (text := _clean_body_block(block))))


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    title = _first(r"<h1[^>]*>(.*?)</h1>", html) or clean_text(strip_tags(title_from_html(html)))
    date = metadata_date(html, str(url))
    author = meta_content(html, ["author", "article:author"])
    body = _body(html) or description_from_html(html) or title
    result = {"title": title, "date": date, "time": "", "author": author, "body": body, "rowdata": html}
    return result if with_metadata else body
