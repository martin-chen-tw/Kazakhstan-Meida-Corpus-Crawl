from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Basement.error_check import REPORT_COLUMNS, main, scan_roots, strict_read_xlsx
from Basement.excel_db import read_xlsx, write_xlsx
from Basement.models import COLUMNS


def _row(**overrides: str) -> dict[str, str]:
    row = {field: f"{field}-value" for field in COLUMNS}
    row.update(overrides)
    return row


class ErrorCheckTest(unittest.TestCase):
    def test_clean_tree_returns_no_errors_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "Stage_1" / "tengri_en" / "tengri_en_Stage1_1.xlsx"
            write_xlsx(path, [_row()])
            out = root / "report.xlsx"

            result = scan_roots([root], out)

            self.assertEqual(result.errors, [])
            self.assertEqual(read_xlsx(out), [])

    def test_missing_column_reports_missing_field(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "Stage_1" / "tengri_en" / "tengri_en_Stage1_1.xlsx"
            write_xlsx(path, [{"url": "https://example.test", "body": "body"}], columns=["url", "body"])

            result = scan_roots([root], root / "report.xlsx")

            self.assertIn("missing_field", {row["error_type"] for row in result.errors})
            self.assertIn("rowdata", {row["field_name"] for row in result.errors})

    def test_missing_required_value_reports_missing_value(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "Stage_1" / "tengri_en" / "tengri_en_Stage1_1.xlsx"
            write_xlsx(path, [_row(rowdata="")])

            result = scan_roots([root], root / "report.xlsx")

            self.assertIn(
                {
                    "platform": "tengri",
                    "category": "Stage_1",
                    "language": "en",
                    "error_type": "missing_value",
                    "field_name": "rowdata",
                    "batch_number": "1",
                    "file_name": "tengri_en_Stage1_1.xlsx",
                    "file_path": str(path),
                },
                result.errors,
            )

    def test_corrupt_xlsx_reports_file_open_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "Stage_1" / "tengri_en" / "tengri_en_Stage1_1.xlsx"
            path.parent.mkdir(parents=True)
            path.write_text("not a zip", encoding="utf-8")

            result = scan_roots([root], root / "report.xlsx")

            self.assertEqual(result.errors[0]["error_type"], "file_open_error")

    def test_strict_read_raises_but_regular_read_swallows_open_errors(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "broken.xlsx"
            path.write_text("not a zip", encoding="utf-8")

            with self.assertRaises(Exception):
                strict_read_xlsx(path)
            self.assertEqual(read_xlsx(path), [])

    def test_main_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            clean = root / "Stage_1" / "tengri_en" / "tengri_en_Stage1_1.xlsx"
            write_xlsx(clean, [_row()])
            self.assertEqual(main([str(root), "--output", str(root / "clean-report.xlsx")]), 0)

            write_xlsx(clean, [_row(body="")])
            self.assertEqual(main([str(root), "--output", str(root / "error-report.xlsx")]), 1)

            self.assertEqual(main([str(root / "missing")]), 2)

    def test_report_uses_required_columns(self) -> None:
        self.assertEqual(REPORT_COLUMNS, [
            "platform",
            "category",
            "language",
            "error_type",
            "field_name",
            "batch_number",
            "file_name",
            "file_path",
        ])


if __name__ == "__main__":
    unittest.main()
