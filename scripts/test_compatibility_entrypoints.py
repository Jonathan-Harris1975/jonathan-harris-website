#!/usr/bin/env python3
"""Regression tests for retained legacy script import/entry-point paths."""
from __future__ import annotations

import unittest

from scripts import check_identifiers, check_redirect_chains, ebook_pipeline, inject_partials
from scripts.audits import inject_partials as audit_inject_partials
from scripts.maintenance import check_identifiers as maintenance_identifiers
from scripts.maintenance import check_redirect_chains as maintenance_redirects
from scripts.maintenance import ebook_pipeline as maintenance_ebook_pipeline


class CompatibilityEntrypointTests(unittest.TestCase):
    def test_maintenance_ebook_pipeline_uses_canonical_implementation(self) -> None:
        self.assertIs(maintenance_ebook_pipeline.load_master, ebook_pipeline.load_master)
        self.assertEqual(maintenance_ebook_pipeline.ROOT, ebook_pipeline.ROOT)

    def test_audit_partial_injector_uses_canonical_implementation(self) -> None:
        self.assertIs(audit_inject_partials.inject, inject_partials.inject)
        self.assertIs(audit_inject_partials.validate, inject_partials.validate)
        self.assertEqual(audit_inject_partials.ROOT, inject_partials.ROOT)

    def test_maintenance_identifier_checker_uses_canonical_implementation(self) -> None:
        self.assertIs(maintenance_identifiers.main, check_identifiers.main)

    def test_maintenance_redirect_checker_uses_canonical_implementation(self) -> None:
        self.assertIs(maintenance_redirects.run_redirect_checks, check_redirect_chains.run_redirect_checks)
        self.assertIs(maintenance_redirects.validate_support_redirects, check_redirect_chains.validate_support_redirects)

    def test_canonical_redirect_checker_resolves_repository_root(self) -> None:
        self.assertEqual(check_redirect_chains.REPO_ROOT, ebook_pipeline.ROOT)


if __name__ == "__main__":
    unittest.main()
