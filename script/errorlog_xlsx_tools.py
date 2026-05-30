from __future__ import annotations

import argparse
import importlib
import json
import re
import sqlite3
import sys
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Basement.config import db_root_path, list_newspapers, load_source_configs
from Basement.excel_db import read_xlsx, rewrite_rows
from Basement.models import COLUMNS
from Basement.parsing import date_from_url, slug_title
from Basement.sql_tmp_db import tmp_db_path


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
    "қаңтар": 1, "ақпан": 2, "наурыз": 3, "сәуір": 4, "мамыр": 5, "маусым": 6,
    "шілде": 7, "тамыз": 8, "қыркүйек": 9, "қазан": 10, "қараша": 11, "желтоқсан": 12,
}


def _column_index(ref: str) -> int:
    value = 0
    for char in "".join(ch for ch in ref if ch.isalpha()):
        value = value * 26 + ord(char.upper()) - 64
    return value - 1


def _read_any_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for row in root.findall(".//m:row", NS):
        values: list[str] = []
        for cell in row.findall("m:c", NS):
            idx = _column_index(cell.attrib.get("r", "A1"))
            while len(values) <= idx:
                values.append("")
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                text = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
            else:
                value = cell.find("m:v", NS)
                text = "" if value is None or value.text is None else value.text
                if cell_type == "s" and text:
                    text = shared[int(text)]
            values[idx] = unescape(text)
        rows.append(values)
    if not rows:
        return []
    header = rows[0]
    out: list[dict[str, str]] = []
    for row in rows[1:]:
        if not any(str(value).strip() for value in row):
            continue
        row = row + [""] * (len(header) - len(row))
        out.append(dict(zip(header, row)))
    return out


def _errorlog_rows(path: Path) -> list[dict[str, str]]:
    return _read_any_xlsx(path)


def _stage(row: dict[str, str]) -> str:
    path = row.get("file_path", "")
    if "Stage_2" in path:
        return "Stage_2"
    if "Stage1" in path or "Stage_1" in path:
        return "Stage_1"
    return "unknown"


def _local_path(row: dict[str, str], root: Path) -> Path | None:
    stage = _stage(row)
    if stage not in {"Stage_1", "Stage_2"}:
        return None
    group = Path(row.get("file_path", "")).parent.name
    return root / stage / group / str(row.get("file_name", ""))


def _config_by_group() -> dict[str, object]:
    configs = {}
    for newspaper in list_newspapers():
        try:
            for cfg in load_source_configs(newspaper):
                configs[Path(cfg.save_path).name] = cfg
        except Exception:
            continue
    return configs


def _parse_day(text: str) -> str:
    normalized = re.sub(r"[,.]", " ", str(text or "")).lower()
    patterns = [
        r"(\d{1,2})\s+([a-zа-яәіңғүұқөһ]+)\s+(20\d{2})",
        r"([a-zа-яәіңғүұқөһ]+)\s+(\d{1,2})\s+(20\d{2})",
        r"(20\d{2})\s+жылғы\s+(\d{1,2})\s+([a-zа-яәіңғүұқөһ]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if not match:
            continue
        if pattern.startswith("(["):
            month_name, day, year = match.groups()
        elif pattern.startswith("(20"):
            year, day, month_name = match.groups()
        else:
            day, month_name, year = match.groups()
        month = MONTHS.get(month_name)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return ""


def _fetch_metadata(newspaper: str, url: str) -> dict[str, str]:
    try:
        module = importlib.import_module(f"Crawling.{newspaper}.crawling_article")
        result = module.crawling_article(url, with_metadata=True)
        if isinstance(result, dict):
            return {key: str(value or "") for key, value in result.items()}
        return {"body": str(result or "")}
    except Exception:
        return {}


def _repair_row(newspaper: str, row: dict[str, str], fields: set[str]) -> tuple[int, dict[str, str]]:
    updated = dict(row)
    url = updated.get("url", "")
    title_fallback = updated.get("title", "") or slug_title(url)
    needs_fetch = any(not str(updated.get(field, "")).strip() for field in fields)
    meta = _fetch_metadata(newspaper, url) if needs_fetch and url else {}
    changed = 0
    if "title" in fields and not str(updated.get("title", "")).strip():
        value = meta.get("title", "") or title_fallback
        if value:
            updated["title"] = value
            changed += 1
    if "date" in fields and not str(updated.get("date", "")).strip():
        value = meta.get("date", "") or _parse_day(updated.get("title", "")) or _parse_day(meta.get("title", "")) or date_from_url(url)
        if value:
            updated["date"] = value[:10]
            changed += 1
    if "body" in fields and not str(updated.get("body", "")).strip():
        value = meta.get("body", "") or meta.get("description", "") or updated.get("title", "") or meta.get("title", "") or title_fallback
        if value:
            updated["body"] = value
            changed += 1
    return changed, updated


def validate(args: argparse.Namespace) -> int:
    root = db_root_path(args.db_root)
    rows = _errorlog_rows(Path(args.errorlog))
    summary = Counter()
    failures: list[dict[str, str]] = []
    cache: dict[Path, list[dict[str, str]] | None] = {}
    for error in rows:
        path = _local_path(error, root)
        stage = _stage(error)
        summary[f"{stage}_records"] += 1
        if path is None or not path.exists():
            summary[f"{stage}_missing_file"] += 1
            if stage == "Stage_1":
                failures.append({"reason": "missing_file", **error})
            continue
        if path not in cache:
            try:
                cache[path] = read_xlsx(path)
                summary[f"{stage}_opened_files"] += 1
            except Exception:
                cache[path] = None
        file_rows = cache[path]
        if file_rows is None:
            summary[f"{stage}_open_failed"] += 1
            failures.append({"reason": "open_failed", **error})
            continue
        field = str(error.get("field_name") or "")
        if field:
            blanks = sum(1 for row in file_rows if not str(row.get(field, "")).strip())
            if blanks:
                summary[f"{stage}_missing_values"] += blanks
                failures.append({"reason": "missing_value", "blank_rows": str(blanks), **error})
            else:
                summary[f"{stage}_field_clean"] += 1
        else:
            summary[f"{stage}_file_open_clean"] += 1
    report = {"summary": dict(summary), "failures": failures[: args.max_failures]}
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if any(item for item in failures if _stage(item) == "Stage_1") else 0


def repair(args: argparse.Namespace) -> int:
    root = db_root_path(args.db_root)
    configs = _config_by_group()
    wanted: dict[str, set[str]] = defaultdict(set)
    for error in _errorlog_rows(Path(args.errorlog)):
        if _stage(error) != "Stage_1":
            continue
        field = str(error.get("field_name") or "")
        if not field:
            continue
        group = Path(error.get("file_path", "")).parent.name
        wanted[group].add(field)
    total_changed = 0
    for group, fields in sorted(wanted.items()):
        cfg = configs.get(group)
        if cfg is None:
            print(f"[SKIP] no config for {group}")
            continue
        sql_path = tmp_db_path(cfg, root)
        if not sql_path.exists():
            print(f"[SKIP] no tmp sql for {group}: {sql_path}")
            continue
        con = sqlite3.connect(sql_path)
        try:
            rows = [
                {"id": row[0], **dict(zip(COLUMNS, row[1:]))}
                for row in con.execute(
                    f"SELECT id, {', '.join(chr(34) + col + chr(34) for col in COLUMNS)} FROM rows ORDER BY id"
                ).fetchall()
            ]
            targets = [row for row in rows if any(not str(row.get(field, "")).strip() for field in fields)]
            print(f"[REPAIR] {group}: fields={sorted(fields)} targets={len(targets)}")
            changed_rows: list[dict[str, str]] = []
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                future_map = {executor.submit(_repair_row, cfg.newspaper, row, fields): row for row in targets}
                for index, future in enumerate(as_completed(future_map), 1):
                    changed, updated = future.result()
                    if changed:
                        changed_rows.append(updated)
                    if index % 500 == 0:
                        print(f"[REPAIR] {group}: checked={index}/{len(targets)} changed={len(changed_rows)}")
            for row in changed_rows:
                assignments = ", ".join(f'"{field}" = ?' for field in COLUMNS)
                con.execute(
                    f"UPDATE rows SET {assignments} WHERE id = ?",
                    [str(row.get(field, "") or "") for field in COLUMNS] + [row["id"]],
                )
            con.commit()
            total_changed += len(changed_rows)
            if changed_rows:
                by_id = {row["id"]: row for row in changed_rows}
                rows = [by_id.get(row["id"], row) for row in rows]
                rewrite_rows(cfg, [{field: str(row.get(field, "") or "") for field in COLUMNS} for row in rows], root)
        finally:
            con.close()
    print(json.dumps({"changed_rows": total_changed}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "repair"):
        p = sub.add_parser(name)
        p.add_argument("--errorlog", default="ErrorLog.xlsx")
        p.add_argument("--db-root", default="/home/martin/Desktop/kz_media/data")
        p.add_argument("--report")
    sub.choices["validate"].add_argument("--max-failures", type=int, default=30)
    sub.choices["repair"].add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    return validate(args) if args.command == "validate" else repair(args)


if __name__ == "__main__":
    raise SystemExit(main())
