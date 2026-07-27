#!/usr/bin/env python3
"""Write a build-specific release marker for post-deploy readiness checks."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release.json"


def first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def resolve_commit_sha() -> str:
    return first_env("CF_PAGES_COMMIT_SHA", "GITHUB_SHA", "SOURCE_VERSION") or git_sha() or "local"


def resolve_branch() -> str:
    return first_env("CF_PAGES_BRANCH", "GITHUB_REF_NAME") or "local"


def main() -> int:
    payload = {
        "commit_sha": resolve_commit_sha(),
        "branch": resolve_branch(),
        "deployment": "cloudflare-pages",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} for commit {payload['commit_sha']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
