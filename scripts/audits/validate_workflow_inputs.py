#!/usr/bin/env python3
"""Validate workflow_dispatch values before privileged audit steps consume them."""
from __future__ import annotations

import argparse
import os
import re
from urllib.parse import urlsplit

SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
BUCKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def value(name: str) -> str:
    return os.environ.get(name, "").strip()


def validate_https_url(name: str, raw: str, *, optional: bool = False, required_suffix: str = "") -> None:
    if not raw:
        if optional:
            return
        raise SystemExit(f"{name} is required")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} is not a valid URL: {exc}") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise SystemExit(f"{name} must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise SystemExit(f"{name} must not contain URL credentials")
    if required_suffix and not parsed.path.rstrip("/").endswith(required_suffix.rstrip("/")):
        raise SystemExit(f"{name} must end with {required_suffix}")



def validate_audit_reference(name: str, raw: str, *, optional: bool = False) -> None:
    if not raw:
        if optional:
            return
        raise SystemExit(f"{name} is required")
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} is not a valid storage reference: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme == "https":
        validate_https_url(name, raw, optional=optional)
        return
    if scheme == "r2":
        bucket = parsed.netloc.strip()
        if not bucket or not BUCKET_RE.fullmatch(bucket):
            raise SystemExit(f"{name} r2:// reference must contain a valid bucket name")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SystemExit(f"{name} r2:// reference must not contain credentials, query parameters or fragments")
        if parsed.path not in {"", "/"}:
            raise SystemExit(f"{name} r2:// reference must identify a bucket base, not an object key")
        return
    raise SystemExit(f"{name} must be an absolute HTTPS URL or r2://bucket reference")

def validate() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--callback-suffix", required=True)
    args = parser.parse_args()

    session_id = value("INPUT_SESSION_ID")
    if not SESSION_RE.fullmatch(session_id):
        raise SystemExit("session_id contains unsupported characters or exceeds 128 characters")

    report_prefix = value("INPUT_REPORT_PREFIX")
    if not PREFIX_RE.fullmatch(report_prefix):
        raise SystemExit("report_prefix must be a relative R2 key prefix using letters, numbers, '.', '_', '-' and '/'")
    if report_prefix.startswith("/") or any(part in {"", ".", ".."} for part in report_prefix.split("/")):
        raise SystemExit("report_prefix must not be absolute or contain empty, '.' or '..' path segments")

    validate_https_url("base_url", value("INPUT_BASE_URL"))
    validate_https_url("analysis_url", value("INPUT_ANALYSIS_URL"), optional=True)
    validate_https_url(
        "callback_url",
        value("INPUT_CALLBACK_URL"),
        optional=True,
        required_suffix=args.callback_suffix,
    )
    validate_audit_reference("audit_public_base_url", value("INPUT_AUDIT_PUBLIC_BASE_URL"), optional=True)

    exclude_prefixes = value("INPUT_EXCLUDE_PREFIXES")
    for prefix in [item.strip() for item in exclude_prefixes.split(",") if item.strip()]:
        if not prefix.startswith("/") or "\\" in prefix or any(ord(ch) < 0x20 for ch in prefix):
            raise SystemExit(f"exclude_prefixes contains an invalid route prefix: {prefix!r}")

    audit_bucket = value("INPUT_AUDIT_BUCKET")
    if audit_bucket and not BUCKET_RE.fullmatch(audit_bucket):
        raise SystemExit("audit_bucket contains unsupported characters")

    if value("INPUT_AUDIT_BUCKET_ENV") != "R2_BUCKET_AUDITS":
        raise SystemExit("audit_bucket_env must be R2_BUCKET_AUDITS")
    if value("INPUT_AUDIT_PUBLIC_BASE_ENV") != "R2_PUBLIC_BASE_URL_AUDITS":
        raise SystemExit("audit_public_base_env must be R2_PUBLIC_BASE_URL_AUDITS")


if __name__ == "__main__":
    validate()
