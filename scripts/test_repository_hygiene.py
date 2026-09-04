#!/usr/bin/env python3
"""Regression tests for repository-hygiene archive fallback behaviour."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_repository_hygiene import fallback_files, source_lint_issues


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


if __name__ == "__main__":
    unittest.main()
