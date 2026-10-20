#!/usr/bin/env python3
"""Validate the public static website health document and headers."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
health_path = ROOT / "health.json"
headers_path = ROOT / "_headers"

health = json.loads(health_path.read_text(encoding="utf-8"))
assert health.get("ok") is False, "static health fallback must not claim runtime health"
assert health.get("status") == "unverified", "static health fallback must identify unverified runtime"
assert health.get("service") == "WEBSITE", "health.json service must be WEBSITE"
assert health.get("deployment") == "cloudflare-pages", "unexpected deployment target"

headers = headers_path.read_text(encoding="utf-8")
assert "/health.json" in headers, "_headers must contain a health.json section"
section = headers.split("/health.json", 1)[1].split("\n/", 1)[0]
assert "no-store" in section.lower(), "health.json must not be cached"
assert "application/json" in section.lower(), "health.json must declare JSON content type"

function_path = ROOT / "functions" / "health.json.js"
assert function_path.is_file(), "dynamic Pages health function is required"
health_function = function_path.read_text(encoding="utf-8")
for binding in ("TRANSCRIPTS_BUCKET", "BLOG_BUCKET", "BLOG_IMAGES_BUCKET"):
    assert binding in health_function, f"health check must report {binding}"
assert 'list({ limit: 1 })' in health_function, "runtime access must be checked with a bounded read-only listing"
assert 'runtime_access: "unavailable"' in health_function
assert "CF_PAGES_COMMIT_SHA" in health_function, "health evidence must identify the deployed source revision"
assert "COGNIPAL_RATE_LIMIT_HEALTH" in health_function, "health check must probe the private CogniPal Worker"
assert "source_commit_sha" in health_function, "health check must verify CogniPal's exact source revision"


wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
for binding, bucket in (("TRANSCRIPTS_BUCKET", "transcripts"), ("BLOG_BUCKET", "blog"), ("BLOG_IMAGES_BUCKET", "blog-images")):
    assert f'binding     = "{binding}"' in wrangler, f"wrangler.toml missing binding {binding}"
    assert f'bucket_name = "{bucket}"' in wrangler, f"wrangler.toml bucket mismatch for {binding}"
assert 'binding = "COGNIPAL_RATE_LIMIT_HEALTH"' in wrangler, "Pages must privately bind to CogniPal health"
assert 'service = "cognipal-rate-limit"' in wrangler, "Pages health binding must target the rate-limit Worker"

transcript_function = (ROOT / "functions" / "transcripts" / "[[slug]].js").read_text(encoding="utf-8")
assert 'binding-missing' in transcript_function, "missing transcript binding must fail clearly"
assert 'read-failed' in transcript_function, "transcript R2 read errors must fail safely"
assert re.search(r'Math\.min\(configuredAttempts,\s*4\)', transcript_function), "podcast feed retries must remain bounded"

print("Website health and Pages R2 binding contract passed.")
