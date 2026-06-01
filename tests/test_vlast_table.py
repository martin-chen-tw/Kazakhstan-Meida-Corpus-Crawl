from __future__ import annotations

import unittest
from importlib import import_module
from unittest.mock import patch

vlast_table = import_module("Crawling.vlast.crawling_table")


class VlastTableTest(unittest.TestCase):
    def test_links_keep_only_current_language_section_articles(self) -> None:
        html = """
        <a href="/english/66402-in-kazakhstan-protecting-workers-rights-might-get-you-fired.html">English</a>
        <a href="/english/66402-in-kazakhstan-protecting-workers-rights-might-get-you-fired.html">Duplicate</a>
        <a href="/novosti/69256-godovaa-inflacia-v-kazahstane-v-aprele-sostavila-106.html">Russian</a>
        <a href="/english/?archive=1">Archive</a>
        """

        self.assertEqual(
            vlast_table._links(html, "https://vlast.kz/english/", "en"),
            ["https://vlast.kz/english/66402-in-kazakhstan-protecting-workers-rights-might-get-you-fired.html"],
        )

    def test_last_page_reads_archive_last_link(self) -> None:
        html = '<link href="/vlast-qazaqsha/27/?archive=1" rel="last">'

        self.assertEqual(vlast_table._last_page(html, "vlast-qazaqsha"), 27)

    def test_last_page_reads_plain_pagination_links(self) -> None:
        html = """
        <a href="/vlast-qazaqsha/6/?archive=1">6</a>
        <a href="/vlast-qazaqsha/7/?archive=1">7</a>
        <a href="/vlast-qazaqsha/8/?archive=1">Next</a>
        """

        self.assertEqual(vlast_table._last_page(html, "vlast-qazaqsha"), 8)

    def test_zero_limit_means_unlimited_not_empty(self) -> None:
        html = """
        <link href="/english/?archive=1" rel="self">
        <a href="/english/66402-in-kazakhstan-protecting-workers-rights-might-get-you-fired.html">English</a>
        """

        with (
            patch.dict("os.environ", {"NCCU_CRAWL_LIMIT": "0"}),
            patch.object(vlast_table, "_get", return_value=(html, 200)),
        ):
            rows = vlast_table.crawling_table("en")

        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
