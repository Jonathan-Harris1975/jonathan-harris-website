#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_FILE = Path(__file__).resolve()
REPO_ROOT = SCRIPT_FILE.parents[2]
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

FOCUS_ROUTES = [
    "/",
    "/ebooks",
    "/newsletter",
    "/contact",
    "/bio",
    "/compare",
    "/topics",
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
    if route == "/":
        return "homepage"
    if route.startswith("/ebooks/") and route.count("/") > 2:
        return "book page"
    if route.startswith("/ebooks"):
        return "book hub"
    if route.startswith("/catalogue"):
        return "category / hub"
    if route.startswith("/topics"):
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
    return "site page"


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
    page = {
        "route": route,
        "url": url,
        "status": fetched.get("status", 0),
        "meta": meta,
        "soup": soup,
        "wordCount": len(soup.get_text(" ", strip=True).split()),
        "pageType": classify_page(route),
        "questionHeadings": [h.get_text(" ", strip=True) for h in soup.select("h2, h3") if "?" in h.get_text(" ", strip=True)],
        "internalLinks": len(soup.select("a[href^='/']")),
        "hasTable": bool(soup.select("table")),
        "hasFaqSchema": any("FAQPage" in script.get_text() for script in soup.select("script[type='application/ld+json']")),
    }
    page["scores"] = score_checks(page)
    page["total"] = total_score(page["scores"])
    page["grade"] = grade(page["total"])
    return page


def build_inventory(excludes: list[str]) -> dict[str, Any]:
    workbook = load_workbook_info(find_workbook(REPO_ROOT))
    repo_routes = repo_html_routes(REPO_ROOT, excludes)
    workbook_routes = [normalise_route(url) for url in workbook.urls if not should_exclude(normalise_route(url), excludes)]
    repo_only = sorted(set(repo_routes) - set(workbook_routes))
    workbook_only = sorted(set(workbook_routes) - set(repo_routes))
    return {
        "workbook": workbook,
        "repoRoutes": repo_routes,
        "workbookRoutes": workbook_routes,
        "repoOnly": repo_only,
        "workbookOnly": workbook_only,
        "pageTypeCounts": Counter(classify_page(route) for route in repo_routes),
    }


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

    for page in pages:
        meta = page["meta"]
        if not meta["metaDescription"]:
            issues.append(issue(
                f"SEO-{count:03d}", "Medium", "SEO", page["route"],
                "Missing meta descriptions reduce SERP control and answer-engine summary quality.",
                "Add a unique meta description aligned to page intent and opening copy.",
                f"Page title present: {meta['title'] or 'missing title'}; meta description missing."
            ))
            count += 1
        if not meta["canonical"]:
            issues.append(issue(
                f"SEO-{count:03d}", "Medium", "Technical", page["route"],
                "Missing canonical weakens duplication control and route normalisation.",
                "Publish an absolute canonical tag matching the intended public URL.",
                f"Canonical missing on {page['url']}."
            ))
            count += 1
        if page["wordCount"] < 180:
            issues.append(issue(
                f"SEO-{count:03d}", "Medium", "GEO", page["route"],
                "Thin copy gives search and generative engines very little reliable passage material.",
                "Add a compact answer-first introduction, supporting evidence, and stronger internal links.",
                f"Visible word count is {page['wordCount']} words."
            ))
            count += 1
        if page["pageType"] in {"lead generation", "comparison"} and not page["questionHeadings"]:
            issues.append(issue(
                f"SEO-{count:03d}", "Low", "AEO", page["route"],
                "The page lacks question-shaped headings or extractable answer blocks.",
                "Add a short direct-answer block and at least one intent-matching FAQ heading.",
                f"No question headings detected on {page['route']}."
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
        f"<tr><td>{page_type}</td><td>{count}</td></tr>" for page_type, count in inventory["pageTypeCounts"].items()
    )

    body = f"""
    <section>
      <h2>Executive summary</h2>
      <div class=\"grid\">
        <div class=\"kpi\"><strong>SEO score</strong><div>{overall_seo}</div></div>
        <div class=\"kpi\"><strong>AEO score</strong><div>{overall_aeo}</div></div>
        <div class=\"kpi\"><strong>GEO score</strong><div>{overall_geo}</div></div>
        <div class=\"kpi\"><strong>Repo routes</strong><div>{len(inventory['repoRoutes'])}</div></div>
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
        <li><a href=\"{artefacts.get('evidence.json', '#')}\">evidence.json</a></li>
        <li><a href=\"{artefacts.get('reconciliation.json', '#')}\">reconciliation.json</a></li>
      </ul>
    </section>
    """
    return html_report_shell("Forensic SEO + AEO + GEO Audit", body)


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    excludes = [item.strip() for item in args.exclude_prefixes.split(",") if item.strip()]
    output_dir = ensure_dir(Path(args.output_dir))

    inventory = build_inventory(excludes)
    focus = []
    repo_routes = set(inventory["repoRoutes"])
    for route in FOCUS_ROUTES:
        route = normalise_route(route)
        if route in repo_routes and not should_exclude(route, excludes):
            focus.append(route)

    for route in inventory["repoRoutes"]:
        if route.startswith("/ebooks/") and route.count("/") > 2:
            focus.append(route)
            break

    focus = list(dict.fromkeys(focus))
    pages = [inspect_page(base_url, route) for route in focus]
    issues = collect_issues(pages, inventory)

    serialisable_pages = [{k: v for k, v in page.items() if k != "soup"} for page in pages]
    evidence = {
        "focusPages": serialisable_pages,
        "issues": issues,
        "generatedAt": utc_now(),
    }
    reconciliation = {
        "repoRoutes": inventory["repoRoutes"],
        "workbookRoutes": inventory["workbookRoutes"],
        "repoOnly": inventory["repoOnly"],
        "workbookOnly": inventory["workbookOnly"],
        "pageTypeCounts": dict(inventory["pageTypeCounts"]),
        "generatedAt": utc_now(),
    }
    summary = {
        "ok": True,
        "sessionId": args.session_id,
        "status": "completed",
        "reportPrefix": args.report_prefix,
        "focusPageCount": len(pages),
        "issueCount": len(issues),
        "generatedAt": utc_now(),
    }

    write_json(output_dir / "evidence.json", evidence)
    write_json(output_dir / "reconciliation.json", reconciliation)
    write_json(output_dir / "summary.json", summary)

    client = build_r2_client()
    uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)
    report_html = build_report(base_url, inventory, pages, issues, uploaded)
    write_text(output_dir / "report.html", report_html)
    uploaded = upload_directory_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, output_dir)

    callback_payload = {
        "auditType": "seo-aeo-geo",
        "sessionId": args.session_id,
        "status": "completed",
        "reportPrefix": args.report_prefix,
        "reportUrl": uploaded.get("report.html"),
        "summaryUrl": uploaded.get("summary.json"),
        "evidenceUrl": uploaded.get("evidence.json"),
        "reconciliationUrl": uploaded.get("reconciliation.json"),
        "issueCount": len(issues),
        "artefacts": uploaded,
        "finishedAt": utc_now(),
        "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
    }
    post_callback(args.callback_url, args.callback_token, callback_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
