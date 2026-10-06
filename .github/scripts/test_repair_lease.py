#!/usr/bin/env python3
from __future__ import annotations
import unittest
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
if __name__=="__main__": unittest.main()
