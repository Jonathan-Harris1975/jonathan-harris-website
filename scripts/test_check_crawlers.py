"""Regression tests for live crawler publication validation."""
from __future__ import annotations

import unittest

from scripts import check_crawlers


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


if __name__ == "__main__":
    unittest.main()
