"""Regression tests for commit-specific production readiness gating."""
from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from scripts import wait_for_live_release as gate
from scripts import write_release_marker as marker


class _Response:
    def __init__(self, payload: dict[str, str], status: int = 200) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self._status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


class ReleaseGateTests(unittest.TestCase):
    def test_expected_sha_prefers_explicit_value(self) -> None:
        with mock.patch.dict("os.environ", {"GITHUB_SHA": "from-env"}, clear=True):
            self.assertEqual(gate.expected_release_sha("explicit"), "explicit")

    def test_expected_sha_falls_back_to_github_sha(self) -> None:
        with mock.patch.dict("os.environ", {"GITHUB_SHA": "from-env"}, clear=True):
            self.assertEqual(gate.expected_release_sha(""), "from-env")

    def test_release_marker_must_match_exact_commit(self) -> None:
        with mock.patch.object(gate.request, "urlopen", return_value=_Response({"commit_sha": "old"})):
            ready, message = gate.live_release_matches("https://example.invalid/release.json", "new", 1)
        self.assertFalse(ready)
        self.assertIn("waiting for new", message)

    def test_release_marker_accepts_exact_commit(self) -> None:
        with mock.patch.object(gate.request, "urlopen", return_value=_Response({"commit_sha": "new"})):
            ready, message = gate.live_release_matches("https://example.invalid/release.json", "new", 1)
        self.assertTrue(ready)
        self.assertIn("matches commit new", message)

    def test_pages_marker_prefers_cloudflare_commit_sha(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CF_PAGES_COMMIT_SHA": "cf-sha", "GITHUB_SHA": "github-sha"},
            clear=True,
        ):
            self.assertEqual(marker.resolve_commit_sha(), "cf-sha")

    def test_pages_marker_prefers_cloudflare_branch(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"CF_PAGES_BRANCH": "main", "GITHUB_REF_NAME": "fallback"},
            clear=True,
        ):
            self.assertEqual(marker.resolve_branch(), "main")



if __name__ == "__main__":
    unittest.main()
