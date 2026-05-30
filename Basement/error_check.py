from __future__ import annotations

import argparse
import sys
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET

from .config import db_root_path
from .excel_db import write_xlsx
from .models import COLUMNS

REPORT_COLUMNS = [
    "platform",
    "category",
    "language",
    "error_type",
    "field_name",
    "batch_number",
    "file_name",
    "file_path",
]
REQUIRED_VALUE_FIELDS = ["newspaper", "url", "title", "date", "body", "rowdata"]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class ScanResult:
    errors: list[dict[str, str]]
    output_path: Path


def strict_read_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(t.text or "" for t in item.findall(".//m:t", NS))
                for item in shared_root.findall("m:si", NS)
            ]
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
    for values in rows[1:]:
        if not any(str(value).strip() for value in values):
            continue
        values = values + [""] * (len(header) - len(values))
        out.append(dict(zip(header, values)))
    return out


def scan_roots(roots: list[Path], output: Path | None = None) -> ScanResult:
    if not roots:
        roots = [db_root_path()]
    resolved = [root.resolve() for root in roots]
    for root in resolved:
        if not root.exists():
            raise FileNotFoundError(str(root))
    output_path = output or _default_output_path(resolved[0])
    files = _xlsx_files(resolved)
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            rows = strict_read_xlsx(path)
        except Exception:
            errors.append(_report_row(path, resolved, "file_open_error", ""))
            continue
        header = set(rows[0].keys()) if rows else _strict_header(path)
        for field in COLUMNS:
            if field not in header:
                errors.append(_report_row(path, resolved, "missing_field", field))
        present_value_fields = [field for field in REQUIRED_VALUE_FIELDS if field in header]
        for field in present_value_fields:
            if any(not str(row.get(field, "") or "").strip() for row in rows):
                errors.append(_report_row(path, resolved, "missing_value", field))
    write_xlsx(output_path, errors, columns=REPORT_COLUMNS)
    return ScanResult(errors=errors, output_path=output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan crawler xlsx outputs and write an xlsx error report.")
    parser.add_argument("roots", nargs="*", help="Data roots, stage folders, group folders, or xlsx files to scan.")
    parser.add_argument("--output", help="Output xlsx report path. Defaults to <first-root>/error_report.xlsx.")
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


def _column_index(ref: str) -> int:
    value = 0
    for char in "".join(ch for ch in ref if ch.isalpha()):
        value = value * 26 + ord(char.upper()) - 64
    return max(0, value - 1)


def _strict_header(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    first = root.find(".//m:row", NS)
    if first is None:
        return set()
    values: list[str] = []
    for cell in first.findall("m:c", NS):
        idx = _column_index(cell.attrib.get("r", "A1"))
        while len(values) <= idx:
            values.append("")
        text = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
        values[idx] = unescape(text)
    return set(values)


def _xlsx_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() != ".xlsx":
                raise NotADirectoryError(str(root))
            files.append(root)
        elif root.is_dir():
            stage_dirs = [root / stage for stage in ("Stage_1", "Stage_2") if (root / stage).is_dir()]
            scan_dirs = stage_dirs or [root]
            for scan_dir in scan_dirs:
                files.extend(path for path in scan_dir.rglob("*.xlsx") if not path.name.startswith("~$"))
        else:
            raise FileNotFoundError(str(root))
    return sorted(dict.fromkeys(files))


def _default_output_path(root: Path) -> Path:
    return (root.parent if root.is_file() else root) / "error_report.xlsx"


def _report_row(path: Path, roots: list[Path], error_type: str, field_name: str) -> dict[str, str]:
    category, group = _category_and_group(path, roots)
    platform, language = _platform_language(group)
    return {
        "platform": platform,
        "category": category,
        "language": language,
        "error_type": error_type,
        "field_name": field_name,
        "batch_number": _batch_number(path),
        "file_name": path.name,
        "file_path": str(path),
    }


def _category_and_group(path: Path, roots: list[Path]) -> tuple[str, str]:
    parts = path.parts
    for stage in ("Stage_1", "Stage_2"):
        if stage in parts:
            index = parts.index(stage)
            group = parts[index + 1] if index + 1 < len(parts) else path.parent.name
            return "Stage_1" if stage == "Stage_2" else stage, group
    for root in roots:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        return (rel.parts[0] if len(rel.parts) > 1 else "unknown", path.parent.name)
    return "unknown", path.parent.name


def _platform_language(group: str) -> tuple[str, str]:
    if "_" not in group:
        return group, ""
    platform, language = group.rsplit("_", 1)
    return platform, language


def _batch_number(path: Path) -> str:
    stem = path.stem
    if "_" in stem:
        tail = stem.rsplit("_", 1)[-1]
        if tail.isdigit():
            return tail
    return ""
