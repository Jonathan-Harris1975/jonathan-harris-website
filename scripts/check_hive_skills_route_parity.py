#!/usr/bin/env python3
"""Fail the website build if duplicate HIVE skills routes drift apart."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "functions" / "api" / "hive-skills" / "[[path]].js"
LEGACY = ROOT / "api" / "hive-skills" / "[[path]].js"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    missing = [str(path.relative_to(ROOT)) for path in (CANONICAL, LEGACY) if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing HIVE skills route file(s): {', '.join(missing)}")
    canonical_sha = digest(CANONICAL)
    legacy_sha = digest(LEGACY)
    if canonical_sha != legacy_sha:
        raise SystemExit(
            "HIVE skills route drift detected: functions/api/hive-skills/[[path]].js "
            "is canonical and api/hive-skills/[[path]].js must remain byte-identical."
        )
    source = CANONICAL.read_text(encoding="utf-8")
    if '"audits"' in source:
        raise SystemExit("Public HIVE skills route must not expose the audits root.")
    print(f"HIVE skills route parity passed: sha256={canonical_sha}")


if __name__ == "__main__":
    main()
