from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Iterator

from .config import db_root_path
from .models import COLUMNS, SourceConfig

SQLITE_TIMEOUT_SECONDS = 60
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000


def final_db_path(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    root = db_root or db_root_path()
    return root / f"{cfg.newspaper}_{cfg.lang}.sqlite"


def existing_files(cfg: SourceConfig, db_root: Path | None = None) -> list[tuple[int, Path]]:
    path = final_db_path(cfg, db_root)
    return [(1, path)] if path.exists() else []


def ensure_final_db(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    path = final_db_path(cfg, db_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path)
    try:
        _ensure_schema(con)
        con.commit()
    finally:
        con.close()
    return path


def reset_final_db(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    path = final_db_path(cfg, db_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    for suffix in ("-journal", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    return ensure_final_db(cfg, db_root)


def read_rows(cfg: SourceConfig, db_root: Path | None = None) -> list[dict[str, str]]:
    return list(iter_rows(final_db_path(cfg, db_root)))


def read_urls(path: Path) -> set[str]:
    if path.suffix != ".sqlite":
        from .final_sql_db import read_urls as read_sql_urls
        return read_sql_urls(path)
    if not path.exists():
        return set()
    con = _connect(path)
    try:
        _ensure_schema(con)
        return {str(row[0] or "") for row in con.execute('SELECT "url" FROM rows WHERE "url" != ""')}
    finally:
        con.close()


def count_rows(path: Path) -> int:
    if not path.exists():
        return 0
    con = _connect(path)
    try:
        _ensure_schema(con)
        return int(con.execute("SELECT COUNT(*) FROM rows").fetchone()[0])
    finally:
        con.close()


def iter_rows(path: Path) -> Iterator[dict[str, str]]:
    if not path.exists():
        return
    con = _connect(path)
    try:
        _ensure_schema(con)
        selected_cols = ", ".join(_quote(col) for col in COLUMNS)
        for row in con.execute(f"SELECT {selected_cols} FROM rows ORDER BY id"):
            yield canonical_row(dict(zip(COLUMNS, row)))
    finally:
        con.close()


def rewrite_rows(cfg: SourceConfig, rows: list[dict[str, str]], db_root: Path | None = None) -> list[Path]:
    return rewrite_sorted_rows(cfg, sort_rows(rows), db_root)


def rewrite_sorted_rows(cfg: SourceConfig, rows: Iterable[dict[str, str]], db_root: Path | None = None) -> list[Path]:
    path = reset_final_db(cfg, db_root)
    append_rows(path, rows)
    return [path]


def append_rows(path: Path, rows: Iterable[dict[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path)
    inserted = 0
    try:
        _ensure_schema(con)
        placeholders = ", ".join("?" for _ in COLUMNS)
        quoted_cols = ", ".join(_quote(col) for col in COLUMNS)
        sql = f"INSERT INTO rows ({quoted_cols}) VALUES ({placeholders})"
        batch = ([str(canonical_row(row).get(col, "") or "") for col in COLUMNS] for row in rows)
        for values in batch:
            con.execute(sql, values)
            inserted += 1
        con.commit()
    finally:
        con.close()
    return inserted


def write_rows(cfg: SourceConfig, rows: list[dict[str, str]], rebuild: bool = False, db_root: Path | None = None) -> list[Path]:
    old_rows = [] if rebuild else read_rows(cfg, db_root)
    return rewrite_rows(cfg, merge_rows(old_rows, rows, rebuild=rebuild), db_root)


def canonical_row(row: dict[str, object]) -> dict[str, str]:
    return {col: str(row.get(col, "") or "") for col in COLUMNS}


def merge_rows(old_rows: Iterable[dict[str, str]], new_rows: Iterable[dict[str, str]], rebuild: bool = False) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    if not rebuild:
        for row in old_rows:
            url = str(row.get("url", "") or "")
            if url:
                merged[url] = canonical_row(row)
    for row in new_rows:
        url = str(row.get("url", "") or "")
        if url and (rebuild or url not in merged):
            merged[url] = canonical_row(row)
    return sort_rows(merged.values())


def sort_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        (canonical_row(row) for row in rows),
        key=lambda row: (
            row.get("newspaper", ""),
            _sort_date_key(row.get("date", "")),
            _sort_time_key(row.get("time", "")),
            row.get("url", ""),
        ),
    )


def _ensure_schema(con: sqlite3.Connection) -> None:
    cols = ", ".join(f"{_quote(col)} TEXT NOT NULL DEFAULT ''" for col in COLUMNS)
    con.execute(f"CREATE TABLE IF NOT EXISTS rows (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols})")
    existing = {row[1] for row in con.execute('PRAGMA table_info("rows")').fetchall()}
    for col in COLUMNS:
        if col not in existing:
            con.execute(f'ALTER TABLE rows ADD COLUMN {_quote(col)} TEXT NOT NULL DEFAULT ""')


def _connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=SQLITE_TIMEOUT_SECONDS)
    con.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA cache_size=-8192")
    con.execute("PRAGMA mmap_size=0")
    return con


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sort_date_key(value: str) -> str:
    value = (value or "").strip()
    return value if value else "9999-99-99"


def _sort_time_key(value: str) -> str:
    value = (value or "").strip()
    return value if value else "99:99"
