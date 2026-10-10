#!/usr/bin/env python3
from __future__ import annotations
import unittest
import os
import json
from unittest.mock import patch
import repair_lease

class LeaseTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_scope_sensitive(self):
        a=repair_lease.fingerprint("o/r","ci","build","a"*40)
        b=repair_lease.fingerprint("o/r","ci","build","a"*40)
        c=repair_lease.fingerprint("o/r","ci","deploy","a"*40)
        self.assertEqual(a,b); self.assertNotEqual(a,c)
    def test_marker_round_trip(self):
        p={"version":1,"status":"active","fingerprint":"abc","owner":"kilo","fence":"f"}
        body=repair_lease.MARKER+__import__("json").dumps(p)+" -->"
        self.assertEqual(repair_lease.marker_payload(body),p)
    def test_untrusted_text_is_not_marker(self):
        self.assertIsNone(repair_lease.marker_payload("please use autonomy-lease"))

class LeaseSafetyTests(unittest.TestCase):
    def test_malformed_marker_shape_is_ignored(self):
        for value in ([], None, 3, "text"):
            self.assertIsNone(repair_lease.marker_payload(repair_lease.MARKER + json.dumps(value) + " -->"))

    def test_forged_comment_is_ignored(self):
        body = repair_lease.MARKER + json.dumps({"version": 1, "fingerprint": "fp", "status": "active"}) + " -->"
        rows = [{"id": 1, "body": body, "user": {"login": "attacker"}}]
        with patch.dict(os.environ, {"REPAIR_APP_LOGIN": "repair[bot]"}), patch.object(repair_lease, "_request", return_value=rows):
            self.assertIsNone(repair_lease.active_for_fingerprint("fp"))

    def test_truncated_history_fails_closed(self):
        with patch.dict(os.environ, {"REPAIR_APP_LOGIN": "repair[bot]"}), patch.object(repair_lease, "_request", return_value=[{}] * 100):
            with self.assertRaisesRegex(RuntimeError, "incomplete ownership"):
                repair_lease.all_lease_comments()

    def test_missing_writer_identity_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "REPAIR_APP_LOGIN"):
                repair_lease.all_lease_comments()

    def test_claim_requires_coordinator_before_reads(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(repair_lease, "active_for_fingerprint") as read:
            with self.assertRaisesRegex(RuntimeError, "serialized"):
                repair_lease.claim(1, "kilo", "ci", "build", "a" * 40)
            read.assert_not_called()

    def test_competing_writer_is_rejected(self):
        env = {"GITHUB_ACTIONS": "true", "AUTONOMY_WRITER_COORDINATOR": "1"}
        with patch.dict(os.environ, env), patch.object(repair_lease, "active_for_fingerprint", return_value={"owner": "cto"}):
            with self.assertRaisesRegex(RuntimeError, "already owned"):
                repair_lease.claim(1, "kilo", "ci", "build", "a" * 40)

if __name__=="__main__": unittest.main()

