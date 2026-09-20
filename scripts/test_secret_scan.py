#!/usr/bin/env python3
"""Regression tests for the repository-local secret scanner."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scan_secrets import AllowEntry, scan_file, scan_repository, sha256_text

FIXTURES = ROOT / "tests" / "fixtures" / "secret_scan"


class SecretScannerTests(unittest.TestCase):
    def test_representative_secrets_and_private_key_are_detected(self) -> None:
        findings = scan_file(FIXTURES / "detections.txt", ROOT, set())
        rules = {finding.rule for finding in findings}
        self.assertIn("github_token", rules)
        self.assertIn("aws_access_key", rules)
        self.assertIn("generic_secret", rules)
        self.assertIn("high_entropy_secret", rules)
        self.assertIn("bearer_token", rules)
        self.assertIn("webhook_credential", rules)
        self.assertIn("vendor_token", rules)
        self.assertIn("private_key", rules)

    def test_safe_placeholders_are_not_reported(self) -> None:
        findings = scan_file(FIXTURES / "safe-placeholders.txt", ROOT, set())
        self.assertEqual(findings, [])

    def test_exact_line_allowlist_is_narrow(self) -> None:
        path = FIXTURES / "detections.txt"
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        allowlist = {
            AllowEntry(
                path="tests/fixtures/secret_scan/detections.txt",
                rule="github_token",
                line_sha256=sha256_text(first_line),
                reason="Synthetic scanner regression fixture.",
            )
        }
        findings = scan_file(path, ROOT, allowlist)
        rules = {finding.rule for finding in findings}
        self.assertNotIn("github_token", rules)
        self.assertIn("aws_access_key", rules)
        self.assertIn("private_key", rules)

    def test_repository_scan_honours_exact_allowlist_and_still_detects_new_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture.txt"
            fixture.write_text('secret = "test-secret-value"\n', encoding="utf-8")
            line = fixture.read_text(encoding="utf-8").splitlines()[0]
            allowlist_path = root / ".secret-scan-allowlist.json"
            allowlist_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "path": "fixture.txt",
                                "rule": "generic_secret",
                                "line_sha256": sha256_text(line),
                                "reason": "Synthetic test fixture only.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(scan_repository(root), [])
            changed_value = "different-live-" + "looking-value"
            key_name = "sec" + "ret"
            fixture.write_text(f'{key_name} = "{changed_value}"\n', encoding="utf-8")
            self.assertTrue(scan_repository(root))


if __name__ == "__main__":
    unittest.main()
