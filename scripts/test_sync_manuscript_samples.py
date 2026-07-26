from __future__ import annotations

import unittest

from scripts.sync_manuscript_samples import _find_heading, find_first_chapter


def words(count: int, prefix: str = "body") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


class ManuscriptHeadingTests(unittest.TestCase):
    def test_dedicated_chapter_title_page_uses_following_body(self) -> None:
        pages = [
            "Table of Contents\nChapter 1\nChapter 2\nChapter 3\nChapter 4",
            "CHAPTER 1\nFoundations of Responsible AI",
            words(220),
            words(220, "more"),
            "CHAPTER 2\nApplying the Framework",
            words(220, "next"),
        ]
        start, heading, end = find_first_chapter(pages)
        self.assertEqual(start, 1)
        self.assertEqual(end, 4)
        self.assertEqual(heading, "CHAPTER 1: Foundations of Responsible AI")

    def test_inline_chapter_heading_remains_supported(self) -> None:
        pages = [
            "Chapter 1: Getting Started\n\n" + words(420),
            "Chapter 2: Next Steps\n\n" + words(420, "next"),
        ]
        start, heading, end = find_first_chapter(pages)
        self.assertEqual(start, 0)
        self.assertEqual(end, 1)
        self.assertEqual(heading, "Chapter 1: Getting Started")

    def test_numbered_heading_fallback_supports_older_layouts(self) -> None:
        pages = [
            "1. Foundations of AI Governance\n\n" + words(210),
            words(210, "continued"),
            "2. Risk and Accountability\n\n" + words(210, "risk"),
        ]
        start, heading, end = find_first_chapter(pages)
        self.assertEqual(start, 0)
        self.assertEqual(end, 2)
        self.assertEqual(heading, "1. Foundations of AI Governance")

    def test_body_line_is_not_appended_to_titled_chapter_heading(self) -> None:
        found = _find_heading("Chapter 1: Foundations\nA short opening sentence.\n" + words(100))
        self.assertEqual(found, ("Chapter 1: Foundations", "chapter"))


if __name__ == "__main__":
    unittest.main()
