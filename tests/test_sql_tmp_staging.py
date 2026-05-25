from __future__ import annotations

import tempfile
import unittest
from datetime import date
from multiprocessing import Queue
from pathlib import Path

from Basement.excel_db import read_rows, write_xlsx
from Basement.models import SourceConfig
from Basement.runner import _write_pending_rows
from Basement.sql_tmp_db import append_tmp_rows, read_tmp_rows, reset_tmp_db, tmp_db_path


def _cfg() -> SourceConfig:
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


def _row(url: str, day: str, title: str) -> dict[str, str]:
    return {
        "newspaper": "tengri",
        "url": url,
        "title": title,
        "date": day,
        "time": "",
        "author": "",
        "body": title,
    }


class SqlTmpStagingTest(unittest.TestCase):
    def test_tmp_db_path_and_round_trip(self) -> None:
        cfg = _cfg()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = reset_tmp_db(cfg, root)
            self.assertEqual(path, root / "sql_tmp" / "tengri_en.sql")

            rows = [_row("https://example.test/1", "2020-01-01", "one")]
            append_tmp_rows(path, rows)

            self.assertEqual(read_tmp_rows(path), rows)

    def test_update_stages_rows_then_merges_once(self) -> None:
        cfg = _cfg()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            folder = root / "Stage_1" / cfg.save_path
            write_xlsx(folder / "tengri_en_Stage1_1.xlsx", [
                _row("https://example.test/existing", "2020-01-01", "existing"),
                _row("https://example.test/dup", "2020-01-02", "old dup"),
            ])

            pending, result = Queue(), Queue()
            pending.put(_row("https://example.test/dup", "2020-01-03", "new dup"))
            pending.put(_row("https://example.test/new", "2020-01-04", "new"))
            pending.put(None)

            _write_pending_rows(cfg, rebuild=False, db_root=root, flush_rows=1, pending_queue=pending, result_queue=result)

            info = result.get(timeout=1)
            rows = read_rows(cfg, root)
            self.assertEqual(info["tmp_db"], str(tmp_db_path(cfg, root)))
            self.assertEqual([row["url"] for row in rows], [
                "https://example.test/existing",
                "https://example.test/dup",
                "https://example.test/new",
            ])
            self.assertEqual([row["title"] for row in rows], ["existing", "old dup", "new"])

    def test_rebuild_stages_rows_then_reconstructs(self) -> None:
        cfg = _cfg()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            folder = root / "Stage_1" / cfg.save_path
            write_xlsx(folder / "tengri_en_Stage1_1.xlsx", [
                _row("https://example.test/old", "2020-01-01", "old"),
            ])

            pending, result = Queue(), Queue()
            pending.put(_row("https://example.test/newer", "2020-01-03", "newer"))
            pending.put(_row("https://example.test/new", "2020-01-02", "new"))
            pending.put(None)

            _write_pending_rows(cfg, rebuild=True, db_root=root, flush_rows=50, pending_queue=pending, result_queue=result)

            result.get(timeout=1)
            rows = read_rows(cfg, root)
            self.assertEqual([row["url"] for row in rows], [
                "https://example.test/new",
                "https://example.test/newer",
            ])


if __name__ == "__main__":
    unittest.main()
