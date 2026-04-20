#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import json
import os
import re
import traceback
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SCRIPT_FILE = Path(__file__).resolve()
REPO_ROOT = SCRIPT_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audits.common import (
    DEFAULT_EXCLUDES,
    REPO_ROOT,
    WorkbookInfo,
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
    build_r2_client,
)

VIEWPORTS = [320, 375, 390, 414, 768, 1024, 1280, 1440]
NAV_TOGGLE = ".jh-hamburger"
MOBILE_NAV = "#jh-mobile-nav"
PRIMARY_CTA_SELECTORS = [
    ".jh-mobile-nav__cta",
    ".jh-topnav__cta",
    "main a[href^='/ebooks/']",
    "main a[href*='amazon.']",
    "main button[type='submit']",
    "main input[type='submit']",
]
INTERACTIVE_SELECTORS = "a, button, input, textarea, select, summary, [role='button'], [tabindex='0']"
TEXT_SELECTORS = "p, li, h1, h2, h3, h4, label, a, button, small, figcaption"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the rendered mobile UX hard-gate audit")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--report-prefix", required=True)
    parser.add_argument("--callback-url")
    parser.add_argument("--callback-token")
    parser.add_argument("--output-dir", default="artifacts/mobile-ux")
    parser.add_argument("--exclude-prefixes", default=",".join(DEFAULT_EXCLUDES))
    return parser.parse_args()


def detect_focus_routes(repo_root: Path, workbook_info: WorkbookInfo, excludes: list[str]) -> list[str]:
    routes = repo_html_routes(repo_root, excludes)
    route_set = set(routes)

    def first_match(prefix: str, fallback: str | None = None) -> str | None:
        for route in routes:
            if route == prefix or route.startswith(f"{prefix}/"):
                return route
        return fallback

    ebook_route = "/ebooks"
    ebook_details = sorted(
        {
            normalise_route(route)
            for route in routes
            if route.startswith("/ebooks/") and route not in {"/ebooks", "/ebooks/"}
        }
    )
    catalogue_page = first_match("/catalogue", "/catalogue/artificial-intelligence")
    topics_page = first_match("/topics", "/topics/ai-for-beginners")
    unique_js_pages = [route for route in ["/compare", "/glossary", "/newsletter", "/contact"] if route in route_set]

    required = [
        "/",
        ebook_route,
        ebook_details[0] if ebook_details else "/ebooks/",
        "/newsletter",
        "/contact",
        "/bio",
        "/compare",
        catalogue_page,
        topics_page,
        "/404.html",
        *unique_js_pages,
    ]

    # Pull in workbook-governed pages with likely mobile risk keywords.
    risk_keywords = ("compare", "contact", "newsletter", "catalogue", "topic", "table", "form")
    for raw in workbook_info.urls:
        route = normalise_route(raw, None)
        if should_exclude(route, excludes):
            continue
        if any(keyword in route for keyword in risk_keywords):
            required.append(route)

    normalised = []
    seen = set()
    for route in required:
        if not route:
            continue
        route = normalise_route(route)
        if route == "/404.html":
            normalised.append(route)
            continue
        if route not in route_set:
            continue
        if route in seen:
            continue
        seen.add(route)
        normalised.append(route)

    if "/404.html" not in normalised:
        normalised.append("/404.html")
    return normalised


def detect_template_family(route: str) -> str:
    if route in {"/", ""}:
        return "homepage"
    if route.startswith("/ebooks/") and route.count("/") > 2:
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
    if route.startswith("/404"):
        return "404"
    return "site-page"


def screenshot_name(route: str, width: int, label: str) -> str:
    cleaned = route.strip("/").replace("/", "-") or "home"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", cleaned)
    return f"{cleaned}-{width}-{label}.png"


def first_visible_locator(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count() and locator.first.is_visible():
                return locator.first
        except Exception:
            continue
    return None


def inspect_touch_targets(page) -> tuple[str, list[dict[str, Any]]]:
    targets = page.locator(INTERACTIVE_SELECTORS)
    count = min(targets.count(), 14)
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


def inspect_readability(page) -> tuple[str, list[dict[str, Any]]]:
    result = page.evaluate(
        """
        (selector) => {
          const items = Array.from(document.querySelectorAll(selector)).slice(0, 60);
          const issues = [];
          for (const el of items) {
            const style = window.getComputedStyle(el);
            const fontSize = parseFloat(style.fontSize || '0');
            const clipped = el.scrollHeight - el.clientHeight > 6 && ['hidden', 'clip'].includes(style.overflowY || style.overflow);
            if (fontSize && fontSize < 14) {
              issues.push({ type: 'font-size', text: (el.textContent || '').trim().slice(0, 60), fontSize });
            }
            if (clipped) {
              issues.push({ type: 'clipped', text: (el.textContent || '').trim().slice(0, 60), fontSize });
            }
          }
          return issues;
        }
        """,
        TEXT_SELECTORS,
    )
    return ("PASS" if not result else "FAIL", result)


def inspect_form_usability(page) -> tuple[str, list[dict[str, Any]] | str]:
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
              fontSize: parseFloat(window.getComputedStyle(el).fontSize || '0')
            }))
            .filter((item) => item.fontSize > 0 && item.fontSize < 16);
        }
        """
    )
    return ("PASS" if not issues else "FAIL", issues)


def inspect_images(page) -> tuple[str, list[dict[str, Any]] | str]:
    images = page.locator("img")
    if images.count() == 0:
        return "N/A", "No images detected"
    issues = page.evaluate(
        """
        () => Array.from(document.images)
          .filter((img) => img.clientWidth > window.innerWidth + 2 || !img.complete)
          .slice(0, 20)
          .map((img) => ({ src: img.currentSrc || img.src || '', width: img.clientWidth, window: window.innerWidth, complete: img.complete }))
        """
    )
    return ("PASS" if not issues else "FAIL", issues)


def inspect_tables(page) -> tuple[str, str, list[dict[str, Any]] | str]:
    tables = page.locator("table, [role='table']")
    if tables.count() == 0:
        return "N/A", "N/A", "No tables detected"
    evaluation = page.evaluate(
        """
        () => {
          const tables = Array.from(document.querySelectorAll('table, [role="table"]'));
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


def inspect_overflow(page) -> tuple[str, list[dict[str, Any]]]:
    issues = page.evaluate(
        """
        () => {
          const offenders = [];
          const viewport = window.innerWidth;
          const nodes = Array.from(document.querySelectorAll('body *')).slice(0, 400);
          for (const el of nodes) {
            const rect = el.getBoundingClientRect();
            if (rect.width > viewport + 2 || rect.right > viewport + 2) {
              offenders.push({
                tag: el.tagName.toLowerCase(),
                className: (el.className || '').toString().trim(),
                width: Math.round(rect.width),
                right: Math.round(rect.right),
              });
              if (offenders.length >= 12) break;
            }
          }
          return offenders;
        }
        """
    )
    return ("PASS" if not issues else "FAIL", issues)


def inspect_hamburger(page, width: int) -> tuple[str, dict[str, Any] | str]:
    if width >= 1024:
        return "N/A", "Desktop viewport"

    toggle = page.locator(NAV_TOGGLE)
    if toggle.count() == 0 or not toggle.first.is_visible():
        return "FAIL", {"reason": "Hamburger toggle not visible at mobile width"}

    nav = page.locator(MOBILE_NAV)
    details: dict[str, Any] = {}
    try:
        toggle.first.click(timeout=5000)
        page.wait_for_timeout(250)
        open_state = nav.get_attribute("hidden") is None and toggle.first.get_attribute("aria-expanded") == "true"
        details["open"] = open_state

        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        closed_state = nav.get_attribute("hidden") is not None and toggle.first.get_attribute("aria-expanded") == "false"
        details["escapeClose"] = closed_state

        toggle.first.click(timeout=5000)
        page.wait_for_timeout(200)
        page.mouse.click(8, 8)
        page.wait_for_timeout(200)
        outside_close = nav.get_attribute("hidden") is not None
        details["outsideClose"] = outside_close

        if all(details.values()):
            return "PASS", details
        return "FAIL", details
    except Exception as exc:
        return "FAIL", {"reason": str(exc), **details}


def inspect_cta(page, base_url: str) -> tuple[str, dict[str, Any] | str]:
    locator = first_visible_locator(page, PRIMARY_CTA_SELECTORS)
    if locator is None:
        return "FAIL", "No visible primary CTA detected"

    href = locator.get_attribute("href")
    label = locator.inner_text(timeout=1000).strip() if locator.count() else ""
    if href and href.startswith("/"):
        target = route_to_url(base_url, href)
        try:
            locator.click(timeout=5000)
            page.wait_for_load_state("domcontentloaded", timeout=8000)
            ok = page.url.startswith(target) or normalise_route(page.url, None) == normalise_route(href)
            page.go_back(wait_until="domcontentloaded", timeout=8000)
            page.wait_for_timeout(150)
            return ("PASS" if ok else "FAIL", {"label": label, "href": href, "target": page.url})
        except Exception as exc:
            return "FAIL", {"label": label, "href": href, "reason": str(exc)}

    if href or locator.evaluate("el => el.tagName.toLowerCase()") == "button":
        return "PASS", {"label": label, "href": href or "button"}
    return "FAIL", {"label": label, "href": href}


def inspect_viewport_markup(page) -> tuple[str, str]:
    content = page.locator("meta[name='viewport']").get_attribute("content") or ""
    bad = "user-scalable=no" in content.lower() or "maximum-scale=1" in content.lower()
    good = "width=device-width" in content.lower()
    return ("PASS" if good and not bad else "FAIL", content or "Viewport meta missing")


def inspect_dynamic_resize(page, width: int) -> tuple[str, dict[str, Any] | str]:
    original = {"width": width, "height": 920}
    next_width = 1024 if width < 768 else 390
    try:
        page.set_viewport_size({"width": next_width, "height": 920})
        page.wait_for_timeout(200)
        stuck = page.locator(MOBILE_NAV).get_attribute("hidden") is None and next_width >= 1024
        page.set_viewport_size(original)
        page.wait_for_timeout(200)
        return ("FAIL", {"stuckMobileNav": stuck}) if stuck else ("PASS", {"resizeTo": next_width})
    except Exception as exc:
        return "FAIL", {"reason": str(exc)}


def preflight(base_url: str, repo_root: Path, workbook_info: WorkbookInfo) -> dict[str, Any]:
    homepage = fetch_html(base_url)
    soup = parse_html(homepage.get("text", "")) if homepage.get("text") else parse_html("")
    meta = extract_meta(soup)
    site_css = (repo_root / "assets/css/site.css").read_text(encoding="utf-8")
    media_queries = re.findall(r"@media\s+([^\{]+)\{", site_css)
    container_queries = re.findall(r"@container\s+([^\{]+)\{", site_css)
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
            "viewport": meta.get("viewport", "HOMEPAGE VIEWPORT META NOT FOUND"),
            "canonical": meta.get("canonical", ""),
            "title": meta.get("title", ""),
            "metaDescription": meta.get("metaDescription", ""),
        },
        "repository": {
            "topLevel": sorted([p.name for p in repo_root.iterdir()]),
            "siteCssPreview": site_css[:500],
            "sharedPartials": [
                "assets/partials/header.html",
                "assets/partials/footer.html",
            ],
            "uiScripts": [
                "assets/js/site-ui.min.js",
                "assets/js/contact-inline.min.js",
                "assets/js/newsletter-inline.min.js",
                "assets/js/compare-inline.min.js",
            ],
            "mediaQueries": media_queries,
            "containerQueries": container_queries,
            "mediaQueryCount": len(media_queries),
            "containerQueryCount": len(container_queries),
        },
        "capabilities": {
            "staticFileInspection": True,
            "fetchSourceInspection": True,
            "renderedBrowserAutomation": True,
            "screenshotCapture": True,
            "mobileViewportEmulation": True,
            "blockedTests": [],
        },
    }


def report_html(summary: dict[str, Any], records: list[dict[str, Any]], artefacts: dict[str, str]) -> str:
    total_failures = sum(1 for record in records if "FAIL" in record["checks"].values())
    total_passes = len(records) * 10 - total_failures
    rows = []
    for record in records:
        checks = record["checks"]
        failed = [name for name, status in checks.items() if status == "FAIL"]
        badge = "pass" if not failed else "fail"
        rows.append(
            f"<tr><td><code>{record['route']}</code></td><td>{record['templateFamily']}</td><td>{record['viewport']}</td>"
            f"<td><span class='badge {badge}'>{'PASS' if not failed else 'FAIL'}</span></td>"
            f"<td>{', '.join(failed) if failed else 'All checks passed'}</td>"
            f"<td>{'<br>'.join(record.get('screenshotRefs', [])) or '—'}</td></tr>"
        )

    focus_cards = []
    for key, value in summary["preflight"]["liveHomepage"].items():
        focus_cards.append(f"<div class='kpi'><strong>{key}</strong><div>{value}</div></div>")

    body = f"""
    <section>
      <h2>Executive summary</h2>
      <div class=\"grid\">
        <div class=\"kpi\"><strong>Session</strong><div>{summary['sessionId']}</div></div>
        <div class=\"kpi\"><strong>Rendered pages</strong><div>{summary['renderedPages']}</div></div>
        <div class=\"kpi\"><strong>Viewport runs</strong><div>{summary['viewportRuns']}</div></div>
        <div class=\"kpi\"><strong>Screenshots</strong><div>{summary['screenshotCount']}</div></div>
        <div class=\"kpi\"><strong>Mobile passes</strong><div>{total_passes}</div></div>
        <div class=\"kpi\"><strong>Mobile fails</strong><div>{total_failures}</div></div>
      </div>
    </section>
    <section>
      <h2>Preflight evidence</h2>
      <div class=\"grid\">{''.join(focus_cards)}</div>
      <p><strong>Workbook:</strong> <code>{summary['preflight']['workbook']['filename']}</code> with {summary['preflight']['workbook']['urlCount']} governed URLs.</p>
      <p><strong>Shared partials:</strong> {', '.join(summary['preflight']['repository']['sharedPartials'])}</p>
      <p><strong>UI scripts:</strong> {', '.join(summary['preflight']['repository']['uiScripts'])}</p>
    </section>
    <section>
      <h2>Mandatory mobile execution scorecard</h2>
      <table>
        <thead><tr><th>URL</th><th>Template family</th><th>Viewport</th><th>Status</th><th>Failed checks</th><th>Screenshots</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    <section>
      <h2>Artefacts</h2>
      <ul>
        <li><a href=\"{artefacts.get('summary.json', '#')}\">summary.json</a></li>
        <li><a href=\"{artefacts.get('execution.json', '#')}\">execution.json</a></li>
        <li><a href=\"{artefacts.get('preflight.json', '#')}\">preflight.json</a></li>
      </ul>
    </section>
    """
    return html_report_shell("Jonathan Harris Mobile UX Hard-Gate Audit", body)


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    excludes = [item.strip() for item in args.exclude_prefixes.split(",") if item.strip()]
    output_dir = ensure_dir(Path(args.output_dir))
    screenshots_dir = ensure_dir(output_dir / "screenshots")

    workbook_path = find_workbook(REPO_ROOT)
    workbook_info = load_workbook_info(workbook_path)
    preflight_data = preflight(base_url, REPO_ROOT, workbook_info)
    write_json(output_dir / "preflight.json", preflight_data)

    routes = detect_focus_routes(REPO_ROOT, workbook_info, excludes)
    records: list[dict[str, Any]] = []
    screenshot_refs: list[str] = []
    failures_count = 0

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 920})
            page = context.new_page()

            for route in routes:
                for width in VIEWPORTS:
                    target = (
                        f"{base_url}/__mobile-ux-404-probe__{args.session_id}"
                        if route == "/404.html"
                        else route_to_url(base_url, route)
                    )
                    page.set_viewport_size({"width": width, "height": 920})
                    page.goto(target, wait_until="domcontentloaded", timeout=25000)
                    page.wait_for_timeout(350)

                    checks: dict[str, str] = {}
                    details: dict[str, Any] = {}
                    screenshot_paths: list[str] = []

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

                    should_capture = any(status == "FAIL" for status in checks.values()) or (
                        route in {"/", "/ebooks", "/newsletter", "/contact", "/compare", "/404.html"} and width in {320, 390}
                    )
                    if should_capture:
                        label = "fail" if any(status == "FAIL" for status in checks.values()) else "pass"
                        name = screenshot_name(route, width, label)
                        file_path = screenshots_dir / name
                        page.screenshot(path=str(file_path), full_page=True)
                        screenshot_paths.append(f"screenshots/{name}")
                        screenshot_refs.extend(screenshot_paths)

                    if any(status == "FAIL" for status in checks.values()):
                        failures_count += 1

                    records.append(
                        {
                            "route": route,
                            "url": target,
                            "templateFamily": detect_template_family(route),
                            "viewport": width,
                            "checks": checks,
                            "details": details,
                            "screenshotRefs": screenshot_paths,
                        }
                    )

            browser.close()
    except Exception as exc:  # pragma: no cover - runtime environment gate
        fail_message = (
            "MOBILE UX HARD GATE FAILED - RENDERED BROWSER AUTOMATION AND SCREENSHOT CAPTURE ARE REQUIRED FOR THIS AUDIT. "
            "HALTING BEFORE SCORING OR VERDICT."
        )
        write_text(output_dir / "halt.txt", fail_message + "\n\n" + traceback.format_exc())
        write_json(output_dir / "summary.json", {
            "ok": False,
            "sessionId": args.session_id,
            "status": "failed",
            "message": fail_message,
            "error": str(exc),
            "finishedAt": utc_now(),
        })
        client = build_r2_client()
        uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)
        payload = {
            "auditType": "mobile-ux",
            "sessionId": args.session_id,
            "status": "failed",
            "reportPrefix": args.report_prefix,
            "message": fail_message,
            "artefacts": uploaded,
            "finishedAt": utc_now(),
        }
        post_callback(args.callback_url, args.callback_token, payload)
        return 1

    execution = {"records": records}
    write_json(output_dir / "execution.json", execution)

    summary = {
        "ok": True,
        "sessionId": args.session_id,
        "status": "completed",
        "reportPrefix": args.report_prefix,
        "renderedPages": len(routes),
        "viewportRuns": len(records),
        "screenshotCount": len(set(screenshot_refs)),
        "mobileFailureCount": failures_count,
        "preflight": preflight_data,
        "startedAt": utc_now(),
        "finishedAt": utc_now(),
    }
    write_json(output_dir / "summary.json", summary)

    client = build_r2_client()
    uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)
    html = report_html(summary, records, uploaded)
    write_text(output_dir / "report.html", html)
    uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)

    callback_payload = {
        "auditType": "mobile-ux",
        "sessionId": args.session_id,
        "status": "completed",
        "reportPrefix": args.report_prefix,
        "reportUrl": uploaded.get("report.html"),
        "summaryUrl": uploaded.get("summary.json"),
        "executionUrl": uploaded.get("execution.json"),
        "preflightUrl": uploaded.get("preflight.json"),
        "screenshotCount": len(set(screenshot_refs)),
        "mobileFailureCount": failures_count,
        "artefacts": uploaded,
        "finishedAt": utc_now(),
        "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
    }
    post_callback(args.callback_url, args.callback_token, callback_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
