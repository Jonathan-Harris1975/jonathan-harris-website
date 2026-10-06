#!/usr/bin/env python3
"""Regression tests for the Kilo failure-routing boundary."""
from __future__ import annotations

import unittest

from kilo_failure_classifier import repairable_failed_steps


class KiloFailureClassifierTests(unittest.TestCase):
    def assertRepairable(self, step: str) -> None:
        self.assertEqual(repairable_failed_steps([step]), [step])

    def assertNotRepairable(self, step: str) -> None:
        self.assertEqual(repairable_failed_steps([step]), [])

    def test_deterministic_build_and_runtime_failures_route_to_kilo(self) -> None:
        for step in (
            "Build static site",
            "Compile application",
            "Resolve broken import",
            "Cloudflare Pages deployment verification",
            "Worker runtime smoke test",
            "Production deployment build",
        ):
            with self.subTest(step=step):
                self.assertRepairable(step)

    def test_non_mechanical_lint_and_format_failures_route_to_kilo(self) -> None:
        for step in (
            "ESLint validation",
            "Ruff lint",
            "Prettier format check",
            "actionlint workflow validation",
        ):
            with self.subTest(step=step):
                self.assertRepairable(step)

    def test_autofix_and_provider_plumbing_do_not_route_to_kilo(self) -> None:
        for step in (
            "autofix lint and format",
            "Checkout repository",
            "Set up Python",
            "Upload artifact",
            "Wait for deployment",
            "Cloudflare account permission check",
            "Deployment credential verification",
        ):
            with self.subTest(step=step):
                self.assertNotRepairable(step)


if __name__ == "__main__":
    unittest.main()
