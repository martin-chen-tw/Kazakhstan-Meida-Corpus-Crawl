from __future__ import annotations

import importlib
from pathlib import Path
import unittest
from unittest.mock import patch

from Basement.models import ArticleMeta
from Basement.runner import _download_row


class RunnerRowdataTest(unittest.TestCase):
    def test_download_row_propagates_metadata_rowdata(self) -> None:
        class ArticleModule:
            @staticmethod
            def crawling_article(url: str, with_metadata: bool = False) -> dict[str, str]:
                self.assertTrue(with_metadata)
                return {
                    "body": "clean body",
                    "rowdata": "<html><body>clean body</body></html>",
                    "title": "Title",
                    "date": "2020-01-01",
                    "time": "12:00:00",
                    "author": "Author",
                }

        with patch("Basement.runner._site_module", return_value=ArticleModule):
            row = _download_row("fake", ArticleMeta(newspaper="fake", lang="en", url="https://example.test/1"))

        self.assertEqual(row["body"], "clean body")
        self.assertEqual(row["rowdata"], "<html><body>clean body</body></html>")
        self.assertEqual(row["title"], "Title")
        self.assertEqual(row["date"], "2020-01-01")
        self.assertEqual(row["time"], "12:00:00")
        self.assertEqual(row["author"], "Author")

    def test_download_row_tolerates_legacy_string_result(self) -> None:
        class ArticleModule:
            @staticmethod
            def crawling_article(url: str, with_metadata: bool = False) -> str:
                return "legacy body"

        with patch("Basement.runner._site_module", return_value=ArticleModule):
            row = _download_row("fake", ArticleMeta(newspaper="fake", lang="en", url="https://example.test/legacy-title"))

        self.assertEqual(row["body"], "legacy body")
        self.assertEqual(row["rowdata"], "")
        self.assertEqual(row["title"], "legacy title")

    def test_generic_crawler_returns_raw_html_rowdata(self) -> None:
        html = "<html><head><title>Raw Title</title></head><body><article><p>Body text</p></article></body></html>"
        with patch("Basement.generic_crawler.get_text", return_value=html):
            module = importlib.import_module("Basement.generic_crawler")
            result = module.crawling_article("https://example.test/1", with_metadata=True)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["rowdata"], html)
        self.assertNotEqual(result["rowdata"], result["body"])

    def test_production_article_modules_declare_rowdata_contract(self) -> None:
        base = Path("Crawling")
        missing = []
        for path in sorted(base.glob("*/crawling_article.py")):
            if path.parts[-2].startswith("."):
                continue
            text = path.read_text(encoding="utf-8")
            if "with_metadata" not in text:
                continue
            if '"rowdata"' not in text and "'rowdata'" not in text:
                missing.append(str(path))

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
