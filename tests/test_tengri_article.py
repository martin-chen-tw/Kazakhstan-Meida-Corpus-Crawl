import unittest

from Crawling.tengri.crawling_article import _author


class TengriArticleTests(unittest.TestCase):
    def test_author_fallback_handles_missing_author_metadata(self):
        html = "<html><body><article><p>Body only.</p></article></body></html>"

        self.assertEqual(_author(html), "")

    def test_author_fallback_extracts_plain_author_label(self):
        html = "<html><body>Author: Staff Writer\n<article></article></body></html>"

        self.assertEqual(_author(html), "Staff Writer")


if __name__ == "__main__":
    unittest.main()
