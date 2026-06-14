from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import db_root_path
from .models import COLUMNS

REQUIRED_VALUE_FIELDS = ["newspaper", "url", "title", "date", "body", "rowdata"]


@dataclass(frozen=True)
class ScanResult:
    errors: list[dict[str, str]]
    output_path: Path


def strict_read_sqlite(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    con = sqlite3.connect(path)
    try:
        columns = {row[1] for row in con.execute('PRAGMA table_info("rows")').fetchall()}
        selected = [field for field in COLUMNS if field in columns]
        if not selected:
            return columns, []
        quoted = ", ".join(_quote(field) for field in selected)
        rows = [
            {field: str(value or "") for field, value in zip(selected, row)}
            for row in con.execute(f"SELECT {quoted} FROM rows ORDER BY id")
        ]
        return columns, rows
    finally:
        con.close()


def scan_roots(roots: list[Path], output: Path | None = None) -> ScanResult:
    if not roots:
        roots = [db_root_path()]
    resolved = [root.resolve() for root in roots]
    for root in resolved:
        if not root.exists():
            raise FileNotFoundError(str(root))
    output_path = output or _default_output_path(resolved[0])
    files = [path for path in _data_files(resolved) if path.resolve() != output_path.resolve()]
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            header, rows = strict_read_sqlite(path)
        except Exception:
            errors.append(_report_row(path, "file_open_error", ""))
            continue
        if not rows:
            errors.append(_report_row(path, "no_rows", ""))
        for field in COLUMNS:
            if field not in header:
                errors.append(_report_row(path, "missing_field", field))
        present_value_fields = [field for field in REQUIRED_VALUE_FIELDS if field in header]
        for field in present_value_fields:
            if any(not str(row.get(field, "") or "").strip() for row in rows):
                errors.append(_report_row(path, "missing_value", field))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ScanResult(errors=errors, output_path=output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan crawler SQLite outputs and write a JSON error report.")
    parser.add_argument("roots", nargs="*", help="Data roots or SQLite files to scan.")
    parser.add_argument("--output", help="Output JSON report path. Defaults to <first-root>/error_report.json.")
    args = parser.parse_args(argv)
    try:
        roots = [Path(root) for root in args.roots]
        output = Path(args.output).resolve() if args.output else None
        result = scan_roots(roots, output)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        print(f"error_check: {exc}", file=sys.stderr)
        return 2
    print(f"error_check: wrote {result.output_path} with {len(result.errors)} error(s)")
    return 1 if result.errors else 0


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _data_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() != ".sqlite":
                raise NotADirectoryError(str(root))
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.glob("*.sqlite"))
        else:
            raise FileNotFoundError(str(root))
    return sorted(dict.fromkeys(files))


def _default_output_path(root: Path) -> Path:
    return (root.parent if root.is_file() else root) / "error_report.json"


def _report_row(path: Path, error_type: str, field_name: str) -> dict[str, str]:
    platform, language = _platform_language(path.stem)
    return {
        "platform": platform,
        "category": "sqlite",
        "language": language,
        "error_type": error_type,
        "field_name": field_name,
        "file_name": path.name,
        "file_path": str(path),
    }


def _platform_language(stem: str) -> tuple[str, str]:
    if "_" not in stem:
        return stem, ""
    platform, language = stem.rsplit("_", 1)
    return platform, language
