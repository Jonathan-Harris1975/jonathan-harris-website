#!/usr/bin/env python3
"""Compatibility no-op for the retired website podcast RSS sync.

The podcast landing page uses the embedded player for recent and previous
episodes. Podcast episode publishing, RSS, audio, and transcript artefacts are
governed outside this static website repository, so this script deliberately
does not fetch or persist podcast data.
"""
from __future__ import annotations


def main() -> int:
    print("Podcast RSS sync skipped: embedded player/R2 podcast estate is the source of truth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
