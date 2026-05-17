#!/usr/bin/env python3
"""Compatibility no-op for retired transcript RSS list generation.

Transcript objects are served from the transcript/R2 estate. The static website
repo keeps the transcript archive route, but it must not collect episode data
from the podcast RSS feed during builds.
"""
from __future__ import annotations


def main() -> int:
    print("Transcript RSS sync skipped: transcript assets are externally governed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
