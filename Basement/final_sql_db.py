from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from .config import output_mode, psql_settings, sql_table_names, sql_template_path
from .models import SourceConfig

VALUE_RE = r"'(?:''|[^']*)'"


def ensure_sql_file(path: Path, rebuild: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rebuild or not path.exists():
        template = sql_template_path().read_text(encoding="utf-8")
        path.write_text(template.rstrip() + "\n\n", encoding="utf-8")
    return path


def read_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {_unquote_sql(match.group(1).strip("'")) for match in _article_re().finditer(text)}


def count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return len(_article_id_re().findall(path.read_text(encoding="utf-8", errors="ignore")))


def append_rows(path: Path, cfg: SourceConfig, rows: Iterable[dict[str, str]]) -> int:
    with SqlAppender(path, cfg) as appender:
        return appender.append(rows)


class SqlAppender:
    def __init__(self, path: Path, cfg: SourceConfig) -> None:
        self.path = ensure_sql_file(path)
        self.cfg = cfg
        if output_mode() == "psql":
            self.platform_id = _db_platform_id(cfg)
            self.next_article_id = _db_max_id("articles", "article_id") + 1
            self.next_platform_id = _db_max_id("platforms", "platform_id") + 1
        else:
            self.platform_id = _platform_id(path, cfg)
            self.next_article_id = _max_article_id(path) + 1
            self.next_platform_id = _max_platform_id(path) + 1
        self.fh = None

    def __enter__(self) -> "SqlAppender":
        self.fh = self.path.open("a", encoding="utf-8")
        if self.platform_id is None:
            self.platform_id = self.next_platform_id
            self.fh.write(_platform_insert(self.platform_id, self.cfg))
        return self

    def __exit__(self, *args) -> None:
        if self.fh is not None:
            self.fh.close()

    def append(self, rows: Iterable[dict[str, str]]) -> int:
        if self.fh is None or self.platform_id is None:
            raise RuntimeError("SqlAppender must be opened before append")
        inserted = 0
        for row in rows:
            self.fh.write(_article_insert(self.next_article_id, self.platform_id, self.cfg, row))
            self.next_article_id += 1
            inserted += 1
        return inserted


def import_with_psql(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    start = sql.find('INSERT INTO ')
    if start < 0:
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sql", delete=False) as tmp:
        tmp.write(sql[start:])
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(_psql_cmd(["-f", str(tmp_path)]), check=True, env=_psql_env())
    finally:
        tmp_path.unlink(missing_ok=True)


def db_read_urls(cfg: SourceConfig) -> set[str]:
    if output_mode() != "psql":
        return set()
    sql = (
        f"select article_url from {_article_table()} "
        f"where newspaper={_sql(cfg.newspaper)} and language={_sql(cfg.lang)} "
        f"and category is not distinct from {_sql(_category(cfg))}"
    )
    return set(_psql_lines(sql))


def _psql_env() -> dict[str, str]:
    settings = psql_settings()
    if not settings["username"] or not settings["db_name"]:
        raise RuntimeError("KZ_MEDIA_PSQL_USERNAME and KZ_MEDIA_PSQL_DB_NAME are required when KZ_MEDIA_OUTPUT_MODE=psql")
    env = os.environ.copy()
    if settings["password"]:
        env["PGPASSWORD"] = settings["password"]
    if settings["sslmode"]:
        env["PGSSLMODE"] = settings["sslmode"]
    return env


def _psql_cmd(args: list[str]) -> list[str]:
    settings = psql_settings()
    return [
        "psql",
        "-h", settings["host"],
        "-p", settings["port"],
        "-U", settings["username"],
        "-d", settings["db_name"],
        "-v", "ON_ERROR_STOP=1",
        *args,
    ]


def _psql_lines(sql: str) -> list[str]:
    return subprocess.check_output(_psql_cmd(["-Atc", sql]), env=_psql_env(), text=True).splitlines()


def _psql_scalar(sql: str, default: int = 0) -> int:
    rows = _psql_lines(sql)
    return int(rows[0]) if rows and rows[0] else default


def _db_max_id(table: str, column: str) -> int:
    table_ref = _article_table() if table == "articles" else _platform_table()
    return _psql_scalar(f"select coalesce(max({_quote_ident(column)}), 0) from {table_ref}")


def _db_platform_id(cfg: SourceConfig) -> int | None:
    sql = (
        f"select platform_id from {_platform_table()} "
        f"where newspaper={_sql(cfg.newspaper)} and language={_sql(cfg.lang)} "
        f"and category is not distinct from {_sql(_category(cfg))} limit 1"
    )
    rows = _psql_lines(sql)
    return int(rows[0]) if rows else None


def _platform_id(path: Path, cfg: SourceConfig) -> int | None:
    if not path.exists():
        return None
    target = (cfg.newspaper, cfg.lang, _category(cfg))
    for match in _platform_re().finditer(path.read_text(encoding="utf-8", errors="ignore")):
        category = None if match.group(4) == "NULL" else _sql_value(match.group(4))
        if (_sql_value(match.group(2)), _sql_value(match.group(3)), category) == target:
            return int(match.group(1))
    return None


def _max_article_id(path: Path) -> int:
    if not path.exists():
        return 0
    ids = [int(value) for value in _article_id_re().findall(path.read_text(encoding="utf-8", errors="ignore"))]
    return max(ids, default=0)


def _max_platform_id(path: Path) -> int:
    if not path.exists():
        return 0
    ids = [int(match.group(1)) for match in _platform_re().finditer(path.read_text(encoding="utf-8", errors="ignore"))]
    return max(ids, default=0)


def _platform_insert(platform_id: int, cfg: SourceConfig) -> str:
    return (
        f'INSERT INTO {_platform_table()} ("platform_id", "newspaper", "language", "category") '
        f"VALUES ({platform_id}, {_sql(cfg.newspaper)}, {_sql(cfg.lang)}, {_sql(_category(cfg))});\n"
    )


def _article_insert(article_id: int, platform_id: int, cfg: SourceConfig, row: dict[str, str]) -> str:
    return (
        f'INSERT INTO {_article_table()} ("article_id", "platform_id", "newspaper", "language", "category", '
        '"article_url", "article_title", "article_date", "article_time", "article_author", "article_body") '
        f"VALUES ({article_id}, {platform_id}, {_sql(cfg.newspaper)}, {_sql(cfg.lang)}, {_sql(_category(cfg))}, "
        f"{_sql(row.get('url', ''))}, {_sql(row.get('title', ''))}, {_sql(row.get('date', ''))}, "
        f"{_sql(row.get('time', ''))}, {_sql(row.get('author', ''))}, {_sql(row.get('body', ''))});\n"
    )


def _category(cfg: SourceConfig) -> str | None:
    raw = cfg.extra.get("category") or str(cfg.save_path.parent if cfg.save_path.parent != Path(".") else "")
    return raw or None


def _sql(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _unquote_sql(value: str) -> str:
    return value.replace("''", "'")


def _sql_value(value: str) -> str:
    return _unquote_sql(value.strip("'"))


def _platform_table() -> str:
    platforms, _ = sql_table_names()
    return _table_ref(platforms)


def _article_table() -> str:
    _, articles = sql_table_names()
    return _table_ref(articles)


def _table_ref(name: str) -> str:
    schema = psql_settings()["schema"]
    table = _quote_ident(name)
    return f"{_quote_ident(schema)}.{table}" if schema else table


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_pattern(name: str) -> str:
    schema = psql_settings()["schema"]
    table = re.escape(_quote_ident(name))
    return rf"{re.escape(_quote_ident(schema))}\s*\.\s*{table}" if schema else table


def _article_re() -> re.Pattern[str]:
    _, articles = sql_table_names()
    return re.compile(
        rf"INSERT INTO {_table_pattern(articles)}.*?VALUES \(\d+, \d+, {VALUE_RE}, {VALUE_RE}, (?:NULL|{VALUE_RE}), ({VALUE_RE})",
        re.S,
    )


def _article_id_re() -> re.Pattern[str]:
    _, articles = sql_table_names()
    return re.compile(rf"INSERT INTO {_table_pattern(articles)}.*?VALUES \((\d+),", re.S)


def _platform_re() -> re.Pattern[str]:
    platforms, _ = sql_table_names()
    return re.compile(
        rf"INSERT INTO {_table_pattern(platforms)}.*?VALUES \((\d+), ({VALUE_RE}), ({VALUE_RE}), (NULL|{VALUE_RE})\)",
        re.S,
    )
