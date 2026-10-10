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
        self.headers = {"Cache-Control": "no-store"}
        self.url = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self) -> int:
        return self._status

    def geturl(self):
        return self.url

    def read(self, limit=65537) -> bytes:
        return self._body[:limit]


class ReleaseGateTests(unittest.TestCase):
    def respond(self, payload, headers=None, redirect=False):
        def opener(req, **kwargs):
            response = _Response(payload)
            response.url = "https://other.invalid/release.json" if redirect else req.full_url
            if headers is not None:
                response.headers = headers
            return response
        return opener

    def test_expected_sha_prefers_explicit_value(self) -> None:
        with mock.patch.dict("os.environ", {"GITHUB_SHA": "from-env"}, clear=True):
            self.assertEqual(gate.expected_release_sha("explicit"), "explicit")

    def test_expected_sha_falls_back_to_github_sha(self) -> None:
        with mock.patch.dict("os.environ", {"GITHUB_SHA": "from-env"}, clear=True):
            self.assertEqual(gate.expected_release_sha(""), "from-env")

    def test_release_marker_must_match_exact_commit(self) -> None:
        with mock.patch.object(gate.request, "urlopen", side_effect=self.respond({"commit_sha": "b" * 40, "deployment": "cloudflare-pages", "branch": "main"})):
            ready, message = gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)
        self.assertFalse(ready)
        self.assertIn("waiting for " + "a" * 40, message)

    def test_release_marker_accepts_exact_commit(self) -> None:
        with mock.patch.object(gate.request, "urlopen", side_effect=self.respond({"commit_sha": "a" * 40, "deployment": "cloudflare-pages", "branch": "main"})):
            ready, message = gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)
        self.assertTrue(ready)
        self.assertIn("matches commit " + "a" * 40, message)

    def test_wrong_branch_is_rejected(self) -> None:
        with mock.patch.object(gate.request, "urlopen", side_effect=self.respond({"commit_sha": "a" * 40, "deployment": "cloudflare-pages", "branch": "preview"})):
            ready, _ = gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)
        self.assertFalse(ready)

    def test_invalid_sha_does_not_call_network(self) -> None:
        with mock.patch.object(gate.request, "urlopen") as urlopen:
            ready, _ = gate.live_release_matches("https://example.invalid/release.json", "short", 1)
        self.assertFalse(ready)
        urlopen.assert_not_called()

    def test_marker_shape_and_provider_fail_closed(self):
        for payload in ([], None, "text", 5, {"commit_sha": "a" * 40}):
            with self.subTest(payload=payload):
                with mock.patch.object(gate.request, "urlopen", side_effect=self.respond(payload)):
                    self.assertFalse(gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)[0])

    def test_redirect_cache_and_response_size_fail_closed(self):
        payload = {"commit_sha": "a" * 40, "deployment": "cloudflare-pages", "branch": "main"}
        cases = ({"redirect": True}, {"headers": {}}, {"headers": {"Cache-Control": "no-store", "Age": "2"}},
                 {"headers": {"Cache-Control": "no-store", "Age": "bad"}})
        for options in cases:
            with self.subTest(options=options):
                with mock.patch.object(gate.request, "urlopen", side_effect=self.respond(payload, **options)):
                    self.assertFalse(gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)[0])
        payload["padding"] = "x" * 70000
        with mock.patch.object(gate.request, "urlopen", side_effect=self.respond(payload)):
            self.assertFalse(gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)[0])

    def test_invalid_origin_does_not_call_network(self):
        for url in ("http://example.invalid/release.json", "https://user:pass@example.invalid/release.json",
                    "https://example.invalid/other", "https://example.invalid/release.json#fragment"):
            with mock.patch.object(gate.request, "urlopen") as network:
                self.assertFalse(gate.live_release_matches(url, "a" * 40, 1)[0])
                network.assert_not_called()

    def test_provider_unavailable_fails_closed(self):
        with mock.patch.object(gate.request, "urlopen", side_effect=gate.error.URLError("offline")):
            self.assertFalse(gate.live_release_matches("https://example.invalid/release.json", "a" * 40, 1)[0])

    def test_marker_only_never_probes_production_crawlers(self):
        args = ["gate", "--marker-only", "--require-release-sha", "--expected-sha", "a" * 40]
        with mock.patch.object(gate.sys, "argv", args), mock.patch.object(gate, "live_release_matches", return_value=(True, "ready")):
            with mock.patch.object(gate, "run_live_checks") as crawler:
                self.assertEqual(gate.main(), 0)
                crawler.assert_not_called()

    def test_marker_only_cannot_report_success_after_deadline(self):
        args = ["gate", "--marker-only", "--require-release-sha", "--expected-sha", "a" * 40, "--timeout-seconds", "1"]
        with mock.patch.object(gate.sys, "argv", args), mock.patch.object(gate, "live_release_matches", return_value=(True, "ready")):
            with mock.patch.object(gate.time, "monotonic", side_effect=[0, 0, 0, 2]):
                self.assertEqual(gate.main(), 1)

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
