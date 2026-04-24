#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audits.common import (
    DEFAULT_EXCLUDES,
    REPO_ROOT,
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

PRIORITY_ROUTES = [
    "/",
    "/ebooks",
    "/newsletter",
    "/contact",
    "/bio",
    "/compare",
    "/topics",
    "/blog",
    "/blog/weekly",
    "/podcast",
    "/catalogue/artificial-intelligence",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the forensic SEO + AEO + GEO audit")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--report-prefix", required=True)
    parser.add_argument("--callback-url")
    parser.add_argument("--callback-token")
    parser.add_argument("--output-dir", default="artifacts/seo-aeo-geo")
    parser.add_argument("--exclude-prefixes", default=",".join(DEFAULT_EXCLUDES))
    return parser.parse_args()


def classify_page(route: str) -> str:
    route = normalise_route(route)
    if route == "/":
        return "homepage"
    if route == "/404" or route == "/404.html":
        return "site page"
    if route.startswith("/ebooks/"):
        return "book page"
    if route == "/ebooks":
        return "book hub"
    if route.startswith("/catalogue/"):
        return "category / hub"
    if route == "/catalogue":
        return "category / hub"
    if route.startswith("/topics/"):
        return "topic hub"
    if route == "/topics":
        return "topic hub"
    if route.startswith("/newsletter"):
        return "lead generation"
    if route.startswith("/contact"):
        return "lead generation"
    if route.startswith("/compare"):
        return "comparison"
    if route.startswith("/bio"):
        return "author / about"
    if route.startswith("/glossary"):
        return "knowledge base"
    if route == "/blog/weekly" or route.startswith("/blog/page") or "/page/" in route or route.startswith("/blog/archive"):
        return "blog archive"
    if route.startswith("/blog/posts/"):
        return "article / blog"
    if route == "/blog":
        return "article / blog"
    if route.startswith("/podcast/episodes/"):
        return "podcast episode"
    if route.startswith("/podcast/transcripts/"):
        return "podcast transcript"
    if route.startswith("/podcast/archive") or route.startswith("/podcast/page"):
        return "archive / pagination"
    if route == "/podcast":
        return "podcast hub"
    return "site page"


def route_family(page_type: str) -> str:
    if page_type in {"book page", "book hub"}:
        return page_type
    if page_type in {"article / blog", "blog archive", "podcast hub", "podcast episode", "podcast transcript", "archive / pagination", "category / hub", "topic hub"}:
        return page_type
    return page_type


def parse_local_sitemap(repo_root: Path) -> list[str]:
    sitemap = repo_root / "Sitemap.xml"
    if not sitemap.exists():
        return []
    routes: list[str] = []
    try:
        root = ET.fromstring(sitemap.read_text(encoding="utf-8"))
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for node in root.findall(".//sm:loc", ns) or root.findall(".//loc"):
            if node.text:
                routes.append(normalise_route(node.text.strip()))
    except ET.ParseError:
        return []
    return sorted(set(routes))


def parse_blog_post_routes(repo_root: Path) -> list[str]:
    routes: list[str] = []
    path = repo_root / "blog" / "posts.json"
    if not path.exists():
        return routes
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return routes
    items = data if isinstance(data, list) else data.get("posts", []) if isinstance(data, dict) else []
    for item in items:
        slug = str(item.get("slug") or "").strip()
        url = str(item.get("url") or "").strip()
        if url:
            routes.append(normalise_route(url))
        elif slug:
            routes.append(normalise_route(f"/blog/posts/{slug}/"))
    return sorted(set(routes))


def parse_podcast_candidate_routes(repo_root: Path) -> list[str]:
    routes: list[str] = []
    path = repo_root / "data" / "podcast-episodes.json"
    if not path.exists():
        return routes
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return routes
    items = data if isinstance(data, list) else data.get("episodes", []) if isinstance(data, dict) else []
    for item in items:
        transcript_url = str(item.get("transcript_url") or "").strip()
        if transcript_url and transcript_url.startswith("/"):
            routes.append(normalise_route(transcript_url))
        slug = str(item.get("slug") or "").strip()
        if slug:
            routes.append(normalise_route(f"/podcast/episodes/{slug}/"))
    return sorted(set(routes))


def parse_internal_links_from_html(repo_root: Path, prefixes: tuple[str, ...]) -> list[str]:
    routes: set[str] = set()
    for html_file in repo_root.rglob("*.html"):
        if html_file.parts[:2] == ("assets", "partials"):
            continue
        try:
            soup = parse_html(html_file.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for tag in soup.select('a[href^="/"]'):
            href = tag.get("href", "")
            route = normalise_route(href)
            if any(route == prefix or route.startswith(prefix + "/") for prefix in prefixes):
                routes.add(route)
    return sorted(routes)


def discover_routes(repo_root: Path, workbook_routes: list[str], excludes: list[str]) -> list[str]:
    routes: set[str] = set(repo_html_routes(repo_root, excludes))
    routes.update(route for route in workbook_routes if not should_exclude(route, excludes))
    routes.update(route for route in parse_local_sitemap(repo_root) if not should_exclude(route, excludes))
    routes.update(route for route in parse_blog_post_routes(repo_root) if not should_exclude(route, excludes))

    # Podcast episode candidates are only accepted when corroborated by another discovery source.
    podcast_candidates = set(parse_podcast_candidate_routes(repo_root))
    linked_candidates = set(parse_internal_links_from_html(repo_root, ("/podcast", "/blog")))
    routes.update(route for route in linked_candidates if not should_exclude(route, excludes))
    routes.update(route for route in podcast_candidates if route in linked_candidates and not should_exclude(route, excludes))

    # Keep the canonical 404 route only once.
    if "/404" in routes and "/404.html" in routes:
        routes.discard("/404")

    return sorted(set(normalise_route(route) for route in routes))


def score_checks(page: dict[str, Any]) -> dict[str, int]:
    meta = page["meta"]
    soup = page["soup"]
    seo = 0
    if page["status"] == 200:
        seo += 4
    if meta["title"]:
        seo += 4
    if 35 <= len(meta["title"]) <= 70:
        seo += 3
    if meta["metaDescription"]:
        seo += 3
    if meta["canonical"]:
        seo += 2
    if meta["h1"]:
        seo += 2
    if meta["schemaCount"]:
        seo += 2
    if soup.select_one("meta[property='og:title']"):
        seo += 2

    intro_text = " ".join(p.get_text(" ", strip=True) for p in soup.select("main p")[:3])
    question_headings = [h.get_text(" ", strip=True) for h in soup.select("h2, h3") if "?" in h.get_text(" ", strip=True)]
    list_count = len(soup.select("main ul, main ol"))
    aeo = 0
    if intro_text and len(intro_text.split()) <= 120:
        aeo += 6
    if question_headings:
        aeo += 5
    if list_count:
        aeo += 4
    if soup.select("script[type='application/ld+json']"):
        aeo += 3
    if soup.select("table"):
        aeo += 2

    body_text = soup.get_text(" ", strip=True)
    internal_links = [a.get("href", "") for a in soup.select("a[href^='/']")]
    geo = 0
    if "Jonathan Harris" in body_text:
        geo += 5
    if "AI" in body_text or "artificial intelligence" in body_text.lower():
        geo += 5
    if len(internal_links) >= 5:
        geo += 4
    if meta["schemaCount"]:
        geo += 3
    if intro_text and len(intro_text.split()) >= 40:
        geo += 3

    entity = 6 if "Jonathan Harris" in body_text else 2
    linking = min(10, len(internal_links))
    conversion = 5 if any(token in page["route"] for token in ("newsletter", "contact", "ebooks", "compare")) else 0

    return {
        "technicalSeo": min(20, seo),
        "onPageIntent": min(15, seo + 2),
        "aeo": min(20, aeo),
        "geo": min(20, geo),
        "entity": min(10, entity),
        "internalLinking": min(10, linking),
        "conversion": min(5, conversion),
    }


def total_score(parts: dict[str, int]) -> int:
    return sum(parts.values())


def grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def issue(issue_id: str, severity: str, lens: str, route: str, why: str, fix: str, evidence: str) -> dict[str, Any]:
    return {
        "issueId": issue_id,
        "severity": severity,
        "confidence": "Confirmed",
        "auditLens": lens,
        "rootCauseLevel": "page",
        "affected": route,
        "evidenceObserved": evidence,
        "whyItMatters": why,
        "exactRemediation": fix,
        "expectedGain": "Cleaner indexing signals and stronger retrieval quality",
        "estimatedEffort": "Low",
        "recommendedOwner": "Engineering",
    }


def inspect_page(base_url: str, route: str) -> dict[str, Any]:
    url = route_to_url(base_url, route)
    fetched = fetch_html(url)
    soup = parse_html(fetched.get("text", ""))
    meta = extract_meta(soup)
    page_type = classify_page(route)
    page = {
        "route": route,
        "url": url,
        "status": fetched.get("status", 0),
        "meta": meta,
        "soup": soup,
        "wordCount": len(soup.get_text(" ", strip=True).split()),
        "pageType": page_type,
        "routeFamily": route_family(page_type),
        "questionHeadings": [h.get_text(" ", strip=True) for h in soup.select("h2, h3") if "?" in h.get_text(" ", strip=True)],
        "internalLinks": len(soup.select("a[href^='/']")),
        "hasTable": bool(soup.select("table")),
        "hasFaqSchema": any("FAQPage" in script.get_text() for script in soup.select("script[type='application/ld+json']")),
    }
    page["scores"] = score_checks(page)
    page["total"] = total_score(page["scores"])
    page["grade"] = grade(page["total"])
    page["coverageState"] = "Fully analysed" if page["status"] == 200 else "Failed to fetch"
    page["riskFlag"] = "High" if page["grade"] in {"D", "F"} else "Low"
    return page


def build_inventory(repo_root: Path, excludes: list[str]) -> dict[str, Any]:
    workbook = load_workbook_info(find_workbook(repo_root))
    if workbook.url_count == 0:
        raise RuntimeError("Workbook resolved to 0 URL rows.")

    workbook_routes = [normalise_route(url) for url in workbook.urls if not should_exclude(normalise_route(url), excludes)]
    discovered_routes = discover_routes(repo_root, workbook_routes, excludes)
    repo_routes = repo_html_routes(repo_root, excludes)
    repo_only = sorted(set(repo_routes) - set(workbook_routes))
    workbook_only = sorted(set(workbook_routes) - set(repo_routes))

    return {
        "workbook": workbook,
        "repoRoutes": repo_routes,
        "workbookRoutes": workbook_routes,
        "discoveredRoutes": discovered_routes,
        "repoOnly": repo_only,
        "workbookOnly": workbook_only,
        "pageTypeCounts": Counter(classify_page(route) for route in discovered_routes),
    }


def validate_full_coverage(pages: list[dict[str, Any]]) -> None:
    mandatory = {"book page", "blog archive"}
    discovered_families = {page["routeFamily"] for page in pages}
    if "podcast episode" in discovered_families:
        mandatory.add("podcast episode")

    failures: list[str] = []
    for family in sorted(mandatory):
        family_pages = [page for page in pages if page["routeFamily"] == family]
        if not family_pages:
            failures.append(family)
            continue
        if any(page["coverageState"] != "Fully analysed" for page in family_pages):
            failures.append(family)

    if failures:
        raise RuntimeError(
            f"Full-estate coverage incomplete. Families below 100% coverage: {', '.join(failures)}"
        )


def collect_issues(pages: list[dict[str, Any]], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    count = 1
    if inventory["repoOnly"]:
        issues.append(issue(
            f"SEO-{count:03d}", "High", "Technical", inventory["repoOnly"][0],
            "Repo routes exist without workbook governance, which weakens source-of-truth control.",
            "Add the missing route(s) to the workbook or remove dead repo files.",
            f"Repo-only routes include {', '.join(inventory['repoOnly'][:8])}."
        ))
        count += 1
    if inventory["workbookOnly"]:
        issues.append(issue(
            f"SEO-{count:03d}", "High", "Technical", inventory["workbookOnly"][0],
            "Workbook-governed routes are missing in the repo, which breaks reconciliation and likely indicates drift.",
            "Restore or intentionally retire the missing route(s) and update workbook state.",
            f"Workbook-only routes include {', '.join(inventory['workbookOnly'][:8])}."
        ))
        count += 1
    return issues


def build_report(base_url: str, inventory: dict[str, Any], pages: list[dict[str, Any]], issues: list[dict[str, Any]], artefacts: dict[str, str]) -> str:
    overall_seo = round(sum(page["scores"]["technicalSeo"] + page["scores"]["onPageIntent"] for page in pages) / (len(pages) * 35) * 100)
    overall_aeo = round(sum(page["scores"]["aeo"] for page in pages) / (len(pages) * 20) * 100)
    overall_geo = round(sum(page["scores"]["geo"] for page in pages) / (len(pages) * 20) * 100)

    page_rows = "".join(
        f"<tr><td><code>{page['route']}</code></td><td>{page['pageType']}</td><td>{page['status']}</td><td>{page['total']}</td><td>{page['grade']}</td><td>{page['meta']['title']}</td></tr>"
        for page in pages
    )
    issue_rows = "".join(
        f"<tr><td>{item['issueId']}</td><td>{item['severity']}</td><td>{item['auditLens']}</td><td><code>{item['affected']}</code></td><td>{item['whyItMatters']}</td><td>{item['exactRemediation']}</td></tr>"
        for item in issues
    )
    type_rows = "".join(
        f"<tr><td>{page_type}</td><td>{count}</td></tr>" for page_type, count in sorted(inventory["pageTypeCounts"].items())
    )
    coverage_counts = Counter(page["coverageState"] for page in pages)

    body = f"""
    <section>
      <h2>Executive summary</h2>
      <div class=\"grid\">
        <div class=\"kpi\"><strong>SEO score</strong><div>{overall_seo}</div></div>
        <div class=\"kpi\"><strong>AEO score</strong><div>{overall_aeo}</div></div>
        <div class=\"kpi\"><strong>GEO score</strong><div>{overall_geo}</div></div>
        <div class=\"kpi\"><strong>Discovered routes</strong><div>{len(inventory['discoveredRoutes'])}</div></div>
        <div class=\"kpi\"><strong>Workbook routes</strong><div>{len(inventory['workbookRoutes'])}</div></div>
        <div class=\"kpi\"><strong>Issues logged</strong><div>{len(issues)}</div></div>
      </div>
      <p><strong>Live estate audited:</strong> <a href=\"{base_url}\">{base_url}</a></p>
    </section>
    <section>
      <h2>Inventory and reconciliation summary</h2>
      <p><strong>Workbook:</strong> <code>{Path(inventory['workbook'].path).name}</code> with {inventory['workbook'].url_count} URL rows.</p>
      <p><strong>Repo-only routes:</strong> {', '.join(inventory['repoOnly'][:12]) or 'None'}</p>
      <p><strong>Workbook-only routes:</strong> {', '.join(inventory['workbookOnly'][:12]) or 'None'}</p>
      <p><strong>Coverage states:</strong> {', '.join(f'{k}: {v}' for k, v in sorted(coverage_counts.items()))}</p>
      <table><thead><tr><th>Page type</th><th>Count</th></tr></thead><tbody>{type_rows}</tbody></table>
    </section>
    <section>
      <h2>Priority page findings</h2>
      <table><thead><tr><th>URL</th><th>Type</th><th>Status</th><th>Score</th><th>Grade</th><th>Title</th></tr></thead><tbody>{page_rows}</tbody></table>
    </section>
    <section>
      <h2>Ranked issue ledger</h2>
      <table><thead><tr><th>ID</th><th>Severity</th><th>Lens</th><th>Affected</th><th>Why it matters</th><th>Exact remediation</th></tr></thead><tbody>{issue_rows}</tbody></table>
    </section>
    <section>
      <h2>Artefacts</h2>
      <ul>
        <li><a href=\"{artefacts.get('summary.json', '#')}\">summary.json</a></li>
        <li><a href=\"{artefacts.get('coverage.json', '#')}\">coverage.json</a></li>
      </ul>
    </section>
    """
    return html_report_shell("Forensic SEO + AEO + GEO Audit", body)


def choose_priority_routes(discovered_routes: list[str]) -> list[str]:
    chosen: list[str] = []
    discovered = set(discovered_routes)
    for route in PRIORITY_ROUTES:
        route = normalise_route(route)
        if route in discovered:
            chosen.append(route)
    for route in discovered_routes:
        if classify_page(route) == "book page":
            chosen.append(route)
            break
    for route in discovered_routes:
        if classify_page(route) == "article / blog":
            chosen.append(route)
            break
    return list(dict.fromkeys(chosen))


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    excludes = [item.strip() for item in args.exclude_prefixes.split(",") if item.strip()]
    output_dir = ensure_dir(Path(args.output_dir))

    inventory = build_inventory(REPO_ROOT, excludes)
    all_pages = [inspect_page(base_url, route) for route in inventory["discoveredRoutes"]]
    validate_full_coverage(all_pages)

    priority_routes = choose_priority_routes(inventory["discoveredRoutes"])
    priority_pages = [page for page in all_pages if page["route"] in priority_routes]
    issues = collect_issues(priority_pages, inventory)

    coverage_rows = []
    for page in all_pages:
        coverage_rows.append({
            "url": page["url"],
            "route": page["route"],
            "pageType": page["pageType"],
            "routeFamily": page["routeFamily"],
            "status": page["status"],
            "title": page["meta"]["title"],
            "canonical": page["meta"]["canonical"],
            "coverageState": page["coverageState"],
            "grade": page["grade"],
            "riskFlag": page["riskFlag"],
        })

    summary = {
        "ok": True,
        "sessionId": args.session_id,
        "status": "completed",
        "reportPrefix": args.report_prefix,
        "focusPageCount": len(priority_pages),
        "issueCount": len(issues),
        "discoveredUrlCount": len(all_pages),
        "generatedAt": utc_now(),
    }

    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "coverage.json", {"rows": coverage_rows, "generatedAt": utc_now()})

    client = build_r2_client()
    uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)
    report_html = build_report(base_url, inventory, priority_pages, issues, uploaded)
    write_text(output_dir / "report.html", report_html)
    uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)

    callback_payload = {
        "auditType": "seo-aeo-geo",
        "sessionId": args.session_id,
        "status": "completed",
        "reportPrefix": args.report_prefix,
        "reportUrl": uploaded.get("report.html"),
        "summaryUrl": uploaded.get("summary.json"),
        "coverageUrl": uploaded.get("coverage.json"),
        "issueCount": len(issues),
        "artefacts": uploaded,
        "finishedAt": utc_now(),
        "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
    }
    post_callback(args.callback_url, args.callback_token, callback_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
