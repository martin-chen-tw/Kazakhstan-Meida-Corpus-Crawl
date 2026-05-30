from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from Basement.excel_db import read_rows, read_xlsx, write_xlsx
from Basement.models import COLUMNS, SourceConfig


class ExcelDbTest(unittest.TestCase):
    def _cfg(self) -> SourceConfig:
        return SourceConfig(
            newspaper="tengri",
            lang="en",
            save_path=Path("tengri_en"),
            base_filename="tengri_en_Stage1_",
            base_url="",
            article_base_url="",
            default_start_date=date(2000, 1, 1),
            sitemaps=[],
            extra={},
        )

    def test_default_columns_include_rowdata(self) -> None:
        self.assertEqual(COLUMNS, ["newspaper", "url", "title", "date", "time", "author", "body", "rowdata"])

    def test_write_xlsx_strips_invalid_xml_characters(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "rows.xlsx"
            write_xlsx(path, [{"url": "https://example.test/1", "body": "good\x00bad\x08text"}], columns=["url", "body"])

            with zipfile.ZipFile(path) as z:
                ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

            self.assertEqual(read_xlsx(path)[0]["body"], "goodbadtext")

    def test_write_xlsx_replaces_existing_file_with_valid_zip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "rows.xlsx"
            path.write_text("not a zip")

            write_xlsx(path, [{"url": "https://example.test/1"}], columns=["url"])

            with zipfile.ZipFile(path) as z:
                self.assertIn("xl/worksheets/sheet1.xml", z.namelist())

    def test_write_xlsx_defaults_include_rowdata_header(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "rows.xlsx"
            write_xlsx(path, [{"url": "https://example.test/1", "body": "body", "rowdata": "<html>raw</html>"}])

            self.assertEqual(read_xlsx(path)[0]["rowdata"], "<html>raw</html>")

    def test_read_rows_tolerates_old_xlsx_missing_rowdata(self) -> None:
        cfg = self._cfg()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "Stage_1" / cfg.save_path / "tengri_en_Stage1_1.xlsx"
            write_xlsx(path, [{"url": "https://example.test/1", "body": "body"}], columns=["url", "body"])

            self.assertEqual(read_rows(cfg, root)[0]["rowdata"], "")

    def test_large_rowdata_round_trips_through_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "rows.xlsx"
            rowdata = "<html>" + ("raw <tag> & text\n" * 4000) + "</html>"
            write_xlsx(path, [{"url": "https://example.test/1", "body": "body", "rowdata": rowdata}])

            with zipfile.ZipFile(path) as z:
                ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(read_xlsx(path)[0]["rowdata"], rowdata)


if __name__ == "__main__":
    unittest.main()
