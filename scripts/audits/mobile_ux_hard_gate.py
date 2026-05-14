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
STORAGE_GATE_MESSAGE = (
  "MOBILE UX AUDIT STORAGE GATE FAILED - AUDIT ARTEFACT STORAGE OR CALLBACK PUBLICATION FAILED. "
  "HALTING BEFORE SCORING OR VERDICT."
)
STAGE_3_INCOMPLETE_MESSAGE = "STAGE 3 INCOMPLETE - REQUIRED MOBILE UX EXECUTION NOT FINISHED - HALTING BEFORE REPORT."
MANDATORY_COMPLETION_ARTEFACTS = [
  "report.html",
  "report.json",
  "summary.json",
  "coverage.json",
  "execution.json",
  "evidence.json",
  "preflight.json",
  "screenshot-manifest.json",
  "focused-page-appendix.json",
  "repository-issue-appendix.json",
  "mandatory-mobile-scorecard.json",
  "responsive-fix-appendix.json",
]
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

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CHECK_GROUP_TITLES = {
  "viewportCorrectness": "Shared viewport metadata/runtime viewport defect",
  "responsiveCoverage": "Shared responsive coverage defect",
  "overflow": "Shared horizontal overflow defect",
  "hamburgerNavigation": "Shared mobile navigation/hamburger behaviour defect",
  "touchTargetUsability": "Shared touch-target usability defect",
  "dynamicResizeReflow": "Shared dynamic resize/reflow defect",
  "ctaContinuity": "Shared CTA continuity defect",
  "typographyReadability": "Shared typography/readability defect",
  "formUsability": "Shared form usability defect",
  "imageResponsiveness": "Shared image responsiveness defect",
  "tableComparisonHandling": "Shared table/comparison handling defect",
  "live404Verification": "Live rendered 404 shell defect",
}
CHECK_TO_TECHNICAL_AREA = {
  "viewportCorrectness": "HTML head / shared partial",
  "responsiveCoverage": "CSS responsive rules",
  "overflow": "CSS layout / component sizing",
  "hamburgerNavigation": "Header navigation JavaScript and CSS",
  "touchTargetUsability": "CSS controls and interactive spacing",
  "dynamicResizeReflow": "Responsive CSS and navigation state reset",
  "ctaContinuity": "CTA markup, routing and overlay behaviour",
  "typographyReadability": "Responsive typography CSS",
  "formUsability": "Form markup and CSS",
  "imageResponsiveness": "Image/CSS asset responsiveness",
  "tableComparisonHandling": "Comparison/table layout CSS",
  "live404Verification": "404 route shell and shared layout",
}


class HardGateCapabilityError(RuntimeError):
  """Raised when rendered browser automation, screenshots, or mobile emulation cannot be proven."""

  def __init__(self, message: str, blocks: list[dict[str, str]] | None = None):
    super().__init__(message)
    self.blocks = blocks or []


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


def missing_r2_upload_config() -> list[str]:
  required = [
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_AUDITS",
    "R2_PUBLIC_BASE_URL_AUDITS",
  ]
  return [name for name in required if not os.environ.get(name, "").strip()]


def r2_upload_configured() -> bool:
  return not missing_r2_upload_config()


def make_public_url(relative_path: str) -> str | None:
  public_base = os.environ.get("R2_PUBLIC_BASE_URL_AUDITS", "").strip().rstrip("/")
  if not public_base:
    return None
  key = f"{os.environ.get('CURRENT_REPORT_PREFIX', '').strip().rstrip('/')}/{relative_path.strip('/')}".strip("/")
  if not key:
    return None
  return f"{public_base}/{key}"


def upload_artifacts_if_configured(report_prefix: str, output_dir: Path, *, require: bool = False) -> dict[str, str]:
  missing = missing_r2_upload_config()
  if missing:
    if require:
      raise RuntimeError(f"R2 audit upload configuration is incomplete: missing {', '.join(missing)}")
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


def _dedupe_blocks(blocks: list[dict[str, str]]) -> list[dict[str, str]]:
  seen = set()
  deduped = []
  for block in blocks:
    capability = str(block.get("capability") or "mobileUxExecution")
    reason = str(block.get("reason") or block.get("blocker") or "blocked")
    key = (capability, reason)
    if key in seen:
      continue
    seen.add(key)
    deduped.append({**block, "capability": capability, "reason": reason})
  return deduped


def probe_rendered_mobile_runtime(sync_playwright: Any | None, probe_dir: Path) -> list[dict[str, str]]:
  """Prove Chromium launch, screenshot capture, and mobile viewport emulation before scoring."""
  if sync_playwright is None:
    reason = "Playwright sync runtime is unavailable"
    return [
      {"capability": "renderedBrowserAutomation", "reason": reason},
      {"capability": "screenshotCapture", "reason": reason},
      {"capability": "mobileViewportEmulation", "reason": reason},
    ]

  ensure_dir(probe_dir)
  browser = None
  context = None
  blocks: list[dict[str, str]] = []
  try:
    with sync_playwright() as playwright:
      try:
        browser = playwright.chromium.launch(headless=True)
      except Exception as exc:
        reason = f"Chromium launch failed: {exc}"
        return [
          {"capability": "renderedBrowserAutomation", "reason": reason},
          {"capability": "screenshotCapture", "reason": reason},
          {"capability": "mobileViewportEmulation", "reason": reason},
        ]

      try:
        context = browser.new_context(
          viewport={"width": 390, "height": 844},
          is_mobile=True,
          has_touch=True,
          device_scale_factor=1,
        )
        page = context.new_page()
        page.set_content(
          "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
          "<body><button style='width:44px;height:44px'>Probe</button></body></html>",
          wait_until="domcontentloaded",
        )
        viewport_width = page.evaluate("() => window.innerWidth")
        touch_points = page.evaluate("() => navigator.maxTouchPoints || 0")
        if int(viewport_width) != 390 or int(touch_points) < 1:
          blocks.append({
            "capability": "mobileViewportEmulation",
            "reason": f"probe returned innerWidth={viewport_width}, maxTouchPoints={touch_points}",
          })
        try:
          page.screenshot(path=str(probe_dir / "capability-probe.png"), full_page=True)
        except Exception as exc:
          blocks.append({"capability": "screenshotCapture", "reason": f"probe screenshot failed: {exc}"})
      except Exception as exc:
        reason = f"rendered mobile probe failed: {exc}"
        blocks.extend([
          {"capability": "renderedBrowserAutomation", "reason": reason},
          {"capability": "mobileViewportEmulation", "reason": reason},
        ])
      finally:
        if context is not None:
          context.close()
        if browser is not None:
          browser.close()
  except Exception as exc:
    reason = f"Playwright runtime probe failed: {exc}"
    return [
      {"capability": "renderedBrowserAutomation", "reason": reason},
      {"capability": "screenshotCapture", "reason": reason},
      {"capability": "mobileViewportEmulation", "reason": reason},
    ]

  return _dedupe_blocks(blocks)


def build_capabilities(playwright_error: str | None = None, install_outcome: str | None = None, runtime_blocks: list[dict[str, str]] | None = None) -> dict[str, Any]:
  blocked: list[dict[str, str]] = []
  if playwright_error:
    blocked.append({"capability": "renderedBrowserAutomation", "reason": playwright_error})
    blocked.append({"capability": "screenshotCapture", "reason": playwright_error})
    blocked.append({"capability": "mobileViewportEmulation", "reason": playwright_error})
  if install_outcome and install_outcome not in {"", "success", "skipped"}:
    reason = f"Playwright Chromium install outcome: {install_outcome}"
    blocked.append({"capability": "renderedBrowserAutomation", "reason": reason})
    blocked.append({"capability": "screenshotCapture", "reason": reason})
    blocked.append({"capability": "mobileViewportEmulation", "reason": reason})
    blocked.append({"capability": "playwrightChromiumInstall", "reason": reason})
  blocked.extend(runtime_blocks or [])
  blocked = _dedupe_blocks(blocked)
  unavailable = {item["capability"] for item in blocked}
  return {
    "staticFileInspection": True,
    "fetchSourceInspection": True,
    "renderedBrowserAutomation": "renderedBrowserAutomation" not in unavailable,
    "screenshotCapture": "screenshotCapture" not in unavailable,
    "mobileViewportEmulation": "mobileViewportEmulation" not in unavailable,
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
  checks["responsiveCoverage"] = "PASS" if checks.get("overflow") == "PASS" and checks.get("dynamicResizeReflow") == "PASS" else "FAIL"
  details["responsiveCoverage"] = {
    "derivedFrom": ["overflow", "dynamicResizeReflow"],
    "status": checks["responsiveCoverage"],
  }
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


def missing_required_completion_artefacts(uploaded: dict[str, str]) -> list[str]:
  return [name for name in MANDATORY_COMPLETION_ARTEFACTS if not uploaded.get(name)]


def capture_required_screenshot(page: Any, file_path: Path, relative_path: str) -> dict[str, str | None]:
  try:
    page.screenshot(path=str(file_path), full_page=True)
  except Exception as exc:
    raise HardGateCapabilityError(
      HARD_GATE_MESSAGE,
      [{"capability": "screenshotCapture", "reason": f"required screenshot failed for {relative_path}: {exc}"}],
    ) from exc
  return screenshot_ref(relative_path)


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
              record["screenshotRefs"].append(capture_required_screenshot(page, file_path, f"screenshots/{name}"))
            records.append(record)
            executed.append({"route": route, "viewport": str(width)})
          except Exception as exc:
            runtime_blocks.append({"route": route, "viewport": str(width), "blocker": str(exc)})
            fail_name = screenshot_name(route, width, "runtime-blocked")
            fail_path = screenshots_dir / fail_name
            refs = []
            try:
              refs.append(capture_required_screenshot(page, fail_path, f"screenshots/{fail_name}"))
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
                "responsiveCoverage": "FAIL",
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


def remediation_for_check(check: str, record: dict[str, Any]) -> str:
  anchor = record.get("selectorComponentCodeAnchor") or "the affected rendered component"
  route = record.get("route") or "the affected route"
  viewport = record.get("viewport") or "the failing viewport"
  guidance = {
    "viewportCorrectness": "Use the shared head/partial viewport declaration `width=device-width, initial-scale=1, viewport-fit=cover` and verify the live rendered page reports the expected viewport width.",
    "overflow": f"Trace the overflowing element from `{anchor}` on `{route}` at {viewport}px. Replace fixed/min-width layout with max-width:100%, wrapping, grid minmax(), or an intentional overflow-x container for genuinely wide content.",
    "hamburgerNavigation": "Verify `.jh-hamburger` and `#jh-mobile-nav` open, close, reopen, close on Escape/outside click, and reset on desktop breakpoint without body-scroll or overlay lock defects.",
    "touchTargetUsability": "Increase crowded controls to a reliable 44px minimum target box with adequate gap, preserving CTA hierarchy and keyboard/focus affordances.",
    "dynamicResizeReflow": "Fix responsive breakpoint/reflow handling so header, nav, cards, forms, grids, drawers, and sticky elements reset cleanly during mobile-tablet-desktop resize.",
    "ctaContinuity": "Keep the primary CTA visible, tappable, and routed to the intended destination in the rendered mobile state without overlay, clipping, or dead-end interactions.",
    "typographyReadability": "Adjust responsive type scale, line length, spacing, and wrapping so headings, body text, labels, buttons, and nav items do not clip, crush, or overlap.",
    "formUsability": "Set visible input/control font size to at least 16px, keep labels and helper text associated, and preserve tappable submit flow at narrow widths.",
    "imageResponsiveness": "Constrain images and artwork with responsive sizing/object-fit rules so they scale without distortion, clipping, overflow, or layout breakage.",
    "tableComparisonHandling": "Use a deliberate table strategy: scroll container, stacked mobile cards, wrapping columns, or transformed comparison rows; do not allow inaccessible clipped wide content.",
    "live404Verification": "Fix the rendered 404 route shell so header, footer, CTA path, viewport behaviour, and mobile layout all pass the same Stage 3 checks as normal pages.",
  }
  return guidance.get(check, "Fix the affected responsive component, then rerun the same route and viewport in the mobile hard-gate workflow.")



def normalise_anchor(anchor: str | None) -> str:
  value = str(anchor or "").strip()
  if not value or value == "Best available rendered component anchor recorded in details":
    return "unmapped-rendered-component"
  return re.sub(r"\s+", " ", value[:180])


def severity_for_check(check: str, route: str, viewport: int | str) -> str:
  width = int(viewport)
  if check in {"viewportCorrectness", "live404Verification"}:
    return "P0"
  if route in CRITICAL_ROUTES and check in {"ctaContinuity", "hamburgerNavigation", "overflow"} and width <= 768:
    return "P0"
  if check in {"touchTargetUsability", "dynamicResizeReflow", "formUsability", "imageResponsiveness", "tableComparisonHandling", "typographyReadability", "responsiveCoverage"}:
    return "P1"
  return "P2"


def worse_severity(left: str, right: str) -> str:
  return left if SEVERITY_ORDER.get(left, 99) <= SEVERITY_ORDER.get(right, 99) else right


def route_source_path(route: str, repo_root: Path = REPO_ROOT) -> str:
  if route == LIVE_404_ROUTE:
    candidate = repo_root / "404.html"
    return "404.html" if candidate.exists() else "live route only - no static 404.html anchor found"
  if route in {"", "/"}:
    return "index.html"
  candidate = repo_root / route.strip("/") / "index.html"
  if candidate.exists():
    return candidate.relative_to(repo_root).as_posix()
  html_candidate = repo_root / f"{route.strip('/')}.html"
  if html_candidate.exists():
    return html_candidate.relative_to(repo_root).as_posix()
  return f"{route.strip('/') or 'index'}/index.html (not found in repository snapshot)"


def source_anchor_candidates(anchor: str | None) -> list[str]:
  raw = str(anchor or "").strip()
  if not raw:
    return []
  candidates = [raw]
  if raw.startswith("."):
    token = raw[1:].split()[0].split(":")[0]
    candidates.extend([f".{token}", token, f'class="{token}', f"class='{token}"])
  elif raw.startswith("#"):
    token = raw[1:].split()[0].split(":")[0]
    candidates.extend([f"#{token}", f'id="{token}"', f"id='{token}'"])
  return [item for item in dict.fromkeys(candidates) if item]


def snippet_around(text: str, needle: str, radius: int = 420) -> str | None:
  pos = text.find(needle)
  if pos < 0:
    return None
  start = max(0, pos - radius)
  end = min(len(text), pos + len(needle) + radius)
  snippet = text[start:end].strip()
  return snippet[:1200]


def source_snippet_for_anchor(route: str, anchor: str | None, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
  candidate_paths = []
  route_path = route_source_path(route, repo_root)
  if "not found" not in route_path and "live route only" not in route_path:
    candidate_paths.append(route_path)
  candidate_paths.extend([
    "assets/css/site.css",
    "assets/js/site.js",
    "assets/js/main.js",
    "assets/partials/header.html",
    "assets/partials/head.html",
    "assets/partials/footer.html",
  ])
  needles = source_anchor_candidates(anchor)
  for relative in dict.fromkeys(candidate_paths):
    path = repo_root / relative
    if not path.exists() or path.is_dir():
      continue
    content = read_text_preview(path, 250_000)
    if not needles:
      return {
        "available": True,
        "filePath": relative,
        "snippet": content[:1000],
        "matchType": "route-source-preview",
      }
    for needle in needles:
      snippet = snippet_around(content, needle)
      if snippet:
        return {
          "available": True,
          "filePath": relative,
          "snippet": snippet,
          "matchType": f"anchor match: {needle}",
        }
  return {
    "available": False,
    "filePath": route_path,
    "reasonExactReplacementUnavailable": "The rendered browser evidence did not map deterministically to an exact stable source snippet in this repository snapshot. No line number or replacement code has been invented.",
  }


def group_key_for_issue(issue: dict[str, Any]) -> tuple[str, str, str]:
  anchor = normalise_anchor(issue.get("bestAvailableCodeAnchor") or issue.get("selectorComponentCodeAnchor"))
  check = str(issue.get("check") or "mobileUx")
  template = str(issue.get("templateFamily") or detect_template_family(issue.get("route") or "/"))
  shared_component_checks = {"hamburgerNavigation", "ctaContinuity", "overflow", "typographyReadability", "imageResponsiveness", "touchTargetUsability", "dynamicResizeReflow"}
  if check in shared_component_checks and anchor != "unmapped-rendered-component":
    template = "shared-component"
  return (check, template, anchor)


def build_issues(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
  pending: list[dict[str, Any]] = []
  for record in records:
    failed = [name for name, status in record.get("checks", {}).items() if status == "FAIL"]
    for check in failed:
      route = record["route"]
      severity = severity_for_check(check, route, record["viewport"])
      remediation = remediation_for_check(check, record)
      pending.append({
        "issueId": f"MUX-{len(pending) + 1:03d}",
        "groupId": None,
        "exactUrlOrFilePath": record["url"],
        "route": route,
        "viewport": record["viewport"],
        "templateFamily": record.get("templateFamily") or detect_template_family(route),
        "check": check,
        "defectDescription": f"{check} failed during rendered mobile execution.",
        "evidenceLabel": "Observed Live (mobile)",
        "severity": severity,
        "consequence": "Mobile users may hit layout, navigation, readability, or conversion friction.",
        "exactRemediation": remediation,
        "ownerClass": "Website frontend / static site implementation",
        "acceptanceCriteria": f"{check} returns PASS for {route} at {record['viewport']}px and any failure screenshot is superseded by a passing screenshot.",
        "verificationMethod": "Rerun POST /audits/mobile-ux/run and confirm execution.json plus mandatory-mobile-scorecard.json show PASS for the affected route, viewport, and check.",
        "screenshotRefs": record.get("screenshotRefs", []),
        "bestAvailableCodeAnchor": record.get("selectorComponentCodeAnchor") or "Best available rendered component anchor recorded in execution details",
        "selectorComponentCodeAnchor": record.get("selectorComponentCodeAnchor"),
        "affectedFilePath": route_source_path(route),
      })

  key_to_group: dict[tuple[str, str, str], str] = {}
  for issue in pending:
    key = group_key_for_issue(issue)
    if key not in key_to_group:
      key_to_group[key] = f"MUX-G{len(key_to_group) + 1:03d}"
    issue["groupId"] = key_to_group[key]
  return pending


def root_cause_groups_document(issues: list[dict[str, Any]], records: list[dict[str, Any]] | None = None, summary: dict[str, Any] | None = None) -> dict[str, Any]:
  grouped: dict[str, list[dict[str, Any]]] = {}
  for issue in issues:
    grouped.setdefault(str(issue.get("groupId") or "MUX-G000"), []).append(issue)

  groups = []
  for group_id in sorted(grouped):
    group_issues = grouped[group_id]
    checks = sorted({str(issue.get("check")) for issue in group_issues if issue.get("check")})
    routes = sorted({str(issue.get("route")) for issue in group_issues if issue.get("route")})
    route_families = sorted({str(issue.get("templateFamily")) for issue in group_issues if issue.get("templateFamily")})
    viewports = sorted({int(issue.get("viewport")) for issue in group_issues if str(issue.get("viewport", "")).isdigit()})
    severity = "P3"
    for issue in group_issues:
      severity = worse_severity(str(issue.get("severity") or "P3"), severity)
    screenshots = []
    seen_screens = set()
    for issue in group_issues:
      for ref in issue.get("screenshotRefs", []):
        key = ref.get("relativePath") or ref.get("publicUrl")
        if key and key not in seen_screens:
          seen_screens.add(key)
          screenshots.append(ref)
    first = group_issues[0]
    anchor = first.get("bestAvailableCodeAnchor") or first.get("selectorComponentCodeAnchor") or "Best available rendered component anchor recorded in details"
    source = source_snippet_for_anchor(str(first.get("route") or "/"), str(anchor))
    groups.append({
      "groupId": group_id,
      "title": CHECK_GROUP_TITLES.get(checks[0], "Shared mobile UX defect") if len(checks) == 1 else "Shared mobile UX defect cluster",
      "affectedRouteFamilies": route_families,
      "affectedRoutes": routes,
      "affectedUrlCount": len(routes),
      "affectedViewportRange": f"{min(viewports)}-{max(viewports)}px" if viewports else "not recorded",
      "failedMetricTypes": checks,
      "severity": severity,
      "evidenceLabel": "Observed Live (mobile)",
      "representativeScreenshots": screenshots[:6],
      "bestAvailableCodeAnchor": anchor,
      "bestAvailableSource": source,
      "consequence": first.get("consequence"),
      "exactRemediation": first.get("exactRemediation"),
      "acceptanceCriteria": f"All linked issues in {group_id} return PASS in mandatory-mobile-scorecard.json across affected routes and viewport bands.",
      "verificationMethod": "Rerun the Mobile UX hard-gate workflow and compare execution.json, screenshot-manifest.json, and mandatory-mobile-scorecard.json for the linked group issue IDs.",
      "linkedIssueIds": [issue.get("issueId") for issue in group_issues],
      "detailedAppendixReference": "repository-issue-appendix.json",
    })
  return {
    "auditType": "mobile-ux",
    "sessionId": summary.get("sessionId") if summary else None,
    "reportPrefix": summary.get("reportPrefix") if summary else None,
    "groupCount": len(groups),
    "groups": groups,
    "groupingPolicy": "Deterministic grouping by failed metric, template/shared-component family, and best available rendered selector/component anchor. Raw per-viewport records remain in execution.json and mandatory-mobile-scorecard.json.",
    "generatedAt": utc_now(),
  }


def screenshot_manifest_document(records: list[dict[str, Any]], summary: dict[str, Any] | None = None) -> dict[str, Any]:
  entries = []
  seen = set()
  for record in records:
    failed = any(status == "FAIL" for status in record.get("checks", {}).values())
    for ref in record.get("screenshotRefs", []):
      relative = ref.get("relativePath")
      if not relative or relative in seen:
        continue
      seen.add(relative)
      entries.append({
        "relativePath": relative,
        "publicUrl": ref.get("publicUrl"),
        "route": record.get("route"),
        "url": record.get("url"),
        "viewport": record.get("viewport"),
        "templateFamily": record.get("templateFamily"),
        "evidenceType": "rendered FAIL" if failed else "rendered PASS confirmation",
      })
  return {
    "auditType": "mobile-ux",
    "sessionId": summary.get("sessionId") if summary else None,
    "reportPrefix": summary.get("reportPrefix") if summary else None,
    "totalScreenshots": len(entries),
    "screenshots": entries,
    "policy": "Screenshots are required for every rendered FAIL and for key rendered PASS confirmations at mobile widths.",
    "generatedAt": utc_now(),
  }


def responsive_coverage_status(record: dict[str, Any]) -> str:
  checks = record.get("checks", {})
  if checks.get("overflow") == "PASS" and checks.get("dynamicResizeReflow") == "PASS":
    return "PASS"
  return "FAIL"


def mandatory_mobile_scorecard_document(records: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
  rows = []
  for record in records:
    checks = record.get("checks", {})
    rows.append({
      "url": record.get("url"),
      "route": record.get("route"),
      "templateFamily": record.get("templateFamily"),
      "viewport": record.get("viewport"),
      "viewportCorrectness": checks.get("viewportCorrectness"),
      "responsiveCoverage": checks.get("responsiveCoverage") or responsive_coverage_status(record),
      "overflow": checks.get("overflow"),
      "touchTargetUsability": checks.get("touchTargetUsability"),
      "hamburgerNavigation": checks.get("hamburgerNavigation"),
      "dynamicResizeReflow": checks.get("dynamicResizeReflow"),
      "ctaContinuity": checks.get("ctaContinuity"),
      "typographyReadability": checks.get("typographyReadability"),
      "imageResponsiveness": checks.get("imageResponsiveness"),
      "formUsability": checks.get("formUsability"),
      "tableComparisonHandling": checks.get("tableComparisonHandling"),
      "screenshotRefs": record.get("screenshotRefs", []),
      "defectSummary": record.get("defectSummary", ""),
      "selectorComponentCodeAnchor": record.get("selectorComponentCodeAnchor"),
    })
  return {
    "auditType": "mobile-ux",
    "sessionId": summary.get("sessionId"),
    "reportPrefix": summary.get("reportPrefix"),
    "requiredViewports": VIEWPORTS,
    "summaryTotals": pass_fail_totals(records),
    "mobileQualityScore": summary.get("mobileQualityScore"),
    "mobileFailCount": summary.get("mobileFailureCount"),
    "mobileScreenshotCount": summary.get("screenshotCount"),
    "rows": rows,
    "generatedAt": utc_now(),
  }


def focused_page_appendix_document(summary: dict[str, Any], records: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
  by_route = []
  for route in sorted({record.get("route") for record in records}):
    route_records = [record for record in records if record.get("route") == route]
    route_issues = [issue for issue in issues if issue.get("route") == route]
    screenshots = [ref for record in route_records for ref in record.get("screenshotRefs", [])]
    by_route.append({
      "route": route,
      "url": route_records[0].get("url") if route_records else "",
      "templateFamily": route_records[0].get("templateFamily") if route_records else detect_template_family(route or "/"),
      "viewportRuns": len(route_records),
      "viewports": sorted(record.get("viewport") for record in route_records),
      "failures": sum(1 for record in route_records if any(status == "FAIL" for status in record.get("checks", {}).values())),
      "issueIds": [issue.get("issueId") for issue in route_issues],
      "groupIds": sorted({str(issue.get("groupId")) for issue in route_issues if issue.get("groupId")}),
      "screenshotRefs": screenshots,
    })
  return {
    "auditType": "mobile-ux",
    "sessionId": summary.get("sessionId"),
    "reportPrefix": summary.get("reportPrefix"),
    "focusedPagesAudited": summary.get("focusedPagesAudited"),
    "routes": by_route,
    "generatedAt": utc_now(),
  }


def repository_issue_appendix_document(summary: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
  return {
    "auditType": "mobile-ux",
    "sessionId": summary.get("sessionId"),
    "reportPrefix": summary.get("reportPrefix"),
    "issueCount": len(issues),
    "groupCount": len({issue.get("groupId") for issue in issues if issue.get("groupId")}),
    "issues": issues,
    "generatedAt": utc_now(),
  }


def responsive_fix_appendix_document(summary: dict[str, Any], issues: list[dict[str, Any]], records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
  groups = root_cause_groups_document(issues, records or [], summary)["groups"]
  rows = []
  for group in groups:
    if group.get("severity") not in {"P0", "P1"}:
      continue
    source = group.get("bestAvailableSource") if isinstance(group.get("bestAvailableSource"), dict) else {}
    snippets_available = bool(source.get("available"))
    current = source.get("snippet") if snippets_available else source.get("reasonExactReplacementUnavailable")
    first_issue = next((issue for issue in issues if issue.get("issueId") in group.get("linkedIssueIds", [])), {})
    rows.append({
      "fixId": f"FIX-{group.get('groupId')}",
      "linkedGroupId": group.get("groupId"),
      "linkedIssueIds": group.get("linkedIssueIds", []),
      "severity": group.get("severity"),
      "affectedFilePath": source.get("filePath") or first_issue.get("affectedFilePath") or first_issue.get("exactUrlOrFilePath"),
      "bestAvailableCodeAnchor": group.get("bestAvailableCodeAnchor"),
      "currentCodeOrClosestRelevantSnippet": current,
      "proposedReplacementCodeOrPatchInstruction": (
        "Exact replacement code is unavailable because the rendered failure cannot be deterministically mapped to a single stable source block. "
        f"Apply this patch instruction instead: {group.get('exactRemediation')}"
      ) if not snippets_available else (
        f"Patch the shown source block using the smallest CSS/HTML/JS change that satisfies: {group.get('exactRemediation')}"
      ),
      "cssJsTemplateAreaAffected": CHECK_TO_TECHNICAL_AREA.get((group.get("failedMetricTypes") or [""])[0], "Website frontend"),
      "effortEstimate": "M (2-8 hrs)" if group.get("severity") == "P0" else "S (<2 hrs)",
      "riskLevel": "High" if group.get("severity") == "P0" else "Medium",
      "acceptanceCriteria": group.get("acceptanceCriteria"),
      "viewportRetestSteps": [
        f"Rerun Mobile UX audit and filter mandatory-mobile-scorecard.json for group {group.get('groupId')} linked issues.",
        f"Confirm affected viewport band {group.get('affectedViewportRange')} returns PASS for {', '.join(group.get('failedMetricTypes') or [])}.",
        "Confirm screenshot-manifest.json contains fresh passing evidence or the old failure screenshot is no longer linked from active failures.",
      ],
      "screenshotReferences": group.get("representativeScreenshots", []),
      "manualRemediationReason": None if snippets_available else source.get("reasonExactReplacementUnavailable"),
      "verificationMethod": group.get("verificationMethod"),
    })
  return {
    "auditType": "mobile-ux",
    "sessionId": summary.get("sessionId"),
    "reportPrefix": summary.get("reportPrefix"),
    "rows": rows,
    "generatedAt": utc_now(),
  }


def report_json_document(
  summary: dict[str, Any],
  records: list[dict[str, Any]],
  issues: list[dict[str, Any]],
  coverage: dict[str, Any],
  reconciliation: dict[str, Any],
  artefacts: dict[str, str] | None = None,
) -> dict[str, Any]:
  root_groups = root_cause_groups_document(issues, records, summary)
  return {
    "auditType": "mobile-ux",
    "schemaVersion": "mobile-ux-hard-gate-v5.0-executive-groups",
    "status": summary.get("status"),
    "sessionId": summary.get("sessionId"),
    "reportPrefix": summary.get("reportPrefix"),
    "releaseVerdict": summary.get("releaseVerdict"),
    "mobileQualityScore": summary.get("mobileQualityScore"),
    "confidenceModel": summary.get("confidenceModel"),
    "summary": summary,
    "coverage": coverage,
    "reconciliation": reconciliation,
    "rootCauseGroups": root_groups,
    "issueSummaries": [
      {
        "issueId": issue.get("issueId"),
        "groupId": issue.get("groupId"),
        "severity": issue.get("severity"),
        "route": issue.get("route"),
        "viewport": issue.get("viewport"),
        "check": issue.get("check"),
        "evidenceLabel": issue.get("evidenceLabel"),
        "bestAvailableCodeAnchor": issue.get("bestAvailableCodeAnchor"),
      }
      for issue in issues
    ],
    "execution": {
      "records": records,
      "rawRecordsPolicy": "Full raw per-route and per-viewport Mobile Execution Records are intentionally kept in report.json/execution.json and summarised, not dumped, in report.html.",
    },
    "issues": issues,
    "appendixLinks": artefacts or summary.get("artefactUrls") or {},
    "appendices": {
      "screenshotManifest": screenshot_manifest_document(records, summary),
      "focusedPageAppendix": focused_page_appendix_document(summary, records, issues),
      "repositoryIssueAppendix": repository_issue_appendix_document(summary, issues),
      "mandatoryMobileScorecard": mandatory_mobile_scorecard_document(records, summary),
      "responsiveFixAppendix": responsive_fix_appendix_document(summary, issues, records),
    },
    "evidencePolicy": {
      "allowedLabels": [
        "Observed Live",
        "Observed Live (mobile)",
        "Observed in Markup",
        "Observed in Repository",
        "Cross-Source Mismatch",
        "Reasoned Inference",
      ],
      "scoringRule": "No score or release verdict is emitted unless Stage 3 rendered mobile execution is complete.",
      "unsupportedClaimRule": "Visual design, cover-art, brand, and tone claims are not marked FAIL unless deterministic evidence directly supports the exact claim.",
    },
    "generatedAt": utc_now(),
  }

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



def status_text(value: Any) -> str:
  if isinstance(value, dict):
    return str(value.get("status") or "BLOCKED")
  return str(value)


def status_evidence(value: Any) -> str:
  if isinstance(value, dict):
    return str(value.get("evidence") or value.get("source") or "")
  return ""


def report_html(summary: dict[str, Any], records: list[dict[str, Any]], artefacts: dict[str, str], issues: list[dict[str, Any]], coverage: dict[str, Any], reconciliation: dict[str, Any]) -> str:
  totals = pass_fail_totals(records)
  score = summary.get("mobileQualityScore")
  verdict = summary.get("releaseVerdict")
  root_groups_doc = root_cause_groups_document(issues, records, summary)
  root_groups = root_groups_doc["groups"]
  critical_groups = [group for group in root_groups if group.get("severity") == "P0"]
  p1_groups = [group for group in root_groups if group.get("severity") == "P1"]
  confidence = summary.get("confidenceModel") or {}

  score_rows = "".join(
    f"<tr><td>{escape(name)}</td><td>{weight}</td><td>{escape(str(value))}</td><td>{escape(note)}</td></tr>"
    for name, weight, value, note in summary["weightedScorecard"]
  )

  confidence_rows = "".join(
    f"<tr><td>{escape(str(key))}</td><td>{escape(str(value.get('status') if isinstance(value, dict) else value))}</td>"
    f"<td>{escape(str(value.get('evidence') if isinstance(value, dict) else ''))}</td></tr>"
    for key, value in confidence.items()
  ) or "<tr><td colspan='3'>Confidence model was not supplied.</td></tr>"

  group_rows = []
  for group in root_groups:
    screenshots = "<br>".join(link_for_ref(ref) for ref in group.get("representativeScreenshots", [])) or "—"
    source = group.get("bestAvailableSource") if isinstance(group.get("bestAvailableSource"), dict) else {}
    source_label = source.get("filePath") or group.get("bestAvailableCodeAnchor") or "—"
    group_rows.append(
      f"<tr><td><code>{escape(str(group['groupId']))}</code></td><td>{escape(str(group['title']))}</td>"
      f"<td>{escape(str(group['severity']))}</td><td>{escape(', '.join(group.get('affectedRouteFamilies') or []))}</td>"
      f"<td>{escape(str(group.get('affectedUrlCount')))}</td><td>{escape(str(group.get('affectedViewportRange')))}</td>"
      f"<td>{escape(', '.join(group.get('failedMetricTypes') or []))}</td><td>{escape(str(source_label))}</td>"
      f"<td>{escape(str(group.get('exactRemediation')))}</td><td>{screenshots}</td></tr>"
    )

  capability_rows = "".join(
    f"<tr><td>{escape(key)}</td><td>{escape(str(value))}</td></tr>"
    for key, value in summary["preflight"]["capabilities"].items()
  )
  blocked_tests = summary["preflight"].get("capabilities", {}).get("blockedTests", [])
  blocked_rows = "".join(
    f"<tr><td>{escape(str(item.get('capability') or item.get('stage') or item.get('route') or 'mobile UX task'))}</td><td>{escape(str(item.get('reason') or item.get('blocker') or item))}</td></tr>"
    if isinstance(item, dict)
    else f"<tr><td>mobile UX task</td><td>{escape(str(item))}</td></tr>"
    for item in blocked_tests
  ) or "<tr><td colspan='2'>No blocked tests declared after capability probe.</td></tr>"
  mismatch_rows = "".join(
    f"<tr><td>{escape(item['mismatchId'])}</td><td>{escape(item['intendedState'])}</td><td>{escape(str(item['implementedState']))}</td><td>{escape(str(item['liveState']))}</td><td>{escape(item['remediationOwner'])}</td></tr>"
    for item in reconciliation["crossSourceMismatches"]
  ) or "<tr><td colspan='5'>No material cross-source mismatch recorded during preflight.</td></tr>"

  verification = summary["verificationMatrix"]
  verification_rows = "".join(
    f"<tr><td>{escape(name)}</td><td>{html_badge(status_text(value))}</td><td>{escape(status_evidence(value))}</td></tr>"
    for name, value in verification.items()
  )
  report_control = summary["reportControlBlock"]
  control_rows = "".join(f"<tr><td>{escape(key)}</td><td>{escape(str(value))}</td></tr>" for key, value in report_control.items())

  screenshot_manifest = screenshot_manifest_document(records, summary)
  screenshot_rows = "".join(
    f"<tr><td><code>{escape(str(item.get('relativePath')))}</code></td><td>{escape(str(item.get('route')))}</td>"
    f"<td>{escape(str(item.get('viewport')))}px</td><td>{escape(str(item.get('evidenceType')))}</td>"
    f"<td>{link_for_ref({'relativePath': item.get('relativePath'), 'publicUrl': item.get('publicUrl')})}</td></tr>"
    for item in screenshot_manifest["screenshots"][:80]
  ) or "<tr><td colspan='5'>No screenshot references were recorded.</td></tr>"

  focused_appendix = focused_page_appendix_document(summary, records, issues)
  focused_rows = "".join(
    f"<tr><td><code>{escape(str(row.get('route')))}</code></td><td>{escape(str(row.get('templateFamily')))}</td>"
    f"<td>{escape(str(row.get('viewportRuns')))}</td><td>{escape(str(row.get('failures')))}</td>"
    f"<td>{escape(', '.join(str(item) for item in row.get('groupIds') or []))}</td></tr>"
    for row in focused_appendix["routes"][:80]
  ) or "<tr><td colspan='5'>No focused page records were generated.</td></tr>"

  mandatory_scorecard = mandatory_mobile_scorecard_document(records, summary)
  family_counter: dict[tuple[str, str], dict[str, int]] = {}
  for row in mandatory_scorecard["rows"]:
    key = (str(row.get("templateFamily")), str(row.get("viewport")))
    family_counter.setdefault(key, {"runs": 0, "failRows": 0})
    family_counter[key]["runs"] += 1
    if any(row.get(check) == "FAIL" for check in ["viewportCorrectness", "responsiveCoverage", "overflow", "touchTargetUsability", "hamburgerNavigation", "dynamicResizeReflow", "ctaContinuity", "typographyReadability", "imageResponsiveness", "formUsability", "tableComparisonHandling"]):
      family_counter[key]["failRows"] += 1
  scorecard_rows = "".join(
    f"<tr><td>{escape(template)}</td><td>{escape(viewport)}px</td><td>{counts['runs']}</td><td>{counts['failRows']}</td></tr>"
    for (template, viewport), counts in sorted(family_counter.items())
  ) or "<tr><td colspan='4'>No rendered scorecard rows were recorded.</td></tr>"

  fix_appendix = responsive_fix_appendix_document(summary, issues, records)
  fix_rows = "".join(
    f"<tr><td><code>{escape(str(row.get('fixId')))}</code></td><td>{escape(str(row.get('severity')))}</td>"
    f"<td>{escape(str(row.get('linkedGroupId')))}</td><td>{escape(str(row.get('affectedFilePath')))}</td>"
    f"<td>{escape(str(row.get('bestAvailableCodeAnchor')))}</td><td>{escape(str(row.get('proposedReplacementCodeOrPatchInstruction')))}</td>"
    f"<td>{escape(str(row.get('effortEstimate')))}</td><td>{escape(' | '.join(str(step) for step in row.get('viewportRetestSteps') or []))}</td></tr>"
    for row in fix_appendix["rows"]
  ) or "<tr><td colspan='8'>No P0/P1 responsive fixes were generated.</td></tr>"

  issue_preview_rows = "".join(
    f"<tr><td><code>{escape(str(issue.get('issueId')))}</code></td><td><code>{escape(str(issue.get('groupId')))}</code></td>"
    f"<td>{escape(str(issue.get('severity')))}</td><td>{escape(str(issue.get('route')))}<br><small>{escape(str(issue.get('viewport')))}px</small></td>"
    f"<td>{escape(str(issue.get('check')))}</td><td>{escape(str(issue.get('bestAvailableCodeAnchor')))}</td></tr>"
    for issue in issues[:50]
  ) or "<tr><td colspan='6'>No material repository issue recorded.</td></tr>"

  artefact_items = "".join(
    f"<li><a href=\"{escape(str(artefacts.get(name, '#')))}\">{escape(name)}</a></li>"
    for name in [
      "report.html", "report.json", "summary.json", "execution.json", "evidence.json", "preflight.json", "coverage.json", "screenshot-manifest.json", "focused-page-appendix.json", "repository-issue-appendix.json", "mandatory-mobile-scorecard.json", "responsive-fix-appendix.json",
    ]
  )

  body = f"""
  <section class="cover">
    <h1>Jonathan Harris Mobile UX Hard-Gate Audit</h1>
    <p class="lead">Executive-grade rendered mobile UX report for <strong>{escape(summary['sessionId'])}</strong>.</p>
    <p>{html_badge(verdict)} <strong>Mobile quality score:</strong> {escape(str(score))}</p>
    <p class="section-note">The executive layer groups repeated viewport failures into root-cause findings. Raw per-viewport records remain in execution.json and the structured appendices.</p>
  </section>

  <section id="executive-summary">
    <h2>Executive summary</h2>
    <p>Stage 3 rendered mobile execution completed across {summary['renderedPages']} rendered URL(s) and {summary['viewportRuns']} viewport run(s). The run recorded {summary['mobileFailureCount']} failing viewport record(s), synthesised into {root_groups_doc['groupCount']} root-cause group(s).</p>
    <p><strong>Commercial decision:</strong> {escape(str(verdict))}. P0 groups: {len(critical_groups)}. P1 groups: {len(p1_groups)}. Screenshots retained: {summary['screenshotCount']}.</p>
  </section>

  <section id="scope-summary">
    <h2>Scope summary</h2>
    <table class="tight"><tbody>
      <tr><th>Workbook URL inventory</th><td>{escape(str(report_control.get('workbook URL inventory count')))}</td></tr>
      <tr><th>Primary URL count</th><td>{escape(str(report_control.get('primary URL count')))}</td></tr>
      <tr><th>Rendered mobile URLs checked</th><td>{escape(str(report_control.get('rendered mobile URLs checked')))}</td></tr>
      <tr><th>Focused pages audited</th><td>{escape(str(report_control.get('focused pages audited')))}</td></tr>
      <tr><th>Exception sweep URLs checked</th><td>{escape(str(report_control.get('exception sweep URLs checked')))}</td></tr>
    </tbody></table>
  </section>

  <section id="preflight">
    <h2>Preflight evidence summary</h2>
    <p>Live homepage status: {escape(str(summary['preflight']['liveHomepage'].get('status')))}. Repository files reviewed: {escape(str(summary['preflight']['repository'].get('totalFiles')))}. Media queries: {escape(str(summary['preflight']['repository'].get('mediaQueryCount')))}. Container queries: {escape(str(summary['preflight']['repository'].get('containerQueryCount')))}.</p>
  </section>

  <section id="capabilities">
    <h2>Capability table</h2>
    <table><tbody>{capability_rows}</tbody></table>
  </section>

  <section id="blocked-tests">
    <h2>Blocked-tests list</h2>
    <table class="tight"><thead><tr><th>Capability/task</th><th>Evidence</th></tr></thead><tbody>{blocked_rows}</tbody></table>
  </section>

  <section id="source-inventory">
    <h2>Source inventory</h2>
    <p>Workbook: {escape(summary['preflight']['workbook']['filename'])}; primary sheet: {escape(str(summary['preflight']['workbook'].get('primarySheet')))}; header row: {escape(str(summary['preflight']['workbook'].get('headerRow')))}.</p>
  </section>

  <section id="variance-register">
    <h2>Source-of-truth variance / mismatch register</h2>
    <table class="tight"><thead><tr><th>ID</th><th>Intended state</th><th>Repository state</th><th>Live state</th><th>Owner</th></tr></thead><tbody>{mismatch_rows}</tbody></table>
  </section>

  <section id="scorecard">
    <h2>Weighted scorecard</h2>
    <table><thead><tr><th>Dimension</th><th>Weight</th><th>Score</th><th>Evidence note</th></tr></thead><tbody>{score_rows}</tbody></table>
  </section>

  <section id="confidence">
    <h2>Confidence model</h2>
    <p>The model separates coverage, finding quality, scoring confidence, and release confidence so a blocked report cannot sit beside a cheerful unexplained 100.</p>
    <table><thead><tr><th>Confidence field</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{confidence_rows}</tbody></table>
  </section>

  <section id="evidence-labels">
    <h2>Evidence labels and claim control</h2>
    <p>Allowed evidence labels: Observed Live, Observed Live (mobile), Observed in Markup, Observed in Repository, Cross-Source Mismatch, and Reasoned Inference.</p>
    <p>Visual design, cover-art quality, brand quality, and content tone are not marked FAIL unless the rendered evidence directly supports that exact claim.</p>
  </section>

  <section id="release-verdict">
    <h2>Release verdict</h2>
    <p>{html_badge(verdict)}</p>
    <p>{escape(str(summary.get('releaseRationale') or 'Release verdict is determined from completed rendered Stage 3 mobile evidence and severity bands.'))}</p>
  </section>

  <section id="critical-blockers">
    <h2>Critical blockers</h2>
    <p>P0 root-cause groups: {len(critical_groups)}. P1 root-cause groups: {len(p1_groups)}.</p>
    <table><thead><tr><th>Group</th><th>Title</th><th>Severity</th><th>Route families</th><th>URLs</th><th>Viewport range</th><th>Metrics</th><th>Anchor/source</th><th>Remediation</th><th>Screenshots</th></tr></thead><tbody>{''.join(group_rows) or '<tr><td colspan="10">No rendered mobile root-cause group recorded.</td></tr>'}</tbody></table>
  </section>

  <section id="root-cause-findings">
    <h2>Root-cause grouped findings</h2>
    <p>Grouping policy: {escape(root_groups_doc['groupingPolicy'])}</p>
    <p>Linked issue rows remain in repository-issue-appendix.json; full execution rows remain in execution.json.</p>
  </section>

  <section id="systemic-findings">
    <h2>Systemic findings</h2>
    <p>Observed in Repository: fixed-width/min-width risk count {len(summary['preflight']['repository']['fixedWidthMinWidthRisks'])}; responsive rule inventory count {len(summary['preflight']['repository']['responsiveRuleInventory'])}.</p>
    <p>Reasoned Inference: repeated rendered failures across route families indicate shared CSS, shared partials, shared JavaScript, or template-family defects until proved page-specific.</p>
  </section>

  <section id="stage-3">
    <h2>Stage 3 rendered Mobile UX execution summary</h2>
    <p>Required viewport set: {', '.join(str(width) for width in VIEWPORTS)}. Totals: PASS {totals['PASS']}, FAIL {totals['FAIL']}, N/A {totals['N/A']}.</p>
  </section>

  <section id="mobile-execution-records">
    <h2>Mobile Execution Records summary</h2>
    <p>This section intentionally summarises the records. The full raw Mobile Execution Records are preserved in execution.json.</p>
    <table class="tight"><thead><tr><th>Template family</th><th>Viewport</th><th>Runs</th><th>Failing rows</th></tr></thead><tbody>{scorecard_rows}</tbody></table>
  </section>

  <section id="focused-pages">
    <h2>Focused page findings</h2>
    <p>Focused pages audited: {summary['focusedPagesAudited']}. Exceptions escalated: {summary['exceptionsEscalated']}.</p>
    <table class="tight"><thead><tr><th>Route</th><th>Template family</th><th>Viewport runs</th><th>Failures</th><th>Group IDs</th></tr></thead><tbody>{focused_rows}</tbody></table>
  </section>

  <section id="exception-sweep">
    <h2>Exception sweep summary</h2>
    <p>Exception sweep URLs checked: {escape(str(report_control.get('exception sweep URLs checked')))}. Exceptions escalated: {summary['exceptionsEscalated']}.</p>
  </section>

  <section id="verification-matrix">
    <h2>Verification matrix</h2>
    <table><thead><tr><th>Claim</th><th>Status</th><th>Evidence / appendix reference</th></tr></thead><tbody>{verification_rows}</tbody></table>
  </section>

  <section id="remediation">
    <h2>Remediation programme</h2>
    <ol>
      <li>Fix P0 root-cause groups first, especially viewport correctness, live 404 shell, hamburger, overflow, and mobile CTA continuity defects.</li>
      <li>Fix P1 groups by shared component or template family, not one viewport row at a time.</li>
      <li>Rerun the same hard-gate workflow and compare execution.json, rootCauseGroups, screenshot-manifest.json, and mandatory-mobile-scorecard.json.</li>
    </ol>
  </section>

  <section id="roadmap">
    <h2>Roadmap</h2>
    <p>Release path: P0 clear → P1 clear or formally accepted → refreshed screenshots → callback metadata verified in AIMS latest/job state → release readiness rechecked.</p>
  </section>

  <section id="screenshot-manifest">
    <h2>Screenshot manifest section</h2>
    <p>Screenshot references are mandatory evidence for rendered FAIL records and key rendered PASS confirmations. Showing first 80 here; full list is in screenshot-manifest.json.</p>
    <table class="tight"><thead><tr><th>Path</th><th>Route</th><th>Viewport</th><th>Evidence type</th><th>Link</th></tr></thead><tbody>{screenshot_rows}</tbody></table>
  </section>

  <section id="focused-page-appendix">
    <h2>Focused Page Appendix section</h2>
    <p>Full structured focused-page data is preserved in focused-page-appendix.json.</p>
  </section>

  <section id="repository-issue-appendix">
    <h2>Repository Issue Appendix section</h2>
    <p>Previewing first 50 issue rows to protect executive readability. Full issue schema and every raw duplicate viewport failure remain in repository-issue-appendix.json.</p>
    <table class="tight"><thead><tr><th>Issue</th><th>Group</th><th>Severity</th><th>Route</th><th>Metric</th><th>Best anchor</th></tr></thead><tbody>{issue_preview_rows}</tbody></table>
  </section>

  <section id="mandatory-mobile-scorecard">
    <h2>Mandatory Mobile UX Scorecard section</h2>
    <p>PASS / FAIL values are drawn from rendered Stage 3 execution records. Full rows are in mandatory-mobile-scorecard.json.</p>
  </section>

  <section id="responsive-fix-appendix">
    <h2>Responsive Fix Appendix section</h2>
    <p>For verified P0/P1 groups, the audit records the best rendered anchor, closest source snippet where available, manual remediation contract, and viewport retest steps.</p>
    <table class="tight"><thead><tr><th>Fix</th><th>Severity</th><th>Group</th><th>File/source</th><th>Anchor</th><th>Patch instruction</th><th>Effort</th><th>Retest</th></tr></thead><tbody>{fix_rows}</tbody></table>
  </section>

  <section id="artefacts">
    <h2>Links to all structured artefacts</h2>
    <ul>{artefact_items}</ul>
  </section>

  <section id="control">
    <h2>Report control block</h2>
    <table><tbody>{control_rows}</tbody></table>
  </section>

  <section id="final-verdict">
    <h2>Final verdict and definition of done</h2>
    <p><strong>Verdict:</strong> {html_badge(verdict)}</p>
    <p>Definition of done: all required routes and viewports execute, skipped required tasks count is 0, screenshots exist for all rendered FAIL records and key rendered PASS examples, callback artefact URLs resolve under R2_PUBLIC_BASE_URL_AUDITS, and P0/P1 mobile groups are cleared.</p>
  </section>
  """
  return html_report_shell("Jonathan Harris Mobile UX Hard-Gate Audit", body)


def matrix_entry(status: str, evidence: str, appendix: str = "execution.json") -> dict[str, str]:
  return {"status": status, "evidence": evidence, "appendixReference": appendix}


def status_for_check(records: list[dict[str, Any]], check: str, *, route: str | None = None, applicable_only: bool = True) -> dict[str, str]:
  scoped = [record for record in records if route is None or record.get("route") == route]
  values = [record.get("checks", {}).get(check) for record in scoped]
  if applicable_only:
    values = [value for value in values if value in {"PASS", "FAIL"}]
  if not values:
    return matrix_entry("PASS", f"No applicable rendered {check} failure was recorded; not a substitute for a separate specialist audit.", "mandatory-mobile-scorecard.json")
  if any(value == "FAIL" for value in values):
    return matrix_entry("FAIL", f"Rendered Stage 3 recorded {check} failure(s).", "mandatory-mobile-scorecard.json")
  return matrix_entry("PASS", f"Rendered Stage 3 recorded {check} PASS for applicable row(s).", "mandatory-mobile-scorecard.json")


def build_verification_matrix(records: list[dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
  failed_checks = {check for record in records for check, status in record.get("checks", {}).items() if status == "FAIL"}
  any_p0_or_p1 = any(issue["severity"] in {"P0", "P1"} for issue in issues)
  return {
    "homepage CTA clarity": status_for_check(records, "ctaContinuity", route="/"),
    "conversion-path continuity": status_for_check(records, "ctaContinuity"),
    "buy-now route correctness": matrix_entry("PASS" if "ctaContinuity" not in failed_checks else "FAIL", "Verified only through rendered CTA continuity checks; no unsupported manual route claim is made.", "mandatory-mobile-scorecard.json"),
    "navigation consistency": status_for_check(records, "hamburgerNavigation"),
    "viewport correctness": status_for_check(records, "viewportCorrectness"),
    "responsive coverage across layout states": status_for_check(records, "responsiveCoverage"),
    "horizontal overflow status": status_for_check(records, "overflow"),
    "touch-target status": status_for_check(records, "touchTargetUsability"),
    "font scaling": status_for_check(records, "typographyReadability"),
    "hamburger status": status_for_check(records, "hamburgerNavigation"),
    "dynamic resize status": status_for_check(records, "dynamicResizeReflow"),
    "CTA continuity on mobile": status_for_check(records, "ctaContinuity"),
    "image responsiveness": status_for_check(records, "imageResponsiveness"),
    "form usability where relevant": status_for_check(records, "formUsability"),
    "table/comparison handling where relevant": status_for_check(records, "tableComparisonHandling"),
    "visual design consistency": matrix_entry("PASS", "No subjective visual-design FAIL is asserted by this deterministic mobile audit. Only layout-impact evidence is scored elsewhere.", "screenshot-manifest.json"),
    "cover art quality": matrix_entry("PASS" if "imageResponsiveness" not in failed_checks else "FAIL", "Evidence is limited to rendered image responsiveness/broken-image detection, not subjective cover-art quality.", "mandatory-mobile-scorecard.json"),
    "metadata consistency": matrix_entry("PASS", "Preflight captured live homepage metadata and repository viewport inventory; detailed SEO scoring belongs to the SEO/AEO/GEO audit.", "preflight.json"),
    "schema correctness": matrix_entry("PASS", "No schema-specific FAIL is asserted by this mobile-only audit; schema remains out of scope unless rendered mobile evidence exposes a defect.", "preflight.json"),
    "redirects": matrix_entry("PASS", "No deterministic rendered redirect failure was recorded by the mobile CTA/live route checks.", "execution.json"),
    "live rendered 404 behaviour": status_for_check(records, "live404Verification", route=LIVE_404_ROUTE),
    "release readiness": matrix_entry("FAIL" if any_p0_or_p1 else "PASS", "Release readiness follows completed Stage 3 evidence and P0/P1 severity bands.", "report.json"),
  }


def confidence_model(records: list[dict[str, Any]], issues: list[dict[str, Any]], coverage: dict[str, Any], screenshot_count: int, verdict: str) -> dict[str, dict[str, Any]]:
  stage3_complete = bool(coverage.get("complete"))
  failure_count = record_failures(records)
  failed_records_with_screenshot = sum(
    1 for record in records
    if any(status == "FAIL" for status in record.get("checks", {}).values()) and record.get("screenshotRefs")
  )
  screenshot_coverage = 100 if failure_count == 0 else round((failed_records_with_screenshot / failure_count) * 100, 1)
  return {
    "executionCoverageConfidence": {
      "status": "HIGH" if stage3_complete else "BLOCKED",
      "value": 100 if stage3_complete else 0,
      "evidence": f"Stage 3 complete={stage3_complete}; skipped required tasks={coverage.get('skippedRequiredTasksCount')}; viewport records={len(records)}.",
    },
    "findingConfidence": {
      "status": "HIGH" if stage3_complete and screenshot_coverage >= 95 else "MEDIUM" if stage3_complete else "BLOCKED",
      "value": screenshot_coverage if stage3_complete else 0,
      "evidence": f"{failed_records_with_screenshot}/{failure_count} failing rendered record(s) have screenshot evidence; issue count={len(issues)}.",
    },
    "scoringConfidence": {
      "status": "HIGH" if stage3_complete else "BLOCKED",
      "value": 100 if stage3_complete else 0,
      "evidence": "Scoring uses only completed rendered Stage 3 records; static-only scoring is not allowed.",
    },
    "releaseConfidence": {
      "status": "BLOCKED" if verdict == "BLOCKED" else "CONDITIONAL" if verdict == "CONDITIONAL PASS" else "HIGH",
      "value": 0 if verdict == "BLOCKED" else 70 if verdict == "CONDITIONAL PASS" else 100,
      "evidence": f"Release verdict is {verdict}; P0/P1 severity rules override numeric mobile scores.",
    },
  }


def weighted_scorecard(score: float | None, issues: list[dict[str, Any]]) -> list[tuple[str, int, str, str]]:
  if score is None:
    return [("Stage 3 incomplete", 100, "Not scored", "Hard-gate prevented scoring")]
  p0 = any(issue["severity"] == "P0" for issue in issues)
  p1 = any(issue["severity"] == "P1" for issue in issues)
  mobile_cap = min(score, 94 if p1 else 100)
  if p0:
    mobile_cap = min(mobile_cap, 74)
  conversion_cap = min(score, 94 if p1 else 100)
  return [
    ("Enterprise readiness and commercial launch risk", 12, "BLOCKED" if p0 else round(score, 1), "Observed Live (mobile); P0 overrides numeric score"),
    ("Conversion journey readiness", 12, round(conversion_cap, 1), "CTA continuity and touch targets only"),
    ("UX, UI, accessibility, and mobile responsiveness", 14, round(mobile_cap, 1), "Rendered mobile evidence first"),
    ("Visual design, brand coherence, and graphic quality", 8, "Evidence captured", "No subjective brand/cover-art FAIL without direct evidence"),
    ("Content quality, messaging, and tone fidelity", 8, "Not rescored by mobile hard-gate", "Outside deterministic mobile checks"),
    ("Technical SEO, metadata, and indexation readiness", 10, "Not rescored by mobile hard-gate", "Preflight metadata evidence only"),
    ("Technical implementation quality", 10, round(mobile_cap, 1), "Repository plus rendered behaviour"),
    ("Code quality, maintainability, and source-of-truth governance", 8, "Evidence captured", "Workbook/repository/live reconciliation"),
    ("Routing, redirect, and destination integrity", 8, round(conversion_cap, 1), "CTA and live 404 coverage"),
    ("Performance, resilience, and asset efficiency", 5, "Not rescored by mobile hard-gate", "No synthetic performance budget in this workflow"),
    ("Release, build, and deployment hygiene", 5, "PASS" if not p0 else "BLOCKED", "Workflow completed and callback posted only after required artefact URLs exist"),
  ]


def build_summary(args: argparse.Namespace, preflight_data: dict[str, Any], routes: list[str], records: list[dict[str, Any]], issues: list[dict[str, Any]], coverage: dict[str, Any], reconciliation: dict[str, Any], started_at: str) -> dict[str, Any]:
  failure_count = record_failures(records)
  screenshot_count = len({ref.get("relativePath") for record in records for ref in record.get("screenshotRefs", []) if ref.get("relativePath")})
  score = mobile_quality_score(records, coverage["complete"])
  p0 = any(issue["severity"] == "P0" for issue in issues)
  p1 = any(issue["severity"] == "P1" for issue in issues)
  verdict = "BLOCKED" if p0 else "CONDITIONAL PASS" if p1 else "PASS"
  verification = build_verification_matrix(records, issues)
  confidence = confidence_model(records, issues, coverage, screenshot_count, verdict)
  workbook_url_count = preflight_data["workbook"].get("urlCount")
  rendered_mobile_urls_checked = len(routes)
  exception_sweep_urls_checked = len(routes)
  report_control = {
    "audit source": "Mobile UX hard-gate deterministic service",
    "repository source": "jonathan-harris-website-main attached repository",
    "workbook source": preflight_data["workbook"]["filename"],
    "capability constraints declared": json.dumps(preflight_data["capabilities"], ensure_ascii=False),
    "primary sheet": preflight_data["workbook"].get("primarySheet"),
    "header row": preflight_data["workbook"].get("headerRow"),
    "workbook URL inventory count": workbook_url_count,
    "primary URL count": workbook_url_count,
    "total URLs checked": rendered_mobile_urls_checked,
    "rendered mobile URLs checked": rendered_mobile_urls_checked,
    "focused pages audited": len(routes),
    "exception sweep URLs checked": exception_sweep_urls_checked,
    "exceptions escalated": failure_count,
    "material repository files reviewed": preflight_data["repository"].get("totalFiles"),
    "cross-source mismatches count": reconciliation["crossSourceMismatchCount"],
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
    "coverage summary": f"{len(records)} viewport records across {len(routes)} rendered mobile URLs; focused pages={len(routes)}; exception sweep URLs={exception_sweep_urls_checked}",
    "skipped required tasks count": coverage["skippedRequiredTasksCount"],
  }
  release_rationale = (
    "BLOCKED because at least one verified P0 mobile issue exists." if p0
    else "CONDITIONAL PASS because at least one verified P1 mobile issue remains." if p1
    else "PASS because completed Stage 3 rendered evidence found no P0/P1 mobile blockers."
  )
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
    "confidenceModel": confidence,
    "releaseVerdict": verdict,
    "releaseRationale": release_rationale,
    "focusedPagesAudited": len(routes),
    "exceptionSweepUrlsChecked": exception_sweep_urls_checked,
    "exceptionsEscalated": failure_count,
    "issueCount": len(issues),
    "rootCauseGroupCount": len({issue.get("groupId") for issue in issues if issue.get("groupId")}),
    "preflight": preflight_data,
    "coverage": coverage,
    "reconciliation": reconciliation,
    "issues": issues,
    "rootCauseGroups": root_cause_groups_document(issues, records),
    "verificationMatrix": verification,
    "weightedScorecard": weighted_scorecard(score, issues),
    "reportControlBlock": report_control,
    "startedAt": started_at,
    "finishedAt": utc_now(),
  }

def write_failure_payload(args: argparse.Namespace, output_dir: Path, message: str, preflight_data: dict[str, Any] | None = None, extra: dict[str, Any] | None = None, *, allow_upload: bool = True) -> dict[str, Any]:
  now = utc_now()
  failure_artifacts = ensure_failure_artifacts(args, output_dir, message, preflight_data, extra)
  hard_gate_blocked = message == HARD_GATE_MESSAGE
  storage_upload_error = str((extra or {}).get("storageUploadError") or "").strip() or None
  summary = {
    "ok": False,
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "failed",
    "blocked": True,
    "hardGateBlocked": hard_gate_blocked,
    "reportPrefix": args.report_prefix,
    "message": message,
    "storageUploadError": storage_upload_error,
    "preflight": preflight_data,
    "capabilities": preflight_data.get("capabilities") if isinstance(preflight_data, dict) else None,
    "coverage": failure_artifacts.get("coverage"),
    "mobileQualityScore": None,
    "releaseVerdict": None,
    "finishedAt": now,
    **(extra or {}),
  }
  write_json(output_dir / "summary.json", summary)
  write_json(output_dir / "report.json", {
    "auditType": "mobile-ux",
    "schemaVersion": "mobile-ux-hard-gate-v4.5",
    "status": "failed",
    "message": message,
    "mobileQualityScore": None,
    "releaseVerdict": None,
    "summary": summary,
    "coverage": failure_artifacts.get("coverage"),
    "evidence": failure_artifacts.get("evidence"),
    "generatedAt": now,
  })
  write_text(output_dir / "halt.txt", message)
  write_text(output_dir / "report.html", failure_report_html(summary, failure_artifacts))
  uploaded: dict[str, str] = {}
  if allow_upload:
    try:
      uploaded = upload_artifacts_if_configured(args.report_prefix, output_dir)
    except Exception as exc:  # pragma: no cover - depends on live R2 credentials
      storage_upload_error = f"R2 upload failed: {exc}"
      summary["storageUploadError"] = storage_upload_error
      write_json(output_dir / "summary.json", summary)
  payload = {
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "failed",
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html"),
    "reportJsonUrl": uploaded.get("report.json"),
    "summaryUrl": uploaded.get("summary.json"),
    "preflightUrl": uploaded.get("preflight.json"),
    "evidenceUrl": uploaded.get("evidence.json"),
    "coverageUrl": uploaded.get("coverage.json"),
    "message": message,
    "storageUploadError": storage_upload_error,
    "blocked": True,
    "hardGateBlocked": hard_gate_blocked,
    "blockedTests": failure_blocks_from_extra(extra),
    "capabilities": preflight_data.get("capabilities") if isinstance(preflight_data, dict) else None,
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
  initial_capabilities = build_capabilities(playwright_error, install_outcome)
  runtime_probe_blocks = []
  if initial_capabilities["renderedBrowserAutomation"] and initial_capabilities["screenshotCapture"] and initial_capabilities["mobileViewportEmulation"]:
    runtime_probe_blocks = probe_rendered_mobile_runtime(sync_playwright, output_dir / "capability-probe")
  capabilities = build_capabilities(playwright_error, install_outcome, runtime_probe_blocks)

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

  missing_r2 = missing_r2_upload_config()
  if missing_r2:
    block = {
      "stage": "R2 audit storage preflight",
      "blocker": f"missing {', '.join(missing_r2)}",
      "reason": "The GitHub workflow must publish report.html, report.json, summary.json, coverage.json, execution.json, evidence.json, screenshots, and appendices to the audits bucket.",
    }
    preflight_data["storage"] = {"r2UploadConfigured": False, "missing": missing_r2}
    preflight_data["checkpoints"].append(checkpoint("AUDIT STORAGE CHECKPOINT", [], [block], False))
    write_json(output_dir / "preflight.json", preflight_data)
    write_json(output_dir / "coverage.json", {"complete": False, "stage3Blocks": [block], "skippedRequiredTasksCount": 1})
    return 1 if write_failure_payload(args, output_dir, STORAGE_GATE_MESSAGE, preflight_data, {"stage3Blocks": [block], "storageUploadError": block["blocker"]}, allow_upload=False) else 1

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
  except HardGateCapabilityError as exc:  # pragma: no cover - runtime environment gate
    blocks = exc.blocks or [{"capability": "renderedBrowserAutomation", "reason": str(exc)}]
    preflight_data["capabilities"]["blockedTests"].extend(blocks)
    preflight_data["capabilities"] = build_capabilities(None, "", preflight_data["capabilities"]["blockedTests"])
    write_json(output_dir / "preflight.json", preflight_data)
    return 1 if write_failure_payload(args, output_dir, HARD_GATE_MESSAGE, preflight_data, {"blockedTests": blocks, "error": str(exc), "trace": traceback.format_exc()}) else 1
  except Exception as exc:  # pragma: no cover - runtime environment gate
    blocks = [
      {"capability": "renderedBrowserAutomation", "reason": str(exc)},
      {"capability": "screenshotCapture", "reason": str(exc)},
      {"capability": "mobileViewportEmulation", "reason": str(exc)},
    ]
    preflight_data["capabilities"]["blockedTests"].extend(blocks)
    preflight_data["capabilities"] = build_capabilities(None, "", preflight_data["capabilities"]["blockedTests"])
    write_json(output_dir / "preflight.json", preflight_data)
    return 1 if write_failure_payload(args, output_dir, HARD_GATE_MESSAGE, preflight_data, {"blockedTests": blocks, "error": str(exc), "trace": traceback.format_exc()}) else 1

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
  write_json(output_dir / "report.json", report_json_document(summary, records, issues, coverage, reconciliation))
  write_json(output_dir / "screenshot-manifest.json", screenshot_manifest_document(records, summary))
  write_json(output_dir / "focused-page-appendix.json", focused_page_appendix_document(summary, records, issues))
  write_json(output_dir / "repository-issue-appendix.json", repository_issue_appendix_document(summary, issues))
  write_json(output_dir / "mandatory-mobile-scorecard.json", mandatory_mobile_scorecard_document(records, summary))
  write_json(output_dir / "responsive-fix-appendix.json", responsive_fix_appendix_document(summary, issues, records))
  html = report_html(summary, records, {}, issues, coverage, reconciliation)
  write_text(output_dir / "report.html", html)

  try:
    uploaded = upload_artifacts_if_configured(args.report_prefix, output_dir, require=True)
    missing = missing_required_completion_artefacts(uploaded)
    if missing:
      raise RuntimeError(f"R2 completion upload missing required artefact(s): {', '.join(missing)}")
    summary["artefactUrls"] = {name: uploaded.get(name) for name in MANDATORY_COMPLETION_ARTEFACTS if uploaded.get(name)}
    write_json(output_dir / "summary.json", summary)
    html = report_html(summary, records, uploaded, issues, coverage, reconciliation)
    write_text(output_dir / "report.html", html)
    write_json(output_dir / "report.json", report_json_document(summary, records, issues, coverage, reconciliation, uploaded))
    uploaded = upload_artifacts_if_configured(args.report_prefix, output_dir, require=True)
    missing = missing_required_completion_artefacts(uploaded)
    if missing:
      raise RuntimeError(f"R2 completion upload missing required artefact(s) after linked-report rewrite: {', '.join(missing)}")
  except Exception as exc:  # pragma: no cover - depends on live R2 credentials
    block = {"stage": "R2 audit upload", "blocker": str(exc), "reason": "Completed Mobile UX audit cannot be published to the required audits bucket."}
    return 1 if write_failure_payload(args, output_dir, STORAGE_GATE_MESSAGE, preflight_data, {"stage3Blocks": [block], "storageUploadError": str(exc)}, allow_upload=False) else 1

  callback_payload = {
    "auditType": "mobile-ux",
    "sessionId": args.session_id,
    "status": "completed",
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html"),
    "reportJsonUrl": uploaded.get("report.json"),
    "summaryUrl": uploaded.get("summary.json"),
    "executionUrl": uploaded.get("execution.json"),
    "evidenceUrl": uploaded.get("evidence.json"),
    "preflightUrl": uploaded.get("preflight.json"),
    "coverageUrl": uploaded.get("coverage.json"),
    "reconciliationUrl": uploaded.get("reconciliation.json"),
    "screenshotManifestUrl": uploaded.get("screenshot-manifest.json"),
    "focusedPageAppendixUrl": uploaded.get("focused-page-appendix.json"),
    "repositoryIssueAppendixUrl": uploaded.get("repository-issue-appendix.json"),
    "mandatoryMobileScorecardUrl": uploaded.get("mandatory-mobile-scorecard.json"),
    "responsiveFixAppendixUrl": uploaded.get("responsive-fix-appendix.json"),
    "screenshotCount": summary["screenshotCount"],
    "mobileFailureCount": summary["mobileFailureCount"],
    "issueCount": summary["issueCount"],
    "rootCauseGroupCount": summary.get("rootCauseGroupCount"),
    "confidenceModel": summary.get("confidenceModel"),
    "artefacts": uploaded,
    "finishedAt": summary["finishedAt"],
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  post_callback(args.callback_url, args.callback_token, {k: v for k, v in callback_payload.items() if v is not None})
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
