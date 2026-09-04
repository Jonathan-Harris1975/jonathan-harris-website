#!/usr/bin/env python3
"""Regression tests for repository-hygiene archive fallback behaviour."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_repository_hygiene import fallback_files


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


if __name__ == "__main__":
    unittest.main()
