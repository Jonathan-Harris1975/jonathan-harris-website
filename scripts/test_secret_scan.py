#!/usr/bin/env python3
"""Regression tests for the repository-local secret scanner.

Synthetic credential-shaped values are assembled only inside temporary files so
repository scanners never have to allowlist credential-like test fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scan_secrets import AllowEntry, scan_file, scan_repository, sha256_text


def _write_detection_fixture(root: Path) -> Path:
    """Create representative secret patterns outside the committed repository."""
    path = root / "detections.txt"
    lines = [
        "github_token = \"" + "gh" + "p_" + "1234567890abcdefghijklmnopqrstuvwxyzABCD\"",
        "aws_access_key_id = \"" + "AK" + "IA" + "1234567890ABCDEF\"",
        "api_" + "key = \"Q7vP2nR8xL4mT9kW6cY3uF5jH1sD0aZB\"",
        "credential = \"fK9vQ2pLm7Xc4Rz8Wn5Ty1Hs6Da3Bj0E\"",
        "Authorization: " + "Bear" + "er eyJhbGciOiJIUzI1NiJ9.syntheticPayload.syntheticSignature",
        "webhook = \"https://hooks.slack.com/" + "services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX\"",
        "vendor_token = \"" + "sk_" + "live_1234567890abcdefghijklmnop\"",
        "-----BEGIN " + "PRIVATE KEY-----",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_safe_fixture(root: Path) -> Path:
    path = root / "safe-placeholders.txt"
    key_name = "api_" + "key"
    secret_name = "webhook_" + "secret"
    lines = [
        f'{key_name} = "REPLACE_WITH_API_KEY"',
        'password = "example-password"',
        f'{secret_name} = "${{WEBHOOK_SECRET}}"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class SecretScannerTests(unittest.TestCase):
    def test_representative_secrets_and_private_key_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = _write_detection_fixture(root)
            findings = scan_file(fixture, root, set())
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = _write_safe_fixture(root)
            findings = scan_file(fixture, root, set())
        self.assertEqual(findings, [])

    def test_exact_line_allowlist_is_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_detection_fixture(root)
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
            allowlist = {
                AllowEntry(
                    path="detections.txt",
                    rule="github_token",
                    line_sha256=sha256_text(first_line),
                    reason="Synthetic scanner regression fixture.",
                )
            }
            findings = scan_file(path, root, allowlist)
        rules = {finding.rule for finding in findings}
        self.assertNotIn("github_token", rules)
        self.assertIn("aws_access_key", rules)
        self.assertIn("private_key", rules)

    def test_repository_scan_honours_exact_allowlist_and_still_detects_new_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture.txt"
            key_name = "sec" + "ret"
            initial_value = "test-" + "secret-value"
            fixture.write_text(f'{key_name} = "{initial_value}"\n', encoding="utf-8")
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
            fixture.write_text(f'{key_name} = "{changed_value}"\n', encoding="utf-8")
            self.assertTrue(scan_repository(root))


if __name__ == "__main__":
    unittest.main()
