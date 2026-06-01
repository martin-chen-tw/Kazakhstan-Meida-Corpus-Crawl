from __future__ import annotations
import re, time
from html import unescape
from urllib.parse import urljoin
import requests
from .config import get_root_config

_HEADERS = {"User-Agent": get_root_config("crawling", "user_agent", default="NCCUCorpusCrawler/2.0")}

def get_text(url: str, retries: int = 2, timeout: int | None = None) -> str:
    timeout = timeout or int(get_root_config("crawling", "request_timeout", default=20))
    headers = {**_HEADERS, "Connection": "close"}
    last = None
    for i in range(retries + 1):
        try:
            with requests.get(url, headers=headers, timeout=timeout) as r:
                r.raise_for_status()
                if not r.encoding or r.encoding.lower() == "iso-8859-1":
                    r.encoding = r.apparent_encoding
                return r.text
        except Exception as e:
            last = e
            time.sleep(0.5 * (i + 1))
    raise RuntimeError(f"GET failed {url}: {last}")

def absolute(base: str, href: str) -> str:
    return urljoin(base, unescape(href or ""))

def strip_tags(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p|</div|</li|</h[1-6]", "\n<", html)
    text = re.sub(r"(?is)<[^>]+>", " ", html)
    lines = [re.sub(r"\s+", " ", unescape(x)).strip() for x in text.splitlines()]
    return "\n".join(x for x in lines if x)

def meta_content(html: str, names: list[str]) -> str:
    for name in names:
        pat = rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)'
        m = re.search(pat, html, re.I)
        if m:
            return unescape(m.group(1)).strip()
    return ""

def title_from_html(html: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return meta_content(html, ["og:title", "twitter:title"]) or (m.group(1).strip() if m else "")

def links_from_html(base_url: str, html: str) -> list[str]:
    hrefs = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.I)
    return list(dict.fromkeys(absolute(base_url, h) for h in hrefs if h and not h.startswith(('#', 'mailto:', 'tel:'))))
