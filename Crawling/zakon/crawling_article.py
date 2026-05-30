from __future__ import annotations

import json
import re

from Basement.http import get_text, meta_content, strip_tags
from Basement.parsing import clean_text, extract_article_parts


def _json_ld_body(html: str) -> str:
    for match in re.finditer(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if not isinstance(item, dict):
                continue
            article_body = item.get("articleBody")
            if article_body:
                return clean_text(str(article_body))
            graph = item.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
    return ""


def _body_from_container(html: str) -> str:
    article_block = re.search(r'(?is)<div[^>]+class=["\'][^"\']*article__block[^"\']*["\'][^>]*>', html)
    if article_block:
        start = re.search(r'(?is)<div[^>]+class=["\']content["\'][^>]*>', html[article_block.end():])
        if start:
            body_start = article_block.end() + start.end()
            stops = []
            for pos in (
                html.find('class="willShare', body_start),
                html.find("class='willShare", body_start),
                html.find('class="google-news-follow', body_start),
                html.find("class='google-news-follow", body_start),
                html.find('class="tags newsTags', body_start),
                html.find("class='tags newsTags", body_start),
            ):
                if pos == -1:
                    continue
                tag_start = html.rfind("<", body_start, pos)
                stops.append(tag_start if tag_start != -1 else pos)
            body_end = min(stops) if stops else len(html)
            body = _clean_body_html(html[body_start:body_end])
            if body:
                return body

    patterns = [
        r'(?is)<div[^>]+itemprop=["\']articleBody["\'][^>]*>(.*?)</div>',
        r'(?is)<div[^>]+class=["\'][^"\']*(?:article__body|article-body|article_text|article-text|news-text|content__text)[^"\']*["\'][^>]*>(.*?)</div>',
        r'(?is)<article[^>]*>(.*?)</article>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if not match:
            continue
        body = _clean_body_html(match.group(1))
        if body:
            return body
    return ""


def _clean_body_html(body_html: str) -> str:
    stop_markers = (
        "\u041f\u043e\u0434\u0435\u043b\u0438\u0442\u0435\u0441\u044c \u043d\u043e\u0432\u043e\u0441\u0442\u044c\u044e",
        "\u0427\u0438\u0442\u0430\u0439\u0442\u0435 \u0442\u0430\u043a\u0436\u0435",
        "\u0421\u043b\u0435\u0434\u0438\u0442\u0435 \u0437\u0430 \u043d\u043e\u0432\u043e\u0441\u0442\u044f\u043c\u0438",
        "\u041d\u0430\u0448\u043b\u0438 \u043e\u0448\u0438\u0431\u043a\u0443",
        "\u0411\u0435\u0442\u0442\u0435\u0433\u0456 \u049b\u0430\u0442\u0435",
        "\u0416\u0430\u04a3\u0430\u043b\u044b\u049b\u0442\u0430\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u044b\u04a3\u0434\u0430",
    )
    photo_prefixes = (
        "\u0424\u043e\u0442\u043e:",
        "\u0424\u043e\u0442\u043e: ",
        "\u0421\u0443\u0440\u0435\u0442:",
    )
    text = strip_tags(body_html).replace("<>", "")
    for marker in stop_markers:
        text = text.split(marker, 1)[0]
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if (
            not line
            or line == "<>"
            or line.startswith("<")
            or "Google News" in line
            or line.startswith(photo_prefixes)
        ):
            continue
        lines.append(line)
    text = "\n".join(lines)
    return clean_text(text)


def _merge_lead_and_body(lead: str, body: str) -> str:
    if not lead:
        return body
    if not body:
        return lead
    if body.startswith(lead) or lead in body:
        return body
    return clean_text(f"{lead}\n{body}")


def _author(html: str, fallback: str = "") -> str:
    author = meta_content(html, ["author", "article:author"])
    if author:
        return author
    match = re.search(r'(?is)<a[^>]+href=["\'][^"\']*/authors/[^"\']*["\'][^>]*>(.*?)</a>', html)
    if match:
        return clean_text(strip_tags(match.group(1)))
    return fallback


def crawling_article(url: str, with_metadata: bool = False) -> str | dict[str, str]:
    html = get_text(str(url))
    parts = extract_article_parts(html)
    lead = _json_ld_body(html)
    body = _merge_lead_and_body(lead, _body_from_container(html)) or parts.get("body", "")
    if not with_metadata:
        return body
    return {
        "body": body,
        "rowdata": html,
        "author": _author(html, parts.get("author", "")),
        "title": parts.get("title", ""),
        "date": parts.get("date", ""),
    }
