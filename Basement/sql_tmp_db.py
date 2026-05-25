from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import db_root_path
from .models import COLUMNS, SourceConfig


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
    con = sqlite3.connect(path)
    try:
        _ensure_schema(con)
        con.commit()
    finally:
        con.close()
    return path


def append_tmp_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    con = sqlite3.connect(path)
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
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    try:
        _ensure_schema(con)
        quoted_cols = ", ".join(_quote(col) for col in COLUMNS)
        rows = con.execute(f"SELECT {quoted_cols} FROM rows ORDER BY id").fetchall()
    finally:
        con.close()
    return [dict(zip(COLUMNS, row)) for row in rows]


def read_tmp_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    con = sqlite3.connect(path)
    try:
        _ensure_schema(con)
        return {row[0] for row in con.execute('SELECT "url" FROM rows WHERE "url" != ""').fetchall()}
    finally:
        con.close()


def _ensure_schema(con: sqlite3.Connection) -> None:
    cols = ", ".join(f"{_quote(col)} TEXT NOT NULL DEFAULT ''" for col in COLUMNS)
    con.execute(f"CREATE TABLE IF NOT EXISTS rows (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols})")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
