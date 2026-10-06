#!/usr/bin/env python3
"""Decide whether failed GitHub Actions steps justify waking the Kilo repair agent."""
from __future__ import annotations

import re
import sys

# Kilo owns deterministic repository-controlled CI/runtime repair. The classifier
# intentionally works only from failed step names, so it must stay conservative:
# provider/account administration and transient runner plumbing are never inferred
# to be code defects, while repository build/deploy/runtime failures remain eligible.
ACTIONABLE_CHECK = re.compile(
    r"\b(test|pytest|vitest|jest|unit|integration|type(?:check)?|mypy|pyright|build|compile|"
    r"import|module|lint|format|prettier|eslint|ruff|schema|migration|lock(?:file)?|dependency|"
    r"dependencies|audit|vulnerab\w*|codeql|trivy|gitleaks|security|actionlint|container image|"
    r"deploy|deployment|cloudflare|pages|worker|runtime)\b",
    re.I,
)

# These names describe workflow/provider mechanics rather than a demonstrated
# repository defect. Mechanical autofix stays with autofix.ci; Kilo may handle a
# lint/format failure only when it is not itself an autofix job.
NON_KILO_CHECK = re.compile(
    r"\b(autofix|checkout|setup|cache|artifact|upload|download|runner|wait|attestation|scorecard|"
    r"permission|credential|secret|account|billing|quota)\b",
    re.I,
)


def repairable_failed_steps(steps: list[str]) -> list[str]:
    return [
        step
        for step in steps
        if ACTIONABLE_CHECK.search(step) and not NON_KILO_CHECK.search(step)
    ]


def main() -> int:
    steps = [line.strip() for line in sys.stdin if line.strip()]
    actionable = repairable_failed_steps(steps)
    if not actionable:
        print("No repository-repairable failed step identified; Kilo will not be triggered.")
        return 3
    for step in actionable[:12]:
        print(step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
