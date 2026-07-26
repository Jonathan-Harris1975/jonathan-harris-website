#!/usr/bin/env python3
"""Regression tests for generated ebook sample-page structured data."""
from __future__ import annotations

import json
import re
import unittest
from unittest.mock import patch

from scripts import ebook_pipeline


JSONLD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


class EbookSampleSchemaTests(unittest.TestCase):
    def test_genuine_sample_article_has_required_schema_fields(self) -> None:
        book = {
            "slug": "test-book",
            "title": "Test Book",
            "canonical_url": "https://jonathan-harris.online/ebooks/test-book/",
            "buy_route": "/ebooks/test-book/buy-now",
            "topic_slug": "artificial-intelligence",
            "datePublished": "2026-01-15",
            "dateModified": "2026-07-26T05:00:00Z",
        }
        sample = {
            "slug": "test-book",
            "chapter_title": "Chapter 1: A Real Chapter",
            "paragraphs": [
                "This is genuine manuscript text used to exercise the generated sample-page schema."
            ],
            "word_count": 12,
            "page_start": 5,
            "page_end": 6,
        }

        with (
            patch.object(ebook_pipeline, "load_book_sample_chapters", return_value={"test-book": sample}),
            patch.object(ebook_pipeline, "render_header", return_value="<header></header>"),
            patch.object(ebook_pipeline, "render_footer", return_value="<footer></footer>"),
        ):
            page = ebook_pipeline.render_book_sample_page(book)

        match = JSONLD_RE.search(page)
        self.assertIsNotNone(match)
        schema = json.loads(match.group(1))

        canonical = "https://jonathan-harris.online/ebooks/test-book/sample/"
        self.assertEqual(schema["@type"], "Article")
        self.assertEqual(schema["datePublished"], book["datePublished"])
        self.assertEqual(schema["dateModified"], book["dateModified"])
        self.assertEqual(
            schema["mainEntityOfPage"],
            {"@type": "WebPage", "@id": canonical},
        )
        self.assertEqual(schema["@id"], f"{canonical}#article")


if __name__ == "__main__":
    unittest.main()
