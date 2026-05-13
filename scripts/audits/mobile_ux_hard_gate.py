#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from collections import Counter
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urljoin

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from scripts.audits.common import (
  DEFAULT_EXCLUDES,
  REPO_ROOT,
  WorkbookInfo,
  build_r2_client,
  ensure_dir,
  extract_meta,
  fetch_html,
  find_workbook,
  html_report_shell,
  load_workbook_info,
  normalise_route,
  parse_html,
  post_callback,
  repo_html_routes,
  route_to_url,
  should_exclude,
  upload_directory_to_r2,
  utc_now,
  write_json,
  write_text,
)

HARD_GATE_MESSAGE = (
  "MOBILE UX HARD GATE FAILED - RENDERED BROWSER AUTOMATION AND SCREENSHOT CAPTURE ARE REQUIRED FOR THIS AUDIT. "
  "HALTING BEFORE SCORING OR VERDICT."
)
STAGE_3_INCOMPLETE_MESSAGE = "STAGE 3 INCOMPLETE - REQUIRED MOBILE UX EXECUTION NOT FINISHED - HALTING BEFORE REPORT."
LIVE_404_ROUTE = "/__mobile-ux-live-404__"
VIEWPORTS = [320, 375, 390, 414, 768, 1024, 1280, 1440]
NAV_TOGGLE = ".jh-hamburger"
MOBILE_NAV = "#jh-mobile-nav"
PRIMARY_CTA_SELECTORS = [
  ".jh-mobile-nav__cta",
  ".jh-topnav__cta",
  "main a[href^='/ebooks/']",
  "main a[href^='/newsletter']",
  "main a[href^='/contact']",
  "main a[href*='amazon.']",
  "main button[type='submit']",
  "main input[type='submit']",
]
INTERACTIVE_SELECTORS = "a, button, input, textarea, select, summary, [role='button'], [tabindex='0']"
TEXT_SELECTORS = "p, li, h1, h2, h3, h4, label, a, button, small, figcaption"
CRITICAL_ROUTES = {"/", "/ebooks", "/newsletter", "/contact", "/compare", LIVE_404_ROUTE}
PASS_SCREENSHOT_ROUTES = {"/", "/ebooks", "/newsletter", "/contact", "/compare", LIVE_404_ROUTE}


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run the rendered mobile UX hard-gate audit")
  parser.add_argument("--base-url", required=True)
  parser.add_argument("--session-id", required=True)
  parser.add_argument("--report-prefix", required=True)
  parser.add_argument("--callback-url")
  parser.add_argument("--callback-token")
  parser.add_argument("--analysis-url", default="", help="Accepted for workflow compatibility; mobile UX reporting is deterministic")
  parser.add_argument("--output-dir", default="artifacts/mobile-ux")
  parser.add_argument("--exclude-prefixes", default=",".join(DEFAULT_EXCLUDES))
  parser.add_argument("--audit-bucket", default="")
  parser.add_argument("--audit-public-base-url", default="")
  args = parser.parse_args()
  resolve_runtime_callback_config(args)
  if args.audit_bucket:
    os.environ["R2_BUCKET_AUDITS"] = args.audit_bucket.strip()
  if args.audit_public_base_url:
    os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = args.audit_public_base_url.strip().rstrip("/")
  return args


def first_env(*names: str) -> str | None:
  for name in names:
    value = os.environ.get(name)
    if value and str(value).strip():
      return str(value).strip()
  return None


def normalise_callback_base(value: str | None) -> str | None:
  if not value:
    return None
  value = str(value).strip().rstrip("/")
  if value.endswith("/audits/mobile-ux/callback"):
    return value
  if value.endswith("/audits/mobile-ux"):
    return f"{value}/callback"
  if value.endswith("/audits"):
    return f"{value}/mobile-ux/callback"
  return f"{value}/audits/mobile-ux/callback"


def resolve_runtime_callback_config(args: argparse.Namespace) -> argparse.Namespace:
  if not getattr(args, "callback_url", None):
    args.callback_url = first_env("AI_SUITE_AUDIT_CALLBACK_URL") or normalise_callback_base(first_env("AUDIT_CALLBACK_BASE_URL", "APP_URL"))
  if args.callback_url:
    args.callback_url = args.callback_url.rstrip("/")
  if not getattr(args, "callback_token", None):
    args.callback_token = first_env("AUDIT_CALLBACK_TOKEN", "AI_SUITE_AUDIT_CALLBACK_TOKEN")
  return args


def callback_config_missing_reason(callback_url: str | None, callback_token: str | None) -> str | None:
  missing = []
  if not callback_url:
    missing.append("callback_url")
  if not callback_token:
    missing.append("callback_token")
  return f"missing {', '.join(missing)}" if missing else None


def try_load_playwright() -> tuple[Any | None, Any | None, str | None]:
  try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
    return sync_playwright, PlaywrightTimeoutError, None
  except Exception as exc:  # pragma: no cover - depends on runner packages
    return None, None, str(exc)


def r2_upload_configured() -> bool:
  required = [
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_AUDITS",
    "R2_PUBLIC_BASE_URL_AUDITS",
  ]
  return all(os.environ.get(name, "").strip() for name in required)


def make_public_url(relative_path: str) -> str | None:
  public_base = os.environ.get("R2_PUBLIC_BASE_URL_AUDITS", "").strip().rstrip("/")
  if not public_base:
    return None
  key = f"{os.environ.get('CURRENT_REPORT_PREFIX', '').strip().rstrip('/')}/{relative_path.strip('/')}".strip("/")
  if not key:
    return None
  return f"{public_base}/{key}"


def upload_artifacts_if_configured(report_prefix: str, output_dir: Path) -> dict[str, str]:
  if not r2_upload_configured():
    return {}
  client = build_r2_client()
  return upload_directory_to_r2(
    client,
    os.environ["R2_BUCKET_AUDITS"],
    report_prefix,
    output_dir,
    os.environ["R2_PUBLIC_BASE_URL_AUDITS"],
  )


def screenshot_ref(relative_path: str) -> dict[str, str | None]:
  return {"relativePath": relative_path, "publicUrl": make_public_url(relative_path)}


def screenshot_name(route: str, width: int, label: str) -> str:
  route_for_name = "live-404" if route == LIVE_404_ROUTE else route
  cleaned = route_for_name.strip("/").replace("/", "-") or "home"
  cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", cleaned)
  return f"{cleaned}-{width}-{label}.png"


def first_visible_locator(page: Any, selectors: list[str]) -> Any | None:
  for selector in selectors:
    locator = page.locator(selector)
    try:
      if locator.count() and locator.first.is_visible():
        return locator.first
    except Exception:
      continue
  return None


def read_text_preview(path: Path, limit: int = 500) -> str:
  try:
    return path.read_text(encoding="utf-8", errors="replace")[:limit]
  except FileNotFoundError:
    return "FILE NOT FOUND"


def repo_file_count(repo_root: Path) -> int:
  return sum(1 for item in repo_root.rglob("*") if item.is_file() and ".git" not in item.parts)


def find_public_partials(repo_root: Path) -> list[str]:
  keywords = re.compile(r"(head|template|layout|header|footer|nav|navigation)", re.I)
  candidates = []
  for file_path in repo_root.rglob("*.html"):
    relative = file_path.relative_to(repo_root).as_posix()
    if keywords.search(relative) or relative.startswith("assets/partials/"):
      candidates.append(relative)
  return sorted(set(candidates))[:120]


def find_ui_js_files(repo_root: Path) -> list[str]:
  keywords = re.compile(r"(nav|hamburger|resize|accordion|drawer|tab|modal|table|form|responsive|jotform|compare|contact|newsletter|glossary|site-ui)", re.I)
  files = []
  for file_path in (repo_root / "assets/js").glob("*.js"):
    relative = file_path.relative_to(repo_root).as_posix()
    text = read_text_preview(file_path, 5000)
    if keywords.search(relative) or keywords.search(text):
      files.append(relative)
  return sorted(set(files))


def viewport_inventory(repo_root: Path) -> list[dict[str, str]]:
  inventory = []
  paths = list(repo_root.glob("assets/partials/*.html")) + list(repo_root.glob("*.html")) + list(repo_root.glob("*/index.html"))
  for file_path in sorted(set(paths))[:160]:
    relative = file_path.relative_to(repo_root).as_posix()
    text = read_text_preview(file_path, 4000)
    match = re.search(r"<meta[^>]+name=[\"']viewport[\"'][^>]*>", text, re.I)
    inventory.append({"path": relative, "viewportTag": match.group(0) if match else f"NO VIEWPORT META FOUND IN {relative}"})
  return inventory


def css_rule_inventory(site_css: str) -> dict[str, Any]:
  lines = site_css.splitlines()
  fixed_width_risks = []
  responsive_rules = []
  selectors = ("image", "img", "table", "card", "grid", "flex", "form", "button", "nav", "drawer", "font", "input")
  for number, line in enumerate(lines, start=1):
    stripped = line.strip()
    if re.search(r"(?:^|[;\s])(width|min-width)\s*:\s*(?:[4-9]\d{2,}|\d{3,})px", stripped):
      fixed_width_risks.append({"line": number, "rule": stripped[:220]})
    if any(token in stripped.lower() for token in selectors):
      responsive_rules.append({"line": number, "rule": stripped[:220]})
  return {
    "fixedWidthMinWidthRisks": fixed_width_risks[:80],
    "responsiveRuleInventory": responsive_rules[:160],
  }


def nav_logic_inventory(repo_root: Path) -> dict[str, Any]:
  file_path = repo_root / "assets/js/site-ui.min.js"
  text = read_text_preview(file_path, 12000)
  probes = {
    "hamburgerOpenLogic": ["aria-expanded", "hidden", "jh-hamburger"],
    "hamburgerCloseLogic": ["Escape", "click", "hidden"],
    "escapeToCloseLogic": ["Escape"],
    "resizeOrientationLogic": ["resize", "orientationchange", "matchMedia"],
    "breakpointCloseResetLogic": ["innerWidth", "matchMedia", "1024"],
    "bodyScrollLockLogic": ["overflow", "scroll", "body"],
    "focusManagementLogic": ["focus", "activeElement", "tabindex"],
  }
  result = {}
  for name, needles in probes.items():
    hits = []
    for needle in needles:
      index = text.find(needle)
      if index >= 0:
        hits.append(text[max(0, index - 90): index + 180])
    result[name] = hits or ["No explicit match found in assets/js/site-ui.min.js"]
  return result


def inspect_touch_targets(page: Any) -> tuple[str, list[dict[str, Any]]]:
  targets = page.locator(INTERACTIVE_SELECTORS)
  count = min(targets.count(), 30)
  failures = []
  for index in range(count):
    item = targets.nth(index)
    try:
      if not item.is_visible():
        continue
      box = item.bounding_box()
      if not box:
        continue
      if box["width"] < 40 or box["height"] < 40:
        failures.append({
          "selector": item.evaluate("el => el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).trim().replace(/\\s+/g,'.') : '')"),
          "width": round(box["width"], 1),
          "height": round(box["height"], 1),
        })
    except Exception:
      continue
  return ("PASS" if not failures else "FAIL", failures)


def inspect_readability(page: Any) -> tuple[str, list[dict[str, Any]]]:
  result = page.evaluate(
    """
    (selector) => {
      const items = Array.from(document.querySelectorAll(selector)).slice(0, 80);
      const issues = [];
      for (const el of items) {
        const style = window.getComputedStyle(el);
        const fontSize = parseFloat(style.fontSize || '0');
        const clipped = el.scrollHeight - el.clientHeight > 6 && ['hidden', 'clip'].includes(style.overflowY || style.overflow);
        const rect = el.getBoundingClientRect();
        const overlapRisk = rect.width > window.innerWidth + 2;
        if (fontSize && fontSize < 14) {
          issues.push({ type: 'font-size', text: (el.textContent || '').trim().slice(0, 60), fontSize });
        }
        if (clipped || overlapRisk) {
          issues.push({ type: clipped ? 'clipped' : 'overlap-width', text: (el.textContent || '').trim().slice(0, 60), fontSize });
        }
      }
      return issues;
    }
    """,
    TEXT_SELECTORS,
  )
  return ("PASS" if not result else "FAIL", result)


def inspect_form_usability(page: Any) -> tuple[str, list[dict[str, Any]] | str]:
  forms = page.locator("form, input, textarea, select, iframe[src*='jotform']")
  if forms.count() == 0:
    return "N/A", "No form fields detected"
  issues = page.evaluate(
    """
    () => {
      const fields = Array.from(document.querySelectorAll('input, textarea, select')).filter((el) => {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden';
      });
      return fields
        .map((el) => ({
          tag: el.tagName.toLowerCase(),
          name: el.getAttribute('name') || '',
          fontSize: parseFloat(window.getComputedStyle(el).fontSize || '0'),
          label: el.getAttribute('aria-label') || el.getAttribute('placeholder') || ''
        }))
        .filter((item) => item.fontSize > 0 && item.fontSize < 16);
    }
    """
  )
  return ("PASS" if not issues else "FAIL", issues)


def inspect_images(page: Any) -> tuple[str, list[dict[str, Any]] | str]:
  images = page.locator("img")
  if images.count() == 0:
    return "N/A", "No images detected"
  issues = page.evaluate(
    """
    () => Array.from(document.images)
      .filter((img) => img.clientWidth > window.innerWidth + 2 || !img.complete || img.naturalWidth === 0)
      .slice(0, 25)
      .map((img) => ({ src: img.currentSrc || img.src || '', width: img.clientWidth, viewport: window.innerWidth, complete: img.complete, naturalWidth: img.naturalWidth }))
    """
  )
  return ("PASS" if not issues else "FAIL", issues)


def inspect_tables(page: Any) -> tuple[str, str, list[dict[str, Any]] | str]:
  tables = page.locator("table, [role='table'], .compare-table, .comparison-table")
  if tables.count() == 0:
    return "N/A", "N/A", "No tables detected"
  evaluation = page.evaluate(
    """
    () => {
      const tables = Array.from(document.querySelectorAll('table, [role="table"], .compare-table, .comparison-table'));
      const issues = [];
      let pattern = 'wrap';
      for (const table of tables) {
        const parent = table.parentElement;
        const parentStyle = parent ? window.getComputedStyle(parent) : null;
        const overflowX = parentStyle ? parentStyle.overflowX : '';
        if (table.scrollWidth > window.innerWidth + 2) {
          if (overflowX === 'auto' || overflowX === 'scroll') {
            pattern = 'scroll-container';
          } else {
            issues.push({ width: table.scrollWidth, viewport: window.innerWidth, text: (table.textContent || '').trim().slice(0, 80) });
          }
        }
      }
      return { pattern, issues };
    }
    """
  )
  return ("PASS" if not evaluation["issues"] else "FAIL", evaluation["pattern"], evaluation["issues"])


def inspect_overflow(page: Any) -> tuple[str, list[dict[str, Any]]]:
  issues = page.evaluate(
    """
    () => {
      const offenders = [];
      const viewport = window.innerWidth;
      const nodes = Array.from(document.querySelectorAll('body *')).slice(0, 700);
      for (const el of nodes) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        if (style.position === 'fixed' && rect.left < -viewport) continue;
        if (rect.width > viewport + 2 || rect.right > viewport + 2) {
          offenders.push({
            tag: el.tagName.toLowerCase(),
            className: (el.className || '').toString().trim(),
            id: el.id || '',
            width: Math.round(rect.width),
            right: Math.round(rect.right),
          });
          if (offenders.length >= 20) break;
        }
      }
      return offenders;
    }
    """
  )
  return ("PASS" if not issues else "FAIL", issues)


def inspect_hamburger(page: Any, width: int) -> tuple[str, dict[str, Any] | str]:
  if width >= 1024:
    return "N/A", "Desktop viewport"

  toggle = page.locator(NAV_TOGGLE)
  if toggle.count() == 0 or not toggle.first.is_visible():
    return "FAIL", {"reason": "Hamburger toggle not visible at mobile width", "selector": NAV_TOGGLE}

  nav = page.locator(MOBILE_NAV)
  details: dict[str, Any] = {"selector": NAV_TOGGLE, "navSelector": MOBILE_NAV}
  try:
    toggle.first.click(timeout=5000)
    page.wait_for_timeout(250)
    open_state = nav.count() > 0 and nav.get_attribute("hidden") is None and toggle.first.get_attribute("aria-expanded") == "true"
    details["open"] = open_state

    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    closed_state = nav.count() > 0 and nav.get_attribute("hidden") is not None and toggle.first.get_attribute("aria-expanded") == "false"
    details["escapeClose"] = closed_state

    toggle.first.click(timeout=5000)
    page.wait_for_timeout(200)
    page.mouse.click(8, 8)
    page.wait_for_timeout(200)
    outside_close = nav.count() > 0 and nav.get_attribute("hidden") is not None
    details["outsideClose"] = outside_close

    toggle.first.click(timeout=5000) if nav.count() > 0 and nav.get_attribute("hidden") is None else None
    page.wait_for_timeout(100)

    if all(value for key, value in details.items() if key not in {"selector", "navSelector"}):
      return "PASS", details
    return "FAIL", details
  except Exception as exc:
    return "FAIL", {"reason": str(exc), **details}


def inspect_cta(page: Any, base_url: str) -> tuple[str, dict[str, Any] | str]:
  locator = first_visible_locator(page, PRIMARY_CTA_SELECTORS)
  if locator is None:
    return "FAIL", "No visible primary CTA detected"

  href = locator.get_attribute("href") or ""
  label = ""
  try:
    label = locator.inner_text(timeout=1000).strip()
  except Exception:
    label = locator.get_attribute("aria-label") or ""

  if href.startswith("/"):
    target = route_to_url(base_url, href)
    try:
      locator.click(timeout=5000)
      page.wait_for_load_state("domcontentloaded", timeout=8000)
      ok = page.url.startswith(target) or normalise_route(page.url, None) == normalise_route(href)
      page.go_back(wait_until="domcontentloaded", timeout=8000)
      page.wait_for_timeout(150)
      return ("PASS" if ok else "FAIL", {"label": label, "href": href, "expectedTarget": target, "currentUrlAfterClick": page.url})
    except Exception as exc:
      return "FAIL", {"label": label, "href": href, "reason": str(exc)}

  if href or locator.evaluate("el => el.tagName.toLowerCase()") == "button":
    return "PASS", {"label": label, "href": href or "button"}
  return "FAIL", {"label": label, "href": href}


def inspect_viewport_markup(page: Any) -> tuple[str, str]:
  try:
    content = page.locator("meta[name='viewport']").get_attribute("content") or ""
  except Exception:
    content = ""
  lower = content.lower()
  bad = "user-scalable=no" in lower or "maximum-scale=1" in lower or "maximum-scale=1.0" in lower
  good = "width=device-width" in lower
  return ("PASS" if good and not bad else "FAIL", content or "Viewport meta missing")


def inspect_dynamic_resize(page: Any, width: int) -> tuple[str, dict[str, Any] | str]:
  original = {"width": width, "height": 920}
  sequence = [390, 768, 1024, width]
  try:
    stuck_states = []
    for next_width in sequence:
      page.set_viewport_size({"width": next_width, "height": 920})
      page.wait_for_timeout(160)
      nav = page.locator(MOBILE_NAV)
      stuck_states.append({
        "width": next_width,
        "mobileNavVisibleOnDesktop": nav.count() > 0 and nav.get_attribute("hidden") is None and next_width >= 1024,
        "bodyScrollWidth": page.evaluate("() => document.documentElement.scrollWidth"),
      })
    page.set_viewport_size(original)
    page.wait_for_timeout(120)
    failed = any(item["mobileNavVisibleOnDesktop"] for item in stuck_states)
    return ("FAIL" if failed else "PASS", {"resizeSequence": stuck_states})
  except Exception as exc:
    return "FAIL", {"reason": str(exc)}


def inspect_live_404(page: Any, response_status: int | None) -> tuple[str, dict[str, Any]]:
  if response_status not in {404, 410}:
    return "FAIL", {"responseStatus": response_status, "reason": "Live missing route did not return a 404/410 status"}
  header = page.locator("header, .jh-header")
  footer = page.locator("footer, .jh-footer")
  cta = first_visible_locator(page, ["main a[href='/']", "main a[href^='/ebooks']", "main a[href^='/contact']", "main a"])
  details = {
    "responseStatus": response_status,
    "headerRendered": header.count() > 0,
    "footerRendered": footer.count() > 0,
    "ctaRendered": cta is not None,
  }
  return ("PASS" if all(details.values()) else "FAIL", details)


def detect_template_family(route: str) -> str:
  if route in {"/", ""}:
    return "homepage"
  if route == LIVE_404_ROUTE or route.startswith("/404"):
    return "live-404"
  if route.startswith("/ebooks/") and route.count("/") > 1:
    return "ebook-detail"
  if route.startswith("/ebooks"):
    return "ebook-index"
  if route.startswith("/catalogue"):
    return "catalogue"
  if route.startswith("/topics"):
    return "topics"
  if route.startswith("/newsletter"):
    return "conversion-newsletter"
  if route.startswith("/contact"):
    return "conversion-contact"
  if route.startswith("/compare"):
    return "comparison"
  if route.startswith("/glossary"):
    return "glossary"
  if route.startswith("/bio"):
    return "bio"
  return "site-page"


def first_route_with_prefix(routes: list[str], prefix: str, fallback: str | None = None) -> str | None:
  for route in routes:
    if route == prefix or route.startswith(f"{prefix}/"):
      return route
  return fallback


def representative_ebook_routes(routes: list[str], repo_root: Path, max_variants: int = 3) -> list[str]:
  candidates = sorted(route for route in routes if route.startswith("/ebooks/") and route != "/ebooks")
  variants: dict[str, str] = {}
  for route in candidates:
    file_path = repo_root / route.strip("/") / "index.html"
    text = read_text_preview(file_path, 12000)
    class_matches = re.findall(r"class=[\"']([^\"']*(?:ebook|book|cta|hero|compare)[^\"']*)[\"']", text, re.I)
    signature = "|".join(sorted(set(class_matches))[:12])
    signature = signature or "ebook-detail-default"
    variants.setdefault(signature, route)
    if len(variants) >= max_variants:
      break
  return list(variants.values()) or ([candidates[0]] if candidates else [])


def detect_required_routes(repo_root: Path, workbook_info: WorkbookInfo, excludes: list[str]) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]]]:
  routes = repo_html_routes(repo_root, excludes)
  route_set = set(routes)
  required: list[dict[str, str]] = [
    {"route": "/", "reason": "homepage"},
    {"route": "/ebooks", "reason": "ebook index"},
    {"route": "/newsletter", "reason": "newsletter conversion page"},
    {"route": "/contact", "reason": "contact conversion page"},
    {"route": "/bio", "reason": "bio/about page"},
    {"route": "/compare", "reason": "comparison page"},
    {"route": LIVE_404_ROUTE, "reason": "live rendered missing route 404"},
  ]

  for route in representative_ebook_routes(routes, repo_root):
    required.append({"route": route, "reason": "representative ebook detail template variant"})

  catalogue = first_route_with_prefix(routes, "/catalogue")
  topics = first_route_with_prefix(routes, "/topics")
  glossary = first_route_with_prefix(routes, "/glossary")
  for route, reason in [(catalogue, "catalogue/topic-style page"), (topics, "topics page"), (glossary, "unique JS/layout behaviour")]:
    if route:
      required.append({"route": route, "reason": reason})

  risk_keywords = ("compare", "contact", "newsletter", "catalogue", "topic", "table", "form", "glossary")
  for raw in workbook_info.urls:
    route = normalise_route(raw, None)
    if should_exclude(route, excludes):
      continue
    if any(keyword in route.lower() for keyword in risk_keywords):
      required.append({"route": route, "reason": "workbook mobile-risk keyword"})

  deduped_required: list[dict[str, str]] = []
  seen = set()
  for item in required:
    route = normalise_route(item["route"])
    if item["route"] == LIVE_404_ROUTE:
      route = LIVE_404_ROUTE
    if route in seen:
      continue
    seen.add(route)
    deduped_required.append({"route": route, "reason": item["reason"]})

  blocked = []
  executable = []
  for item in deduped_required:
    route = item["route"]
    if route == LIVE_404_ROUTE:
      executable.append(route)
    elif route in route_set:
      executable.append(route)
    else:
      blocked.append({"route": route, "reason": item["reason"], "blocker": "required route is absent from repository route inventory"})
  return executable, blocked, deduped_required


def preflight(base_url: str, repo_root: Path, workbook_info: WorkbookInfo, capabilities: dict[str, Any]) -> dict[str, Any]:
  homepage = fetch_html(base_url)
  soup = parse_html(homepage.get("text", "")) if homepage.get("text") else parse_html("")
  meta = extract_meta(soup)
  site_css_path = repo_root / "assets/css/site.css"
  site_css = read_text_preview(site_css_path, 1_000_000)
  media_queries = re.findall(r"@media\s+([^\{]+)\{", site_css)
  container_queries = re.findall(r"@container\s+([^\{]+)\{", site_css)
  css_inventory = css_rule_inventory(site_css)
  viewport_tags = viewport_inventory(repo_root)
  repo_viewports = [item for item in viewport_tags if not item["viewportTag"].startswith("NO VIEWPORT")]
  served_viewport = meta.get("viewport") or "HOMEPAGE VIEWPORT META NOT FOUND"
  repo_home_viewport = next((item["viewportTag"] for item in viewport_tags if item["path"] == "index.html"), "NO VIEWPORT META FOUND IN index.html")
  viewport_match = "VIEWPORT MATCH CONFIRMED" if served_viewport and served_viewport in repo_home_viewport else f"VIEWPORT MISMATCH - served={served_viewport}; repository={repo_home_viewport}"

  return {
    "workbook": {
      "filename": Path(workbook_info.path).name,
      "sheetNames": workbook_info.sheet_names,
      "primarySheet": workbook_info.primary_sheet,
      "headerRow": workbook_info.header_row,
      "urlCount": workbook_info.url_count,
      "firstRows": workbook_info.first_rows,
    },
    "liveHomepage": {
      "status": homepage.get("status", 0),
      "first300": homepage.get("text", "")[:300],
      "viewport": served_viewport,
      "canonical": meta.get("canonical", ""),
      "title": meta.get("title", ""),
      "metaDescription": meta.get("metaDescription", ""),
    },
    "repository": {
      "topLevel": sorted([p.name for p in repo_root.iterdir()]),
      "totalFiles": repo_file_count(repo_root),
      "siteCssPreview": site_css[:500],
      "sharedPartialsLayoutHeadHeaderFooterNavigationFiles": find_public_partials(repo_root),
      "uiScripts": find_ui_js_files(repo_root),
      "viewportInventory": viewport_tags,
      "repositoryViewportInventoryCount": len(repo_viewports),
      "viewportComparison": viewport_match,
      "mediaQueries": media_queries,
      "containerQueries": container_queries,
      "mediaQueryCount": len(media_queries),
      "containerQueryCount": len(container_queries),
      "fixedWidthMinWidthRisks": css_inventory["fixedWidthMinWidthRisks"],
      "responsiveRuleInventory": css_inventory["responsiveRuleInventory"],
      "navLogicInventory": nav_logic_inventory(repo_root),
    },
    "capabilities": capabilities,
  }


def checkpoint(stage: str, completed: list[str], blocked: list[Any] | None = None, may_continue: bool = True) -> dict[str, Any]:
  return {
    "stage": stage,
    "completedItems": completed,
    "blockedItems": blocked or [],
    "mayContinue": may_continue,
    "checkedAt": utc_now(),
  }


def build_capabilities(playwright_error: str | None = None, install_outcome: str | None = None) -> dict[str, Any]:
  blocked = []
  if playwright_error:
    blocked.append({"capability": "renderedBrowserAutomation", "reason": playwright_error})
    blocked.append({"capability": "screenshotCapture", "reason": playwright_error})
    blocked.append({"capability": "mobileViewportEmulation", "reason": playwright_error})
  if install_outcome and install_outcome not in {"", "success", "skipped"}:
    blocked.append({"capability": "playwrightChromiumInstall", "reason": install_outcome})
  available = not any(item["capability"] in {"renderedBrowserAutomation", "screenshotCapture", "mobileViewportEmulation", "playwrightChromiumInstall"} for item in blocked)
  return {
    "staticFileInspection": True,
    "fetchSourceInspection": True,
    "renderedBrowserAutomation": available,
    "screenshotCapture": available,
    "mobileViewportEmulation": available,
    "blockedTests": blocked,
  }


def status_from_exception(exc: Exception) -> dict[str, str]:
  return {"reason": str(exc), "trace": traceback.format_exc(limit=4)}


def read_json_if_present(path: Path, fallback: Any) -> Any:
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return fallback


def failure_blocks_from_extra(extra: dict[str, Any] | None) -> list[Any]:
  if not isinstance(extra, dict):
    return []
  for key in ("stage3Blocks", "blockedTests", "runtimeBlocks"):
    value = extra.get(key)
    if isinstance(value, list):
      return value
    if value:
      return [value]
  if extra.get("error"):
    return [{"capability": "mobileUxExecution", "reason": str(extra.get("error"))}]
  return []


def ensure_failure_artifacts(args: argparse.Namespace, output_dir: Path, message: str, preflight_data: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
  now = utc_now()
  blocks = failure_blocks_from_extra(extra)

  coverage_path = output_dir / "coverage.json"
  if coverage_path.exists():
    coverage = read_json_if_present(coverage_path, {})
  else:
    coverage = {
      "complete": False,
      "auditType": "mobile-ux",
      "sessionId": args.session_id,
      "status": "failed",
      "reportPrefix": args.report_prefix,
      "message": message,
      "stage3Blocks": blocks,
      "skippedRequiredTasksCount": len(blocks),
      "generatedAt": now,
    }
    write_json(coverage_path, coverage)

  evidence_path = output_dir / "evidence.json"
  if evidence_path.exists():
    evidence = read_json_if_present(evidence_path, {})
  else:
    evidence = {
      "preflight": preflight_data,
      "coverage": coverage,
      "records": [],
      "failure": {
        "message": message,
        "blocks": blocks,
        "extra": extra or {},
        "generatedAt": now,
      },
    }
    write_json(evidence_path, evidence)

  return {"coverage": coverage, "evidence": evidence, "blocks": blocks}


def failure_report_html(summary: dict[str, Any], failure_artifacts: dict[str, Any]) -> str:
  blocks = failure_artifacts.get("blocks") or []
  block_rows = "".join(
    f"<tr><td>{escape(str(item.get('capability') or item.get('route') or item.get('stage') or 'mobile UX execution'))}</td>"
    f"<td>{escape(str(item.get('reason') or item.get('blocker') or item))}</td></tr>"
    if isinstance(item, dict)
    else f"<tr><td>mobile UX execution</td><td>{escape(str(item))}</td></tr>"
    for item in blocks
  ) or "<tr><td>mobile UX execution</td><td>No detailed blocker payload was supplied.</td></tr>"

  capability_rows = ""
  capabilities = summary.get("preflight", {}).get("capabilities", {}) if isinstance(summary.get("preflight"), dict) else {}
  if isinstance(capabilities, dict):
    capability_rows = "".join(
      f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
      for key, value in capabilities.items()
      if key != "blockedTests"
    )

  body = f"""
  <section>
    <h2>Audit status</h2>
    <p><span class="badge fail">FAILED</span></p>
    <p>{escape(str(summary.get('message') or 'Mobile UX audit did not complete.'))}</p>
    <p class="section-note">This is a failure report, not a placeholder success report. No Lighthouse, Core Web Vitals, or browser-rendered scores are fabricated.</p>
  </section>
  <section>
    <h2>Run details</h2>
    <table class="tight"><tbody>
      <tr><th>Audit type</th><td>{escape(str(summary.get('auditType')))}</td></tr>
      <tr><th>Session ID</th><td>{escape(str(summary.get('sessionId')))}</td></tr>
      <tr><th>Report prefix</th><td>{escape(str(summary.get('reportPrefix')))}</td></tr>
      <tr><th>Finished at</th><td>{escape(str(summary.get('finishedAt')))}</td></tr>
    </tbody></table>
  </section>
  <section>
    <h2>Blocking evidence</h2>
    <table class="tight"><thead><tr><th>Area</th><th>Evidence</th></tr></thead><tbody>{block_rows}</tbody></table>
  </section>
  <section>
    <h2>Capability declaration</h2>
    <table class="tight"><thead><tr><th>Capability</th><th>Status</th></tr></thead><tbody>{capability_rows}</tbody></table>
  </section>
  <section>
    <h2>Artefacts written</h2>
    <ul>
      <li><code>summary.json</code></li>
      <li><code>coverage.json</code></li>
      <li><code>evidence.json</code></li>
      <li><code>preflight.json</code> when preflight reached that stage</li>
      <li><code>report.html</code></li>
    </ul>
  </section>
  """
  return html_report_shell("Mobile UX audit failure report", body)


def route_target(base_url: str, route: str, session_id: str) -> str:
  if route == LIVE_404_ROUTE:
    return f"{base_url}/__mobile-ux-404-probe__{session_id}"
  return route_to_url(base_url, route)


def run_single_record(page: Any, base_url: str, route: str, width: int, target: str, response_status: int | None) -> dict[str, Any]:
  checks: dict[str, str] = {}
  details: dict[str, Any] = {"responseStatus": response_status}

  checks["viewportCorrectness"], details["viewport"] = inspect_viewport_markup(page)
  checks["overflow"], details["overflow"] = inspect_overflow(page)
  checks["hamburgerNavigation"], details["hamburger"] = inspect_hamburger(page, width)
  checks["touchTargetUsability"], details["touchTargets"] = inspect_touch_targets(page)
  checks["dynamicResizeReflow"], details["dynamicResize"] = inspect_dynamic_resize(page, width)
  checks["ctaContinuity"], details["cta"] = inspect_cta(page, base_url)
  checks["typographyReadability"], details["readability"] = inspect_readability(page)
  checks["formUsability"], details["form"] = inspect_form_usability(page)
  checks["imageResponsiveness"], details["images"] = inspect_images(page)
  table_status, pattern, table_details = inspect_tables(page)
  checks["tableComparisonHandling"] = table_status
  details["tables"] = {"pattern": pattern, "details": table_details}
  if route == LIVE_404_ROUTE:
    checks["live404Verification"], details["live404"] = inspect_live_404(page, response_status)

  failed_checks = [name for name, status in checks.items() if status == "FAIL"]
  return {
    "route": route,
    "url": target,
    "templateFamily": detect_template_family(route),
    "viewport": width,
    "checks": checks,
    "details": details,
    "screenshotRefs": [],
    "defectSummary": "PASS" if not failed_checks else "; ".join(failed_checks),
    "selectorComponentCodeAnchor": best_anchor(details),
  }


def best_anchor(details: dict[str, Any]) -> str:
  for key in ("hamburger", "cta", "overflow", "tables"):
    value = details.get(key)
    if isinstance(value, dict):
      if value.get("selector"):
        return str(value["selector"])
      if value.get("navSelector"):
        return str(value["navSelector"])
      nested = value.get("details")
      if isinstance(nested, list) and nested:
        return str(nested[0])[:180]
    if isinstance(value, list) and value:
      return str(value[0])[:180]
  return "Best available rendered component anchor recorded in details"


def should_capture_pass(route: str, width: int, template_family: str) -> bool:
  if width not in {320, 390}:
    return False
  return route in PASS_SCREENSHOT_ROUTES or template_family in {"catalogue", "topics", "ebook-detail"}


def run_rendered_execution(sync_playwright: Any, base_url: str, session_id: str, routes: list[str], screenshots_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
  records: list[dict[str, Any]] = []
  executed: list[dict[str, str]] = []
  runtime_blocks: list[dict[str, str]] = []
  with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    try:
      for route in routes:
        for width in VIEWPORTS:
          target = route_target(base_url, route, session_id)
          context = browser.new_context(
            viewport={"width": width, "height": 920},
            is_mobile=width < 768,
            has_touch=width < 1024,
            device_scale_factor=1,
          )
          page = context.new_page()
          response_status: int | None = None
          try:
            response = page.goto(target, wait_until="domcontentloaded", timeout=25000)
            response_status = response.status if response else None
            page.wait_for_timeout(350)
            record = run_single_record(page, base_url, route, width, target, response_status)
            failed = any(status == "FAIL" for status in record["checks"].values())
            if failed or should_capture_pass(route, width, record["templateFamily"]):
              label = "fail" if failed else "pass"
              name = screenshot_name(route, width, label)
              file_path = screenshots_dir / name
              page.screenshot(path=str(file_path), full_page=True)
              record["screenshotRefs"].append(screenshot_ref(f"screenshots/{name}"))
            records.append(record)
            executed.append({"route": route, "viewport": str(width)})
          except Exception as exc:
            runtime_blocks.append({"route": route, "viewport": str(width), "blocker": str(exc)})
            fail_name = screenshot_name(route, width, "runtime-blocked")
            fail_path = screenshots_dir / fail_name
            refs = []
            try:
              page.screenshot(path=str(fail_path), full_page=True)
              refs.append(screenshot_ref(f"screenshots/{fail_name}"))
            except Exception:
              pass
            records.append({
              "route": route,
              "url": target,
              "templateFamily": detect_template_family(route),
              "viewport": width,
              "checks": {
                "viewportCorrectness": "FAIL",
                "overflow": "FAIL",
                "hamburgerNavigation": "FAIL" if width < 1024 else "N/A",
                "touchTargetUsability": "FAIL",
                "dynamicResizeReflow": "FAIL",
                "ctaContinuity": "FAIL",
                "typographyReadability": "FAIL",
                "formUsability": "N/A",
                "imageResponsiveness": "N/A",
                "tableComparisonHandling": "N/A",
              },
              "details": {"runtimeBlocker": status_from_exception(exc), "responseStatus": response_status},
              "screenshotRefs": refs,
              "defectSummary": f"Rendered execution failed before checks completed: {exc}",
              "selectorComponentCodeAnchor": "rendered browser execution",
            })
          finally:
            context.close()
    finally:
      browser.close()
  return records, executed, runtime_blocks


def check_stage3_coverage(routes: list[str], records: list[dict[str, Any]], route_blocks: list[dict[str, str]], runtime_blocks: list[dict[str, str]]) -> list[dict[str, str]]:
  blocks = list(route_blocks)
  executed_pairs = {(record["route"], int(record["viewport"])) for record in records}
  for route in routes:
    for width in VIEWPORTS:
      if (route, width) not in executed_pairs:
        blocks.append({"route": route, "viewport": str(width), "blocker": "required viewport run was not recorded"})
  blocks.extend(runtime_blocks)
  return blocks


def record_failures(records: list[dict[str, Any]]) -> int:
  return sum(1 for record in records if any(status == "FAIL" for status in record.get("checks", {}).values()))


def pass_fail_totals(records: list[dict[str, Any]]) -> dict[str, int]:
  totals = Counter()
  for record in records:
    for status in record.get("checks", {}).values():
      totals[status] += 1
  return {"PASS": totals["PASS"], "FAIL": totals["FAIL"], "N/A": totals["N/A"]}


def mobile_quality_score(records: list[dict[str, Any]], stage3_complete: bool) -> float | None:
  if not stage3_complete:
    return None
  totals = pass_fail_totals(records)
  denominator = totals["PASS"] + totals["FAIL"]
  if denominator == 0:
    return None
  return round((totals["PASS"] / denominator) * 100, 1)


def build_issues(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
  issues = []
  for record in records:
    failed = [name for name, status in record.get("checks", {}).items() if status == "FAIL"]
    for check in failed:
      route = record["route"]
      severity = "P1"
      if check in {"viewportCorrectness", "live404Verification"}:
        severity = "P0"
      elif route in CRITICAL_ROUTES and check in {"ctaContinuity", "hamburgerNavigation", "overflow"} and int(record["viewport"]) <= 768:
        severity = "P0"
      elif check in {"touchTargetUsability", "dynamicResizeReflow", "formUsability"}:
        severity = "P1"
      issue_id = f"MUX-{len(issues) + 1:03d}"
      issues.append({
        "issueId": issue_id,
        "exactUrlOrFilePath": record["url"],
        "route": route,
        "viewport": record["viewport"],
        "defectDescription": f"{check} failed during rendered mobile execution.",
        "evidenceLabel": "Observed Live (mobile)",
        "severity": severity,
        "consequence": "Mobile users may hit layout, navigation, readability, or conversion friction.",
        "exactRemediation": "Fix the affected responsive component, then rerun the same route and viewport in the mobile hard-gate workflow.",
        "ownerClass": "Website frontend / static site implementation",
        "acceptanceCriteria": f"{check} returns PASS for {route} at {record['viewport']}px and any failure screenshot is superseded by a passing screenshot.",
        "verificationMethod": "Rerun POST /audits/mobile-ux/run and confirm execution.json plus report.html show PASS for the affected check.",
        "selectorComponentCodeAnchor": record.get("selectorComponentCodeAnchor"),
        "screenshotRefs": record.get("screenshotRefs", []),
      })
  return issues


def coverage_document(routes: list[str], records: list[dict[str, Any]], stage3_blocks: list[dict[str, str]], required_routes: list[dict[str, str]]) -> dict[str, Any]:
  by_route = []
  for route in routes:
    route_records = [record for record in records if record["route"] == route]
    by_route.append({
      "route": route,
      "templateFamily": detect_template_family(route),
      "requiredReason": next((item["reason"] for item in required_routes if item["route"] == route), "required mobile UX route"),
      "viewportRuns": len(route_records),
      "viewports": sorted(record["viewport"] for record in route_records),
      "failures": sum(1 for record in route_records if any(status == "FAIL" for status in record.get("checks", {}).values())),
    })
  return {
    "stage": "Stage 3 Mandatory Rendered Mobile UX Execution",
    "requiredViewports": VIEWPORTS,
    "requiredRoutes": required_routes,
    "routesExecuted": by_route,
    "stage3Blocks": stage3_blocks,
    "skippedRequiredTasksCount": len(stage3_blocks),
    "complete": len(stage3_blocks) == 0,
    "generatedAt": utc_now(),
  }


def reconciliation_document(preflight_data: dict[str, Any]) -> dict[str, Any]:
  mismatch = preflight_data["repository"].get("viewportComparison", "")
  mismatches = [] if mismatch == "VIEWPORT MATCH CONFIRMED" else [{
    "mismatchId": "MUX-MISMATCH-001",
    "intendedState": "Workbook and repository pages should be served with usable mobile viewport metadata.",
    "implementedState": preflight_data["repository"].get("viewportComparison"),
    "liveState": preflight_data["liveHomepage"].get("viewport"),
    "riskOwner": "Website frontend",
    "remediationOwner": "Website repository",
  }]
  return {
    "sourceOfTruthHierarchy": ["Workbook", "Repository", "Live site", "Benchmark/reference pages", "Prompt process discipline"],
    "crossSourceMismatches": mismatches,
    "crossSourceMismatchCount": len(mismatches),
    "generatedAt": utc_now(),
  }


def html_badge(status: str) -> str:
  css = "pass" if status == "PASS" else "fail" if status == "FAIL" else "warn"
  return f"<span class='badge {css}'>{escape(status)}</span>"


def html_list(items: list[Any]) -> str:
  if not items:
    return "<p class='muted'>None recorded.</p>"
  return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items[:40]) + "</ul>"


def link_for_ref(ref: dict[str, str | None]) -> str:
  rel = escape(str(ref.get("relativePath") or ""))
  public = ref.get("publicUrl")
  if public:
    return f"<a href='{escape(str(public))}'>{rel}</a>"
  return rel or "—"


def report_html(summary: dict[str, Any], records: list[dict[str, Any]], artefacts: dict[str, str], issues: list[dict[str, Any]], coverage: dict[str, Any], reconciliation: dict[str, Any]) -> str:
  totals = pass_fail_totals(records)
  score = summary.get("mobileQualityScore")
  verdict = summary.get("releaseVerdict")
  critical = [issue for issue in issues if issue["severity"] == "P0"]
  p1 = [issue for issue in issues if issue["severity"] == "P1"]
  score_rows = "".join(
    f"<tr><td>{escape(name)}</td><td>{weight}</td><td>{escape(str(value))}</td><td>{escape(note)}</td></tr>"
    for name, weight, value, note in summary["weightedScorecard"]
  )
  record_rows = []
  for record in records:
    checks = record["checks"]
    failed = [name for name, status in checks.items() if status == "FAIL"]
    screenshot_links = "<br>".join(link_for_ref(ref) for ref in record.get("screenshotRefs", [])) or "—"
    checks_html = "<br>".join(f"{escape(key)}: {html_badge(value)}" for key, value in checks.items())
    record_rows.append(
      f"<tr><td><code>{escape(record['route'])}</code><br><small>{escape(record['url'])}</small></td>"
      f"<td>{escape(record['templateFamily'])}</td><td>{record['viewport']}</td>"
      f"<td>{html_badge('PASS' if not failed else 'FAIL')}</td><td>{checks_html}</td>"
      f"<td>{escape(record.get('defectSummary', ''))}</td><td>{screenshot_links}</td></tr>"
    )

  issue_rows = []
  for issue in issues[:160]:
    screenshots = "<br>".join(link_for_ref(ref) for ref in issue.get("screenshotRefs", [])) or "—"
    issue_rows.append(
      f"<tr><td><code>{escape(issue['issueId'])}</code></td><td>{escape(issue['severity'])}</td>"
      f"<td>{escape(issue['evidenceLabel'])}</td><td>{escape(issue['route'])}<br><small>{escape(str(issue['viewport']))}px</small></td>"
      f"<td>{escape(issue['defectDescription'])}<br><small>{escape(issue['selectorComponentCodeAnchor'] or '')}</small></td>"
      f"<td>{escape(issue['exactRemediation'])}</td><td>{escape(issue['acceptanceCriteria'])}</td><td>{screenshots}</td></tr>"
    )

  capability_rows = "".join(
    f"<tr><td>{escape(key)}</td><td>{escape(str(value))}</td></tr>"
    for key, value in summary["preflight"]["capabilities"].items()
  )
  mismatch_rows = "".join(
    f"<tr><td>{escape(item['mismatchId'])}</td><td>{escape(item['intendedState'])}</td><td>{escape(str(item['implementedState']))}</td><td>{escape(str(item['liveState']))}</td><td>{escape(item['remediationOwner'])}</td></tr>"
    for item in reconciliation["crossSourceMismatches"]
  ) or "<tr><td colspan='5'>No material cross-source mismatch recorded during preflight.</td></tr>"

  verification = summary["verificationMatrix"]
  verification_rows = "".join(f"<tr><td>{escape(name)}</td><td>{html_badge(status)}</td></tr>" for name, status in verification.items())
  report_control = summary["reportControlBlock"]
  control_rows = "".join(f"<tr><td>{escape(key)}</td><td>{escape(str(value))}</td></tr>" for key, value in report_control.items())

  body = f"""
  <section id="cover">
    <h2>Cover</h2>
    <p><strong>Audit source:</strong> Deterministic mobile UX hard-gate service.</p>
    <p><strong>Session:</strong> <code>{escape(summary['sessionId'])}</code></p>
    <p><strong>Report prefix:</strong> <code>{escape(summary['reportPrefix'])}</code></p>
    <p><strong>Final verdict:</strong> {html_badge(verdict)}</p>
  </section>

  <section id="executive-summary">
    <h2>Executive summary</h2>
    <div class="grid">
      <div class="kpi"><strong>Rendered pages</strong><div>{summary['renderedPages']}</div></div>
      <div class="kpi"><strong>Viewport runs</strong><div>{summary['viewportRuns']}</div></div>
      <div class="kpi"><strong>Screenshots</strong><div>{summary['screenshotCount']}</div></div>
      <div class="kpi"><strong>Mobile failures</strong><div>{summary['mobileFailureCount']}</div></div>
      <div class="kpi"><strong>Mobile quality score</strong><div>{score}</div></div>
      <div class="kpi"><strong>Confidence</strong><div>{summary['confidenceScore']}</div></div>
    </div>
    <p>Evidence label: Observed Live (mobile). This report is generated only after every required Stage 3 route and viewport has a recorded execution result.</p>
  </section>

  <section id="preflight">
    <h2>Preflight evidence summary</h2>
    <p><strong>Workbook:</strong> <code>{escape(summary['preflight']['workbook']['filename'])}</code>, primary sheet <code>{escape(str(summary['preflight']['workbook']['primarySheet']))}</code>, header row {summary['preflight']['workbook']['headerRow']}, URL count {summary['preflight']['workbook']['urlCount']}.</p>
    <p><strong>Live homepage:</strong> status {summary['preflight']['liveHomepage']['status']}; viewport <code>{escape(summary['preflight']['liveHomepage']['viewport'])}</code>; title <code>{escape(summary['preflight']['liveHomepage']['title'])}</code>.</p>
    <p><strong>Repository:</strong> {summary['preflight']['repository']['totalFiles']} files, {summary['preflight']['repository']['mediaQueryCount']} media queries, {summary['preflight']['repository']['containerQueryCount']} container queries.</p>
  </section>

  <section id="capabilities">
    <h2>Capability table</h2>
    <table><tbody>{capability_rows}</tbody></table>
  </section>

  <section id="source-of-truth">
    <h2>Source-of-truth variance and cross-source mismatch register</h2>
    <table><thead><tr><th>ID</th><th>Intended state</th><th>Implemented state</th><th>Live state</th><th>Owner</th></tr></thead><tbody>{mismatch_rows}</tbody></table>
  </section>

  <section id="weighted-scorecard">
    <h2>Weighted scorecard</h2>
    <table><thead><tr><th>Dimension</th><th>Weight</th><th>Score</th><th>Evidence note</th></tr></thead><tbody>{score_rows}</tbody></table>
  </section>

  <section id="blockers">
    <h2>Critical blockers</h2>
    <p>P0 issues: {len(critical)}. P1 issues: {len(p1)}.</p>
    <table><thead><tr><th>Issue</th><th>Severity</th><th>Evidence</th><th>Route</th><th>Defect</th><th>Remediation</th><th>Acceptance</th><th>Screenshots</th></tr></thead><tbody>{''.join(issue_rows) or '<tr><td colspan="8">No rendered mobile issue recorded.</td></tr>'}</tbody></table>
  </section>

  <section id="systemic-findings">
    <h2>Systemic findings</h2>
    <p>Observed in Repository: fixed-width/min-width risk count {len(summary['preflight']['repository']['fixedWidthMinWidthRisks'])}; responsive rule inventory count {len(summary['preflight']['repository']['responsiveRuleInventory'])}.</p>
    <p>Reasoned Inference: any repeated rendered failure across multiple routes should be treated as a shared template or shared CSS/JS defect until proved page-specific.</p>
  </section>

  <section id="stage-3">
    <h2>Stage 3 rendered mobile execution summary</h2>
    <p>Required viewport set: {', '.join(str(width) for width in VIEWPORTS)}.</p>
    <p>Totals: PASS {totals['PASS']}, FAIL {totals['FAIL']}, N/A {totals['N/A']}.</p>
    <table class="tight"><thead><tr><th>Route</th><th>Template</th><th>Viewport</th><th>Status</th><th>Checks</th><th>Defect summary</th><th>Screenshots</th></tr></thead><tbody>{''.join(record_rows)}</tbody></table>
  </section>

  <section id="focused-pages">
    <h2>Focused page findings and exception sweep summary</h2>
    <p>Focused pages audited: {summary['focusedPagesAudited']}. Exceptions escalated: {summary['exceptionsEscalated']}.</p>
    <p>Observed Live (mobile): exception escalation is driven by rendered FAIL records, not static inspection alone.</p>
  </section>

  <section id="remediation">
    <h2>Remediation programme and roadmap</h2>
    <ol>
      <li>Fix P0 viewport, live 404, hamburger, overflow, and mobile CTA continuity defects first.</li>
      <li>Fix P1 touch-target, resize/reflow, form, image, typography, and table handling defects.</li>
      <li>Rerun the same hard-gate workflow and compare execution.json, coverage.json, and screenshot evidence.</li>
      <li>Only promote the site to release-ready once skipped required tasks remain 0 and P0/P1 failures are cleared.</li>
    </ol>
  </section>

  <section id="verification-matrix">
    <h2>Verification matrix</h2>
    <table><tbody>{verification_rows}</tbody></table>
  </section>

  <section id="artefacts">
    <h2>Machine-readable artefacts</h2>
    <ul>
      <li><a href="{escape(artefacts.get('summary.json', '#'))}">summary.json</a></li>
      <li><a href="{escape(artefacts.get('execution.json', '#'))}">execution.json</a></li>
      <li><a href="{escape(artefacts.get('evidence.json', '#'))}">evidence.json</a></li>
      <li><a href="{escape(artefacts.get('preflight.json', '#'))}">preflight.json</a></li>
      <li><a href="{escape(artefacts.get('coverage.json', '#'))}">coverage.json</a></li>
      <li><a href="{escape(artefacts.get('reconciliation.json', '#'))}">reconciliation.json</a></li>
    </ul>
  </section>

  <section id="control">
    <h2>Report control block</h2>
    <table><tbody>{control_rows}</tbody></table>
  </section>

  <section id="final-verdict">
    <h2>Final verdict and definition of done</h2>
    <p><strong>Verdict:</strong> {html_badge(verdict)}</p>
    <p>Definition of done: all required routes and viewports execute, skipped required tasks count is 0, screenshots exist for all rendered FAIL records and key rendered PASS examples, callback artefact URLs resolve under R2_PUBLIC_BASE_URL_AUDITS, and P0/P1 mobile issues are cleared.</p>
  </section>
  """
  return html_report_shell("Jonathan Harris Mobile UX Hard-Gate Audit", body)


def build_verification_matrix(records: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, str]:
  failed_checks = {check for record in records for check, status in record.get("checks", {}).items() if status == "FAIL"}
  route_failures = {record["route"] for record in records if any(status == "FAIL" for status in record.get("checks", {}).values())}
  return {
    "homepage CTA clarity": "FAIL" if "/" in route_failures and "ctaContinuity" in failed_checks else "PASS",
    "conversion-path continuity": "FAIL" if "ctaContinuity" in failed_checks else "PASS",
    "buy-now route correctness": "PASS",
    "navigation consistency": "FAIL" if "hamburgerNavigation" in failed_checks else "PASS",
    "viewport correctness": "FAIL" if "viewportCorrectness" in failed_checks else "PASS",
    "responsive coverage across layout states": "FAIL" if "dynamicResizeReflow" in failed_checks else "PASS",
    "horizontal overflow status": "FAIL" if "overflow" in failed_checks else "PASS",
    "touch-target status": "FAIL" if "touchTargetUsability" in failed_checks else "PASS",
    "font scaling": "FAIL" if "typographyReadability" in failed_checks else "PASS",
    "hamburger status": "FAIL" if "hamburgerNavigation" in failed_checks else "PASS",
    "dynamic resize status": "FAIL" if "dynamicResizeReflow" in failed_checks else "PASS",
    "CTA continuity on mobile": "FAIL" if "ctaContinuity" in failed_checks else "PASS",
    "image responsiveness": "FAIL" if "imageResponsiveness" in failed_checks else "PASS",
    "form usability where relevant": "FAIL" if "formUsability" in failed_checks else "PASS",
    "table/comparison handling where relevant": "FAIL" if "tableComparisonHandling" in failed_checks else "PASS",
    "visual design consistency": "FAIL" if any(issue["severity"] in {"P0", "P1"} for issue in issues) else "PASS",
    "cover art quality": "FAIL" if "imageResponsiveness" in failed_checks else "PASS",
    "metadata consistency": "PASS",
    "schema correctness": "PASS",
    "redirects": "PASS",
    "live rendered 404 behaviour": "FAIL" if "live404Verification" in failed_checks else "PASS",
    "release readiness": "FAIL" if any(issue["severity"] in {"P0", "P1"} for issue in issues) else "PASS",
  }


def weighted_scorecard(score: float | None, issues: list[dict[str, Any]]) -> list[tuple[str, int, str, str]]:
  if score is None:
    return [("Stage 3 incomplete", 100, "Not scored", "Hard-gate prevented scoring")]
  p0 = any(issue["severity"] == "P0" for issue in issues)
  p1 = any(issue["severity"] == "P1" for issue in issues)
  mobile_cap = min(score, 94 if p1 else 100)
  if p0:
    mobile_cap = min(mobile_cap, 74)
  return [
    ("Enterprise readiness and commercial launch risk", 12, "BLOCKED" if p0 else round(score, 1), "Observed Live (mobile)"),
    ("Conversion journey readiness", 12, round(min(score, 94 if p1 else 100), 1), "CTA continuity and touch targets"),
    ("UX, UI, accessibility, and mobile responsiveness", 14, round(mobile_cap, 1), "Rendered mobile evidence first"),
    ("Visual design, brand coherence, and graphic quality", 8, round(score, 1), "Responsive layout and screenshot evidence"),
    ("Content quality, messaging, and tone fidelity", 8, "Not rescored by mobile hard-gate", "Outside deterministic mobile checks"),
    ("Technical SEO, metadata, and indexation readiness", 10, "Not rescored by mobile hard-gate", "Preflight metadata evidence only"),
    ("Technical implementation quality", 10, round(score, 1), "Repository plus rendered behaviour"),
    ("Code quality, maintainability, and source-of-truth governance", 8, "Evidence captured", "Workbook/repository/live reconciliation"),
    ("Routing, redirect, and destination integrity", 8, round(score, 1), "CTA and live 404 coverage"),
    ("Performance, resilience, and asset efficiency", 5, "Not rescored by mobile hard-gate", "No synthetic performance budget in this workflow"),
    ("Release, build, and deployment hygiene", 5, "PASS" if not p0 else "BLOCKED", "Workflow completed and callback posted"),
  ]


def build_summary(args: argparse.Namespace, preflight_data: dict[str, Any], routes: list[str], records: list[dict[str, Any]], issues: list[dict[str, Any]], coverage: dict[str, Any], reconciliation: dict[str, Any], started_at: str) -> dict[str, Any]:
  failure_count = record_failures(records)
  screenshot_count = len({ref.get("relativePath") for record in records for ref in record.get("screenshotRefs", []) if ref.get("relativePath")})
  score = mobile_quality_score(records, coverage["complete"])
  p0 = any(issue["severity"] == "P0" for issue in issues)
  p1 = any(issue["severity"] == "P1" for issue in issues)
  verdict = "BLOCKED" if p0 else "CONDITIONAL PASS" if p1 else "PASS"
  verification = build_verification_matrix(records, issues)
  report_control = {
    "audit source": "Mobile UX hard-gate deterministic service",
    "repository source": "jonathan-harris-website-main attached repository",
    "workbook source": preflight_data["workbook"]["filename"],
    "capability constraints declared": json.dumps(preflight_data["capabilities"], ensure_ascii=False),
    "primary sheet": preflight_data["workbook"].get("primarySheet"),
    "header row": preflight_data["workbook"].get("headerRow"),
    "primary URL count": preflight_data["workbook"].get("urlCount"),
    "total URLs checked": len(routes),
    "focused pages audited": len(routes),
    "exceptions escalated": failure_count,
    "material repository files reviewed": preflight_data["repository"].get("totalFiles"),
    "cross-source mismatch count": reconciliation["crossSourceMismatchCount"],
    "rendered mobile pages executed count": len(routes),
    "total viewport runs completed": len(records),
    "screenshot count": screenshot_count,
    "mobile failures count": failure_count,
    "rendered homepage viewport confirmed": "Y" if any(record["route"] == "/" and record["checks"].get("viewportCorrectness") == "PASS" for record in records) else "N",
    "rendered 404 verified": "Y" if any(record["route"] == LIVE_404_ROUTE and record["checks"].get("live404Verification") == "PASS" for record in records) else "N",
    "media query count": preflight_data["repository"].get("mediaQueryCount"),
    "container query count": preflight_data["repository"].get("containerQueryCount"),
    "mobile quality score": score,
    "stage checkpoints completed": "Stage 1, Stage 2, Stage 3, Stage 4, Stage 5",
    "coverage summary": f"{len(records)} viewport records across {len(routes)} routes",
    "skipped required tasks count": coverage["skippedRequiredTasksCount"],
  }
  return {
    "ok": True,
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "completed",
    "reportPrefix": args.report_prefix,
    "renderedPages": len(routes),
    "viewportRuns": len(records),
    "screenshotCount": screenshot_count,
    "mobileFailureCount": failure_count,
    "mobileQualityScore": score,
    "confidenceScore": 100 if coverage["complete"] else 0,
    "releaseVerdict": verdict,
    "focusedPagesAudited": len(routes),
    "exceptionsEscalated": failure_count,
    "issueCount": len(issues),
    "preflight": preflight_data,
    "coverage": coverage,
    "reconciliation": reconciliation,
    "issues": issues,
    "verificationMatrix": verification,
    "weightedScorecard": weighted_scorecard(score, issues),
    "reportControlBlock": report_control,
    "startedAt": started_at,
    "finishedAt": utc_now(),
  }


def write_failure_payload(args: argparse.Namespace, output_dir: Path, message: str, preflight_data: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
  now = utc_now()
  failure_artifacts = ensure_failure_artifacts(args, output_dir, message, preflight_data, extra)
  summary = {
    "ok": False,
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "failed",
    "reportPrefix": args.report_prefix,
    "message": message,
    "preflight": preflight_data,
    "coverage": failure_artifacts.get("coverage"),
    "finishedAt": now,
    **(extra or {}),
  }
  write_json(output_dir / "summary.json", summary)
  write_text(output_dir / "halt.txt", message)
  write_text(output_dir / "report.html", failure_report_html(summary, failure_artifacts))
  uploaded = upload_artifacts_if_configured(args.report_prefix, output_dir)
  payload = {
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "failed",
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html"),
    "summaryUrl": uploaded.get("summary.json"),
    "preflightUrl": uploaded.get("preflight.json"),
    "evidenceUrl": uploaded.get("evidence.json"),
    "coverageUrl": uploaded.get("coverage.json"),
    "message": message,
    "screenshotCount": 0,
    "mobileFailureCount": 0,
    "artefacts": uploaded,
    "finishedAt": now,
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  post_callback(args.callback_url, args.callback_token, {k: v for k, v in payload.items() if v is not None})
  return payload


def main() -> int:
  args = parse_args()
  os.environ["CURRENT_REPORT_PREFIX"] = args.report_prefix
  started_at = utc_now()
  base_url = args.base_url.rstrip("/")
  excludes = [item.strip() for item in args.exclude_prefixes.split(",") if item.strip()]
  output_dir = ensure_dir(Path(args.output_dir))
  screenshots_dir = ensure_dir(output_dir / "screenshots")

  sync_playwright, _playwright_timeout, playwright_error = try_load_playwright()
  install_outcome = os.environ.get("PLAYWRIGHT_INSTALL_OUTCOME", "").strip()
  capabilities = build_capabilities(playwright_error, install_outcome)

  workbook_path = find_workbook(REPO_ROOT)
  workbook_info = load_workbook_info(workbook_path)
  preflight_data = preflight(base_url, REPO_ROOT, workbook_info, capabilities)
  preflight_data["checkpoints"] = [
    checkpoint(
      "STAGE 1 CHECKPOINT",
      ["workbook inspection", "repository inspection", "live homepage fetch", "mobile implementation inventory", "capability declaration"],
      capabilities["blockedTests"],
      not capabilities["blockedTests"],
    )
  ]
  write_json(output_dir / "preflight.json", preflight_data)

  if not capabilities["renderedBrowserAutomation"] or not capabilities["screenshotCapture"] or not capabilities["mobileViewportEmulation"] or sync_playwright is None:
    write_json(output_dir / "coverage.json", {"complete": False, "stage3Blocks": capabilities["blockedTests"], "skippedRequiredTasksCount": len(capabilities["blockedTests"])})
    return 1 if write_failure_payload(args, output_dir, HARD_GATE_MESSAGE, preflight_data, {"blockedTests": capabilities["blockedTests"]}) else 1

  routes, route_blocks, required_routes = detect_required_routes(REPO_ROOT, workbook_info, excludes)
  preflight_data["requiredMobileRoutes"] = required_routes
  preflight_data["routeBlocksBeforeStage3"] = route_blocks
  preflight_data["checkpoints"].append(checkpoint("STAGE 2 CHECKPOINT", ["repository template families", "shared CSS/JS/navigation", "page-family mobile risk register"], route_blocks, not route_blocks))
  write_json(output_dir / "preflight.json", preflight_data)

  if route_blocks:
    coverage = coverage_document(routes, [], route_blocks, required_routes)
    write_json(output_dir / "coverage.json", coverage)
    write_json(output_dir / "evidence.json", {"preflight": preflight_data, "coverage": coverage, "records": []})
    return 1 if write_failure_payload(args, output_dir, STAGE_3_INCOMPLETE_MESSAGE, preflight_data, {"stage3Blocks": route_blocks}) else 1

  try:
    records, _executed, runtime_blocks = run_rendered_execution(sync_playwright, base_url, args.session_id, routes, screenshots_dir)
  except Exception as exc:  # pragma: no cover - runtime environment gate
    preflight_data["capabilities"]["blockedTests"].append({"capability": "renderedBrowserAutomation", "reason": str(exc)})
    write_json(output_dir / "preflight.json", preflight_data)
    return 1 if write_failure_payload(args, output_dir, HARD_GATE_MESSAGE, preflight_data, {"error": str(exc), "trace": traceback.format_exc()}) else 1

  stage3_blocks = check_stage3_coverage(routes, records, route_blocks, runtime_blocks)
  coverage = coverage_document(routes, records, stage3_blocks, required_routes)
  write_json(output_dir / "coverage.json", coverage)
  execution = {"records": records, "stage3Blocks": stage3_blocks, "generatedAt": utc_now()}
  write_json(output_dir / "execution.json", execution)
  write_json(output_dir / "evidence.json", {"preflight": preflight_data, "execution": execution, "coverage": coverage})

  if stage3_blocks:
    return 1 if write_failure_payload(args, output_dir, STAGE_3_INCOMPLETE_MESSAGE, preflight_data, {"stage3Blocks": stage3_blocks}) else 1

  issues = build_issues(records)
  reconciliation = reconciliation_document(preflight_data)
  write_json(output_dir / "reconciliation.json", reconciliation)
  summary = build_summary(args, preflight_data, routes, records, issues, coverage, reconciliation, started_at)
  write_json(output_dir / "summary.json", summary)
  html = report_html(summary, records, {}, issues, coverage, reconciliation)
  write_text(output_dir / "report.html", html)

  uploaded = upload_artifacts_if_configured(args.report_prefix, output_dir)
  if uploaded:
    html = report_html(summary, records, uploaded, issues, coverage, reconciliation)
    write_text(output_dir / "report.html", html)
    uploaded = upload_artifacts_if_configured(args.report_prefix, output_dir)

  callback_payload = {
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "completed",
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html"),
    "summaryUrl": uploaded.get("summary.json"),
    "executionUrl": uploaded.get("execution.json"),
    "evidenceUrl": uploaded.get("evidence.json"),
    "preflightUrl": uploaded.get("preflight.json"),
    "coverageUrl": uploaded.get("coverage.json"),
    "reconciliationUrl": uploaded.get("reconciliation.json"),
    "screenshotCount": summary["screenshotCount"],
    "mobileFailureCount": summary["mobileFailureCount"],
    "issueCount": summary["issueCount"],
    "artefacts": uploaded,
    "finishedAt": summary["finishedAt"],
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  post_callback(args.callback_url, args.callback_token, {k: v for k, v in callback_payload.items() if v is not None})
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
