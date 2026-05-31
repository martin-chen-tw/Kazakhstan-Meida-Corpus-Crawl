from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .config import db_root_path
from .models import COLUMNS, SourceConfig

SQLITE_TIMEOUT_SECONDS = 60
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000


def tmp_db_path(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    root = db_root or db_root_path()
    return root / "sql_tmp" / f"{cfg.newspaper}_{cfg.lang}.sql"


def reset_tmp_db(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    path = tmp_db_path(cfg, db_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    return ensure_tmp_db(cfg, db_root)


def ensure_tmp_db(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    path = tmp_db_path(cfg, db_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path)
    try:
        _ensure_schema(con)
        con.commit()
    finally:
        con.close()
    return path


def append_tmp_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    con = _connect(path)
    try:
        _ensure_schema(con)
        placeholders = ", ".join("?" for _ in COLUMNS)
        quoted_cols = ", ".join(_quote(col) for col in COLUMNS)
        sql = f"INSERT INTO rows ({quoted_cols}) VALUES ({placeholders})"
        con.executemany(sql, [[str(row.get(col, "") or "") for col in COLUMNS] for row in rows])
        con.commit()
    finally:
        con.close()


def read_tmp_rows(path: Path) -> list[dict[str, str]]:
    return list(iter_tmp_rows(path))


def iter_tmp_rows(path: Path, *, sorted_for_output: bool = False) -> Iterator[dict[str, str]]:
    if not path.exists():
        return
    con = _connect(path)
    try:
        _ensure_schema(con)
        quoted_cols = ", ".join(_quote(col) for col in COLUMNS)
        if sorted_for_output:
            order_by = (
                'CASE WHEN substr("date", 1, 10) GLOB "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]" '
                'THEN substr("date", 1, 10) ELSE "9999-12-31" END, '
                'CASE WHEN "time" != "" THEN substr("time", 1, 8) '
                'WHEN instr("date", "T") > 0 THEN substr(substr("date", instr("date", "T") + 1), 1, 8) '
                'ELSE "00:00:00" END, '
                "id"
            )
        else:
            order_by = "id"
        for row in con.execute(f"SELECT {quoted_cols} FROM rows ORDER BY {order_by}"):
            yield dict(zip(COLUMNS, row))
    finally:
        con.close()


def count_tmp_rows(path: Path) -> int:
    if not path.exists():
        return 0
    con = _connect(path)
    try:
        _ensure_schema(con)
        return int(con.execute("SELECT COUNT(*) FROM rows").fetchone()[0] or 0)
    finally:
        con.close()


def read_tmp_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    con = _connect(path)
    try:
        _ensure_schema(con)
        return {row[0] for row in con.execute('SELECT "url" FROM rows WHERE "url" != ""').fetchall()}
    finally:
        con.close()


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
    return con


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
