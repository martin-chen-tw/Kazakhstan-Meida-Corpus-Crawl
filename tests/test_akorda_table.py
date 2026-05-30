from __future__ import annotations

import unittest
from importlib import import_module
from unittest.mock import patch


class AkordaTableDateTest(unittest.TestCase):
    def test_addresses_reads_h5_date_after_title(self) -> None:
        table = import_module("Crawling.akorda_addresses.crawling_table")
        html = """
        <h3><a href="/ru/addresses/addresses_of_president/sample-address">Sample</a></h3>
        <div class="summary">summary without date</div>
        <h5 class="mt-3">28 февраля 2007 года</h5>
        """

        with (
            patch.object(table, "get_text", return_value=html),
            patch.object(table, "_article_body_len", return_value=100),
        ):
            rows = table._rows_from_page("ru", 1)

        self.assertEqual(rows[0]["date"], "2007-02-28")

    def test_speeches_reads_h5_date_after_title(self) -> None:
        table = import_module("Crawling.akorda_speeches.crawling_table")
        html = """
        <h3><a href="/en/sample-speech-123">Sample</a></h3>
        <div class="summary">summary without date</div>
        <h5 class="mt-3">May 28 2026</h5>
        """

        with patch.object(table, "get_text", return_value=html):
            rows = table._rows_from_page("en", 1)

        self.assertEqual(rows[0]["date"], "2026-05-28")


if __name__ == "__main__":
    unittest.main()
