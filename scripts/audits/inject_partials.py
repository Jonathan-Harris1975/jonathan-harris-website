#!/usr/bin/env python3
"""Compatibility entry point for the canonical partial injector.

The maintained implementation lives in :mod:`scripts.inject_partials`.  Keep
this path operational for older tooling without maintaining a second copy of
the injection logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import inject_partials as _canonical

__all__ = [name for name in dir(_canonical) if not name.startswith("_")]
globals().update({name: getattr(_canonical, name) for name in __all__})

if __name__ == "__main__":
    raise SystemExit(_canonical.main())
