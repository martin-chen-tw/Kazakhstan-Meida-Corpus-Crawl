from __future__ import annotations

import unittest
from importlib import import_module
from unittest.mock import Mock, patch

crawling_table = import_module("Crawling.orda.crawling_table")


class OrdaTableTest(unittest.TestCase):
    def test_reachable_article_url_skips_explicit_404(self) -> None:
        response = Mock(status_code=404)
        with patch.object(crawling_table.requests, "head", return_value=response):
            self.assertFalse(crawling_table._reachable_article_url("https://orda.kz/missing/"))

    def test_reachable_article_url_keeps_transient_request_errors(self) -> None:
        with patch.object(crawling_table.requests, "head", side_effect=crawling_table.requests.Timeout):
            self.assertTrue(crawling_table._reachable_article_url("https://orda.kz/maybe-valid/"))

    def test_reachable_article_url_falls_back_when_head_not_allowed(self) -> None:
        head_response = Mock(status_code=405)
        get_response = Mock(status_code=200)
        with (
            patch.object(crawling_table.requests, "head", return_value=head_response),
            patch.object(crawling_table.requests, "get", return_value=get_response),
        ):
            self.assertTrue(crawling_table._reachable_article_url("https://orda.kz/head-disabled/"))
        get_response.close.assert_called_once()

    def test_reachable_rows_uses_table_worker_pool(self) -> None:
        class FakeExecutor:
            seen_workers: list[int] = []

            def __init__(self, max_workers: int) -> None:
                self.seen_workers.append(max_workers)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def map(self, fn, urls):
                return [url.endswith("/keep/") for url in urls]

        rows = [
            {"url": "https://orda.kz/drop/"},
            {"url": "https://orda.kz/keep/"},
        ]

        with patch.object(crawling_table, "ThreadPoolExecutor", FakeExecutor):
            self.assertEqual(crawling_table._reachable_rows(rows), [rows[1]])
        self.assertEqual(FakeExecutor.seen_workers, [10])


if __name__ == "__main__":
    unittest.main()
