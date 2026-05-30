from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

COLUMNS = ["newspaper", "url", "title", "date", "time", "author", "body", "rowdata"]

@dataclass(slots=True)
class SourceConfig:
    newspaper: str
    lang: str
    save_path: Path
    base_filename: str
    base_url: str
    article_base_url: str
    default_start_date: date
    sitemaps: list[str]
    extra: dict[str, Any]

@dataclass(slots=True)
class ArticleMeta:
    newspaper: str
    url: str
    title: str = ""
    date: str = ""
    time: str = ""
    author: str = ""
    lang: str = ""

    @classmethod
    def from_any(cls, value: Any, newspaper: str = "", lang: str = "") -> "ArticleMeta":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(newspaper=newspaper, lang=lang, url=value)
        data = dict(value)
        return cls(
            newspaper=data.get("newspaper", newspaper),
            lang=data.get("lang", lang),
            url=str(data.get("url", "")),
            title=str(data.get("title", "") or ""),
            date=str(data.get("date", "") or ""),
            time=str(data.get("time", "") or ""),
            author=str(data.get("author", "") or ""),
        )

    def row(self, body: str, rowdata: str = "") -> dict[str, str]:
        return {"newspaper": self.newspaper, "url": self.url, "title": self.title,
                "date": self.date, "time": self.time, "author": self.author,
                "body": body, "rowdata": rowdata}
