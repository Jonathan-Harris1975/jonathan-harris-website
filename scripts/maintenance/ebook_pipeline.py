#!/usr/bin/env python3
"""Compatibility import path for the canonical ebook pipeline.

The maintained implementation lives in :mod:`scripts.ebook_pipeline`.  This
module remains importable so existing maintenance tooling does not break while
all behaviour comes from the canonical implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import ebook_pipeline as _canonical

__all__ = [name for name in dir(_canonical) if not name.startswith("_")]
globals().update({name: getattr(_canonical, name) for name in __all__})
