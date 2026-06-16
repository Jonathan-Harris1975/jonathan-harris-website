#!/usr/bin/env python3
"""Validate the public static website health document and headers."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
health_path = ROOT / "health.json"
headers_path = ROOT / "_headers"

health = json.loads(health_path.read_text(encoding="utf-8"))
assert health.get("ok") is True, "health.json ok must be true"
assert health.get("status") == "healthy", "health.json status must be healthy"
assert health.get("service") == "WEBSITE", "health.json service must be WEBSITE"
assert health.get("deployment") == "cloudflare-pages", "unexpected deployment target"

headers = headers_path.read_text(encoding="utf-8")
assert "/health.json" in headers, "_headers must contain a health.json section"
section = headers.split("/health.json", 1)[1].split("\n/", 1)[0]
assert "no-store" in section.lower(), "health.json must not be cached"
assert "application/json" in section.lower(), "health.json must declare JSON content type"

print("Website health contract passed.")
