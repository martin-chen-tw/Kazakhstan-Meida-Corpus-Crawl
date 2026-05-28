from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from Basement.excel_db import read_xlsx, write_xlsx


class ExcelDbTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
