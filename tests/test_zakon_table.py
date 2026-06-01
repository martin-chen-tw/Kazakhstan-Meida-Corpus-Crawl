from __future__ import annotations

import unittest
from datetime import date
from importlib import import_module
from unittest.mock import patch

zakon_table = import_module("Crawling.zakon.crawling_table")


RU_PAGE = """
<article>
  <time>2026-05-30</time>
  <a href="/novosti/1234567-russian-title.html">Russian title</a>
</article>
"""

KZ_PAGE = """
<div>
  <span>30.05.2026</span>
  <a href="/vlast-kazakhstana/7654321-kazakh-title.html">Kazakh title</a>
</div>
"""


class ZakonTableTest(unittest.TestCase):
    def setUp(self) -> None:
        zakon_table._PAGE_CACHE.clear()

    def test_endpoint_construction(self) -> None:
        self.assertEqual(
            zakon_table._load_more_url("ru", 3),
            "https://www.zakon.kz/news/?handler=LoadMoreNews&p=3&type=list",
        )
        self.assertEqual(
            zakon_table._load_more_url("kz", 4),
            "https://kaz.zakon.kz/news/?handler=LoadMoreNews&p=4&type=list",
        )

    def test_ru_and_kz_fixtures_parse_article_rows(self) -> None:
        self.assertEqual(
            zakon_table._items_from_page_html(RU_PAGE, "ru")[0]["url"],
            "https://www.zakon.kz/novosti/1234567-russian-title.html",
        )
        kz = zakon_table._items_from_page_html(KZ_PAGE, "kz")[0]
        self.assertEqual(kz["url"], "https://kaz.zakon.kz/vlast-kazakhstana/7654321-kazakh-title.html")
        self.assertEqual(kz["date"], "2026-05-30")

    def test_page_cache_avoids_duplicate_fetches(self) -> None:
        with patch.object(zakon_table, "_bounded_get_text", return_value=RU_PAGE) as get_text:
            self.assertEqual(len(zakon_table._items_from_page("ru", 1)), 1)
            self.assertEqual(len(zakon_table._items_from_page("ru", 1)), 1)

        self.assertEqual(get_text.call_count, 1)

    def test_limit_and_with_metadata_false(self) -> None:
        pages = {
            "https://www.zakon.kz/news/?handler=LoadMoreNews&p=1&type=list": RU_PAGE,
            "https://www.zakon.kz/news/?handler=LoadMoreNews&p=2&type=list": "",
            "https://www.zakon.kz/news/?handler=LoadMoreNews&p=3&type=list": "",
        }

        def fake_get(url: str, retries: int = 2) -> str:
            return pages[url]

        with (
            patch.dict("os.environ", {"NCCU_CRAWL_LIMIT": "1"}),
            patch.object(zakon_table, "_bounded_get_text", side_effect=fake_get),
        ):
            urls = zakon_table.crawling_table("ru", with_metadata=False)

        self.assertEqual(urls, ["https://www.zakon.kz/novosti/1234567-russian-title.html"])

    def test_empty_pages_stop_without_sitemap(self) -> None:
        requested: list[str] = []

        def fake_get(url: str, retries: int = 2) -> str:
            requested.append(url)
            return ""

        with patch.object(zakon_table, "_bounded_get_text", side_effect=fake_get):
            rows = zakon_table.crawling_table("ru")

        self.assertEqual(rows, [])
        self.assertEqual(len(requested), zakon_table.CONSECUTIVE_EMPTY_STOP)
        self.assertFalse(any("sitemap" in url for url in requested))

    def test_duplicate_only_pages_stop(self) -> None:
        requested: list[str] = []

        def fake_get(url: str, retries: int = 2) -> str:
            requested.append(url)
            return RU_PAGE

        with patch.object(zakon_table, "_bounded_get_text", side_effect=fake_get):
            rows = zakon_table.crawling_table("ru")

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(requested), 1 + zakon_table.CONSECUTIVE_DUPLICATE_STOP)

    def test_date_window_stops_when_page_is_older(self) -> None:
        requested: list[str] = []

        def fake_get(url: str, retries: int = 2) -> str:
            requested.append(url)
            return RU_PAGE

        with patch.object(zakon_table, "_bounded_get_text", side_effect=fake_get):
            rows = zakon_table.crawling_table("ru", start_date=date(2026, 6, 1))

        self.assertEqual(rows, [])
        self.assertEqual(len(requested), 1)

    def test_max_page_cap_is_bounded(self) -> None:
        class Cfg:
            extra = {"max_load_more_page": "2"}

        with patch.object(zakon_table, "get_source_config", return_value=Cfg()):
            self.assertEqual(zakon_table._max_page(Cfg()), 2)


if __name__ == "__main__":
    unittest.main()
