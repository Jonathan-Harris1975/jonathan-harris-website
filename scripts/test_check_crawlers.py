"""Regression tests for live crawler publication validation."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import check_crawlers, check_live_pages


SITE = "https://jonathan-harris.online"


def sitemap(*entries: tuple[str, str]) -> str:
    blocks = []
    for loc, lastmod in entries:
        lastmod_xml = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
        blocks.append(f"  <url>\n    <loc>{loc}</loc>{lastmod_xml}\n  </url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(blocks)
        + "\n</urlset>\n"
    )


class LiveSitemapValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
        )

    def validate(self, body: str) -> str | None:
        return check_crawlers.validate_live_body("sitemap", body, self.expected)

    def test_exact_governed_sitemap_passes(self) -> None:
        self.assertIsNone(self.validate(self.expected))

    def test_runtime_podcast_and_transcript_entries_are_allowed(self) -> None:
        live = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
            (f"{SITE}/podcast/episodes/ai-agents-authority-not-just-ability/", "2026-08-22"),
            (f"{SITE}/transcripts/TT-2026-08-22.html", "2026-08-22"),
        )
        self.assertIsNone(self.validate(live))

    def test_empty_weekly_archive_may_be_removed_at_runtime(self) -> None:
        live = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
        )
        self.assertIsNone(self.validate(live))

    def test_missing_governed_entry_fails(self) -> None:
        live = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/transcripts/", ""),
        )
        error = self.validate(live)
        self.assertIsNotNone(error)
        self.assertIn("missing governed entries", error or "")
        self.assertIn(f"{SITE}/podcast/", error or "")

    def test_governed_lastmod_drift_fails(self) -> None:
        live = sitemap(
            (f"{SITE}/", "2026-08-22"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
        )
        error = self.validate(live)
        self.assertIsNotNone(error)
        self.assertIn("lastmod values drift", error or "")

    def test_rogue_runtime_entry_fails(self) -> None:
        live = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
            (f"{SITE}/definitely-not-governed/", "2026-08-23"),
        )
        error = self.validate(live)
        self.assertIsNotNone(error)
        self.assertIn("ungoverned entries", error or "")

    def test_runtime_entry_rejects_query_strings_and_bad_dates(self) -> None:
        queried = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
            (f"{SITE}/podcast/episodes/example/?preview=1", "2026-08-23"),
        )
        self.assertIn("ungoverned entries", self.validate(queried) or "")

        bad_date = sitemap(
            (f"{SITE}/", "2026-08-23"),
            (f"{SITE}/blog/weekly/", ""),
            (f"{SITE}/podcast/", ""),
            (f"{SITE}/transcripts/", ""),
            (f"{SITE}/podcast/episodes/example/", "2026-99-99"),
        )
        self.assertIn("ungoverned entries", self.validate(bad_date) or "")


class RepositoryCrawlerPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.books = check_crawlers.load_master()

    def test_validation_snapshots_are_distinct_from_live_payloads(self) -> None:
        snapshots = check_crawlers.build_crawler_snapshot_paths(self.books)
        live_payloads = check_crawlers.build_crawler_snapshot_payloads(self.books)

        for path, snapshot in snapshots.items():
            live = live_payloads[path.name]
            self.assertNotEqual(snapshot, live)
            self.assertIn("Generated validation snapshot; not a publication target.", snapshot)
            self.assertNotIn("Generated validation snapshot; not a publication target.", live)

    def test_robot_typo_is_redirect_only(self) -> None:
        published = check_crawlers.build_published_crawler_paths(self.books)
        published_names = {path.name for path in published}
        self.assertIn("robots.txt", published_names)
        self.assertNotIn("robot.txt", published_names)

        redirects = (check_crawlers.ROOT / "_redirects").read_text(encoding="utf-8")
        self.assertRegex(redirects, r"(?m)^/robot\.txt\s+/robots\.txt\s+301\s*$")


class LiveBookApiParityTests(unittest.TestCase):
    """Guard live KDP catalogue parity without confusing two build clocks."""

    def check(self, live_book: dict, expected_book: dict) -> check_live_pages.PageResult:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "api" / "v1" / "books.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(json.dumps([expected_book]), encoding="utf-8")
            response = check_live_pages.FetchResult(
                body=json.dumps([live_book]),
                status_code=200,
                final_url=f"{SITE}/api/v1/books.json",
            )
            with (
                mock.patch.object(check_live_pages, "ROOT", root),
                mock.patch.object(check_live_pages, "fetch_url", return_value=response),
            ):
                return check_live_pages.run_api_contract_check(timeout=1)

    def book(self) -> dict:
        return {
            "id": 1,
            "slug": "example-ebook",
            "pages": 227,
            "datePublished": "2024-12-14",
            "dateModified": "2026-11-16T22:02:28Z",
            "buy_url": "https://mybook.to/known-link",
        }

    def test_independent_build_timestamps_do_not_trigger_false_failure(self) -> None:
        expected = self.book()
        live = {**expected, "dateModified": "2026-11-16T22:04:28Z"}
        self.assertTrue(self.check(live, expected).ok)

    def test_changed_book_page_count_is_still_a_failure(self) -> None:
        expected = self.book()
        live = {**expected, "dateModified": "2026-11-16T22:04:28Z", "pages": 240}
        self.assertFalse(self.check(live, expected).ok)

    def test_changed_purchase_link_is_still_a_failure(self) -> None:
        expected = self.book()
        live = {**expected, "buy_url": "https://example.com/different-book"}
        self.assertFalse(self.check(live, expected).ok)

    def test_invalid_date_modified_fails_closed(self) -> None:
        expected = self.book()
        live = {**expected, "dateModified": "not-a-date"}
        result = self.check(live, expected)
        self.assertFalse(result.ok)
        self.assertIn("invalid dateModified", result.message)

    def test_modified_before_publication_fails_closed(self) -> None:
        expected = self.book()
        live = {**expected, "dateModified": "2020-01-01"}
        result = self.check(live, expected)
        self.assertFalse(result.ok)
        self.assertIn("before datePublished", result.message)


if __name__ == "__main__":
    unittest.main()
