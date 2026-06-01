from __future__ import annotations

import unittest
from importlib import import_module
from unittest.mock import patch

crawling_table = import_module("Crawling.orda.crawling_table")


class OrdaTableTest(unittest.TestCase):
    def test_crawling_table_skips_reachability_prefetch(self) -> None:
        class FakeExecutor:
            seen_workers: list[int] = []

            def __init__(self, max_workers: int) -> None:
                self.seen_workers.append(max_workers)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def map(self, fn, pages):
                return [
                    [
                        {
                            "url": "https://orda.kz/keep/",
                            "date": "2024-01-01",
                            "time": "2024-01-01T00:00:00+06:00",
                            "title": "",
                            "author": "",
                        }
                    ],
                    None,
                    None,
                    None,
                ]

        with patch.object(crawling_table, "ThreadPoolExecutor", FakeExecutor):
            rows = crawling_table.crawling_table("ru")
        self.assertEqual([row["url"] for row in rows], ["https://orda.kz/keep/"])
        self.assertEqual(FakeExecutor.seen_workers, [10])

    def test_staged_urls_reads_runner_env_path(self) -> None:
        with (
            patch.dict("os.environ", {"NCCU_STAGED_URL_DB": "/tmp/orda_ru.sql"}),
            patch.object(crawling_table, "read_tmp_urls", return_value={"https://orda.kz/staged/"}),
        ):
            self.assertEqual(crawling_table._staged_urls(), {"https://orda.kz/staged/"})


if __name__ == "__main__":
    unittest.main()
