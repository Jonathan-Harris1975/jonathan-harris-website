#!/usr/bin/env python3
"""Validate that both HIVE skills route wrappers use one shared implementation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "functions" / "_shared" / "hive-skills-route.js"
PAGES_ROUTE = ROOT / "functions" / "api" / "hive-skills" / "[[path]].js"
LEGACY_ROUTE = ROOT / "api" / "hive-skills" / "[[path]].js"

EXPECTED_IMPORTS = {
    PAGES_ROUTE: '../../_shared/hive-skills-route.js',
    LEGACY_ROUTE: '../../functions/_shared/hive-skills-route.js',
}


def main() -> None:
    missing = [
        str(path.relative_to(ROOT))
        for path in (SHARED, PAGES_ROUTE, LEGACY_ROUTE)
        if not path.is_file()
    ]
    if missing:
        raise SystemExit(f"Missing HIVE skills route file(s): {', '.join(missing)}")

    shared_source = SHARED.read_text(encoding="utf-8")
    if 'export async function onRequest' not in shared_source:
        raise SystemExit("Shared HIVE skills route does not export onRequest.")
    if '"audits"' in shared_source:
        raise SystemExit("Public HIVE skills route must not expose the audits root.")

    for wrapper, expected_import in EXPECTED_IMPORTS.items():
        source = wrapper.read_text(encoding="utf-8")
        if expected_import not in source or 'export { onRequest }' not in source:
            relative = wrapper.relative_to(ROOT)
            raise SystemExit(
                f"HIVE skills route wrapper drift detected in {relative}: "
                f"expected shared import {expected_import!r}."
            )

    print("HIVE skills route parity passed: one shared implementation, two wrappers.")


if __name__ == "__main__":
    main()
