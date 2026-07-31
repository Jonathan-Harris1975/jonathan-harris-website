#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PREFIXES = (
    "artifacts/",
    "assets/site-shell/",
    "data/book-sample-chapters.json",
    "release.json",
    "scripts/__pycache__/",
    "scripts/data/manuscripts.json",
)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    inside = git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print("Generated-output drift check skipped: build is not running in a Git worktree.")
        return 0

    status = git("status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        print(status.stderr.strip() or "Could not inspect Git working-tree status.")
        return 1

    unexpected: list[str] = []
    for raw_line in status.stdout.splitlines():
        if not raw_line.strip():
            continue
        path_text = raw_line[3:].strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        path_text = path_text.strip('"')
        if any(path_text == prefix.rstrip("/") or path_text.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        unexpected.append(raw_line)

    if unexpected:
        print("Generated-output drift detected after the canonical build:")
        for line in unexpected:
            print(f"  {line}")
        print("Run the build locally, commit the regenerated files, and rerun CI.")
        return 1

    print("Generated-output drift check passed: the canonical build left the Git worktree clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
