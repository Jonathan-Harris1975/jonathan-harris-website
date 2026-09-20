#!/usr/bin/env python3
"""Fail closed when the production dependency hash lock drifts or weakens."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECT_FILE = ROOT / "requirements.in"
LOCK_FILE = ROOT / "requirements.txt"

PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)$")
HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})$")

# This is the reviewed production closure for Python 3.13. Deliberately keeping
# the closure explicit means a new transitive package cannot enter production
# merely because an upstream package changes its metadata.
EXPECTED_LOCK = {
    "beautifulsoup4": "4.15.0",
    "charset-normalizer": "3.4.7",
    "et-xmlfile": "2.0.0",
    "openpyxl": "3.1.5",
    "pillow": "12.3.0",
    "pypdf": "6.19.0",
    "reportlab": "5.0.1",
    "soupsieve": "2.9",
    "typing-extensions": "4.16.0",
}


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_direct_requirements(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s\\]+)", line)
        if not match:
            raise ValueError(f"{path.name}:{number}: direct requirement must be exactly pinned: {line}")
        name, version = canonical_name(match.group(1)), match.group(2)
        if name in result:
            raise ValueError(f"{path.name}:{number}: duplicate direct requirement: {name}")
        result[name] = version
    return result


def parse_lock(path: Path) -> dict[str, tuple[str, tuple[str, ...]]]:
    result: dict[str, tuple[str, tuple[str, ...]]] = {}
    active_name: str | None = None
    active_version: str | None = None
    active_hashes: list[str] = []

    def finish() -> None:
        nonlocal active_name, active_version, active_hashes
        if active_name is None or active_version is None:
            return
        if len(set(active_hashes)) < 2:
            raise ValueError(f"{path.name}: {active_name} must carry at least two distinct SHA-256 hashes")
        if active_name in result:
            raise ValueError(f"{path.name}: duplicate locked requirement: {active_name}")
        result[active_name] = (active_version, tuple(active_hashes))
        active_name = None
        active_version = None
        active_hashes = []

    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        continued = stripped.endswith("\\")
        token = stripped[:-1].rstrip() if continued else stripped
        if token.startswith("--hash="):
            if active_name is None:
                raise ValueError(f"{path.name}:{number}: hash is not attached to a requirement")
            match = HASH_RE.fullmatch(token)
            if not match:
                raise ValueError(f"{path.name}:{number}: only sha256 hashes are permitted")
            active_hashes.append(match.group(1))
            continue

        finish()
        match = PIN_RE.fullmatch(token)
        if not match:
            raise ValueError(
                f"{path.name}:{number}: lock entries must be exact package==version pins with hashes: {stripped}"
            )
        if not continued:
            raise ValueError(f"{path.name}:{number}: locked requirement must continue onto SHA-256 hash lines")
        active_name = canonical_name(match.group(1))
        active_version = match.group(2)

    finish()
    return result


def main() -> int:
    direct = parse_direct_requirements(DIRECT_FILE)
    locked = parse_lock(LOCK_FILE)
    locked_versions = {name: version for name, (version, _hashes) in locked.items()}

    if locked_versions != EXPECTED_LOCK:
        missing = sorted(set(EXPECTED_LOCK) - set(locked_versions))
        extra = sorted(set(locked_versions) - set(EXPECTED_LOCK))
        mismatched = sorted(
            name
            for name in set(EXPECTED_LOCK) & set(locked_versions)
            if EXPECTED_LOCK[name] != locked_versions[name]
        )
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        if mismatched:
            details.append(
                "version_mismatch="
                + repr({name: (EXPECTED_LOCK[name], locked_versions[name]) for name in mismatched})
            )
        raise SystemExit("Production lock does not match the reviewed dependency closure: " + "; ".join(details))

    for name, version in direct.items():
        locked_version = locked_versions.get(name)
        if locked_version != version:
            raise SystemExit(
                f"Direct pin {name}=={version} is not represented exactly in requirements.txt "
                f"(locked={locked_version!r})"
            )

    print(
        f"Production dependency lock OK: {len(direct)} direct requirements, "
        f"{len(locked)} fully pinned/hash-locked packages."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
