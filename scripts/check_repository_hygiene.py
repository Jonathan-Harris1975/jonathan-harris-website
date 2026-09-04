#!/usr/bin/env python3
"""Fail CI when source hygiene regresses into duplicate tracked files or extreme Python lines."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAX_PYTHON_LINE_LENGTH = 200
FALLBACK_GENERATED_FILES = {
    "data/book-sample-chapters.json",
    "release.json",
    "scripts/data/manuscripts.json",
}
FALLBACK_GENERATED_PREFIXES = (".pytest_cache/", "assets/site-shell/")


def fallback_files(root: Path = ROOT) -> list[Path]:
    """Approximate ``git ls-files`` for source archives without Git metadata."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if ".git" in relative.parts or "__pycache__" in relative.parts:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if relative_text in FALLBACK_GENERATED_FILES:
            continue
        if any(relative_text.startswith(prefix) for prefix in FALLBACK_GENERATED_PREFIXES):
            continue
        files.append(path)
    return files


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return fallback_files()

    return [ROOT / raw.decode("utf-8") for raw in output.split(b"\0") if raw]


def python_line_issues(paths: list[Path]) -> list[str]:
    issues: list[str] = []
    for path in paths:
        if path.suffix != ".py" or not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if len(line) > MAX_PYTHON_LINE_LENGTH:
                relative = path.relative_to(ROOT)
                issues.append(
                    f"{relative}:{line_number} is {len(line)} characters; maximum is {MAX_PYTHON_LINE_LENGTH}"
                )
    return issues


def duplicate_groups(paths: list[Path]) -> list[list[str]]:
    by_digest: dict[tuple[int, bytes], list[str]] = defaultdict(list)
    for path in paths:
        if not path.is_file():
            continue
        data = path.read_bytes()
        if not data:
            continue
        relative = path.relative_to(ROOT).as_posix()
        by_digest[(len(data), hashlib.sha256(data).digest())].append(relative)

    return sorted(
        (sorted(group) for group in by_digest.values() if len(group) > 1),
        key=lambda group: group[0],
    )


def main() -> int:
    paths = tracked_files()
    line_issues = python_line_issues(paths)
    duplicates = duplicate_groups(paths)

    if not line_issues and not duplicates:
        print(
            "Repository hygiene passed: no tracked byte-identical duplicates and "
            f"no Python lines exceed {MAX_PYTHON_LINE_LENGTH} characters."
        )
        return 0

    print("Repository hygiene failures:")
    for issue in line_issues:
        print(f" - line_too_long: {issue}")
    for group in duplicates:
        print(f" - duplicate_content: {', '.join(group)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
