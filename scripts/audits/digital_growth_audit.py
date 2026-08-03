#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from scripts.audits.common import (
  build_r2_client,
  ensure_dir,
  extract_meta,
  fetch_html,
  html_report_shell,
  normalise_route,
  parse_html,
  post_callback,
  repo_html_routes,
  route_to_url,
  upload_selected_files_to_r2,
  utc_now,
  write_json,
  write_text,
)

AUDIT_TYPE = "digital-growth"
CALLBACK_MARKER_FILENAME = ".digital-growth-callback-posted.json"
DEFAULT_PRIORITY_ROUTES = [
  "/", "/newsletter", "/podcast", "/ebooks", "/catalogue", "/compare", "/bio", "/contact", "/topics", "/blog", "/transcripts",
]
CTA_WORDS = (
  "subscribe", "newsletter", "listen", "podcast", "buy", "ebook", "book", "download", "read", "contact", "learn more", "get",
)


def callback_marker_path(output_dir: Path) -> Path:
  return output_dir / CALLBACK_MARKER_FILENAME


def post_digital_growth_callback(
  callback_url: str | None,
  callback_token: str | None,
  output_dir: Path,
  payload: dict[str, Any],
) -> None:
  """Post one structured callback and leave a workflow-visible marker.

  Optional fields with ``None`` values are omitted so strict receivers do not
  reject an otherwise successful callback as JSON ``null``.
  """
  if not callback_url:
    print(f"[digital-growth] callback not configured; status={payload.get('status')}", flush=True)
    return
  clean_payload = {key: value for key, value in payload.items() if value is not None}
  post_callback(callback_url, callback_token, clean_payload)
  write_json(callback_marker_path(output_dir), {
    "postedAt": utc_now(),
    "auditType": clean_payload.get("auditType"),
    "sessionId": clean_payload.get("sessionId"),
    "status": clean_payload.get("status"),
    "reportPrefix": clean_payload.get("reportPrefix"),
    "hasReportUrl": bool(clean_payload.get("reportUrl")),
    "hasReportJsonUrl": bool(clean_payload.get("reportJsonUrl")),
  })
  print(f"[digital-growth] callback posted status={clean_payload.get('status')}", flush=True)


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run the Digital Growth and Monetisation website audit")
  parser.add_argument("--base-url", required=True)
  parser.add_argument("--session-id", default=utc_now())
  parser.add_argument("--report-prefix", required=True)
  parser.add_argument("--callback-url", default=None)
  parser.add_argument("--callback-token", default=None)
  parser.add_argument("--analysis-url", default=None)
  parser.add_argument("--output-dir", default="artifacts/digital-growth")
  parser.add_argument("--exclude-prefixes", default="")
  parser.add_argument("--audit-bucket", default=None)
  parser.add_argument("--audit-public-base-url", default=None)
  args = parser.parse_args()
  args.callback_url = (args.callback_url or os.environ.get("AUDIT_CALLBACK_URL") or os.environ.get("AI_SUITE_AUDIT_CALLBACK_URL") or "").strip() or None
  args.callback_token = (args.callback_token or os.environ.get("AUDIT_CALLBACK_TOKEN") or os.environ.get("AI_SUITE_AUDIT_CALLBACK_TOKEN") or "").strip() or None
  if args.audit_bucket:
    os.environ["R2_BUCKET_AUDITS"] = str(args.audit_bucket).strip()
  if args.audit_public_base_url:
    os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = str(args.audit_public_base_url).strip().rstrip("/")
  return args


def is_internal(url: str, base_url: str) -> bool:
  try:
    host = (urlparse(urljoin(base_url.rstrip("/") + "/", url)).hostname or "").lower()
    return host == (urlparse(base_url).hostname or "").lower()
  except Exception:
    return False


def schema_types(soup: BeautifulSoup) -> list[str]:
  types: set[str] = set()
  for node in soup.select("script[type='application/ld+json']"):
    try:
      data = json.loads(node.get_text(" ", strip=True) or "{}")
    except Exception:
      continue
    stack = [data]
    while stack:
      item = stack.pop()
      if isinstance(item, dict):
        value = item.get("@type")
        if isinstance(value, str):
          types.add(value)
        elif isinstance(value, list):
          types.update(str(v) for v in value if v)
        stack.extend(item.values())
      elif isinstance(item, list):
        stack.extend(item)
  return sorted(types)


def cta_records(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
  records: list[dict[str, str]] = []
  for node in soup.select("a[href], button"):
    label = " ".join(node.get_text(" ", strip=True).split())
    if not label:
      continue
    lower = label.lower()
    if not any(word in lower for word in CTA_WORDS):
      continue
    href = str(node.get("href") or "").strip()
    if href and href.startswith("/"):
      href = urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))
    records.append({"label": label[:160], "href": href[:500], "tag": node.name})
  return records[:80]


def form_records(soup: BeautifulSoup) -> list[dict[str, Any]]:
  rows = []
  for form in soup.select("form"):
    rows.append({
      "action": str(form.get("action") or "")[:500],
      "method": str(form.get("method") or "get").lower(),
      "inputCount": len(form.select("input,select,textarea")),
      "requiredCount": len(form.select("[required]")),
      "buttonText": [" ".join(btn.get_text(" ", strip=True).split())[:120] for btn in form.select("button,input[type='submit']")][:8],
    })
  return rows[:20]


def page_evidence(route: str, base_url: str) -> dict[str, Any]:
  url = route_to_url(base_url, route)
  fetched = fetch_html(url, timeout=20)
  soup = parse_html(fetched.get("text", ""))
  meta = extract_meta(soup)
  headings = [" ".join(h.get_text(" ", strip=True).split())[:220] for h in soup.select("h1,h2,h3") if h.get_text(" ", strip=True)]
  links = []
  for link in soup.select("a[href]"):
    href = str(link.get("href") or "").strip()
    if not href:
      continue
    absolute = urljoin(url, href)
    if is_internal(absolute, base_url):
      links.append({"label": " ".join(link.get_text(" ", strip=True).split())[:120], "href": absolute.split("#", 1)[0]})
  body_text = " ".join(soup.get_text(" ", strip=True).split())
  return {
    "route": route,
    "url": url,
    "status": int(fetched.get("status") or 0),
    "finalUrl": fetched.get("url") or url,
    "title": meta.get("title", ""),
    "metaDescription": meta.get("metaDescription", ""),
    "canonical": meta.get("canonical", ""),
    "h1": meta.get("h1", ""),
    "viewport": meta.get("viewport", ""),
    "schemaTypes": schema_types(soup),
    "headings": headings[:35],
    "forms": form_records(soup),
    "ctas": cta_records(soup, base_url),
    "internalLinks": links[:100],
    "textPreview": body_text[:4500],
  }


def route_priority(routes: list[str]) -> list[str]:
  normalised = {normalise_route(route) for route in routes}
  selected: list[str] = []
  for route in DEFAULT_PRIORITY_ROUTES:
    route = normalise_route(route)
    if route in normalised and route not in selected:
      selected.append(route)
  families = ["/ebooks/", "/podcast/", "/transcripts/", "/blog/", "/topics/"]
  for prefix in families:
    candidates = sorted(route for route in normalised if route.startswith(prefix) and route != prefix.rstrip("/"))
    selected.extend([route for route in candidates[:3] if route not in selected])
  if "/" not in selected:
    selected.insert(0, "/")
  return selected[:35]



def ebook_repository_evidence() -> list[dict[str, Any]]:
  rows: list[dict[str, Any]] = []
  ebook_root = REPO_ROOT / "ebooks"
  if not ebook_root.exists():
    return rows
  for path in sorted(ebook_root.rglob("index.html")):
    try:
      html = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
      continue
    soup = parse_html(html)
    relative = path.relative_to(REPO_ROOT)
    route = "/" + relative.parent.as_posix()
    if route.endswith("/."):
      route = route[:-2] or "/"
    links = []
    for node in soup.select("a[href], button"):
      label = " ".join(node.get_text(" ", strip=True).split())
      href = str(node.get("href") or "").strip()
      haystack = f"{label} {href}".lower()
      if any(word in haystack for word in ("buy", "purchase", "sample", "download", "amazon", "gumroad", "payhip", "ebook")):
        links.append({"label": label[:160], "href": href[:500], "tag": node.name})
    body = " ".join(soup.get_text(" ", strip=True).split())
    rows.append({
      "route": normalise_route(route),
      "file": relative.as_posix(),
      "h1": (soup.select_one("h1").get_text(" ", strip=True) if soup.select_one("h1") else "")[:240],
      "salesLinks": links[:20],
      "hasPriceSignal": bool(re.search(r"(?:£|\$|€)\s*\d", body)),
      "hasProofSignal": any(term in body.lower() for term in ("testimonial", "review", "reader", "rating", "what you will learn", "what you'll learn")),
      "hasSampleSignal": "sample" in body.lower(),
    })
  return rows

def repo_signals(routes: list[str]) -> dict[str, Any]:
  relevant_files = [
    "assets/partials/header.html", "assets/partials/footer.html", "assets/css/site.css", "assets/js/site-ui.min.js",
    "index.html", "newsletter/index.html", "podcast/index.html", "ebooks/index.html", "compare/index.html", "bio/index.html", "contact/index.html",
  ]
  snippets: dict[str, str] = {}
  keyword_counts = Counter()
  for relative in relevant_files:
    path = REPO_ROOT / relative
    if not path.exists() or not path.is_file():
      continue
    text = path.read_text(encoding="utf-8", errors="replace")
    snippets[relative] = text[:3500]
    lower = text.lower()
    for keyword in ("newsletter", "subscribe", "podcast", "ebook", "buy", "schema", "application/ld+json", "canonical"):
      keyword_counts[keyword] += lower.count(keyword)
  return {
    "repoRoot": str(REPO_ROOT),
    "routeCount": len(routes),
    "relevantFilesPresent": sorted(snippets),
    "keywordReferenceCounts": dict(keyword_counts),
    "sourcePreviews": snippets,
    "ebookSalesPathEvidence": ebook_repository_evidence(),
  }


def heuristic_issues(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  issues = []
  for page in pages:
    route = page["route"]
    if page["status"] != 200:
      issues.append({"issueId": f"DG-H-{len(issues)+1:03d}", "severity": "High", "objective": "Traffic Growth", "location": page["url"], "evidence": f"HTTP status {page['status']}", "issue": "Priority growth page did not return HTTP 200."})
    if not page["title"]:
      issues.append({"issueId": f"DG-H-{len(issues)+1:03d}", "severity": "High", "objective": "Traffic Growth", "location": page["url"], "evidence": "Missing <title>", "issue": "Priority page has no title."})
    if not page["h1"]:
      issues.append({"issueId": f"DG-H-{len(issues)+1:03d}", "severity": "Medium", "objective": "Traffic Growth", "location": page["url"], "evidence": "No H1 extracted", "issue": "Priority page has no visible H1 in fetched markup."})
  homepage = next((p for p in pages if p["route"] == "/"), None)
  if homepage:
    cta_text = " ".join(item["label"].lower() for item in homepage["ctas"])
    for term, objective in (("newsletter", "Newsletter Sign-Up Rate"), ("podcast", "Podcast Click-Throughs"), ("ebook", "Ebook Sales Maximisation")):
      if term not in cta_text:
        issues.append({"issueId": f"DG-H-{len(issues)+1:03d}", "severity": "Medium", "objective": objective, "location": homepage["url"], "evidence": f"No CTA label containing '{term}' was identified in the fetched homepage CTA set.", "issue": f"Homepage CTA prominence for {term} needs human/AI review."})
  return issues[:80]


def derive_analysis_url(callback_url: str | None, override: str | None) -> str | None:
  if override and override.strip():
    return override.strip()
  if not callback_url:
    return None
  callback_url = callback_url.rstrip("/")
  if callback_url.endswith("/callback"):
    return callback_url[:-len("/callback")] + "/analysis"
  return None


def extract_analysis(data: Any) -> dict[str, Any] | None:
  if not isinstance(data, dict):
    return None
  for value in (data.get("analysis"), (data.get("result") or {}).get("analysis") if isinstance(data.get("result"), dict) else None, (data.get("job") or {}).get("analysis") if isinstance(data.get("job"), dict) else None):
    if isinstance(value, dict) and value:
      return value
  if data.get("scorecard") and data.get("findings"):
    return data
  return None


def call_analysis(url: str | None, token: str | None, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
  if not url or not token:
    return None, "Digital growth analysis endpoint or callback token was not configured."
  headers = {"Authorization": f"Bearer {token}", "X-Audit-Callback-Token": token, "Content-Type": "application/json"}
  try:
    response = requests.post(url, headers=headers, json=payload, timeout=int(os.environ.get("AUDIT_ANALYSIS_POST_TIMEOUT_SECONDS", "45")))
  except Exception as exc:
    return None, f"Analysis POST failed: {exc}"
  if response.status_code == 200:
    try:
      return extract_analysis(response.json()), "Synchronous analysis response"
    except Exception as exc:
      return None, f"Analysis response JSON failed: {exc}"
  if response.status_code != 202:
    return None, f"Analysis endpoint returned HTTP {response.status_code}: {response.text[:700]}"
  try:
    data = response.json()
  except Exception as exc:
    return None, f"Analysis 202 response JSON failed: {exc}"
  status_url = str(data.get("statusUrl") or "").strip()
  if not status_url:
    return None, "Analysis endpoint returned 202 without statusUrl"
  deadline = time.monotonic() + max(30, int(os.environ.get("AUDIT_ANALYSIS_MAX_WAIT_SECONDS", "900")))
  poll_seconds = max(2, int(os.environ.get("AUDIT_ANALYSIS_POLL_SECONDS", "8")))
  while time.monotonic() < deadline:
    try:
      poll = requests.get(status_url, headers=headers, timeout=int(os.environ.get("AUDIT_ANALYSIS_POLL_TIMEOUT_SECONDS", "30")))
      if poll.status_code == 200:
        parsed = poll.json()
        analysis = extract_analysis(parsed)
        if analysis:
          return analysis, "Async analysis completed"
        if str(parsed.get("status", "")).lower() == "failed":
          return None, f"Analysis job failed: {parsed.get('error')}"
      elif poll.status_code >= 400 and poll.status_code != 404:
        return None, f"Analysis polling returned HTTP {poll.status_code}: {poll.text[:700]}"
    except Exception as exc:
      last_error = str(exc)
    time.sleep(poll_seconds)
  return None, f"Analysis polling timed out{': ' + last_error if 'last_error' in locals() else ''}"


def report_html(report: dict[str, Any]) -> str:
  analysis = report.get("analysis") or {}
  scorecard = analysis.get("scorecard") or {}
  rows = "".join(
    f"<tr><td>{key}</td><td>{value.get('score','')}</td><td>{value.get('rationale','')}</td></tr>"
    for key, value in scorecard.items() if isinstance(value, dict)
  )
  findings = analysis.get("findings") or []
  finding_rows = "".join(
    f"<tr><td>{item.get('findingId','')}</td><td>{item.get('objective','')}</td><td>{item.get('severity','')}</td><td>{item.get('location','')}</td><td>{item.get('exactChange','')}</td></tr>"
    for item in findings[:80] if isinstance(item, dict)
  )
  body = f"<section><h2>Stage status</h2><p>{report.get('status')}</p><p>{report.get('analysisDetail','')}</p></section>"
  body += f"<section><h2>Scorecard</h2><table><tr><th>Objective</th><th>Score</th><th>Rationale</th></tr>{rows}</table></section>"
  body += f"<section><h2>Findings</h2><table><tr><th>ID</th><th>Objective</th><th>Severity</th><th>Location</th><th>Exact change</th></tr>{finding_rows}</table></section>"
  body += "<section><h2>Retention note</h2><p>This is temporary stage evidence. AIMS deletes it after the unified final PDF has been safely published.</p></section>"
  return html_report_shell("Digital Growth & Monetisation Audit - Temporary Stage Report", body)


def analysis_is_complete(analysis: dict[str, Any] | None) -> bool:
  if not isinstance(analysis, dict):
    return False
  completion_state = str(analysis.get("auditCompletionState") or "").strip().lower()
  if completion_state != "complete":
    return False
  scorecard = analysis.get("scorecard") if isinstance(analysis.get("scorecard"), dict) else {}
  findings = analysis.get("findings") if isinstance(analysis.get("findings"), list) else []
  executive = analysis.get("executiveSummary") if isinstance(analysis.get("executiveSummary"), dict) else {}
  top_actions = executive.get("top10Actions") if isinstance(executive.get("top10Actions"), list) else []
  has_verdict = bool(str(analysis.get("overallVerdict") or "").strip())
  return bool(scorecard) and bool(findings or top_actions or has_verdict)


def main() -> int:
  args = parse_args()
  base_url = args.base_url.rstrip("/")
  output_dir = ensure_dir(Path(args.output_dir))
  excludes = [normalise_route(value.strip()) for value in args.exclude_prefixes.split(",") if value.strip()]
  all_routes = repo_html_routes(REPO_ROOT, excludes=excludes)
  if not all_routes:
    all_routes = ["/"]
  priority_routes = route_priority(all_routes)
  pages = [page_evidence(route, base_url) for route in priority_routes]
  repo = repo_signals(all_routes)
  heuristics = heuristic_issues(pages)

  inventory = {
    "repoRouteCount": len(all_routes),
    "priorityRouteCount": len(priority_routes),
    "routeFamilies": dict(Counter(route.split("/")[1] if route != "/" else "homepage" for route in all_routes)),
  }
  analysis_payload = {
    "auditType": AUDIT_TYPE,
    "sessionId": args.session_id,
    "baseUrl": base_url,
    "generatedAt": utc_now(),
    "inventory": inventory,
    "priorityPages": pages,
    "allRoutes": [{"route": route, "url": route_to_url(base_url, route)} for route in all_routes],
    "heuristicIssues": heuristics,
    "repoSignals": repo,
    "liveDynamicUrls": [],
    "coverage": [{"route": page["route"], "url": page["url"], "status": page["status"]} for page in pages],
    "conversionEvidence": {
      "priorityPageForms": {page["route"]: page["forms"] for page in pages if page["forms"]},
      "priorityPageCtas": {page["route"]: page["ctas"] for page in pages if page["ctas"]},
    },
    "navigationEvidence": {"homepageInternalLinks": next((page["internalLinks"] for page in pages if page["route"] == "/"), [])},
    "measurementAvailability": {"analyticsExportSupplied": False, "salesDataSupplied": False, "searchConsoleExportSupplied": False},
  }

  analysis_url = derive_analysis_url(args.callback_url, args.analysis_url)
  analysis, analysis_detail = call_analysis(analysis_url, args.callback_token, analysis_payload)
  complete_analysis = analysis_is_complete(analysis)
  status = "completed" if complete_analysis else "failed"
  audit_completion_state = "Complete" if complete_analysis else str((analysis or {}).get("auditCompletionState") or "Incomplete")
  evidence = {
    "auditType": AUDIT_TYPE,
    "sessionId": args.session_id,
    "generatedAt": utc_now(),
    "inventory": inventory,
    "priorityPages": pages,
    "repoSignals": repo,
    "heuristicIssues": heuristics,
    "limitations": [
      "No analytics, sales or Search Console export was supplied to this workflow; performance claims are intentionally not invented.",
      "Stage 1 uses fetched live markup and repository evidence. Rendered mobile interaction is reserved for the Mobile UX hard-gate stage.",
    ],
  }
  report = {
    "schemaVersion": "digital-growth-stage-report-v1",
    "auditType": AUDIT_TYPE,
    "sessionId": args.session_id,
    "generatedAt": utc_now(),
    "status": status,
    "auditCompletionState": audit_completion_state,
    "analysisDetail": analysis_detail,
    "analysis": analysis or {},
    "evidenceSummary": evidence,
    "heuristicIssues": heuristics,
    "priorityPages": pages,
    "inventory": inventory,
    "limitations": evidence["limitations"],
  }
  summary = {
    "auditType": AUDIT_TYPE,
    "sessionId": args.session_id,
    "status": status,
    "auditCompletionState": audit_completion_state,
    "analysisAvailable": bool(analysis),
    "analysisComplete": complete_analysis,
    "analysisDetail": analysis_detail,
    "scorecard": (analysis or {}).get("scorecard", {}),
    "overallVerdict": (analysis or {}).get("overallVerdict", "Digital growth AI analysis unavailable; evidence was preserved without invented scores."),
    "topActions": ((analysis or {}).get("executiveSummary") or {}).get("top10Actions", []),
    "generatedAt": utc_now(),
  }

  report_json_path = write_json(output_dir / "report.json", report)
  summary_path = write_json(output_dir / "summary.json", summary)
  evidence_path = write_json(output_dir / "evidence.json", evidence)
  report_html_path = write_text(output_dir / "report.html", report_html(report))

  bucket = (args.audit_bucket or os.environ.get("R2_BUCKET_AUDITS") or "").strip()
  public_base = (args.audit_public_base_url or os.environ.get("R2_PUBLIC_BASE_URL_AUDITS") or "").strip().rstrip("/")
  if args.callback_url and (not bucket or not public_base):
    raise RuntimeError("R2_BUCKET_AUDITS and R2_PUBLIC_BASE_URL_AUDITS are required for pipeline execution")

  uploaded: dict[str, str] = {}
  if bucket and public_base:
    client = build_r2_client()
    uploaded = upload_selected_files_to_r2(client, bucket, args.report_prefix, {
      "report.json": report_json_path,
      "summary.json": summary_path,
      "evidence.json": evidence_path,
      "report.html": report_html_path,
    }, public_base)

  callback = {
    "auditType": AUDIT_TYPE,
    "sessionId": args.session_id,
    "status": status,
    "auditCompletionState": audit_completion_state,
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html", str(report_html_path)),
    "reportJsonUrl": uploaded.get("report.json", str(report_json_path)),
    "summaryUrl": uploaded.get("summary.json", str(summary_path)),
    "evidenceUrl": uploaded.get("evidence.json", str(evidence_path)),
    "issueCount": len((analysis or {}).get("findings") or heuristics),
    "message": "Digital Growth and Monetisation stage completed with a valid machine-readable analysis contract." if complete_analysis else f"Digital Growth stage failed its analysis evidence contract: {analysis_detail}",
    "artefacts": uploaded,
    "finishedAt": utc_now(),
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  if not complete_analysis:
    callback["error"] = f"Digital Growth analysis was missing auditCompletionState=Complete, a scorecard, or substantive findings/actions. Detail: {analysis_detail}"
  try:
    post_digital_growth_callback(args.callback_url, args.callback_token, output_dir, callback)
  except Exception as exc:
    print(f"[callback] post failed: {exc}", file=sys.stderr)
    if args.callback_url:
      raise
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
