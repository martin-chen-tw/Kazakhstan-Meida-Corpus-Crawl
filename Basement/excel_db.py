from __future__ import annotations
import ctypes, gc, re, shutil, subprocess, tempfile, zipfile
from datetime import date, time
from html import escape, unescape
from itertools import chain
from pathlib import Path
from typing import Iterable, Iterator
from xml.etree import ElementTree as ET
from .config import db_root_path, get_root_config
from .models import COLUMNS, SourceConfig

INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]")
XML_TEXT_CHUNK_SIZE = 4096
EXCEL_CELL_TEXT_LIMIT = 32767
TRUNCATED_CELL_SUFFIX = "\n...[truncated for xlsx]"
try:
    LIBC = ctypes.CDLL("libc.so.6")
except Exception:
    LIBC = None

def _col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s

def _xml_text(value: object) -> str:
    return escape(_excel_cell_text(value))


def _write_xml_text(sheet, value: object) -> None:
    text = _excel_cell_text(value)
    for start in range(0, len(text), XML_TEXT_CHUNK_SIZE):
        chunk = text[start:start + XML_TEXT_CHUNK_SIZE]
        if chunk:
            sheet.write(escape(chunk).encode("utf-8"))


def _excel_cell_text(value: object) -> str:
    text = INVALID_XML_CHARS.sub("", str(value or ""))
    if len(text) <= EXCEL_CELL_TEXT_LIMIT:
        return text
    keep = EXCEL_CELL_TEXT_LIMIT - len(TRUNCATED_CELL_SUFFIX)
    return text[:keep] + TRUNCATED_CELL_SUFFIX

def write_xlsx(path: Path, rows: list[dict[str, str]], columns: list[str] = COLUMNS) -> None:
    write_xlsx_stream(path, rows, columns)


def write_xlsx_stream(path: Path, rows: Iterable[dict[str, str]], columns: list[str] = COLUMNS) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    files = {
        '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        '_rels/.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    }
    if shutil.which("zip"):
        _write_xlsx_stream_external_zip(path, rows, columns, files)
        return
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items(): z.writestr(name, data)
            with z.open('xl/worksheets/sheet1.xml', 'w') as sheet:
                _write_sheet_xml(sheet, rows, columns)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _write_xlsx_stream_external_zip(path: Path, rows: Iterable[dict[str, str]], columns: list[str], files: dict[str, str]) -> None:
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.unlink(missing_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{path.name}.", dir=path.parent))
    try:
        for name, data in files.items():
            file_path = tmp_dir / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(data, encoding="utf-8")
        sheet_path = tmp_dir / "xl" / "worksheets" / "sheet1.xml"
        sheet_path.parent.mkdir(parents=True, exist_ok=True)
        with sheet_path.open("wb") as sheet:
            _write_sheet_xml(sheet, rows, columns)
        subprocess.run(["zip", "-q", "-r", str(tmp_path), "."], cwd=tmp_dir, check=True)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _write_sheet_xml(sheet, rows: Iterable[dict[str, str]], columns: list[str]) -> None:
    sheet.write(b'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>')
    for r, row in enumerate(chain([dict(zip(columns, columns))], rows), 1):
        sheet.write(f'<row r="{r}">'.encode("utf-8"))
        for c, name in enumerate(columns, 1):
            sheet.write(f'<c r="{_col(c)}{r}" t="inlineStr"><is><t>'.encode("utf-8"))
            _write_xml_text(sheet, row.get(name, ""))
            sheet.write(b'</t></is></c>')
        sheet.write(b'</row>')
    sheet.write(b'</sheetData></worksheet>')

def read_xlsx(path: Path) -> list[dict[str, str]]:
    try:
        with zipfile.ZipFile(path) as z: xml = z.read('xl/worksheets/sheet1.xml')
        root = ET.fromstring(xml); ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rows = []
        for row in root.findall('.//m:row', ns):
            vals = []
            for c in row.findall('m:c', ns):
                t = c.find('.//m:t', ns); v = c.find('m:v', ns)
                vals.append(unescape((t.text if t is not None else v.text if v is not None else '') or ''))
            rows.append(vals)
        if not rows: return []
        return [dict(zip(rows[0], vals)) for vals in rows[1:]]
    except Exception:
        return []

def canonical_row(row: dict[str, str]) -> dict[str, str]:
    return {col: str(row.get(col, "") or "") for col in COLUMNS}

def folder_for(cfg: SourceConfig, db_root: Path | None = None) -> Path:
    return (db_root or db_root_path()) / 'Stage_1' / cfg.save_path

def existing_files(cfg: SourceConfig, db_root: Path | None = None) -> list[tuple[int, Path]]:
    folder = folder_for(cfg, db_root); pat = re.compile(rf'^{re.escape(cfg.base_filename)}(\d+)\.xlsx$')
    return sorted((int(m.group(1)), p) for p in folder.glob('*.xlsx') if (m := pat.match(p.name)))

def read_rows(cfg: SourceConfig, db_root: Path | None = None) -> list[dict[str, str]]:
    return [canonical_row(r) for _, p in existing_files(cfg, db_root) for r in read_xlsx(p)]

def _parse_date(row: dict[str, str]) -> date:
    try:
        return date.fromisoformat(str(row.get("date", ""))[:10])
    except Exception:
        return date.max

def _parse_time(row: dict[str, str]) -> time:
    raw = str(row.get("time", "") or "")
    if not raw and "T" in str(row.get("date", "")):
        raw = str(row.get("date", "")).split("T", 1)[1]
    if "T" in raw:
        raw = raw.split("T", 1)[1]
    raw = raw.split("+", 1)[0].split("Z", 1)[0]
    try:
        return time.fromisoformat(raw[:8])
    except Exception:
        return time.min

def sort_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for _, row in sorted(enumerate(rows), key=lambda item: (_parse_date(item[1]), _parse_time(item[1]), item[0]))]

def merge_rows(old_rows: list[dict[str, str]], rows: list[dict[str, str]], rebuild: bool = False) -> list[dict[str, str]]:
    source_rows = [] if rebuild else list(old_rows)
    seen = {row.get("url") for row in source_rows if row.get("url")}
    for row in rows:
        url = row.get("url")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        source_rows.append(row)
    return sort_rows(source_rows)

def clear_rows(cfg: SourceConfig, db_root: Path | None = None) -> None:
    folder_for(cfg, db_root).mkdir(parents=True, exist_ok=True)
    for _, p in existing_files(cfg, db_root):
        p.unlink(missing_ok=True)

def merge_update(old_rows: list[dict[str, str]], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return merge_rows(old_rows, rows, rebuild=False)

def merge_rebuild(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return merge_rows([], rows, rebuild=True)

def rewrite_rows(cfg: SourceConfig, rows: list[dict[str, str]], db_root: Path | None = None) -> list[Path]:
    max_rows = int(get_root_config('extracting', 'save_xlsx_file_per_data', default=1000))
    rows = sort_rows(rows)
    return rewrite_sorted_rows(cfg, rows, db_root)


def rewrite_sorted_rows(cfg: SourceConfig, rows: Iterable[dict[str, str]], db_root: Path | None = None) -> list[Path]:
    max_rows = int(get_root_config('extracting', 'save_xlsx_file_per_data', default=1000))
    folder = folder_for(cfg, db_root); folder.mkdir(parents=True, exist_ok=True)
    clear_rows(cfg, db_root)
    written = []
    row_iter = iter(rows)
    idx = 1
    while True:
        try:
            first = next(row_iter)
        except StopIteration:
            break
        path = folder / f'{cfg.base_filename}{idx}.xlsx'
        write_xlsx_stream(path, _limited_rows(first, row_iter, max_rows))
        written.append(path)
        _release_memory()
        idx += 1
    return written


def _limited_rows(first: dict[str, str], rows: Iterator[dict[str, str]], limit: int) -> Iterator[dict[str, str]]:
    yield first
    for _ in range(limit - 1):
        try:
            yield next(rows)
        except StopIteration:
            return


def _release_memory() -> None:
    gc.collect()
    if LIBC is not None:
        try:
            LIBC.malloc_trim(0)
        except Exception:
            pass

def write_rows(cfg: SourceConfig, rows: list[dict[str, str]], rebuild: bool = False, db_root: Path | None = None) -> list[Path]:
    old_rows = [] if rebuild else read_rows(cfg, db_root)
    return rewrite_rows(cfg, merge_rows(old_rows, rows, rebuild=rebuild), db_root)
