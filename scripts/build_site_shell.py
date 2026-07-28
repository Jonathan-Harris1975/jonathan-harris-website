#!/usr/bin/env python3
"""Build the canonical external site-shell contract used by AIMS-generated pages.

The website repository remains the single source of truth for the shared header,
footer, stylesheet and site UI script. This script publishes a versioned,
read-only shell artefact that downstream R2 content can consume without exposing
an application API.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://jonathan-harris.online").rstrip("/")
HEADER_PATH = ROOT / "assets" / "partials" / "header.html"
FOOTER_PATH = ROOT / "assets" / "partials" / "footer.html"
OUTPUT_ROOT = ROOT / "assets" / "site-shell"
RELEASE_MARKER = ROOT / "release.json"

ROOT_RELATIVE_ATTR_RE = re.compile(r'(?P<prefix>\b(?:href|src|action)\s*=\s*["\'])/(?!/)', re.IGNORECASE)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def release_sha() -> str:
    if RELEASE_MARKER.is_file():
        try:
            payload = json.loads(RELEASE_MARKER.read_text(encoding="utf-8"))
            value = str(payload.get("commit_sha") or "").strip()
            if value:
                return value
        except (OSError, json.JSONDecodeError):
            pass

    for key in ("CF_PAGES_COMMIT_SHA", "GITHUB_SHA", "SOURCE_VERSION"):
        value = os.environ.get(key, "").strip()
        if value:
            return value

    raise RuntimeError("Cannot build site shell without a release commit SHA.")


def make_external_html(fragment: str, base_url: str = SITE_BASE_URL) -> str:
    base = base_url.rstrip("/")
    return ROOT_RELATIVE_ATTR_RE.sub(lambda match: f'{match.group("prefix")}{base}/', fragment.strip())


def wrap_fragment(kind: str, html: str, version: str) -> str:
    upper = kind.upper()
    return (
        f"<!-- JH_SITE_SHELL_{upper}_START release={version} -->\n"
        f"{html.strip()}\n"
        f"<!-- JH_SITE_SHELL_{upper}_END -->\n"
    )


def build_site_shell(*, root: Path = ROOT, base_url: str = SITE_BASE_URL, version: str | None = None) -> dict:
    version = (version or release_sha()).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{7,128}", version):
        raise ValueError(f"Unsafe release SHA/version: {version!r}")

    header_source = (root / "assets" / "partials" / "header.html").read_text(encoding="utf-8")
    footer_source = (root / "assets" / "partials" / "footer.html").read_text(encoding="utf-8")
    header_html = wrap_fragment("header", make_external_html(header_source, base_url), version)
    footer_html = wrap_fragment("footer", make_external_html(footer_source, base_url), version)

    output_root = root / "assets" / "site-shell"
    version_dir = output_root / version
    version_dir.mkdir(parents=True, exist_ok=True)

    base = base_url.rstrip("/")
    version_path = f"assets/site-shell/{version}"
    manifest = {
        "schemaVersion": 1,
        "releaseSha": version,
        "siteBaseUrl": base,
        "headerUrl": urljoin(f"{base}/", f"{version_path}/header.html"),
        "footerUrl": urljoin(f"{base}/", f"{version_path}/footer.html"),
        "stylesheetUrl": urljoin(f"{base}/", f"assets/css/site.css?v={version}"),
        "siteUiScriptUrl": urljoin(f"{base}/", f"assets/js/site-ui.min.js?v={version}"),
        "headerSha256": sha256_text(header_html),
        "footerSha256": sha256_text(footer_html),
        "managedFamilies": ["newsletter-web", "blog", "blog-social", "transcripts"],
    }

    header_file = version_dir / "header.html"
    footer_file = version_dir / "footer.html"
    manifest_file = version_dir / "manifest.json"
    latest_file = output_root / "manifest.json"

    header_file.write_text(header_html, encoding="utf-8")
    footer_file.write_text(footer_html, encoding="utf-8")
    encoded_manifest = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_file.write_text(encoded_manifest, encoding="utf-8")
    latest_file.write_text(encoded_manifest, encoding="utf-8")

    return manifest


def main() -> int:
    manifest = build_site_shell()
    print(f"Published site-shell contract for release {manifest['releaseSha']}.")
    print(f"Latest manifest: {OUTPUT_ROOT / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
