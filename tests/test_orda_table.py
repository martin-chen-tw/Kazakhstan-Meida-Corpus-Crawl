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


if __name__ == "__main__":
    unittest.main()
