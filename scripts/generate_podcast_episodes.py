#!/usr/bin/env python3
"""Compatibility no-op for retired static podcast episode generation.

Podcast episode pages and related artefacts are hosted by the podcast/R2
pipeline. The website repository owns the podcast hub page only, which embeds
the external player that lists previous episodes.
"""
from __future__ import annotations


def main() -> int:
    print("Static podcast episode generation skipped: podcast episodes are not repo-owned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
