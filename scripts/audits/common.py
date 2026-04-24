#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import boto3
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCLUDES: list[str] = []


@dataclass(slots=True)
class WorkbookInfo:
    path: str
    sheet_names: list[str]
    header_row: int | None
    primary_sheet: str | None
    url_count: int
    first_rows: list[list[Any]]
    urls: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value).strip()).strip("-._")
    return slug or "audit"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return path


def find_workbook(repo_root: Path = REPO_ROOT) -> Path:
    canonical = repo_root / "jonathan-harris-site-url-inventory-remediated-release-ready.xlsm"
    if canonical.exists():
        return canonical
    candidates = sorted(repo_root.glob("*site-url-inventory*.xls*"))
    if not candidates:
        raise FileNotFoundError("Workbook not found in repo root")
    return candidates[0]


def _find_header_row(rows: list[list[Any]]) -> tuple[int | None, dict[str, int]]:
    wanted = {
        "url": {"url", "page url", "live url", "public url", "full url", "public url path"},
    }
    for idx, row in enumerate(rows[:12], start=1):
        normalised = [str(cell).strip().lower() if cell is not None else "" for cell in row]
        found: dict[str, int] = {}
        for col_index, value in enumerate(normalised):
            for key, aliases in wanted.items():
                if value in aliases and key not in found:
                    found[key] = col_index
        if "url" in found:
            return idx, found
    return None, {}


def load_workbook_info(path: Path) -> WorkbookInfo:
    wb = load_workbook(path, read_only=True, data_only=True)
    sheet_names = list(wb.sheetnames)
    primary_sheet = "Pages" if "Pages" in wb.sheetnames else (sheet_names[0] if sheet_names else None)
    if primary_sheet is None:
        return WorkbookInfo(str(path), [], None, None, 0, [], [])

    ws = wb[primary_sheet]
    rows = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 12), values_only=True))
    header_row, cols = _find_header_row(rows)

    urls: list[str] = []
    if header_row and "url" in cols:
        url_col = cols["url"]
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            if url_col >= len(row):
                continue
            value = row[url_col]
            if not value:
                continue
            urls.append(str(value).strip())

    first_rows = [list(row) for row in rows[:5]]
    return WorkbookInfo(
        path=str(path),
        sheet_names=sheet_names,
        header_row=header_row,
        primary_sheet=primary_sheet,
        url_count=len(urls),
        first_rows=first_rows,
        urls=urls,
    )


def normalise_route(value: str, base_url: str | None = None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "/"
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        raw = parsed.path or "/"
    elif base_url and raw.startswith(base_url):
        parsed = urlparse(raw)
        raw = parsed.path or "/"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    raw = raw.replace("\\", "/")
    if raw.endswith("index.html"):
        raw = raw[: -len("index.html")]
    if raw == "/404.html":
        return raw
    if raw != "/" and raw.endswith("/"):
        raw = raw[:-1]
    return raw or "/"


def route_to_url(base_url: str, route: str) -> str:
    route = normalise_route(route)
    return urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))


def should_exclude(route: str, excludes: Iterable[str] | None = None) -> bool:
    check = normalise_route(route)
    prefixes = DEFAULT_EXCLUDES if excludes is None else list(excludes)
    for prefix in prefixes:
        prefix = normalise_route(prefix)
        if prefix == "/":
            continue
        if check == prefix or check.startswith(f"{prefix}/"):
            return True
    return False


def repo_html_routes(repo_root: Path = REPO_ROOT, excludes: Iterable[str] | None = None) -> list[str]:
    routes: list[str] = []
    for file_path in repo_root.rglob("index.html"):
        relative = file_path.relative_to(repo_root)
        if relative.parts[:2] == ("assets", "partials"):
            continue
        route = "/" + str(relative.parent).replace(os.sep, "/")
        if route == "/.":
            route = "/"
        route = normalise_route(route)
        if should_exclude(route, excludes):
            continue
        routes.append(route)

    root_404 = repo_root / "404.html"
    if root_404.exists():
        routes.append("/404.html")

    return sorted(set(routes))


def _build_headers() -> dict[str, str]:
    return {
        "User-Agent": "AI-management-suite/audits (+https://jonathan-harris.online)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def fetch_html(url: str, timeout: float = 20.0) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=timeout, headers=_build_headers())
        text = response.text or ""
        return {"ok": response.ok, "status": response.status_code, "text": text, "url": response.url}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "status": 0, "text": "", "url": url, "error": str(exc)}


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def extract_meta(soup: BeautifulSoup) -> dict[str, Any]:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    canonical = ""
    canonical_tag = soup.select_one("link[rel='canonical']")
    if canonical_tag and canonical_tag.get("href"):
        canonical = canonical_tag["href"].strip()

    meta_description = ""
    description_tag = soup.select_one("meta[name='description']")
    if description_tag and description_tag.get("content"):
        meta_description = description_tag["content"].strip()

    viewport = ""
    viewport_tag = soup.select_one("meta[name='viewport']")
    if viewport_tag and viewport_tag.get("content"):
        viewport = viewport_tag["content"].strip()

    h1 = soup.select_one("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""
    og_tags = {
        tag.get("property") or tag.get("name"): tag.get("content", "").strip()
        for tag in soup.select("meta[property^='og:'], meta[name^='og:']")
        if tag.get("content")
    }
    schema_count = len(soup.select("script[type='application/ld+json']"))

    return {
        "title": title,
        "canonical": canonical,
        "metaDescription": meta_description,
        "viewport": viewport,
        "h1": h1_text,
        "og": og_tags,
        "schemaCount": schema_count,
    }


def html_report_shell(title: str, body: str) -> str:
    generated = utc_now()
    return f'''<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title><style>
body{{font-family:Arial,Helvetica,sans-serif;margin:0;background:#f4f7fb;color:#111827;line-height:1.55;}}
main{{max-width:1180px;margin:0 auto;padding:40px 24px 72px;}}
header{{background:#0d1420;color:#fff;padding:28px 24px;}}
h1,h2,h3{{line-height:1.2;margin:0 0 12px;}}
section{{background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:24px;margin:20px 0;box-shadow:0 12px 30px rgba(13,20,32,.06);}}
table{{width:100%;border-collapse:collapse;font-size:14px;}}
th,td{{border-bottom:1px solid #e5e7eb;padding:10px 8px;text-align:left;vertical-align:top;}}
small,.muted{{color:#6b7280;}}
.badge{{display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;background:#eef2ff;color:#4338ca;}}
.badge.fail{{background:#fee2e2;color:#991b1b;}}
.badge.pass{{background:#dcfce7;color:#166534;}}
.badge.warn{{background:#fef3c7;color:#92400e;}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#f3f4f6;padding:2px 6px;border-radius:6px;}}
ul{{padding-left:20px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;}}
.kpi{{background:#0d1420;color:#fff;border-radius:18px;padding:18px;}}
a{{color:#4338ca;}}
</style></head><body><header><h1>{title}</h1><div class="muted">Generated {generated}</div></header><main>{body}</main></body></html>'''


def build_r2_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("R2_REGION", "auto"),
    )


def upload_directory_to_r2(client: Any, bucket: str, prefix: str, directory: Path) -> dict[str, str]:
    uploaded: dict[str, str] = {}
    public_base = os.environ["R2_PUBLIC_BASE_URL_BRAND_ASSETS"].rstrip("/")
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_dir():
            continue
        relative = file_path.relative_to(directory).as_posix()
        key = f"{prefix.rstrip('/')}/{relative}"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        client.upload_file(str(file_path), bucket, key, ExtraArgs={"ContentType": content_type})
        uploaded[relative] = f"{public_base}/{key}"
    return uploaded


def post_callback(callback_url: str | None, callback_token: str | None, payload: dict[str, Any]) -> None:
    if not callback_url:
        return
    headers = {"Content-Type": "application/json"}
    if callback_token:
        headers["Authorization"] = f"Bearer {callback_token}"
    response = requests.post(callback_url, headers=headers, data=json.dumps(payload), timeout=20)
    response.raise_for_status()
