from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .config import db_root_path
from .excel_db import EXCEL_CELL_TEXT_LIMIT, TRUNCATED_CELL_SUFFIX
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
    for suffix in ("-journal", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
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


def iter_tmp_rows(path: Path, *, sorted_for_output: bool = False, xlsx_compatible: bool = False) -> Iterator[dict[str, str]]:
    if not path.exists():
        return
    con = _connect(path)
    try:
        _ensure_schema(con)
        selected_cols = ", ".join(_select_column(col, xlsx_compatible) for col in COLUMNS)
        if sorted_for_output:
            keys = []
            for row_id, row_date, row_time in con.execute('SELECT id, "date", "time" FROM rows'):
                keys.append((_sort_date_key(row_date), _sort_time_key(row_date, row_time), row_id))
            for _, _, row_id in sorted(keys):
                row = con.execute(f"SELECT {selected_cols} FROM rows WHERE id = ?", (row_id,)).fetchone()
                if row is not None:
                    yield dict(zip(COLUMNS, row))
            return
        else:
            order_by = "id"
        for row in con.execute(f"SELECT {selected_cols} FROM rows ORDER BY {order_by}"):
            yield dict(zip(COLUMNS, row))
    finally:
        con.close()


def count_tmp_rows(path: Path) -> int:
    if not path.exists():
        return 0
    con = _connect(path)
    try:
        _ensure_schema(con)
        return int(con.execute("SELECT MAX(id) FROM rows").fetchone()[0] or 0)
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
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA cache_size=-8192")
    con.execute("PRAGMA mmap_size=0")
    return con


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _select_column(col: str, xlsx_compatible: bool) -> str:
    if col != "rowdata" or not xlsx_compatible:
        return _quote(col)
    keep = EXCEL_CELL_TEXT_LIMIT - len(TRUNCATED_CELL_SUFFIX)
    suffix = _quote_literal(TRUNCATED_CELL_SUFFIX)
    return (
        f"CASE WHEN substr({_quote(col)}, {keep + 1}, 1) != '' "
        f"THEN substr({_quote(col)}, 1, {keep}) || {suffix} "
        f"ELSE {_quote(col)} END AS {_quote(col)}"
    )


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sort_date_key(value: object) -> str:
    text = str(value or "")[:10]
    if len(text) == 10 and text[4] == "-" and text[7] == "-" and text.replace("-", "").isdigit():
        return text
    return "9999-12-31"


def _sort_time_key(row_date: object, row_time: object) -> str:
    text = str(row_time or "")
    if not text and "T" in str(row_date or ""):
        text = str(row_date or "").split("T", 1)[1]
    if "T" in text:
        text = text.split("T", 1)[1]
    text = text.split("+", 1)[0].split("Z", 1)[0][:8]
    if len(text) == 8 and text[2] == ":" and text[5] == ":":
        return text
    return "00:00:00"
