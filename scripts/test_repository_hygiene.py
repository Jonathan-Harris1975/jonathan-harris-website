#!/usr/bin/env python3
"""Regression tests for repository-hygiene archive fallback behaviour."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_repository_hygiene import (
    blog_asset_issues,
    fallback_files,
    retired_hive_skills_issues,
    source_lint_issues,
)


class RepositoryHygieneFallbackTests(unittest.TestCase):
    def test_fallback_excludes_generator_owned_gitignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "scripts" / "source.py"
            generated = [
                root / "release.json",
                root / ".pytest_cache" / "v" / "cache" / "nodeids",
                root / "assets" / "site-shell" / "abc1234" / "manifest.json",
                root / "assets" / "site-shell" / "manifest.json",
                root / "scripts" / "data" / "manuscripts.json",
                root / "data" / "book-sample-chapters.json",
                root / "scripts" / "__pycache__" / "source.cpython-313.pyc",
            ]

            expected.parent.mkdir(parents=True, exist_ok=True)
            expected.write_text("print('source')\n", encoding="utf-8")
            for path in generated:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("generated\n", encoding="utf-8")

            self.assertEqual(fallback_files(root), [expected])

    def test_source_lint_issues_match_hive_line_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            js = root / "worker.js"
            py = root / "script.py"
            ignored = root / "test.mjs"
            js.write_text("x" * 201 + "\nconst ok = true;   \n", encoding="utf-8")
            py.write_text("x" * 200 + "\nprint('ok')\t\n", encoding="utf-8")
            ignored.write_text("x" * 250 + "   \n", encoding="utf-8")

            self.assertEqual(
                source_lint_issues([js, py, ignored], root=root),
                [
                    "line_too_long: worker.js:1 is 201 characters; maximum is 200",
                    "trailing_whitespace: worker.js:2",
                    "trailing_whitespace: script.py:2",
                ],
            )

    def test_retired_hive_skills_integration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "keep.js"
            retired_route = root / "api" / ("hive-" + "skills") / "[[path]].js"
            stale_config = root / "wrangler.toml"
            clean.write_text("export const ok = true;\n", encoding="utf-8")
            retired_route.parent.mkdir(parents=True)
            retired_route.write_text("export const stale = true;\n", encoding="utf-8")
            stale_config.write_text(
                'binding = "' + "HIVE_" + "SKILLS_BUCKET" + '"\n',
                encoding="utf-8",
            )

            issues = retired_hive_skills_issues(
                [clean, retired_route, stale_config],
                root=root,
            )

            self.assertIn(
                "retired_hive_skills_path: api/" + "hive-" + "skills/[[path]].js",
                issues,
            )
            self.assertTrue(
                any(issue.startswith("retired_hive_skills_marker: wrangler.toml") for issue in issues)
            )


    def test_blog_asset_guard_rejects_legacy_parallel_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "assets" / "js" / "blog.bundle.min.js"
            legacy = root / "assets" / "js" / "blog.min.js"
            active.parent.mkdir(parents=True)
            active.write_text("active", encoding="utf-8")
            legacy.write_text("legacy", encoding="utf-8")
            pages = []
            for relative in ("blog/index.html", "blog/weekly/index.html"):
                page = root / relative
                page.parent.mkdir(parents=True, exist_ok=True)
                page.write_text('<script src="/assets/js/blog.bundle.min.js"></script>', encoding="utf-8")
                pages.append(page)

            issues = blog_asset_issues([active, legacy, *pages], root=root)
            self.assertIn("retired_blog_asset_present: assets/js/blog.min.js", issues)

    def test_blog_asset_guard_requires_active_bundle_on_both_blog_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "assets" / "js" / "blog.bundle.min.js"
            active.parent.mkdir(parents=True)
            active.write_text("active", encoding="utf-8")
            blog = root / "blog" / "index.html"
            weekly = root / "blog" / "weekly" / "index.html"
            weekly.parent.mkdir(parents=True)
            blog.parent.mkdir(parents=True, exist_ok=True)
            blog.write_text('<script src="/assets/js/blog.bundle.min.js"></script>', encoding="utf-8")
            weekly.write_text("<html></html>", encoding="utf-8")

            issues = blog_asset_issues([active, blog, weekly], root=root)
            self.assertIn(
                "active_blog_asset_unreferenced: blog/weekly/index.html must load /assets/js/blog.bundle.min.js",
                issues,
            )


if __name__ == "__main__":
    unittest.main()
