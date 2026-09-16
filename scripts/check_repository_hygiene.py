#!/usr/bin/env python3
"""Fail CI when tracked source hygiene regresses."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_LINE_LENGTH = 200
SOURCE_SUFFIXES = {".js", ".py"}
TEXT_SUFFIXES = {".js", ".json", ".md", ".mjs", ".py", ".sh", ".toml", ".txt", ".yaml", ".yml"}
HIVE_SKILLS_SEGMENT = "hive-" + "skills"
RETIRED_HIVE_SKILLS_PATHS = {
    f"api/{HIVE_SKILLS_SEGMENT}/[[path]].js",
    "data/" + HIVE_SKILLS_SEGMENT + "-config.json",
    "docs/hive-shared-" + "skills.md",
    f"functions/api/{HIVE_SKILLS_SEGMENT}/[[path]].js",
    "functions/_shared/" + HIVE_SKILLS_SEGMENT + "-route.js",
    "scripts/check_" + HIVE_SKILLS_SEGMENT.replace("-", "_") + "_route_parity.py",
    "scripts/setup-batch-1-" + "skills.sh",
}
RETIRED_HIVE_SKILLS_MARKERS = (
    HIVE_SKILLS_SEGMENT,
    "HIVE_" + "SKILLS_BUCKET",
    "R2_BUCKET_HIVE_" + "SKILLS",
    "R2_PUBLIC_BASE_URL_HIVE_" + "SKILLS",
    "skills@" + "latest add coreyhaines31/marketingskills",
)
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


def source_lint_issues(paths: list[Path], root: Path = ROOT) -> list[str]:
    """Return deterministic line-length and trailing-whitespace findings."""
    issues: list[str] = []
    for path in paths:
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        relative = path.relative_to(root)
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(),
            1,
        ):
            if len(line) > MAX_SOURCE_LINE_LENGTH:
                issues.append(
                    f"line_too_long: {relative}:{line_number} is {len(line)} characters; "
                    f"maximum is {MAX_SOURCE_LINE_LENGTH}"
                )
            if line.rstrip(" \t") != line:
                issues.append(f"trailing_whitespace: {relative}:{line_number}")
    return issues


def python_line_issues(paths: list[Path]) -> list[str]:
    """Backward-compatible helper for callers that only want Python line length."""
    issues: list[str] = []
    for path in paths:
        if path.suffix != ".py" or not path.is_file():
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(),
            1,
        ):
            if len(line) > MAX_SOURCE_LINE_LENGTH:
                relative = path.relative_to(ROOT)
                issues.append(
                    f"{relative}:{line_number} is {len(line)} characters; "
                    f"maximum is {MAX_SOURCE_LINE_LENGTH}"
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


def retired_hive_skills_issues(paths: list[Path], root: Path = ROOT) -> list[str]:
    """Reject the retired shared HIVE skills bucket integration and installer."""
    issues: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in RETIRED_HIVE_SKILLS_PATHS:
            issues.append(f"retired_hive_skills_path: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        contents = path.read_text(encoding="utf-8", errors="ignore")
        for marker in RETIRED_HIVE_SKILLS_MARKERS:
            if marker in contents:
                issues.append(f"retired_hive_skills_marker: {relative} contains {marker}")
    return sorted(issues)


def main() -> int:
    paths = tracked_files()
    lint_issues = source_lint_issues(paths)
    duplicates = duplicate_groups(paths)
    retired_skills_issues = retired_hive_skills_issues(paths)

    if not lint_issues and not duplicates and not retired_skills_issues:
        print(
            "Repository hygiene passed: no tracked byte-identical duplicates, "
            f"no JavaScript/Python lines exceed {MAX_SOURCE_LINE_LENGTH} characters, "
            "no JavaScript/Python lines contain trailing whitespace, "
            "and no retired HIVE skills bucket integration remains."
        )
        return 0

    print("Repository hygiene failures:")
    for issue in lint_issues:
        print(f" - {issue}")
    for group in duplicates:
        print(f" - duplicate_content: {', '.join(group)}")
    for issue in retired_skills_issues:
        print(f" - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
