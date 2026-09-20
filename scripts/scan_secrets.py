#!/usr/bin/env python3
"""Repository-local secret scanner for committed source and configuration files.

The scanner intentionally reports only file, line, rule and a one-way fingerprint.
Secret values are never written to stdout/stderr.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / ".secret-scan-allowlist.json"

TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "vendor",
}
EXCLUDED_PATH_PREFIXES = ("assets/site-shell/",)
MAX_FILE_BYTES = 4 * 1024 * 1024

SAFE_VALUE_RE = re.compile(
    r"(?ix)^(?:"
    r"(?:replace|insert|your|example|sample|dummy|fake|test|redacted|masked|changeme)[-_ .a-z0-9]*"
    r"|<[^>]+>"
    r"|\$\{[^}]+\}"
    r"|\{\{[^}]+\}\}"
    r")$"
)

RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "private_key",
        "private-key block",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "github_token",
        "GitHub token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b"),
    ),
    (
        "aws_access_key",
        "AWS access key ID",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    (
        "bearer_token",
        "bearer/API token",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}\b"),
    ),
    (
        "vendor_token",
        "vendor credential",
        re.compile(
            r"(?:\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"
            r"|\bxox[baprs]-[A-Za-z0-9-]{20,}\b"
            r"|\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"
            r"|\bnpm_[A-Za-z0-9]{24,}\b"
            r"|\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{20,}\b)"
        ),
    ),
    (
        "webhook_credential",
        "credential-bearing webhook URL",
        re.compile(
            r"https://(?:hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}"
            r"|(?:discord(?:app)?\.com)/api/webhooks/[0-9]+/[A-Za-z0-9._-]{20,})"
        ),
    ),
)

ASSIGNMENT_RE = re.compile(
    r"(?ix)\b("
    r"password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"webhook[_-]?secret|client[_-]?secret|private[_-]?token|secret[_-]?access[_-]?key"
    r")\b\s*[:=]\s*[\"']([^\"']{8,})[\"']"
)
ENTROPY_ASSIGNMENT_RE = re.compile(
    r"(?ix)\b(credential|signing[_-]?key|auth[_-]?key|service[_-]?key)\b\s*[:=]\s*[\"']([^\"']{20,})[\"']"
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    description: str
    line_sha256: str


@dataclass(frozen=True)
class AllowEntry:
    path: str
    rule: str
    line_sha256: str
    reason: str


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def looks_safe_placeholder(value: str) -> bool:
    return bool(SAFE_VALUE_RE.fullmatch(value.strip()))


def load_allowlist(path: Path = ALLOWLIST_PATH) -> set[AllowEntry]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError(f"Invalid secret-scan allowlist schema: {path}")

    entries: set[AllowEntry] = set()
    for raw in data["entries"]:
        entry = AllowEntry(
            path=str(raw.get("path", "")),
            rule=str(raw.get("rule", "")),
            line_sha256=str(raw.get("line_sha256", "")),
            reason=str(raw.get("reason", "")),
        )
        if not entry.path or not entry.rule or len(entry.line_sha256) != 64 or not entry.reason.strip():
            raise ValueError(f"Secret-scan allowlist entry is not tightly scoped: {raw!r}")
        entries.add(entry)
    return entries


def tracked_files(root: Path) -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [path for path in root.rglob("*") if path.is_file()]
    return [root / raw.decode("utf-8") for raw in output.split(b"\0") if raw]


def candidate_files(root: Path) -> Iterable[Path]:
    for path in tracked_files(root):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if any(relative_text.startswith(prefix) for prefix in EXCLUDED_PATH_PREFIXES):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def line_findings(relative: str, line_number: int, line: str) -> list[Finding]:
    findings: list[Finding] = []
    digest = sha256_text(line)
    for rule, description, pattern in RULES:
        if pattern.search(line):
            findings.append(Finding(relative, line_number, rule, description, digest))

    assignment = ASSIGNMENT_RE.search(line)
    if assignment and not looks_safe_placeholder(assignment.group(2)):
        findings.append(
            Finding(relative, line_number, "generic_secret", "hard-coded password or generic secret", digest)
        )

    entropy_assignment = ENTROPY_ASSIGNMENT_RE.search(line)
    if entropy_assignment:
        value = entropy_assignment.group(2).strip()
        if not looks_safe_placeholder(value) and shannon_entropy(value) >= 3.8:
            findings.append(
                Finding(relative, line_number, "high_entropy_secret", "high-entropy credential value", digest)
            )
    return findings


def scan_file(path: Path, root: Path, allowlist: set[AllowEntry]) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return findings

    for line_number, line in enumerate(lines, 1):
        for finding in line_findings(relative, line_number, line):
            allowed = AllowEntry(
                path=finding.path,
                rule=finding.rule,
                line_sha256=finding.line_sha256,
                reason="",
            )
            if any(
                entry.path == allowed.path
                and entry.rule == allowed.rule
                and entry.line_sha256 == allowed.line_sha256
                for entry in allowlist
            ):
                continue
            findings.append(finding)
    return findings


def scan_repository(root: Path = ROOT, allowlist_path: Path | None = None) -> list[Finding]:
    selected_allowlist = allowlist_path if allowlist_path is not None else root / ALLOWLIST_PATH.name
    allowlist = load_allowlist(selected_allowlist)
    findings: list[Finding] = []
    for path in candidate_files(root):
        findings.extend(scan_file(path, root, allowlist))
    return sorted(findings, key=lambda item: (item.path, item.line, item.rule))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked repository text files for likely committed secrets.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to scan.")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="Optional tightly scoped allowlist JSON. Defaults to <root>/.secret-scan-allowlist.json.",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    findings = scan_repository(root, args.allowlist)
    if not findings:
        print("Secret scan passed: no likely committed credentials detected.")
        return 0

    print(f"Secret scan failed: {len(findings)} likely credential finding(s). Values are intentionally redacted.")
    for finding in findings:
        print(
            f" - {finding.path}:{finding.line} [{finding.rule}] {finding.description}; "
            f"line-sha256={finding.line_sha256[:12]}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
