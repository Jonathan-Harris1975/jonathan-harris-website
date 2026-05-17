#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict, deque
from bs4 import BeautifulSoup
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from scripts.audits.common import (
  DEFAULT_EXCLUDES,
  REPO_ROOT,
  WorkbookInfo,
  build_r2_client,
  detect_challenge_page,
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
  upload_selected_files_to_r2,
  utc_now,
  write_json,
  write_text,
)


ALLOWED_NON_HTML_EXTENSIONS = {""}
BLOCKED_PATH_SUFFIXES = {
  ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".ico", ".css", ".js", ".map", ".xml", ".json", ".txt", ".pdf", ".mp3", ".wav", ".m4a", ".zip",
}
ROUTE_FAMILY_ORDER = [
  "homepage",
  "author / about",
  "service / product",
  "category / hub",
  "book page",
  "book buy-now path",
  "book hub",
  "topic hub",
  "blog archive",
  "blog article",
  "podcast hub",
  "podcast episode",
  "podcast transcript",
  "archive / pagination / utility",
  "lead generation",
  "comparison",
  "knowledge base",
  "site page",
]
IMPORTANT_PAGE_TYPES = {
  "homepage",
  "lead generation",
  "comparison",
  "author / about",
  "book hub",
  "book page",
  "category / hub",
  "topic hub",
  "blog article",
  "podcast episode",
  "podcast transcript",
  "podcast hub",
  "blog archive",
}
FINAL_ARTIFACTS = ("report.html", "summary.json", "coverage.json")
DEFAULT_PODCAST_FEED = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml"
ANALYSED_STATES = {"Fully analysed", "Analysed through shared template plus page-specific checks"}
EXCLUDED_STATE_PREFIX = "Excluded"
COVERED_STATES = ANALYSED_STATES
SHARED_TEMPLATE_FAMILIES = {"book page", "category / hub", "topic hub", "archive / pagination / utility"}
AI_REQUIRED_SECTIONS = [
  "executive synthesis",
  "issue prioritisation",
  "AEO/GEO judgement",
  "exact remediation language",
  "page-family verdicts",
  "implementation sequence",
  "business impact explanations",
]
AI_RESTORE_STEPS = [
  "Provide a callback_url that resolves to /audits/seo-aeo-geo/callback so the workflow can derive /audits/seo-aeo-geo/analysis.",
  "Ensure AUDIT_CALLBACK_TOKEN / AI_SUITE_AUDIT_CALLBACK_TOKEN matches the AI Management Suite callback auth configuration.",
  "Verify the AI Management Suite auditForensic route has at least one configured provider in services/shared/utils/ai-config.js with its existing OPENROUTER_* model and key variables set.",
  "Rerun /audits/seo-aeo-geo/run after the /analysis endpoint returns a validated forensic JSON payload.",
]


def coverage_state_for_page(page_type: str, status_code: int) -> str:
  if status_code != 200:
    return "Failed to fetch"
  if page_type in SHARED_TEMPLATE_FAMILIES:
    return "Analysed through shared template plus page-specific checks"
  return "Fully analysed"


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run the full-estate forensic SEO + AEO + GEO audit")
  parser.add_argument("--base-url", required=True)
  parser.add_argument("--session-id", default=utc_now())
  parser.add_argument("--report-prefix", default="seo-aeo-geo-audit")
  parser.add_argument("--callback-url", default=None)
  parser.add_argument("--callback-token", default=None)
  parser.add_argument("--analysis-url", default=None, help="Override the LLM analysis endpoint")
  parser.add_argument("--output-dir", default="artifacts/seo-aeo-geo")
  parser.add_argument("--exclude-prefixes", default="")
  parser.add_argument("--audit-bucket", default=None, help="Dedicated audits R2 bucket name")
  parser.add_argument("--audit-public-base-url", default=None, help="Dedicated audits R2 public base URL")
  args = parser.parse_args()
  resolve_runtime_callback_config(args)
  resolve_runtime_audit_r2_config(args)
  return args


def _first_env(*names: str) -> str | None:
  for name in names:
    value = os.environ.get(name)
    if value and str(value).strip():
      return str(value).strip()
  return None


def _normalise_callback_base(value: str | None) -> str | None:
  if not value:
    return None
  value = value.strip().rstrip("/")
  if not value:
    return None
  if value.endswith("/audits/seo-aeo-geo/callback"):
    return value
  if value.endswith("/audits/seo-aeo-geo"):
    return f"{value}/callback"
  if value.endswith("/audits"):
    return f"{value}/seo-aeo-geo/callback"
  return f"{value}/audits/seo-aeo-geo/callback"


def resolve_runtime_callback_config(args: argparse.Namespace) -> argparse.Namespace:
  """Fill callback URL/token from GitHub Actions env when workflow inputs are blank."""
  if not getattr(args, "callback_url", None):
    args.callback_url = (
      _first_env("AUDIT_CALLBACK_URL", "AI_SUITE_AUDIT_CALLBACK_URL")
      or _normalise_callback_base(_first_env("AUDIT_CALLBACK_BASE_URL", "APP_URL"))
    )
  if args.callback_url:
    args.callback_url = args.callback_url.rstrip("/")

  if not getattr(args, "callback_token", None):
    args.callback_token = _first_env("AUDIT_CALLBACK_TOKEN", "AI_SUITE_AUDIT_CALLBACK_TOKEN")
  return args


def resolve_runtime_audit_r2_config(args: argparse.Namespace) -> argparse.Namespace:
  """Route SEO/AEO/GEO audit artefacts to the dedicated audits bucket only."""
  if getattr(args, "audit_bucket", None):
    os.environ["R2_BUCKET_AUDITS"] = str(args.audit_bucket).strip()
  if getattr(args, "audit_public_base_url", None):
    os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = str(args.audit_public_base_url).strip().rstrip("/")
  return args


def require_audit_r2_config(callback_url: str | None = None) -> tuple[str, str]:
  bucket = os.environ.get("R2_BUCKET_AUDITS", "").strip()
  public_base = os.environ.get("R2_PUBLIC_BASE_URL_AUDITS", "").strip().rstrip("/")
  missing = []
  if not bucket:
    missing.append("R2_BUCKET_AUDITS")
  if not public_base:
    missing.append("R2_PUBLIC_BASE_URL_AUDITS")
  if missing and callback_url:
    raise RuntimeError(f"{' and '.join(missing)} must be configured before posting an SEO/AEO/GEO audit callback")
  return bucket, public_base


def callback_config_missing_reason(callback_url: str | None, callback_token: str | None) -> str | None:
  missing = []
  if not callback_url:
    missing.append("callback_url")
  if not callback_token:
    missing.append("callback_token")
  if not missing:
    return None
  return "missing " + " and ".join(missing)


def _safe_detail(value: Any, limit: int = 900) -> str:
  text = str(value or "")
  text = re.sub(r"Bearer\s+[^\s,;]+", "Bearer [masked]", text)
  text = re.sub(r"sk-or-[A-Za-z0-9._\-]+", "sk-or-[masked]", text)
  text = re.sub(r"github_pat_[A-Za-z0-9_]+", "github_pat_[masked]", text)
  return text[:limit]


def base_host(base_url: str) -> str:
  return (urlparse(base_url).hostname or "").lower()


def is_primary_site_url(url: str, base_url: str) -> bool:
  parsed = urlparse(urljoin(base_url.rstrip("/") + "/", url))
  host = (parsed.hostname or "").lower()
  allowed_host = base_host(base_url)
  return bool(host and allowed_host and host == allowed_host)


def is_in_scope_url(url: str, base_url: str) -> bool:
  """Return true only for the audited website host, not RSS/source/asset subdomains."""
  return is_primary_site_url(url, base_url)


def normalise_absolute_url(url: str, base_url: str, context_url: str | None = None) -> str:
  source_base = (context_url or base_url).rstrip("/") + "/"
  absolute = urljoin(source_base, url)
  parsed = urlparse(absolute)
  scheme = parsed.scheme or "https"
  host = (parsed.netloc or base_host(base_url)).lower()
  path = parsed.path or "/"
  path = normalise_route(path)
  return f"{scheme}://{host}{path}"


def is_excluded_state(state: str) -> bool:
  return str(state or "").startswith(EXCLUDED_STATE_PREFIX)


def is_analysed_state(state: str) -> bool:
  return state in ANALYSED_STATES


def is_covered_state(state: str) -> bool:
  return is_analysed_state(state) or is_excluded_state(state)


def is_podcast_compatibility_redirect(page: dict[str, Any]) -> bool:
  path = normalise_route(page.get("path") or urlparse(page.get("url", "")).path)
  title = str(page.get("meta", {}).get("title") or "").strip().lower()
  return bool(re.match(r"^/podcast/TT-\d{4}-\d{2}-\d{2}$", path)) or title.startswith("redirecting")


def is_redirect_or_non_page_family(page_type: str, coverage_state: str = "") -> bool:
  family = str(page_type or "").lower()
  return "buy-now" in family or is_excluded_state(coverage_state) or "redirect" in str(coverage_state or "").lower()


def clean_template_observed_logic(page_type: str, observed: str, analysed_count: int = 0) -> str:
  text = str(observed or "")
  if "transcript" in str(page_type or "").lower() and text.lower().startswith("0 transcript page"):
    total = analysed_count or 0
    return f"{total}/{total} transcript page(s) lack verified above-the-fold summary, key-takeaway, topic-index, timestamp/section-anchor, or entity-index evidence before the transcript body."
  return text


def clean_link_candidate(href: str, context_url: str, base_url: str) -> str | None:
  href = (href or "").strip()
  if not href or href.startswith("#"):
    return None
  if href.startswith(("mailto:", "tel:", "javascript:")):
    return None
  absolute = normalise_absolute_url(href, base_url, context_url=context_url)
  parsed = urlparse(absolute)
  suffix = Path(parsed.path).suffix.lower()
  if suffix and suffix in BLOCKED_PATH_SUFFIXES:
    return None
  if not is_in_scope_url(absolute, base_url):
    return None
  return absolute


def normalise_discovery_url(url: str, base_url: str) -> str:
  normalised = normalise_absolute_url(url, base_url)
  path = normalise_route(urlparse(normalised).path)
  if re.match(r"^/TT-\d{4}-\d{2}-\d{2}$", path):
    return normalise_absolute_url(f"/podcast{path}", base_url)
  return normalised

def classify_page(url: str) -> str:
  parsed = urlparse(url)
  path = normalise_route(parsed.path)
  host = (parsed.hostname or "").lower()
  if path == "/":
    return "homepage"
  if host.startswith("transcripts.") or "/transcript" in path or "/transcripts" in path:
    return "podcast transcript"
  if path.startswith("/blog/posts/"):
    return "blog article"
  if path.startswith("/blog"):
    return "blog archive"
  if path.startswith("/podcast/episodes/") or re.match(r"^/podcast/TT-\d{4}-\d{2}-\d{2}$", path):
    return "podcast episode"
  if path.startswith("/podcast"):
    return "podcast hub"
  if path.startswith("/ebooks/") and path.endswith("/buy-now"):
    return "book buy-now path"
  if path.startswith("/ebooks/") and path.count("/") >= 2:
    return "book page"
  if path.startswith("/ebooks"):
    return "book hub"
  if path.startswith("/catalogue"):
    return "category / hub"
  if path.startswith("/topics"):
    return "topic hub"
  if path.startswith("/newsletter") or path.startswith("/contact"):
    return "lead generation"
  if path.startswith("/compare"):
    return "comparison"
  if path.startswith("/bio"):
    return "author / about"
  if path.startswith("/glossary"):
    return "knowledge base"
  if path.startswith("/affiliate") or path.startswith("/api/docs"):
    return "service / product"
  if path.startswith("/404") or any(token in path for token in ("/page/", "/tag/", "/category/", "?page=")):
    return "archive / pagination / utility"
  return "site page"

def representative_family_source(page_type: str) -> str:
  mapping = {
    "book page": "ebooks/*/index.html",
    "book buy-now path": "ebooks/*/buy-now redirect",
    "book hub": "ebooks/index.html",
    "category / hub": "catalogue/*/index.html",
    "topic hub": "topics/*/index.html",
    "blog article": "blog/posts.json + blog/posts/*/index.html",
    "blog archive": "blog/index.html + blog/weekly/index.html",
    "podcast hub": "podcast/index.html + podcast RSS feed",
    "podcast episode": "live podcast episode routes + podcast RSS feed",
    "podcast transcript": "live transcript routes + podcast RSS transcript links",
    "homepage": "index.html",
    "author / about": "bio/index.html",
    "lead generation": "newsletter/index.html + contact/index.html",
    "comparison": "compare/index.html",
    "knowledge base": "glossary/index.html",
  }
  return mapping.get(page_type, "repo route family")


def _safe_mean(values: list[float]) -> float:
  return round(mean(values), 1) if values else 0.0


def _sample(values: list[Any], limit: int = 5) -> list[Any]:
  return values[:limit]


def _route_or_url(value: str) -> str:
  parsed = urlparse(value)
  if parsed.scheme or parsed.netloc:
    return normalise_route(parsed.path)
  return normalise_route(value)


def _jsonld_schema_types(soup: BeautifulSoup | None) -> list[str]:
  if not soup:
    return []
  found: list[str] = []

  def collect(value: Any) -> None:
    if isinstance(value, dict):
      schema_type = value.get("@type")
      if isinstance(schema_type, list):
        found.extend(str(item) for item in schema_type if item)
      elif schema_type:
        found.append(str(schema_type))
      graph = value.get("@graph")
      if isinstance(graph, list):
        for node in graph:
          collect(node)
    elif isinstance(value, list):
      for item in value:
        collect(item)

  for script in soup.select("script[type='application/ld+json']"):
    try:
      collect(json.loads(script.string or ""))
    except Exception:
      continue
  return sorted(set(found))


def _soup_text_contains(soup: BeautifulSoup | None, patterns: tuple[str, ...]) -> bool:
  if not soup:
    return False
  text = soup.get_text(" ", strip=True).lower()
  return any(pattern in text for pattern in patterns)


def _has_internal_link_to(soup: BeautifulSoup | None, prefixes: tuple[str, ...]) -> bool:
  if not soup:
    return False
  for link in soup.select("a[href]"):
    href = (link.get("href") or "").strip()
    if any(href.startswith(prefix) or f"jonathan-harris.online{prefix}" in href for prefix in prefixes):
      return True
  return False


def _opening_paragraph_repeats(soup: BeautifulSoup | None) -> bool:
  if not soup:
    return False
  paragraphs = [p.get_text(" ", strip=True) for p in soup.select("p") if len(p.get_text(" ", strip=True).split()) >= 12]
  if len(paragraphs) < 3:
    return False
  normalised = [re.sub(r"\s+", " ", p.lower()).strip() for p in paragraphs[:6]]
  counts = Counter(normalised)
  return any(count >= 2 for text, count in counts.items() if len(text) > 80)


def build_family_diagnostics(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Build page-family forensic diagnostics for the AI context and report annex."""
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)

  rows: list[dict[str, Any]] = []
  for page_type in sorted(family_map.keys(), key=lambda item: ROUTE_FAMILY_ORDER.index(item) if item in ROUTE_FAMILY_ORDER else 999):
    family_pages = family_map[page_type]
    analysed = [page for page in family_pages if is_analysed_state(page.get("coverageState", ""))]
    score_pages = analysed or family_pages
    schemas_by_type: Counter[str] = Counter()
    audio_pages: list[str] = []
    transcript_link_pages: list[str] = []
    takeaway_pages: list[str] = []
    faq_pages: list[str] = []
    topic_link_pages: list[str] = []
    repeated_intro_pages: list[str] = []
    raw_transcript_wall_pages: list[str] = []
    transcript_structure_gap_pages: list[str] = []

    for page in analysed:
      soup = page.get("soup")
      for schema_type in _jsonld_schema_types(soup):
        schemas_by_type[schema_type] += 1
      if soup and soup.select("audio"):
        audio_pages.append(page["url"])
      if _has_internal_link_to(soup, ("/transcripts/",)):
        transcript_link_pages.append(page["url"])
      if _soup_text_contains(soup, ("key takeaway", "key takeaways", "what this means", "what changed")):
        takeaway_pages.append(page["url"])
      if page.get("hasFaqSchema") or "FAQPage" in schemas_by_type:
        faq_pages.append(page["url"])
      if _has_internal_link_to(soup, ("/topics/", "/ebooks/", "/glossary")):
        topic_link_pages.append(page["url"])
      if _opening_paragraph_repeats(soup):
        repeated_intro_pages.append(page["url"])
      if page_type == "podcast transcript":
        has_summary_led_structure = _soup_text_contains(
          soup,
          (
            "key takeaway", "key takeaways", "what changed", "topic index",
            "entity index", "timestamp", "section anchor", "topics covered",
          ),
        )
        if not has_summary_led_structure:
          transcript_structure_gap_pages.append(page["url"])
        if page.get("wordCount", 0) > 1200:
          h2_count = len(soup.select("h2")) if soup else 0
          if h2_count < 3 or len(page.get("introText", "").split()) < 60:
            raw_transcript_wall_pages.append(page["url"])

    no_questions = [page["url"] for page in analysed if not page.get("questionHeadings")]
    weak_intro = [page["url"] for page in analysed if len(page.get("introText", "").split()) < 35]
    missing_meta = [page["url"] for page in analysed if not page.get("meta", {}).get("metaDescription")]
    missing_canonical = [page["url"] for page in analysed if not page.get("meta", {}).get("canonical")]

    observed: list[str] = []
    if page_type == "podcast episode":
      observed.append(
        f"{len(audio_pages)}/{len(analysed)} analysed episode pages expose audio; "
        f"{len(transcript_link_pages)}/{len(analysed)} link to transcripts; "
        f"{len(takeaway_pages)}/{len(analysed)} expose key-takeaway style copy; "
        f"{len(topic_link_pages)}/{len(analysed)} link into topic/book/glossary assets."
      )
    elif page_type == "podcast transcript":
      observed.append(
        f"{len(transcript_structure_gap_pages)}/{len(analysed)} transcript page(s) lack verified above-the-fold summary, key-takeaway, topic-index, timestamp/section-anchor, or entity-index evidence before the transcript body."
      )
    elif page_type == "blog article":
      observed.append(
        f"{len(repeated_intro_pages)} analysed blog article pages repeat an opening paragraph/standfirst near the top."
      )
    else:
      observed.append(
        f"{len(no_questions)} analysed URLs lack question-led headings; {len(weak_intro)} have short openings under 35 words."
      )

    rows.append({
      "pageType": page_type,
      "routeFamily": derive_route_family(family_pages[0]["url"]),
      "sourceFile": representative_family_source(page_type),
      "totalUrls": len(family_pages),
      "analysedUrls": len(analysed),
      "excludedUrls": len([page for page in family_pages if is_excluded_state(page.get("coverageState", ""))]),
      "failedUrls": len([page for page in family_pages if page.get("coverageState") == "Failed to fetch"]),
      "averageScore": _safe_mean([float(page.get("total", 0)) for page in analysed]),
      "averageAeo": _safe_mean([float(page.get("scores", {}).get("aeo", 0)) for page in analysed]),
      "averageGeo": _safe_mean([float(page.get("scores", {}).get("geo", 0)) for page in analysed]),
      "schemaTypesObserved": dict(schemas_by_type),
      "missingMetaCount": len(missing_meta),
      "missingCanonicalCount": len(missing_canonical),
      "noQuestionHeadingCount": len(no_questions),
      "weakOpeningCount": len(weak_intro),
      "audioPageCount": len(audio_pages),
      "transcriptLinkCount": len(transcript_link_pages),
      "takeawayBlockCount": len(takeaway_pages),
      "topicOrBookLinkCount": len(topic_link_pages),
      "repeatedOpeningCount": len(repeated_intro_pages),
      "rawTranscriptWallCount": len(raw_transcript_wall_pages),
      "transcriptStructureGapCount": len(transcript_structure_gap_pages),
      "sampleUrls": _sample([page["url"] for page in family_pages], 8),
      "sampleWeakUrls": _sample(no_questions or weak_intro or transcript_structure_gap_pages or raw_transcript_wall_pages or repeated_intro_pages, 8),
      "observedTemplateEvidence": observed,
    })
  return rows


def build_source_ledger(discovery_meta: dict[str, Any], workbook: WorkbookInfo, repo_signals: dict[str, Any]) -> list[dict[str, Any]]:
  counts = discovery_meta.get("sourceCounts", {})
  return [
    {
      "source": "Repository static routes",
      "count": counts.get("repo", 0),
      "role": "Primary source for static HTML and route-family templates",
      "status": "Confirmed",
      "evidence": "Routes discovered by repo_html_routes().",
    },
    {
      "source": "Workbook Pages inventory",
      "count": workbook.url_count,
      "role": "Governance source for intended published URLs",
      "status": "Confirmed" if workbook.url_count else "Needs verification",
      "evidence": f"Workbook sheet: {workbook.primary_sheet or 'not detected'}.",
    },
    {
      "source": "Repository sitemap.xml",
      "count": counts.get("sitemap", 0),
      "role": "Crawler-facing URL ledger",
      "status": "Confirmed" if counts.get("sitemap", 0) else "Needs verification",
      "evidence": "Local sitemap URLs parsed from sitemap.xml.",
    },
    {
      "source": "Blog manifest",
      "count": repo_signals.get("blogManifestCount", 0),
      "role": "Dynamic editorial article inventory",
      "status": "Confirmed" if repo_signals.get("blogManifestCount", 0) else "Needs verification",
      "evidence": repo_signals.get("blogManifestPath", "blog/posts.json"),
    },
    {
      "source": "Podcast manifest",
      "count": repo_signals.get("podcastManifestCount", 0),
      "role": "Podcast episode and transcript route source",
      "status": "Confirmed" if repo_signals.get("podcastManifestCount", 0) else "Needs verification",
      "evidence": repo_signals.get("podcastManifestPath", "data/podcast-episodes.json"),
    },
    {
      "source": "llms discovery files",
      "count": len(repo_signals.get("llmsFiles", [])),
      "role": "Machine-readable discovery surface for generative retrieval",
      "status": "Confirmed" if repo_signals.get("llmsFiles") else "Needs verification",
      "evidence": f"Scope detected: {repo_signals.get('llmsScope', 'unknown')}",
    },
  ]


def build_source_mismatches(
  discovered: dict[str, dict[str, Any]],
  pages: list[dict[str, Any]],
  workbook: WorkbookInfo,
  repo_signals: dict[str, Any],
) -> list[dict[str, Any]]:
  mismatches: list[dict[str, Any]] = []
  excluded_prefixes = set(repo_signals.get("governanceScriptExcludes", []))
  if {"blog/posts/", "podcast/episodes/"} & excluded_prefixes:
    mismatches.append({
      "id": "SRC-001",
      "severity": "Critical",
      "sources": "repo release gate vs dynamic route families",
      "evidence": f"scripts/check_ungoverned_routes.py excludes {', '.join(sorted(excluded_prefixes))}.",
      "impact": "Canonical blog and podcast routes can drift outside workbook, sitemap, repo, and audit control.",
      "fix": "Replace blanket dynamic exclusions with a generated route manifest consumed by CI, sitemap and audit coverage.",
    })
  if repo_signals.get("duplicatePodcastPageUrls"):
    duplicate = repo_signals["duplicatePodcastPageUrls"][0]
    mismatches.append({
      "id": "SRC-002",
      "severity": "Critical",
      "sources": "data/podcast-episodes.json vs canonical episode URL ledger",
      "evidence": f"{duplicate.get('count')} podcast records share {duplicate.get('pageUrl')}.",
      "impact": "Multiple episodes collapse into one canonical route, making episode-level coverage and sitemap evidence unreliable.",
      "fix": "Generate unique episode slugs by title plus session_id/date when a slug repeats.",
    })
  if repo_signals.get("transcriptSitemapMissingCount", 0):
    mismatches.append({
      "id": "SRC-003",
      "severity": "High",
      "sources": "data/podcast-episodes.json vs sitemap.xml",
      "evidence": f"{repo_signals.get('transcriptSitemapMissingCount')} transcript URLs from the podcast manifest are absent from sitemap.xml.",
      "impact": "Transcript leaves hold citation-ready text but are not exposed in the crawler-facing ledger.",
      "fix": "Generate transcript sitemap entries from data/podcast-episodes.json with lastmod from episode date.",
    })
  if repo_signals.get("llmsScope") == "ebook-only":
    mismatches.append({
      "id": "SRC-004",
      "severity": "High",
      "sources": "llms.txt / llm-index.json vs full estate",
      "evidence": "llms.txt is detected as ebook-only and does not expose blog, podcast or transcript entities.",
      "impact": "The strongest editorial and transcript assets are missing from machine-readable discovery surfaces.",
      "fix": "Expand llms.txt and llm-index.json to include topics, glossary, blog, podcast, transcripts and entity pages.",
    })

  workbook_only = [entry for entry in discovered.values() if "workbook" in entry.get("sources", set()) and "repo" not in entry.get("sources", set())]
  repo_only = [entry for entry in discovered.values() if "repo" in entry.get("sources", set()) and "workbook" not in entry.get("sources", set())]
  if workbook_only:
    mismatches.append({
      "id": "SRC-005",
      "severity": "High",
      "sources": "workbook vs repository routes",
      "evidence": f"{len(workbook_only)} workbook-only URLs remain, including {', '.join(item.get('path', '') for item in workbook_only[:5])}.",
      "impact": "The governance workbook and repo snapshot disagree about what the estate contains.",
      "fix": "Restore intended workbook-only URLs or retire them from the workbook with evidence.",
    })
  if repo_only:
    mismatches.append({
      "id": "SRC-006",
      "severity": "Medium",
      "sources": "repository routes vs workbook",
      "evidence": f"{len(repo_only)} repo-only URLs remain, including {', '.join(item.get('path', '') for item in repo_only[:5])}.",
      "impact": "Repo routes absent from workbook weaken release-grade URL governance.",
      "fix": "Add intended repo routes to workbook Pages or generated dynamic inventory.",
    })
  return mismatches


def build_template_diagnostics(template_annex: list[dict[str, Any]], family_diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
  by_type = {row["pageType"]: row for row in family_diagnostics}
  rows: list[dict[str, Any]] = []
  for item in template_annex:
    diag = by_type.get(item["pageType"], {})
    rows.append({
      "sourceFile": item.get("sourceFile", ""),
      "area": item.get("pageType", ""),
      "pagesAffected": item.get("pagesAffected", 0),
      "observedLogic": clean_template_observed_logic(
        item.get("pageType", ""),
        "; ".join(diag.get("observedTemplateEvidence", [])) or "; ".join(item.get("repeatedDefects", [])),
        int(diag.get("analysedUrls", 0) or item.get("pagesAffected", 0) or 0),
      ),
      "metadataLogic": f"missing meta: {diag.get('missingMetaCount', 0)}; missing canonical: {diag.get('missingCanonicalCount', 0)}",
      "schemaLogic": f"schema types observed: {', '.join(sorted(diag.get('schemaTypesObserved', {}).keys())) or 'none detected'}",
      "answerPatternGap": f"no question headings: {diag.get('noQuestionHeadingCount', 0)}; weak openings: {diag.get('weakOpeningCount', 0)}",
      "generativeSearchGap": f"raw transcript walls: {diag.get('rawTranscriptWallCount', 0)}; topic/book links: {diag.get('topicOrBookLinkCount', 0)}",
      "fixPriority": item.get("fixPriority", "Medium"),
      "sampleUrls": diag.get("sampleUrls", []),
    })
  return rows


def derive_route_family(url: str) -> str:
  path = normalise_route(urlparse(url).path)
  if path.startswith("/blog/posts/"):
    return "/blog/posts"
  if path.startswith("/blog"):
    return "/blog"
  if path.startswith("/podcast/episodes/") or re.match(r"^/podcast/TT-\d{4}-\d{2}-\d{2}$", path):
    return "/podcast/episodes"
  if path.startswith("/podcast"):
    return "/podcast"
  if path.startswith("/ebooks/") and path.endswith("/buy-now"):
    return "/ebooks/buy-now"
  if path.startswith("/ebooks/"):
    return "/ebooks/detail"
  if path.startswith("/ebooks"):
    return "/ebooks"
  if path.startswith("/catalogue/"):
    return "/catalogue/category"
  if path.startswith("/topics/"):
    return "/topics/detail"
  if path.startswith("/topics"):
    return "/topics"
  if path.startswith("/newsletter"):
    return "/newsletter"
  if path.startswith("/contact"):
    return "/contact"
  return path if path.count("/") <= 2 else "/" + path.strip("/").split("/")[0]


def _strip_xml_namespace(tag: str) -> str:
  return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[str]]:
  sitemap_links: list[str] = []
  url_links: list[str] = []
  if not xml_text or not xml_text.strip():
    return sitemap_links, url_links
  try:
    root = ET.fromstring(xml_text)
  except ET.ParseError:
    return sitemap_links, url_links

  for elem in root.iter():
    tag = _strip_xml_namespace(elem.tag)
    if tag not in {"sitemap", "url"}:
      continue
    for child in elem:
      if _strip_xml_namespace(child.tag) == "loc" and child.text:
        value = child.text.strip()
        if not value:
          continue
        if tag == "sitemap":
          sitemap_links.append(value)
        else:
          url_links.append(value)
  return sitemap_links, url_links


def fetch_live_sitemap_urls(base_url: str) -> list[str]:
  discovered: list[str] = []
  queue = deque([urljoin(base_url.rstrip("/") + "/", "sitemap.xml")])
  seen = set()
  while queue:
    sitemap_url = queue.popleft()
    if sitemap_url in seen:
      continue
    seen.add(sitemap_url)
    fetched = fetch_html(sitemap_url, timeout=15.0, extra_headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8"})
    if fetched.get("status") != 200 or not fetched.get("text"):
      continue
    child_sitemaps, urls = parse_sitemap_xml(fetched["text"])
    for child in child_sitemaps:
      if child not in seen:
        queue.append(child)
    discovered.extend(urls)
  return discovered


def local_sitemap_urls(repo_root: Path, base_url: str) -> list[str]:
  urls: list[str] = []
  for filename in ("sitemap.xml", "site-map.xml"):
    path = repo_root / filename
    if not path.exists():
      continue
    child_sitemaps, discovered = parse_sitemap_xml(path.read_text(encoding="utf-8"))
    urls.extend(discovered)
    for child in child_sitemaps:
      child_path = repo_root / Path(urlparse(child).path.lstrip("/"))
      if child_path.exists():
        _, nested = parse_sitemap_xml(child_path.read_text(encoding="utf-8"))
        urls.extend(nested)
  return urls


def blog_manifest_urls(repo_root: Path, base_url: str) -> list[str]:
  urls: list[str] = []
  posts_json = repo_root / "blog" / "posts.json"
  if posts_json.exists():
    data = json.loads(posts_json.read_text(encoding="utf-8"))
    items = data.get("items") or data.get("posts") or []
    for item in items:
      value = item.get("url") or item.get("canonical_url") or item.get("path")
      if value:
        urls.append(normalise_absolute_url(value, base_url))
  return urls


def podcast_manifest_urls(repo_root: Path, base_url: str) -> list[str]:
  urls: list[str] = []
  manifest = repo_root / "data" / "podcast-episodes.json"
  if not manifest.exists():
    return urls
  data = json.loads(manifest.read_text(encoding="utf-8"))
  items = data if isinstance(data, list) else data.get("items") or data.get("episodes") or []
  for item in items:
    page_url = item.get("page_url")
    if not page_url and item.get("slug"):
      page_url = f"/podcast/episodes/{item['slug']}/"
    if page_url:
      urls.append(normalise_absolute_url(page_url, base_url))
    transcript_url = item.get("transcript_url")
    if transcript_url and is_in_scope_url(transcript_url, base_url):
      urls.append(normalise_absolute_url(transcript_url, base_url))
  return urls


def discover_feed_candidates(repo_root: Path) -> list[str]:
  candidates = {DEFAULT_PODCAST_FEED}
  podcast_index = repo_root / "podcast" / "index.html"
  if podcast_index.exists():
    soup = BeautifulSoup(podcast_index.read_text(encoding="utf-8"), "html.parser")
    for anchor in soup.select("a[href]"):
      href = anchor.get("href", "")
      if href.endswith(".xml"):
        candidates.add(href.strip())
  return sorted(candidates)


def feed_candidate_to_site_url(candidate: str, feed_url: str, base_url: str) -> str | None:
  raw = (candidate or "").strip()
  if not raw:
    return None

  # RSS GUIDs are often plain IDs, not URLs. Accept only URL-like values or the
  # podcast date slugs that the estate intentionally supports as compatibility routes.
  date_slug_match = re.match(r"^/?TT-\d{4}-\d{2}-\d{2}/?$", raw)
  if date_slug_match:
    date_slug = raw.strip("/")
    return normalise_absolute_url(f"/podcast/{date_slug}", base_url)

  if not raw.startswith(("http://", "https://", "/")):
    return None

  absolute = urljoin(feed_url, raw) if raw.startswith("/") else raw
  parsed = urlparse(absolute)
  path = normalise_route(parsed.path or "/")

  # Some older podcast feed entries exposed root-level /TT-YYYY-MM-DD links.
  # Those are feed artefacts, not live page URLs. Audit the governed podcast
  # compatibility route instead of generating false root-level 404s.
  if re.match(r"^/TT-\d{4}-\d{2}-\d{2}$", path):
    return normalise_absolute_url(f"/podcast{path}", base_url)

  if not is_in_scope_url(absolute, base_url):
    return None
  return normalise_absolute_url(absolute, base_url)


def parse_feed_urls(feed_url: str, base_url: str) -> list[str]:
  fetched = fetch_html(feed_url, timeout=20.0, extra_headers={"Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"})
  if fetched.get("status") != 200 or not fetched.get("text"):
    return []

  try:
    root = ET.fromstring(fetched["text"])
  except ET.ParseError:
    return []

  urls: list[str] = []
  for item in root.iter():
    if _strip_xml_namespace(item.tag) != "item":
      continue

    candidates: list[str] = []
    for child in item:
      child_tag = _strip_xml_namespace(child.tag).lower()
      child_text = (child.text or "").strip()
      if child_tag in {"link", "guid"} and child_text:
        candidates.append(child_text)
      if "transcript" in child_tag:
        href = child.attrib.get("url") or child.attrib.get("href") or child_text
        if href:
          candidates.append(href.strip())

    for candidate in candidates:
      site_url = feed_candidate_to_site_url(candidate, feed_url, base_url)
      if site_url:
        urls.append(site_url)
  return sorted(set(urls))

def extract_internal_links(url: str, soup: BeautifulSoup, base_url: str) -> list[str]:
  discovered: list[str] = []
  for tag in soup.select("a[href], link[rel='canonical'][href]"):
    href = tag.get("href", "").strip()
    cleaned = clean_link_candidate(href, url, base_url)
    if cleaned:
      discovered.append(cleaned)
  return discovered


def add_discovered(discovered: dict[str, dict[str, Any]], url: str, source: str, base_url: str, **metadata: Any) -> str:
  normalised = normalise_discovery_url(url, base_url)
  entry = discovered.setdefault(
    normalised,
    {
      "url": normalised,
      "host": urlparse(normalised).hostname or "",
      "path": normalise_route(urlparse(normalised).path),
      "sources": set(),
      "sourceDetails": [],
      "repoRelativePath": metadata.get("repoRelativePath") or "",
      "workbookRelativePath": metadata.get("workbookRelativePath") or "",
      "workbookTitle": metadata.get("workbookTitle") or "",
    },
  )
  entry["sources"].add(source)
  if metadata.get("detail"):
    entry["sourceDetails"].append(metadata["detail"])
  if metadata.get("repoRelativePath") and not entry.get("repoRelativePath"):
    entry["repoRelativePath"] = metadata["repoRelativePath"]
  if metadata.get("workbookRelativePath") and not entry.get("workbookRelativePath"):
    entry["workbookRelativePath"] = metadata["workbookRelativePath"]
  if metadata.get("workbookTitle") and not entry.get("workbookTitle"):
    entry["workbookTitle"] = metadata["workbookTitle"]
  return normalised


def build_complete_inventory(base_url: str, excludes: list[str]) -> tuple[WorkbookInfo, dict[str, dict[str, Any]], dict[str, Any]]:
  workbook = load_workbook_info(find_workbook(REPO_ROOT))
  if workbook.url_count <= 0:
    raise RuntimeError(
      f"Workbook {Path(workbook.path).name} produced 0 URL rows from sheet {workbook.primary_sheet or '(missing)'}; halting audit."
    )

  discovered: dict[str, dict[str, Any]] = {}
  source_counts: Counter[str] = Counter()

  for route in repo_html_routes(REPO_ROOT, excludes):
    if should_exclude(route, excludes):
      continue
    normalised = add_discovered(discovered, route_to_url(base_url, route), "repo", base_url, repoRelativePath=route)
    source_counts["repo"] += 1

  for row in workbook.rows:
    raw = row.get("full_url") or row.get("public_url_path") or row.get("relative_file_path")
    if not raw:
      continue
    if row.get("public_url_path") and should_exclude(row["public_url_path"], excludes):
      continue
    url = row.get("full_url") or row.get("public_url_path") or row.get("relative_file_path")
    normalised = add_discovered(
      discovered,
      url,
      "workbook",
      base_url,
      workbookRelativePath=row.get("relative_file_path", ""),
      workbookTitle=row.get("page_title", ""),
    )
    source_counts["workbook"] += 1

  for url in local_sitemap_urls(REPO_ROOT, base_url) + fetch_live_sitemap_urls(base_url):
    if is_in_scope_url(url, base_url) and not should_exclude(urlparse(normalise_absolute_url(url, base_url)).path, excludes):
      add_discovered(discovered, url, "sitemap", base_url)
      source_counts["sitemap"] += 1

  for url in blog_manifest_urls(REPO_ROOT, base_url):
    if not should_exclude(urlparse(url).path, excludes):
      add_discovered(discovered, url, "blog-manifest", base_url)
      source_counts["blog-manifest"] += 1

  for url in podcast_manifest_urls(REPO_ROOT, base_url):
    if not should_exclude(urlparse(url).path, excludes):
      add_discovered(discovered, url, "podcast-manifest", base_url)
      source_counts["podcast-manifest"] += 1

  for feed_url in discover_feed_candidates(REPO_ROOT):
    for url in parse_feed_urls(feed_url, base_url):
      if not should_exclude(urlparse(url).path, excludes):
        add_discovered(discovered, url, "feed", base_url, detail=feed_url)
        source_counts["feed"] += 1

  return workbook, discovered, {"sourceCounts": dict(source_counts)}


def score_page(page: dict[str, Any]) -> dict[str, int]:
  meta = page["meta"]
  soup = page["soup"]
  intro = page["introText"]
  internal_links = page["internalLinkCount"]
  question_headings = page["questionHeadings"]
  body_text = page["visibleText"]
  paragraph_count = page["paragraphCount"]
  list_count = page["listCount"]
  table_count = page["tableCount"]
  has_faq_schema = page["hasFaqSchema"]
  has_author_signal = "Jonathan Harris" in body_text or "Jonathan Harris" in meta.get("title", "")

  technical = 0
  if page["status"] == 200:
    technical += 5
  if meta["title"]:
    technical += 4
  if 35 <= len(meta["title"]) <= 72:
    technical += 2
  if meta["metaDescription"]:
    technical += 3
  if meta["canonical"]:
    technical += 3
  if meta["h1"]:
    technical += 2
  if meta["viewport"]:
    technical += 1
  technical = min(20, technical)

  on_page = 0
  if intro and 35 <= len(intro.split()) <= 140:
    on_page += 5
  if meta["h1"] and meta["title"]:
    on_page += 3
  if paragraph_count >= 3:
    on_page += 3
  if page["wordCount"] >= 220:
    on_page += 4
  on_page = min(15, on_page)

  aeo = 0
  if intro and len(intro.split()) <= 90:
    aeo += 6
  if question_headings:
    aeo += 5
  if list_count:
    aeo += 3
  if table_count:
    aeo += 2
  if has_faq_schema:
    aeo += 4
  aeo = min(20, aeo)

  geo = 0
  if has_author_signal:
    geo += 5
  if intro and len(intro.split()) >= 45:
    geo += 4
  if meta["schemaCount"]:
    geo += 4
  if internal_links >= 4:
    geo += 4
  if page["wordCount"] >= 250:
    geo += 3
  geo = min(20, geo)

  entity = 0
  if has_author_signal:
    entity += 6
  if meta["schemaCount"]:
    entity += 2
  if page["pageType"] in {"author / about", "podcast hub", "book page", "book hub"}:
    entity += 2
  entity = min(10, entity)

  linking = min(10, internal_links)

  conversion = 0
  if page["pageType"] in {"lead generation", "comparison", "book hub", "book page", "service / product"}:
    conversion += 3
  if page["ctaCount"]:
    conversion += 2
  conversion = min(5, conversion)

  return {
    "technicalSeo": technical,
    "onPageIntent": on_page,
    "aeo": aeo,
    "geo": geo,
    "entity": entity,
    "internalLinking": linking,
    "conversion": conversion,
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


def compliance_label(avg_score: float) -> str:
  if avg_score >= 85:
    return "Strong"
  if avg_score >= 70:
    return "Partial"
  return "Weak"


def make_unanalysed_page(
  entry: dict[str, Any],
  base_url: str,
  fetched: dict[str, Any],
  coverage_state: str,
  reason: str,
) -> dict[str, Any]:
  url = entry["url"]
  page_type = classify_page(url)
  final_url = fetched.get("url", url)
  status = fetched.get("status", 0)
  return {
    **entry,
    "status": status,
    "finalUrl": final_url,
    "redirectChain": fetched.get("history", []),
    "fetchError": fetched.get("error", ""),
    "exclusionReason": reason,
    "meta": {"title": "", "canonical": "", "metaDescription": "", "viewport": "", "h1": "", "og": {}, "schemaCount": 0},
    "canonicalNormalised": "",
    "wordCount": 0,
    "visibleText": "",
    "introText": "",
    "paragraphCount": 0,
    "listCount": 0,
    "tableCount": 0,
    "questionHeadings": [],
    "internalLinkCount": 0,
    "internalLinks": [],
    "hasFaqSchema": False,
    "indexability": "excluded" if is_excluded_state(coverage_state) else "not verified",
    "ctaCount": 0,
    "pageType": page_type,
    "coverageState": coverage_state,
    "soup": None,
    "scores": {"technicalSeo": 0, "onPageIntent": 0, "aeo": 0, "geo": 0, "entity": 0, "internalLinking": 0, "conversion": 0},
    "total": 0,
    "grade": "F",
    "riskFlag": "high" if coverage_state == "Failed to fetch" else "low",
  }


def inspect_url(entry: dict[str, Any], base_url: str) -> dict[str, Any]:
  url = entry["url"]
  fetched = fetch_html(url)
  final_url = fetched.get("url", url)
  final_host = (urlparse(final_url).hostname or "").lower()
  final_norm = normalise_absolute_url(final_url, base_url) if final_host else url
  current_norm = normalise_absolute_url(url, base_url)
  history = fetched.get("history", []) or []

  # External buy-now and platform redirects are intentional conversion/support paths.
  # They must be inventoried, but they are not first-party HTML pages to score.
  if final_host and final_host != base_host(base_url):
    return make_unanalysed_page(
      entry,
      base_url,
      fetched,
      "Excluded as redirected to external destination",
      f"Final URL leaves audited host: {final_url}",
    )

  # Same-host redirect aliases are covered as redirect/canonical evidence; the final
  # destination is queued separately by crawl_and_analyse for page-level analysis.
  if history and final_norm != current_norm:
    return make_unanalysed_page(
      entry,
      base_url,
      fetched,
      "Excluded as redirected/canonicalised",
      f"Redirects to canonical in-scope URL: {final_norm}",
    )

  challenge_reason = detect_challenge_page(fetched.get("status", 0), fetched.get("text", ""))
  if challenge_reason:
    raise RuntimeError(f"Live audit blocked on {url}: {challenge_reason}")

  if fetched.get("status", 0) != 200:
    return make_unanalysed_page(
      entry,
      base_url,
      fetched,
      "Failed to fetch",
      fetched.get("error") or f"HTTP {fetched.get('status', 0)} after live fetch retry",
    )

  soup = parse_html(fetched.get("text", ""))
  meta = extract_meta(soup)
  body_text = soup.get_text(" ", strip=True)
  main_node = soup.select_one("main") or soup.body or soup
  intro_text = " ".join(p.get_text(" ", strip=True) for p in main_node.select("p")[:3]).strip()
  question_headings = [h.get_text(" ", strip=True) for h in main_node.select("h2, h3") if "?" in h.get_text(" ", strip=True)]
  robots_tag = soup.select_one("meta[name='robots']")
  robots_content = robots_tag.get("content", "").lower() if robots_tag else ""
  canonical_target = meta["canonical"]
  canonical_normalised = normalise_absolute_url(canonical_target, base_url, context_url=url) if canonical_target else ""
  links = extract_internal_links(url, soup, base_url)
  cta_candidates = [
    a for a in soup.select("a[href]")
    if any(token in (a.get_text(" ", strip=True).lower() + " " + a.get("href", "").lower()) for token in ("contact", "newsletter", "amazon", "buy", "subscribe", "listen"))
  ]
  page_type = classify_page(url)
  page = {
    **entry,
    "status": fetched.get("status", 0),
    "finalUrl": final_url,
    "redirectChain": history,
    "fetchError": fetched.get("error", ""),
    "exclusionReason": "",
    "meta": meta,
    "canonicalNormalised": canonical_normalised,
    "wordCount": len(body_text.split()),
    "visibleText": body_text,
    "introText": intro_text,
    "paragraphCount": len(main_node.select("p")),
    "listCount": len(main_node.select("ul, ol")),
    "tableCount": len(main_node.select("table")),
    "questionHeadings": question_headings,
    "internalLinkCount": len([link for link in links if is_in_scope_url(link, base_url)]),
    "internalLinks": sorted(set(links))[:25],
    "hasFaqSchema": any("FAQPage" in script.get_text() for script in soup.select("script[type='application/ld+json']")),
    "indexability": "noindex" if "noindex" in robots_content else "indexable",
    "ctaCount": len(cta_candidates),
    "pageType": page_type,
    "coverageState": coverage_state_for_page(page_type, fetched.get("status", 0)),
    "soup": soup,
  }
  page["scores"] = score_page(page)
  page["total"] = total_score(page["scores"])
  page["grade"] = grade(page["total"])
  page["riskFlag"] = "high" if page["total"] < 70 else ("medium" if page["total"] < 80 else "low")
  return page

def crawl_and_analyse(base_url: str, discovered: dict[str, dict[str, Any]], excludes: list[str]) -> list[dict[str, Any]]:
  queue = deque(sorted(discovered.keys()))
  processed: dict[str, dict[str, Any]] = {}

  while queue:
    url = queue.popleft()
    if url in processed:
      continue
    path = normalise_route(urlparse(url).path)
    if should_exclude(path, excludes):
      continue
    entry = discovered[url]
    page = inspect_url(entry, base_url)
    processed[url] = page

    final_url = page.get("finalUrl") or ""
    if page["coverageState"] == "Excluded as redirected/canonicalised" and final_url and is_in_scope_url(final_url, base_url):
      final_norm = normalise_absolute_url(final_url, base_url)
      final_path = normalise_route(urlparse(final_norm).path)
      if not should_exclude(final_path, excludes) and final_norm not in processed:
        if final_norm not in discovered:
          add_discovered(discovered, final_norm, "redirect-target", base_url, detail=f"redirect target from {url}")
        queue.append(final_norm)

    if not is_analysed_state(page["coverageState"]):
      continue

    for linked_url in page["internalLinks"]:
      linked_path = normalise_route(urlparse(linked_url).path)
      if should_exclude(linked_path, excludes):
        continue
      if linked_url not in discovered:
        add_discovered(discovered, linked_url, "live-link", base_url)
        queue.append(linked_url)
  return [processed[url] for url in sorted(processed.keys())]

def issue_record(issue_id: str, severity: str, confidence: str, lens: str, root_cause: str, affected: str, evidence: str, why: str, remediation: str, effort: str = "Low", owner: str = "Engineering") -> dict[str, Any]:
  return {
    "issueId": issue_id,
    "severity": severity,
    "confidence": confidence,
    "auditLens": lens,
    "rootCauseLevel": root_cause,
    "affected": affected,
    "affectedPagesTemplatesFilesOrRoutes": affected,
    "evidenceObserved": evidence,
    "whyItMatters": why,
    "exactRemediation": remediation,
    "expectedGain": "Stronger crawl, answer extraction, and generative retrieval quality",
    "estimatedEffort": effort,
    "recommendedOwner": owner,
    "verificationMethod": "Rerun the SEO + AEO + GEO audit and confirm the affected URL, template, or route returns the expected evidence state in coverage.json and report.html.",
  }


def collect_issues(
  pages: list[dict[str, Any]],
  discovered: dict[str, dict[str, Any]],
  repo_signals: dict[str, Any] | None = None,
  family_diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
  """Create a forensic issue ledger from source conflicts and page-family evidence.

  The old implementation elevated the same generic AEO recommendation for almost
  every family. This version promotes root-cause issues first, then adds only
  grounded family issues where the supplied evidence identifies the broken source.
  """
  repo_signals = repo_signals or {}
  family_diagnostics = family_diagnostics or []
  diag_by_type = {row.get("pageType"): row for row in family_diagnostics}
  issues: list[dict[str, Any]] = []

  def add(issue: dict[str, Any]) -> None:
    if issue["issueId"] not in {existing["issueId"] for existing in issues}:
      issues.append(issue)

  failed_pages = [page for page in pages if page.get("coverageState") == "Failed to fetch"]
  if failed_pages:
    add(issue_record(
      "JH-TECH-000",
      "Critical",
      "Confirmed",
      "Technical / Crawl / Coverage",
      "route / fetch",
      ", ".join(page["url"] for page in failed_pages[:8]),
      f"{len(failed_pages)} in-scope URLs failed to fetch during the audit crawl.",
      "Failed in-scope URLs prevent full-estate verification and create crawl reliability risk.",
      "Restore the failing routes or mark them as explicit redirects/canonicalised exclusions with evidence before rerunning the audit.",
      "Medium",
      "Engineering / SEO",
    ))

  excluded_prefixes = set(repo_signals.get("governanceScriptExcludes", []))
  dynamic_exclusions = sorted(excluded_prefixes & {"blog/posts/", "podcast/episodes/"})
  if dynamic_exclusions:
    add(issue_record(
      "JH-TECH-001",
      "Critical",
      "Confirmed",
      "Technical / Governance / SEO",
      "system / release gate",
      "scripts/check_ungoverned_routes.py; blog/posts/; podcast/episodes/; workbook Pages sheet",
      f"EXCLUDED_ROUTE_PREFIXES contains {', '.join(dynamic_exclusions)}.",
      "High-value dynamic blog and podcast routes can exist live without workbook, sitemap, repo, or audit parity.",
      "Remove canonical dynamic route families from EXCLUDED_ROUTE_PREFIXES and replace the blanket exclusions with a generated route manifest consumed by sitemap, workbook/governance checks, and audit coverage. Keep only compatibility redirect pages such as podcast/TT-* exempted.",
      "Medium",
      "Engineering / SEO",
    ))

  duplicate_urls = repo_signals.get("duplicatePodcastPageUrls") or []
  if duplicate_urls:
    duplicate = duplicate_urls[0]
    add(issue_record(
      "JH-TECH-002",
      "Critical",
      "Confirmed",
      "Technical / Canonical / SEO",
      "data / generator",
      "data/podcast-episodes.json; scripts/generate_podcast_episodes.py; sitemap.xml; podcast episode canonicals",
      f"{duplicate.get('count')} podcast episode records share the same page_url: {duplicate.get('pageUrl')}.",
      "Multiple different episodes collapse into one URL, destroying episode-level canonical integrity and making sitemap coverage misleading.",
      "Make podcast slugs unique by appending session_id or ISO date when a title slug repeats. Regenerate episode pages, update data/podcast-episodes.json, update sitemap/workbook or dynamic inventory, and add controlled redirects only where a single legacy canonical is deliberately chosen.",
      "Medium",
      "Engineering",
    ))

  missing_transcripts = repo_signals.get("transcriptSitemapMissingCount", 0)
  if missing_transcripts:
    sample = repo_signals.get("transcriptSitemapMissingSample", [])
    sample_paths = [item.get("path") or item.get("url") for item in sample[:6] if isinstance(item, dict)]
    add(issue_record(
      "JH-SEO-001",
      "High",
      "Confirmed",
      "SEO / AEO / GEO",
      "sitemap / inventory",
      "sitemap.xml; transcript archive; transcript leaf pages under /transcripts/TT-*.html",
      f"{missing_transcripts} transcript URLs from data/podcast-episodes.json are absent from sitemap.xml. Sample: {', '.join(sample_paths)}.",
      "Transcript leaves contain citation-ready podcast text, but crawlers and LLM retrieval systems are not being given the full URL ledger.",
      "Generate transcript sitemap entries from data/podcast-episodes.json and podcast RSS transcript tags. Include lastmod from episode date and add transcript URLs to workbook Pages or a generated dynamic route inventory verified in CI.",
      "Low / Medium",
      "SEO / Engineering",
    ))

  if repo_signals.get("llmsScope") == "ebook-only":
    add(issue_record(
      "JH-GEO-001",
      "High",
      "Confirmed",
      "GEO / Entity / Retrieval",
      "llms discovery asset",
      "llms.txt; llm-index.json",
      "llms.txt is detected as ebook-only and llm-index.json does not expose blog, podcast, transcript, glossary, or full topic-guide entities.",
      "The site hides its best retrieval assets from LLM-friendly discovery files, weakening generative search visibility outside the ebook catalogue.",
      "Expand llms.txt and llm-index.json to include homepage, bio, topic guides, glossary, comparison, blog hub, latest weekly posts, podcast hub, recent episode pages, transcript archive, and transcript leaves with short descriptions and entity relationships.",
      "Low / Medium",
      "GEO / Engineering",
    ))

  podcast_diag = diag_by_type.get("podcast episode") or {}
  if podcast_diag and (podcast_diag.get("takeawayBlockCount", 0) < max(1, podcast_diag.get("analysedUrls", 0) // 2) or podcast_diag.get("topicOrBookLinkCount", 0) < max(1, podcast_diag.get("analysedUrls", 0) // 2)):
    add(issue_record(
      "JH-AEO-001",
      "High",
      "Confirmed",
      "AEO / Content / Podcast",
      "template / content",
      podcast_diag.get("sourceFile", "live podcast episode routes"),
      f"Podcast episode family evidence: {', '.join(podcast_diag.get('observedTemplateEvidence', []))}",
      "Episode pages cannot win direct-answer or generative citation surfaces if they remain thin wrappers around audio and a transcript link.",
      "Update the episode template to render a 60-word answer-first summary, 3-5 key takeaways, discussed entities/topics, transcript preview anchors, related topic guides/books, PodcastEpisode JSON-LD, FAQPage JSON-LD, and canonical transcript relationship.",
      "Medium",
      "Content / Engineering",
    ))

  transcript_diag = diag_by_type.get("podcast transcript") or {}
  if transcript_diag and transcript_diag.get("analysedUrls", 0):
    analysed_transcripts = transcript_diag.get("analysedUrls", 0)
    add(issue_record(
      "JH-AEO-002",
      "High",
      "Confirmed",
      "AEO / GEO / Transcript",
      "template / content structure",
      transcript_diag.get("sourceFile", "live transcript routes"),
      f"{analysed_transcripts}/{analysed_transcripts} transcript page(s) lack verified above-the-fold summary, key-takeaway, topic-index, timestamp/section-anchor, or entity-index evidence before the transcript body.",
      "Long transcript pages without summary-led chunking are harder for answer engines and LLM retrievers to cite accurately.",
      "Before the transcript body, render episode summary, what changed this week, key named entities, five bullet takeaways, topic index, timestamped or sectioned anchors, related books/topics, and Transcript/PodcastEpisode schema alignment.",
      "Medium",
      "Editorial / Engineering",
    ))

  blog_diag = diag_by_type.get("blog article") or {}
  if blog_diag and blog_diag.get("repeatedOpeningCount", 0):
    add(issue_record(
      "JH-AEO-003",
      "High",
      "Confirmed",
      "AEO / Blog / Content",
      "template / R2 HTML",
      blog_diag.get("sourceFile", "blog post template"),
      f"{blog_diag.get('repeatedOpeningCount')} analysed blog article pages repeat an opening paragraph or standfirst near the top.",
      "Repeated standfirst text wastes the first screen, looks automated, and weakens answer extraction clarity.",
      "Render the standfirst once after the H1. Remove duplicate summary echoes in hero/article body hydration and use a distinct TL;DR bullet block only when needed.",
      "Low",
      "Frontend / Editorial",
    ))

  ebook_trim = repo_signals.get("ebookPipelineTrimLimit")
  if ebook_trim and ebook_trim <= 80:
    add(issue_record(
      "JH-SEO-004",
      "Medium",
      "Confirmed",
      "SEO / AEO / Template",
      "template / copy generation",
      "scripts/ebook_pipeline.py; all ebook detail pages",
      f"scripts/ebook_pipeline.py contains a hard heading trim of {ebook_trim} characters.",
      "Hard-trimmed headings can cut meaning mid-phrase and weaken answer-style headings on otherwise strong ebook pages.",
      "Remove the hard character slice. Use semantic heading source fields or a word-safe shorten utility that preserves whole words and only shortens above 96-110 characters. Let CSS handle wrapping.",
      "Low",
      "Engineering / Content",
    ))

  workbook_only = [entry for entry in discovered.values() if "workbook" in entry.get("sources", set()) and "repo" not in entry.get("sources", set())]
  repo_only = [entry for entry in discovered.values() if "repo" in entry.get("sources", set()) and "workbook" not in entry.get("sources", set()) and classify_page(entry["url"]) != "podcast episode"]
  if workbook_only and not any(item["issueId"] == "JH-SEO-002" for item in issues):
    add(issue_record(
      "JH-SEO-002",
      "High",
      "Confirmed",
      "SEO / Source reconciliation",
      "workbook mismatch",
      ", ".join(item.get("path", "") for item in workbook_only[:8]),
      f"{len(workbook_only)} workbook-only URLs remain outside confirmed repo route evidence.",
      "Workbook-governed routes missing from the repo weaken source-of-truth integrity and release confidence.",
      "Restore the intended URLs, retire stale workbook rows, or move dynamic families into the generated route manifest used by sitemap and audit coverage.",
      "Low / Medium",
      "SEO / Engineering",
    ))
  if repo_only:
    add(issue_record(
      "JH-TECH-003",
      "Medium",
      "Confirmed",
      "Technical / Governance",
      "workbook mismatch",
      ", ".join(item.get("path", "") for item in repo_only[:8]),
      f"{len(repo_only)} repo routes are absent from workbook Pages evidence.",
      "Repo routes absent from the workbook dilute governance and estate reconciliation quality.",
      "Add intended repo routes to workbook Pages or the generated dynamic inventory; explicitly exclude only non-indexable utility routes with evidence.",
      "Low",
      "Engineering / SEO",
    ))

  # Add a small number of grounded metadata/canonical issues only when observed.
  issue_counter = 1
  for diag in family_diagnostics:
    page_type = diag.get("pageType", "route family")
    source = diag.get("sourceFile", representative_family_source(page_type))
    if diag.get("missingMetaCount", 0):
      add(issue_record(
        f"JH-META-{issue_counter:03d}",
        "Medium",
        "Confirmed",
        "SEO / Metadata",
        "template / page family",
        source,
        f"{diag.get('missingMetaCount')} analysed {page_type} URLs have no meta description. Sample: {', '.join(diag.get('sampleUrls', [])[:5])}.",
        "Missing descriptions reduce SERP control and weaken answer-engine page summaries.",
        f"Add unique meta descriptions in {source}, using the first-screen answer summary as source copy and keeping every description page-specific.",
        "Medium",
        "SEO / Frontend",
      ))
      issue_counter += 1
    if diag.get("missingCanonicalCount", 0):
      add(issue_record(
        f"JH-CANON-{issue_counter:03d}",
        "Medium",
        "Confirmed",
        "Technical / Canonical",
        "template / page family",
        source,
        f"{diag.get('missingCanonicalCount')} analysed {page_type} URLs have no canonical tag. Sample: {', '.join(diag.get('sampleUrls', [])[:5])}.",
        "Canonical gaps weaken route normalisation and duplicate control.",
        f"Emit absolute canonicals in {source}, matching the final intended URL after redirect/canonical policy is applied.",
        "Medium",
        "Engineering / SEO",
      ))
      issue_counter += 1

  return issues


def scored_pages_for_family(family_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [page for page in family_pages if is_analysed_state(page.get("coverageState", ""))]


def family_coverage(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  rows: list[dict[str, Any]] = []
  for family in ROUTE_FAMILY_ORDER:
    family_pages = family_map.get(family, [])
    if not family_pages:
      continue
    analysed = len([page for page in family_pages if is_analysed_state(page["coverageState"])])
    excluded = len([page for page in family_pages if is_excluded_state(page["coverageState"])])
    failed = len(family_pages) - analysed - excluded
    score_pages = scored_pages_for_family(family_pages)
    rows.append({
      "pageType": family,
      "discovered": len(family_pages),
      "analysed": analysed,
      "excluded": excluded,
      "failed": failed,
      "coveragePercent": round(((analysed + excluded) / len(family_pages)) * 100, 1) if family_pages else 0,
      "averageScore": round(mean(page["total"] for page in score_pages), 1) if score_pages else 0,
      "lowestScore": min(page["total"] for page in score_pages) if score_pages else 0,
      "highestScore": max(page["total"] for page in score_pages) if score_pages else 0,
    })
  return rows

def build_template_annex(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  rows: list[dict[str, Any]] = []
  for page_type, family_pages in sorted(family_map.items()):
    score_pages = scored_pages_for_family(family_pages)
    avg_score = round(mean(page["total"] for page in score_pages), 1) if score_pages else 0
    repeated_strengths = []
    repeated_defects = []
    checked_pages = score_pages or family_pages
    if score_pages and all(page["meta"]["canonical"] for page in score_pages):
      repeated_strengths.append("Canonical coverage is present across the analysed family pages.")
    if score_pages and all(page["meta"]["metaDescription"] for page in score_pages):
      repeated_strengths.append("Meta descriptions are present across the analysed family pages.")
    if score_pages and any(not page["questionHeadings"] for page in score_pages):
      repeated_defects.append("Question-led headings are missing on part of the analysed family.")
    if score_pages and any(len(page["introText"].split()) < 35 for page in score_pages):
      repeated_defects.append("Openings are too thin for strong answer-first extraction on some pages.")
    if not score_pages and any(is_excluded_state(page["coverageState"]) for page in checked_pages):
      repeated_strengths.append("Family was inventoried and explicitly excluded as redirect/canonical/non-page evidence where applicable.")
    display_avg = "N/A" if not score_pages and any(is_excluded_state(page["coverageState"]) for page in checked_pages) else avg_score
    rows.append({
      "pageType": page_type,
      "pagesAffected": len(family_pages),
      "sourceFile": representative_family_source(page_type),
      "averageScore": display_avg,
      "repeatedStrengths": repeated_strengths or ["No repeated strengths confirmed beyond baseline rendering and metadata."],
      "repeatedDefects": repeated_defects or ["No repeated family-level defect was strong enough to elevate into a template issue."],
      "fixPriority": "High" if avg_score and avg_score < 75 else ("Medium" if avg_score and avg_score < 85 else "Low"),
    })
  return rows

def specific_gap_matrix_top_missing(page_type: str, score_pages: list[dict[str, Any]]) -> str:
  family = str(page_type or "").lower()
  if family == "homepage":
    return "Homepage needs stronger question-led extraction for entity, books, podcast, and newsletter intents"
  if family == "author / about":
    return "Missing concise AI-author entity summary, credentials block, and podcast/book cross-links"
  if family == "service / product":
    return "Missing problem-answer structure, implementation examples, and trust proof"
  if family == "comparison":
    return "Missing direct comparison answer block and decision matrix"
  if family == "archive / pagination / utility":
    return "Missing archive purpose statement and crawlable route explanation"
  if family == "site page":
    return "Missing question-led summary and internal path to books/topics/podcast"
  if family == "category / hub" or family == "book hub" or family == "podcast hub":
    return "Hub pages need more extractable intent summaries and contextual next-step links"
  if family == "topic hub":
    return "Topic guides need more question-led headings and citation-ready answer blocks"
  if family == "book page":
    return "Question-led H2/H3 opportunities remain despite strong Book and FAQ schema"
  if family == "blog archive":
    return "Archive list freshness and crawlable article-card depth need stronger server-rendered evidence"
  if family == "blog article":
    return "Repeated standfirst and weak question-led extraction structure"
  if family == "podcast episode":
    return "Missing key takeaways, FAQPage JSON-LD, transcript preview anchors, and related topic/book CTAs"
  if family == "podcast transcript":
    return "Missing summary, entity index, timestamp/section anchors before transcript body"
  if family == "lead generation":
    return "Conversion pages need answer-led objections, trust cues, and clearer next-step copy"
  if family == "knowledge base":
    return "Glossary needs richer definitions, examples, and entity relationships"
  if sum(1 for page in score_pages if not page.get("questionHeadings")) >= max(1, len(score_pages) // 2):
    return "Missing route-family-specific question-led headings"
  return "Needs stronger route-family-specific opening summaries"


def build_gap_matrix(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  rows: list[dict[str, Any]] = []
  for page_type, family_pages in sorted(family_map.items()):
    score_pages = scored_pages_for_family(family_pages)
    if not score_pages:
      rows.append({
        "pageType": page_type,
        "seo": "Not applicable",
        "aeo": "Not applicable",
        "geo": "Not applicable",
        "confidence": "Confirmed",
        "topMissing": "Explicitly excluded redirect or non-page route",
        "businessImpact": "Medium" if page_type in IMPORTANT_PAGE_TYPES else "Low",
      })
      continue
    avg_seo = mean(page["scores"]["technicalSeo"] + page["scores"]["onPageIntent"] for page in score_pages)
    avg_aeo = mean(page["scores"]["aeo"] for page in score_pages)
    avg_geo = mean(page["scores"]["geo"] for page in score_pages)
    top_missing = specific_gap_matrix_top_missing(page_type, score_pages)
    rows.append({
      "pageType": page_type,
      "seo": compliance_label(avg_seo / 35 * 100),
      "aeo": compliance_label(avg_aeo / 20 * 100),
      "geo": compliance_label(avg_geo / 20 * 100),
      "confidence": "Confirmed",
      "topMissing": top_missing,
      "businessImpact": "High" if page_type in IMPORTANT_PAGE_TYPES else "Medium",
    })
  return rows

def build_page_type_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  findings = []
  for page_type, family_pages in sorted(family_map.items()):
    score_pages = scored_pages_for_family(family_pages)
    scores = [page["total"] for page in score_pages]
    analysed = len(score_pages)
    excluded = len([page for page in family_pages if is_excluded_state(page["coverageState"])])
    failed = len(family_pages) - analysed - excluded
    if failed:
      coverage_state = "Partial / failed"
    elif analysed and excluded:
      coverage_state = "Analysed plus explicit exclusions"
    elif analysed:
      coverage_state = "Fully analysed"
    else:
      coverage_state = "Excluded / redirected"
    display_average = round(mean(scores), 1) if scores else "N/A"
    display_lowest = min(scores) if scores else "N/A"
    display_highest = max(scores) if scores else "N/A"
    findings.append({
      "pageType": page_type,
      "count": len(family_pages),
      "averageScore": display_average,
      "lowestScore": display_lowest,
      "highestScore": display_highest,
      "exampleUrl": family_pages[0]["url"],
      "coverageState": coverage_state,
    })
  return findings

def build_priority_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  candidate_pages = [
    page for page in pages
    if (is_analysed_state(page["coverageState"]) or page["coverageState"] == "Failed to fetch")
    and not is_podcast_compatibility_redirect(page)
  ]
  family_best: dict[str, dict[str, Any]] = {}
  family_worst: dict[str, dict[str, Any]] = {}
  for page in candidate_pages:
    page_type = page["pageType"]
    if page_type not in family_best or page["total"] > family_best[page_type]["total"]:
      family_best[page_type] = page
    if page_type not in family_worst or page["total"] < family_worst[page_type]["total"]:
      family_worst[page_type] = page

  selected = {page["url"]: page for page in family_worst.values()}
  family_limits = {
    "podcast episode": 6,
    "podcast transcript": 6,
    "blog article": 4,
    "book page": 4,
    "category / hub": 3,
    "topic hub": 3,
  }
  family_counts: Counter[str] = Counter(page["pageType"] for page in selected.values())
  for page in sorted(candidate_pages, key=lambda item: (item["total"], item["pageType"], item["url"])):
    page_type = page["pageType"]
    if page_type not in IMPORTANT_PAGE_TYPES:
      continue
    limit = family_limits.get(page_type, 2)
    if page["url"] in selected or family_counts[page_type] < limit:
      if page["url"] not in selected:
        family_counts[page_type] += 1
      selected.setdefault(page["url"], page)
  return sorted(selected.values(), key=lambda page: (page["total"], page["pageType"], page["url"]))[:30]


def build_redirect_compatibility_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return sorted(
    [page for page in pages if is_podcast_compatibility_redirect(page)],
    key=lambda page: page.get("url", ""),
  )

def make_url_entry(page: dict[str, Any]) -> dict[str, Any]:
  return {
    "url": page["url"],
    "path": page["path"],
    "pageType": page["pageType"],
    "sources": sorted(page["sources"]),
    "status": page["status"],
    "finalUrl": page.get("finalUrl", page["url"]),
    "redirectChain": page.get("redirectChain", []),
    "canonical": page["canonicalNormalised"] or page["meta"]["canonical"] or "",
    "indexability": page["indexability"],
    "coverageState": page["coverageState"],
    "exclusionReason": page.get("exclusionReason", ""),
    "fetchError": page.get("fetchError", ""),
    "score": page["total"],
    "grade": page["grade"],
    "riskFlag": page["riskFlag"],
    "sources": sorted(page.get("sources", [])),
    "sourceDetails": page.get("sourceDetails", []),
    "finalUrl": page.get("finalUrl", page["url"]),
    "canonicalNormalised": page.get("canonicalNormalised", ""),
    "exclusionReason": page.get("exclusionReason", ""),
    "fetchError": page.get("fetchError", ""),
  }

def build_report_control(pages: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], artefacts: dict[str, str], analysis_state: dict[str, Any]) -> dict[str, Any]:
  analysed = len([page for page in pages if is_analysed_state(page["coverageState"])])
  failed = len([page for page in pages if page["coverageState"] == "Failed to fetch"])
  excluded = len([page for page in pages if is_excluded_state(page["coverageState"])])
  return {
    "totalDiscoveredUrls": len(pages),
    "totalAnalysedUrls": analysed,
    "totalFailedUrls": failed,
    "totalExcludedUrls": excluded,
    "coveragePercent": round(((analysed + excluded) / len(pages)) * 100, 1) if pages else 0,
    "mandatoryFamiliesIncomplete": [row["pageType"] for row in coverage_rows if row["coveragePercent"] < 100],
    "aiAnalysisStatus": analysis_state.get("statusLabel", "Unknown"),
    "auditCompletionState": analysis_state.get("completionState", "Unknown"),
    "repoSource": "jonathan-harris-website-main repository snapshot",
    "workbookSource": "jonathan-harris-site-url-inventory-remediated-release-ready.xlsm",
    "sitemapFeedSource": "sitemap.xml, local sitemap snapshot, podcast RSS feed, blog and podcast manifests, live internal links",
    "liveFetchStatus": "Live route responses fetched during workflow execution; fetch failures are recorded URL-by-URL.",
    "generatedArtefactPaths": artefacts,
  }


def build_report(base_url: str, workbook: WorkbookInfo, discovery_meta: dict[str, Any], pages: list[dict[str, Any]], issues: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], template_annex: list[dict[str, Any]], gap_matrix: list[dict[str, Any]], page_type_findings: list[dict[str, Any]], priority_pages: list[dict[str, Any]], artefacts: dict[str, str], claude_analysis: dict[str, Any] | None = None, analysis_state: dict[str, Any] | None = None, source_ledger: list[dict[str, Any]] | None = None, source_mismatches: list[dict[str, Any]] | None = None, template_diagnostics: list[dict[str, Any]] | None = None) -> str:
  analysis_state = analysis_state or {
    "available": bool(claude_analysis),
    "completionState": "Complete" if claude_analysis else "Failed-gate",
    "statusLabel": "AI forensic analysis available" if claude_analysis else "AI FORENSIC ANALYSIS UNAVAILABLE",
    "failureReason": "",
    "attempts": [],
  }
  ai_available = bool(claude_analysis)
  failed_gate = not ai_available
  source_ledger = (claude_analysis or {}).get("sourceLedger") or source_ledger or []
  source_mismatches = (claude_analysis or {}).get("sourceMismatchesThatMatter") or (claude_analysis or {}).get("sourceMismatches") or source_mismatches or []
  template_diagnostics = template_diagnostics or []
  control = build_report_control(pages, coverage_rows, artefacts, analysis_state)
  score_pages = [page for page in pages if is_analysed_state(page.get("coverageState", ""))]
  if not score_pages:
    score_pages = pages
  overall_seo = round(mean((page["scores"]["technicalSeo"] + page["scores"]["onPageIntent"]) / 35 * 100 for page in score_pages)) if score_pages else 0
  overall_aeo = round(mean(page["scores"]["aeo"] / 20 * 100 for page in score_pages)) if score_pages else 0
  overall_geo = round(mean(page["scores"]["geo"] / 20 * 100 for page in score_pages)) if score_pages else 0
  overall_entity = round(mean(page["scores"]["entity"] / 10 * 100 for page in score_pages)) if score_pages else 0
  conversion_pages = [page for page in score_pages if page["pageType"] in {"lead generation", "comparison", "book hub", "book page", "service / product"}]
  overall_conversion = round(mean((page["scores"]["conversion"] / 5 * 100) if page["scores"]["conversion"] else 100 for page in conversion_pages)) if conversion_pages else 0

  family_rows = "".join(
    f"<tr><td>{row['pageType']}</td><td>{row['discovered']}</td><td>{row['analysed']}</td><td>{row.get('excluded', 0)}</td><td>{row['failed']}</td><td>{row['coveragePercent']}%</td><td>{row['averageScore']}</td></tr>"
    for row in coverage_rows
  )
  issue_rows = "".join(
    f"<tr><td>{item['issueId']}</td><td>{item['severity']}</td><td>{item.get('confidence', '')}</td><td>{item['auditLens']}</td><td>{item.get('rootCauseLevel', '')}</td><td>{item['affected']}</td><td>{item.get('evidenceObserved', '')}</td><td>{item['whyItMatters']}</td><td>{item['exactRemediation']}</td><td>{item.get('expectedGain', '')}</td><td>{item.get('estimatedEffort', '')}</td><td>{item.get('recommendedOwner', '')}</td><td>{item.get('verificationMethod', '')}</td></tr>"
    for item in issues
  ) or "<tr><td colspan='13'>No significant issues were confirmed from the available evidence.</td></tr>"
  page_type_rows = "".join(
    f"<tr><td>{item['pageType']}</td><td>{item['count']}</td><td>{item['coverageState']}</td><td>{item['averageScore']}</td><td>{item['lowestScore']}–{item['highestScore']}</td><td><code>{item['exampleUrl']}</code></td></tr>"
    for item in page_type_findings
  )
  priority_rows = "".join(
    f"<tr><td><code>{page['url']}</code></td><td>{page['pageType']}</td><td>{page['status']}</td><td>{page['meta']['title'] or '(missing title)'}</td><td>{page['meta']['metaDescription'] and 'Present' or 'Missing'}</td><td>{page['meta']['canonical'] and 'Present' or 'Missing'}</td><td>{page['scores']['aeo']}/20</td><td>{page['scores']['geo']}/20</td><td>{page['total']}</td><td>{page['grade']}</td></tr>"
    for page in priority_pages
  )
  redirect_compatibility_pages = build_redirect_compatibility_pages(pages)
  redirect_compatibility_rows = "".join(
    f"<tr><td><code>{_esc(page['url'])}</code></td><td>{_esc(page.get('canonicalNormalised') or page['meta'].get('canonical') or '')}</td><td>{_esc(page['coverageState'])}</td><td>{_esc(page.get('exclusionReason') or 'Compatibility redirect / legacy podcast route')}</td></tr>"
    for page in redirect_compatibility_pages[:80]
  )
  template_rows = "".join(
    f"<tr><td>{row['pageType']}</td><td>{row['pagesAffected']}</td><td><code>{row['sourceFile']}</code></td><td>{row['averageScore']}</td><td>{'; '.join(row['repeatedStrengths'])}</td><td>{'; '.join(row['repeatedDefects'])}</td><td>{row['fixPriority']}</td></tr>"
    for row in template_annex
  )
  gap_rows = "".join(
    f"<tr><td>{row['pageType']}</td><td>{row['seo']}</td><td>{row['aeo']}</td><td>{row['geo']}</td><td>{row['confidence']}</td><td>{row['topMissing']}</td><td>{row['businessImpact']}</td></tr>"
    for row in gap_matrix
  )
  coverage_appendix_rows = "".join(
    f"<tr><td><code>{page['url']}</code></td><td>{page['pageType']}</td><td>{', '.join(sorted(page['sources']))}</td><td>{page['status']}</td><td>{page['canonicalNormalised'] or page['meta']['canonical'] or '—'}</td><td>{page['indexability']}</td><td>{page['coverageState']}</td><td>{page['total']} / {page['grade']}</td><td>{page['riskFlag']}</td></tr>"
    for page in pages
  )
  source_ledger_rows = "".join(
    f"<tr><td>{_esc(row.get('source', ''))}</td><td>{_esc(row.get('count', ''))}</td><td>{_esc(row.get('role', ''))}</td><td>{_esc(row.get('status') or row.get('confidence') or row.get('state') or '')}</td><td>{_esc(row.get('evidence') or row.get('notes') or row.get('detail') or '')}</td></tr>"
    for row in source_ledger
  ) or "<tr><td colspan='5'>No source ledger was supplied by the analysis context.</td></tr>"
  source_mismatch_rows = "".join(
    f"<tr><td>{_esc(row.get('id') or row.get('issueId') or row.get('mismatch') or '')}</td><td>{_esc(row.get('severity') or row.get('confidence') or '')}</td><td>{_esc(row.get('sources') or row.get('affected') or row.get('sourcePair') or '')}</td><td>{_esc(row.get('evidence') or row.get('evidenceObserved') or row.get('mismatch') or '')}</td><td>{_esc(row.get('impact') or row.get('whyItMatters') or '')}</td><td>{_esc(row.get('fix') or row.get('requiredAction') or row.get('exactRemediation') or '')}</td></tr>"
    for row in source_mismatches
  ) or "<tr><td colspan='6'>No material source mismatch was supplied by the analysis context.</td></tr>"
  template_diagnostic_rows = "".join(
    f"<tr><td><code>{_esc(row.get('sourceFile', ''))}</code></td><td>{_esc(row.get('area', ''))}</td><td>{_esc(row.get('pagesAffected', ''))}</td><td>{_esc(row.get('observedLogic', ''))}</td><td>{_esc(row.get('metadataLogic', ''))}</td><td>{_esc(row.get('schemaLogic', ''))}</td><td>{_esc(row.get('answerPatternGap', ''))}</td><td>{_esc(row.get('generativeSearchGap', ''))}</td><td>{_esc(row.get('fixPriority', ''))}</td></tr>"
    for row in template_diagnostics
  )

  # Prefer LLM-derived labels and priorities when available
  llm_summary = (claude_analysis or {}).get("executiveSummary", {})
  llm_findings = (claude_analysis or {}).get("findingsByLens", {})
  llm_issues_list = (claude_analysis or {}).get("issues", [])
  llm_impl = (claude_analysis or {}).get("implementationOrder", {})
  llm_page_types = (claude_analysis or {}).get("pageTypeFindings", [])
  llm_template_annex = (claude_analysis or {}).get("templateAnnex", [])
  llm_gap_matrix = (claude_analysis or {}).get("bestPracticeGapMatrix", [])
  llm_remediation = (claude_analysis or {}).get("codeRemediationAppendix", [])

  labels = llm_summary.get("estateLabels") or []
  if not labels:
    if overall_seo >= 85 and overall_geo >= 85:
      labels.append("citation-ready")
    if overall_aeo < 70:
      labels.append("answer-engine weak")
    if any(row['coveragePercent'] < 100 for row in coverage_rows):
      labels.append("structurally weak")
    if not labels:
      labels.append("partially ready")

  llm_top5 = llm_summary.get("topFivePriorities") or []
  llm_quickwins = llm_summary.get("quickWins") or []
  quick_wins = issues[:5]
  top_actions = issues[:5]
  scored_coverage_rows = [row for row in coverage_rows if row.get("analysed", 0) > 0]
  strongest_areas = sorted(scored_coverage_rows or coverage_rows, key=lambda row: row["averageScore"], reverse=True)[:3]
  weakest_areas = sorted(scored_coverage_rows or coverage_rows, key=lambda row: row["averageScore"])[:3]

  # LLM score overrides (use if available, else fall back to heuristic)
  llm_scores = llm_summary.get("scores", {})
  display_seo_score = llm_scores.get("seo", {}).get("score", overall_seo)
  display_seo_grade = llm_scores.get("seo", {}).get("grade", grade(overall_seo))
  display_aeo_score = llm_scores.get("aeo", {}).get("score", overall_aeo)
  display_aeo_grade = llm_scores.get("aeo", {}).get("grade", grade(overall_aeo))
  display_geo_score = llm_scores.get("geo", {}).get("score", overall_geo)
  display_geo_grade = llm_scores.get("geo", {}).get("grade", grade(overall_geo))
  display_entity_score = llm_scores.get("entityAuthority", {}).get("score", overall_entity)
  display_entity_grade = llm_scores.get("entityAuthority", {}).get("grade", grade(overall_entity))
  display_conv_score = llm_scores.get("conversionSupport", {}).get("score", overall_conversion)
  display_conv_grade = llm_scores.get("conversionSupport", {}).get("grade", grade(overall_conversion))

  if failed_gate:
    display_seo_score = display_aeo_score = display_geo_score = display_entity_score = display_conv_score = "Not issued"
    display_seo_grade = display_aeo_grade = display_geo_grade = display_entity_grade = display_conv_grade = "Blocked"

  # Issue and remediation tables. Keep the ranked ledger compact and render the full
  # evidence fields separately so PDF output is readable instead of a squeezed 13-column grid.
  issue_items_for_render = llm_issues_list if llm_issues_list else issues
  full_issue_items_for_render = (claude_analysis or {}).get("fullIssueRecords") or issue_items_for_render
  active_issues_html = render_issue_summary_table(issue_items_for_render)
  active_issue_records_html = render_issue_record_cards(full_issue_items_for_render)
  active_page_types_html = render_llm_page_type_table(llm_page_types) if llm_page_types else ""
  active_gap_matrix_html = render_llm_gap_matrix(llm_gap_matrix) if llm_gap_matrix else f"<table class='tight'><thead><tr><th>Page type</th><th>SEO</th><th>AEO</th><th>GEO</th><th>Confidence</th><th>Top missing element</th><th>Business impact</th></tr></thead><tbody>{gap_rows}</tbody></table>"
  active_remediation_html = render_llm_remediation_table(llm_remediation)

  overall_verdict = llm_summary.get("overallVerdict") or (
    "Full-estate coverage completed with no material family omitted."
    if all(row["coveragePercent"] == 100 for row in coverage_rows)
    else "Coverage was materially incomplete and should be rerun after the missing family is fixed."
  )
  implementation_narrative = llm_impl.get("narrative") or (
    "No urgent remediation item exceeded the evidence threshold." if not issues
    else "; ".join(item["issueId"] + " " + item["exactRemediation"] for item in issues[:5])
  )
  implementation_steps = llm_impl.get("steps") or [
    "Source-of-truth reconciliation",
    "Template-level metadata and canonical fixes",
    "Answer-first and citation-ready copy upgrades",
    "Internal linking reinforcement",
    "Final validation rerun",
  ]
  implementation_gains = llm_impl.get("expectedGains") or [
    "Better route governance",
    "Stronger answer-engine extractability",
    "Cleaner generative summaries and tighter internal topical signals",
  ]

  # Per-lens narrative blocks
  def _lens(key: str, fallback: str) -> str:
    text = llm_findings.get(key, "").strip()
    return f"<p>{_esc(text)}</p>" if text else f"<p>{fallback}</p>"

  control_rows = "".join(
    f"<tr><th>{_esc(key)}</th><td>{_esc(value if not isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False))}</td></tr>"
    for key, value in control.items()
  )
  ai_attempt_rows = "".join(
    f"<tr><td>{_esc(item.get('path', ''))}</td><td>{_esc(item.get('status', ''))}</td><td>{_esc(item.get('detail', ''))}</td></tr>"
    for item in analysis_state.get("attempts", [])
  ) or "<tr><td colspan='3'>No AI call attempt was available from the supplied runtime configuration.</td></tr>"
  skipped_sections_html = "".join(f"<li>{_esc(item)}</li>" for item in analysis_state.get("skippedSections", AI_REQUIRED_SECTIONS))
  restore_steps_html = "".join(f"<li>{_esc(item)}</li>" for item in analysis_state.get("restoreSteps", AI_RESTORE_STEPS))
  failure_banner = ""
  if failed_gate:
    failure_banner = f"""
    <section class="failed-gate">
      <h2>AI FORENSIC ANALYSIS UNAVAILABLE</h2>
      <p><strong>Completion state:</strong> Failed-gate. This artefact is an incomplete diagnostic control report, not a release-ready forensic audit.</p>
      <p><strong>Reason:</strong> {_esc(analysis_state.get('failureReason') or 'The required AI-assisted forensic analysis did not return a validated JSON payload.')}</p>
      <p><strong>Skipped AI-led sections:</strong></p>
      <ul>{skipped_sections_html}</ul>
      <p><strong>Required remediation to restore the full audit:</strong></p>
      <ol>{restore_steps_html}</ol>
      <table class="tight"><thead><tr><th>AI path</th><th>Status</th><th>Detail</th></tr></thead><tbody>{ai_attempt_rows}</tbody></table>
    </section>
    """
  baseline_score_note = ""
  if failed_gate:
    baseline_score_note = f"""
    <p class="section-note"><strong>Diagnostic-only baseline:</strong> heuristic collection produced SEO {overall_seo}, AEO {overall_aeo}, GEO {overall_geo}, Entity Authority {overall_entity}, and Conversion Support {overall_conversion}. These are not final forensic scores and must not be used as a release-ready verdict.</p>
    """

  body = f"""
  <style>
    .llm-badge{{display:inline-block;margin:0 0 12px;padding:5px 12px;border-radius:999px;font-size:12px;font-weight:700;background:#ecfdf5;color:#065f46;border:1px solid #6ee7b7;}}
    .llm-badge.heuristic{{background:#fef9c3;color:#92400e;border-color:#fcd34d;}}
    .llm-badge.failed{{background:#fee2e2;color:#991b1b;border-color:#fecaca;}}
    .failed-gate{{border-color:#fecaca;background:#fff7f7;}}
    .failed-gate h2{{color:#991b1b;}}
    .control-table th{{width:260px;background:#f8fafc;}}
    .llm-verdict{{font-size:15px;line-height:1.65;border-left:3px solid #4338ca;padding-left:12px;margin:0 0 16px;}}
    .kpi .grade{{display:block;font-size:28px;font-weight:800;margin-top:4px;}}
    .priority-item{{display:block;margin:4px 0;padding:4px 8px;border-radius:6px;background:#f3f4f6;font-size:13px;}}
    .lens-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;}}
    .lens-block{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:16px;}}
    .lens-block--full{{grid-column:1/-1;}}
    .lens-block h3{{margin:0 0 8px;font-size:14px;color:#1e3a5f;}}
    .lens-block p{{margin:0;font-size:13px;line-height:1.6;color:#374151;}}
    .sev-critical td{{background:#fef2f2;}}
    .sev-high td{{background:#fff7ed;}}
    .sev-medium td{{background:#fefce8;}}
    .issue-summary th,.issue-summary td{{font-size:11px;vertical-align:top;}}
    .issue-record{{border:1px solid #dbe4ef;border-radius:12px;padding:16px;margin:14px 0;background:#ffffff;page-break-inside:avoid;break-inside:avoid;}}
    .issue-record h3{{margin:0 0 8px;font-size:16px;color:#102033;}}
    .issue-meta{{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px;}}
    .issue-chip{{display:inline-block;border:1px solid #cbd5e1;border-radius:999px;background:#f8fafc;padding:3px 8px;font-size:11px;font-weight:700;color:#334155;}}
    .issue-field{{font-size:13px;line-height:1.55;margin:7px 0;color:#1f2937;}}
    .issue-field strong{{color:#0f172a;}}
    .remediation-card{{border:1px solid #dbe4ef;border-radius:12px;padding:14px;margin:12px 0;background:#fff;page-break-inside:avoid;break-inside:avoid;}}
    .remediation-card h3{{margin:0 0 8px;font-size:15px;color:#102033;}}
    .remediation-card p{{font-size:13px;line-height:1.55;margin:6px 0;color:#1f2937;}}
    .remediation-card code{{white-space:normal;word-break:break-word;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:2px 5px;}}
    pre code{{display:block;white-space:pre-wrap;word-break:break-word;font-size:11px;background:#f3f4f6;padding:8px;border-radius:6px;}}
    ol,ul{{padding-left:20px;margin:8px 0;}}
    ol li,ul li{{margin:4px 0;font-size:14px;}}
  </style>
  <section id="cover">
    <h2>Cover page</h2>
    <p><strong>Report title:</strong> Full-Estate Forensic SEO + AEO + GEO Audit</p>
    <p><strong>Website:</strong> <a href="{base_url}">{base_url}</a></p>
    <p><strong>Date/time:</strong> {utc_now()}</p>
    <p><strong>Audit mode:</strong> {'Full AI-assisted forensic mode' if ai_available else 'Failed-gate control mode'}</p>
    <p><strong>Workbook:</strong> <code>{Path(workbook.path).name}</code></p>
    <p><strong>Scope inspected:</strong> Full in-scope website estate including homepage, books, catalogue, topics, blog, podcast, archives, utilities, and programmatic families discovered from repo, workbook, sitemap, feed, and live internal links.</p>
    <p><strong>Completion state:</strong> {analysis_state.get('completionState', 'Unknown')}</p>
    <p><strong>AI analysis state:</strong> {analysis_state.get('statusLabel', 'Unknown')}</p>
    <p><strong>Total URLs discovered:</strong> {control['totalDiscoveredUrls']}</p>
    <p><strong>Material limitations:</strong> {'AI forensic synthesis was unavailable; no final release-ready verdict was issued.' if failed_gate else 'No AI-analysis limitation was detected. Non-AI data limitations are listed in the method section.'}</p>
  </section>

  {failure_banner}

  <section id="report-control">
    <h2>Report control block</h2>
    <table class="tight control-table"><tbody>{control_rows}</tbody></table>
  </section>

  <section id="summary">
    <h2>Executive summary</h2>
    {'<p class="llm-verdict">' + _esc(overall_verdict) + '</p>' if ai_available else '<p class="llm-verdict"><strong>No release-ready verdict issued.</strong> The audit halted at the AI forensic gate. Heuristic evidence collection completed, but the required AI-assisted synthesis did not return a validated analysis payload.</p>'}
    <div class="grid">
      <div class="kpi"><strong>SEO</strong><div>{display_seo_score}<span class="grade">{display_seo_grade}</span></div></div>
      <div class="kpi"><strong>AEO</strong><div>{display_aeo_score}<span class="grade">{display_aeo_grade}</span></div></div>
      <div class="kpi"><strong>GEO</strong><div>{display_geo_score}<span class="grade">{display_geo_grade}</span></div></div>
      <div class="kpi"><strong>Entity Authority</strong><div>{display_entity_score}<span class="grade">{display_entity_grade}</span></div></div>
      <div class="kpi"><strong>Conversion Support</strong><div>{display_conv_score}<span class="grade">{display_conv_grade}</span></div></div>
      <div class="kpi"><strong>Discovered URLs</strong><div>{len(pages)}</div></div>
    </div>
    <p>{' '.join(f'<span class="pill">{label}</span>' for label in labels)}</p>
    <p><strong>Top five priorities:</strong> {('<br>'.join(f'<span class="priority-item">{_esc(p)}</span>' for p in llm_top5)) if llm_top5 else ('; '.join(item['issueId'] + ' ' + item['whyItMatters'] for item in top_actions) if top_actions else 'No Critical or High issue required escalation from the available evidence.')}</p>
    <p><strong>Quick wins:</strong> {('<br>'.join(_esc(w) for w in llm_quickwins)) if llm_quickwins else ('; '.join(item['exactRemediation'] for item in quick_wins[:3]) if quick_wins else 'No immediate quick-win issue was confirmed.')}</p>
    <p><strong>Major risks:</strong> {'; '.join(item['whyItMatters'] for item in issues[:3]) if issues else 'No estate-wide blocker was confirmed.'}</p>
    <p><strong>Strongest areas:</strong> {'; '.join(f"{row['pageType']} ({row['averageScore']})" for row in strongest_areas)}</p>
    <p><strong>Weakest areas:</strong> {'; '.join(f"{row['pageType']} ({row['averageScore']})" for row in weakest_areas)}</p>
    {baseline_score_note}
    {'<p class="llm-badge">✦ Scores and priorities enriched by LLM forensic analysis</p>' if ai_available else '<p class="llm-badge failed">⚠ AI FORENSIC ANALYSIS UNAVAILABLE — failed gate, no final verdict</p>'}
  </section>

  <section id="method">
    <h2>Scope, inputs, and method</h2>
    <p><strong>Inspected inputs:</strong> repository routes, live route responses, workbook inventory, sitemap sources, podcast feed sources, blog and podcast manifest files, and live internal links.</p>
    <p><strong>Known limitations:</strong> metrics such as Core Web Vitals, Search Console, and analytics exports were not supplied, so they are marked as not verified rather than invented.</p>
    <p><strong>Chain of truth:</strong> repo and source files, live HTML responses, workbook inventory, sitemap and feed sources, and user context.</p>
    <p><strong>LLM analysis:</strong> {'Forensic narrative and ranked issues generated using the configured AI analysis path and the full context package.' if ai_available else 'Failed. The report was deliberately marked as failed-gate rather than completed.'}</p>
  </section>

  <section id="source-ledger">
    <h2>Source ledger</h2>
    <table class="tight"><thead><tr><th>Source</th><th>Count</th><th>Role</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{source_ledger_rows}</tbody></table>
  </section>

  <section id="source-mismatches">
    <h2>Source mismatches that matter</h2>
    <table class="tight"><thead><tr><th>ID</th><th>Severity</th><th>Sources</th><th>Evidence</th><th>Impact</th><th>Fix</th></tr></thead><tbody>{source_mismatch_rows}</tbody></table>
  </section>

  <section id="inventory">
    <h2>Inventory and reconciliation summary</h2>
    <p><strong>Workbook rows:</strong> {workbook.url_count}</p>
    <p><strong>Discovery source counts:</strong> {'; '.join(f"{key}: {value}" for key, value in sorted(discovery_meta['sourceCounts'].items()))}</p>
    <table class="tight"><thead><tr><th>Page family</th><th>Discovered</th><th>Analysed</th><th>Excluded</th><th>Failed</th><th>Coverage</th><th>Average score</th></tr></thead><tbody>{family_rows}</tbody></table>
    <p class="section-note">Every discovered in-scope URL was assigned a coverage state. This audit hard-fails if a mandatory family is only partly covered.</p>
  </section>

  <section id="lens">
    <h2>Findings by audit lens</h2>
    {'<p class="llm-badge">✦ Narratives below are LLM forensic analysis based on live crawl data</p>' if claude_analysis else ''}
    <div class="lens-grid">
      <div class="lens-block"><h3>Technical SEO</h3>{_lens('technicalSeo', 'Canonicals, titles, descriptions, indexability, redirect histories, and route normalisation were inspected page by page.')}</div>
      <div class="lens-block"><h3>On-page SEO and intent match</h3>{_lens('onPageSeo', 'Openings, heading structures, visible copy depth, and title-to-page alignment were scored across the estate.')}</div>
      <div class="lens-block"><h3>AEO</h3>{_lens('aeo', 'Answer-first summaries, extractable question headings, FAQs, tables, and snippet-friendly structures were measured family by family.')}</div>
      <div class="lens-block"><h3>GEO</h3>{_lens('geo', 'Entity clarity, summary safety, schema support, and reusable explanatory passages were assessed for citation readiness.')}</div>
      <div class="lens-block"><h3>Entity authority</h3>{_lens('entityAuthority', 'Author, book, podcast, and topic relationships were checked for visible reinforcement and schema support.')}</div>
      <div class="lens-block"><h3>Structured data</h3>{_lens('structuredData', 'Schema types, coverage, and alignment with visible content were reviewed across the estate.')}</div>
      <div class="lens-block"><h3>Internal linking</h3>{_lens('internalLinking', 'Orphan pages, anchor-text precision, cluster connections, and commercial bridging were reviewed.')}</div>
      <div class="lens-block"><h3>Content architecture</h3>{_lens('contentArchitecture', 'Topical graph coherence, cluster completeness, and static vs dynamic governance alignment were assessed.')}</div>
      <div class="lens-block"><h3>Conversion support</h3>{_lens('conversionSupport', 'Buy-now path clarity, CTA visibility, and proof-block presence were reviewed on commercial pages.')}</div>
      <div class="lens-block lens-block--full"><h3>Blog, podcast, transcript, and programmatic systems</h3>{_lens('blogPodcastTranscriptSystems', 'Blog article, podcast, archive, topic, catalogue, and book families were inventoried and fully analysed rather than silently sampled.')}</div>
    </div>
  </section>

  <section id="issues">
    <h2>Ranked issue ledger</h2>
    {'<p class="llm-badge">✦ Issues below are LLM forensic findings with exact remediations</p>' if llm_issues_list else ''}
    {active_issues_html}
  </section>

  <section id="full-issue-records">
    <h2>Full issue records</h2>
    <p class="section-note">The compact ledger above is for prioritisation. These records preserve the full evidence, root cause, impact, owner, effort and implementation detail required for engineering action.</p>
    {active_issue_records_html}
  </section>

  <section id="page-types">
    <h2>Page-type findings</h2>
    {active_page_types_html if active_page_types_html else f"<table class='tight'><thead><tr><th>Page type</th><th>Count</th><th>Coverage state</th><th>Average score</th><th>Range</th><th>Example</th></tr></thead><tbody>{page_type_rows}</tbody></table>"}
  </section>

  <section id="priority">
    <h2>Priority page annex</h2>
    <p class="section-note">Compatibility redirects and intentionally excluded routes are kept out of this table so real content pages are not buried by redirect wrappers.</p>
    <table class="tight"><thead><tr><th>URL</th><th>Type</th><th>Status</th><th>Title</th><th>Meta</th><th>Canonical</th><th>AEO</th><th>GEO</th><th>Total</th><th>Grade</th></tr></thead><tbody>{priority_rows}</tbody></table>
  </section>

  {f'<section id="redirect-compatibility"><h2>Redirect / compatibility route annex</h2><p class="section-note">These routes are compatibility wrappers and should be verified for canonical/redirect intent, not scored as priority content pages.</p><table class="tight"><thead><tr><th>URL</th><th>Canonical target</th><th>Coverage state</th><th>Reason</th></tr></thead><tbody>{redirect_compatibility_rows}</tbody></table></section>' if redirect_compatibility_rows else ''}

  <section id="templates">
    <h2>Template / component / generator annex</h2>
    <table class="tight"><thead><tr><th>Page family</th><th>Pages</th><th>Source</th><th>Average score</th><th>Repeated strengths</th><th>Repeated defects</th><th>Fix priority</th></tr></thead><tbody>{template_rows}</tbody></table>
    {f'<h3>Template diagnostics</h3><table class="tight"><thead><tr><th>Source</th><th>Area</th><th>Pages</th><th>Observed logic</th><th>Metadata logic</th><th>Schema logic</th><th>Answer-pattern gap</th><th>GEO gap</th><th>Priority</th></tr></thead><tbody>{template_diagnostic_rows}</tbody></table>' if template_diagnostic_rows else ''}
  </section>

  {'<section id="code-remediation"><h2>Code-level remediation appendix</h2><p class="llm-badge">✦ Exact corrected patterns from LLM forensic analysis</p>' + active_remediation_html + '</section>' if active_remediation_html else ''}

  <section id="gap-matrix">
    <h2>Best-practice gap matrix</h2>
    {active_gap_matrix_html}
  </section>

  <section id="implementation">
    <h2>Final verdict and implementation order</h2>
    <p><strong>Overall verdict:</strong> {_esc(overall_verdict)}</p>
    <p><strong>Implementation sequence:</strong></p>
    <ol>{''.join(f'<li>{_esc(step)}</li>' for step in implementation_steps)}</ol>
    <p><strong>Expected gains:</strong></p>
    <ul>{''.join(f'<li>{_esc(gain)}</li>' for gain in implementation_gains)}</ul>
    {('<p><strong>Forensic narrative:</strong> ' + _esc(implementation_narrative) + '</p>') if claude_analysis else ''}
  </section>

  <section id="coverage">
    <h2>Full URL coverage appendix</h2>
    <table class="tight"><thead><tr><th>URL</th><th>Page type</th><th>Discovered from</th><th>Status</th><th>Canonical</th><th>Indexability</th><th>Coverage state</th><th>Score</th><th>Risk</th></tr></thead><tbody>{coverage_appendix_rows}</tbody></table>
    <p class="section-note">Machine-friendly full-estate ledger is preserved separately in <code>coverage.json</code>.</p>
  </section>

  <section id="artefacts">
    <h2>Final artefacts</h2>
    <ul>
      <li><a href="{artefacts.get('report.html', '#')}">report.html</a></li>
      <li><a href="{artefacts.get('summary.json', '#')}">summary.json</a></li>
      <li><a href="{artefacts.get('coverage.json', '#')}">coverage.json</a></li>
    </ul>
  </section>
  """
  return html_report_shell("Full-Estate Forensic SEO + AEO + GEO Audit", body)


def validate_full_coverage(coverage_rows: list[dict[str, Any]]) -> None:
  mandatory_families = {
    "blog archive", "blog article", "podcast hub", "podcast episode",
    "podcast transcript", "archive / pagination / utility", "book page",
    "category / hub", "topic hub",
  }
  rows_by_type = {row["pageType"]: row for row in coverage_rows}
  missing = [f for f in mandatory_families if f in rows_by_type and rows_by_type[f]["coveragePercent"] < 100]
  absent = [f for f in mandatory_families if f not in rows_by_type]
  if missing:
    print(f"[coverage] WARNING: Families below 100% coverage: {', '.join(missing)}", file=sys.stderr)
  if absent:
    print(f"[coverage] NOTE: Mandatory families not discovered: {', '.join(absent)}", file=sys.stderr)


def build_summary(base_url: str, pages: list[dict[str, Any]], issues: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], report_prefix: str, workbook: WorkbookInfo, analysis_state: dict[str, Any], session_id: str = "") -> dict[str, Any]:
  control = build_report_control(pages, coverage_rows, {}, analysis_state)
  state = analysis_state.get("completionState")
  complete = state == "Complete"
  return {
    "ok": complete,
    "sessionId": session_id,
    "status": "completed" if complete else ("incomplete" if state == "Incomplete" else "failed-gate"),
    "auditCompletionState": analysis_state.get("completionState"),
    "aiAnalysisStatus": analysis_state.get("statusLabel"),
    "aiFailureReason": analysis_state.get("failureReason", ""),
    "reportPrefix": report_prefix,
    "websiteUrl": base_url,
    "generatedAt": utc_now(),
    "totalDiscoveredUrls": control["totalDiscoveredUrls"],
    "auditedUrlCount": control["totalAnalysedUrls"],
    "failedUrlCount": control["totalFailedUrls"],
    "excludedUrlCount": control["totalExcludedUrls"],
    "coveragePercent": control["coveragePercent"],
    "issueCount": len(issues),
    "familyCoverage": coverage_rows,
    "workbookRows": workbook.url_count,
    "pageTypeCounts": dict(Counter(page["pageType"] for page in pages)),
  }


# ── Repo signals ──────────────────────────────────────────────────────────────

def build_repo_signals(repo_root: Path, base_url: str) -> dict:
  """Extract repo-level signals relevant to forensic source reconciliation."""
  signals: dict[str, Any] = {}

  governance_script = repo_root / "scripts" / "check_ungoverned_routes.py"
  excludes_in_governance: list[str] = []
  if governance_script.exists():
    src = governance_script.read_text(encoding="utf-8")
    m = re.search(r"EXCLUDED_ROUTE_PREFIXES\s*=\s*\((.*?)\)", src, re.S)
    if m:
      excludes_in_governance = re.findall(r'["\']([^"\']+)["\']', m.group(1))
    else:
      excludes_in_governance = re.findall(r'["\']([^"\']+/)["\']', src)
  signals["governanceScriptPath"] = "scripts/check_ungoverned_routes.py" if governance_script.exists() else ""
  signals["governanceScriptExcludes"] = sorted(set(excludes_in_governance))

  ebook_pipeline = repo_root / "scripts" / "ebook_pipeline.py"
  ebook_trim = None
  if ebook_pipeline.exists():
    src = ebook_pipeline.read_text(encoding="utf-8")
    m = re.search(r'\[:(\d+)\]', src)
    if m:
      ebook_trim = int(m.group(1))
  signals["ebookPipelinePath"] = "scripts/ebook_pipeline.py" if ebook_pipeline.exists() else ""
  signals["ebookPipelineTrimLimit"] = ebook_trim

  blog_manifest = repo_root / "blog" / "posts.json"
  blog_count = 0
  blog_items: list[dict[str, Any]] = []
  if blog_manifest.exists():
    try:
      data = json.loads(blog_manifest.read_text(encoding="utf-8"))
      items = data.get("items") or data.get("posts") or [] if isinstance(data, dict) else data
      if isinstance(items, list):
        blog_items = [item for item in items if isinstance(item, dict)]
        blog_count = len(blog_items)
    except Exception:
      pass
  signals["blogManifestPath"] = "blog/posts.json" if blog_manifest.exists() else ""
  signals["blogManifestCount"] = blog_count
  signals["blogManifestSample"] = [item.get("url") or item.get("path") or item.get("slug") for item in blog_items[:5]]

  sitemap_urls = set(local_sitemap_urls(repo_root, base_url))
  sitemap_paths = {_route_or_url(url) for url in sitemap_urls}
  signals["localSitemapUrlCount"] = len(sitemap_urls)

  podcast_manifest = repo_root / "data" / "podcast-episodes.json"
  podcast_count = 0
  podcast_items: list[dict[str, Any]] = []
  if podcast_manifest.exists():
    try:
      data = json.loads(podcast_manifest.read_text(encoding="utf-8"))
      items = data if isinstance(data, list) else data.get("items") or data.get("episodes") or []
      if isinstance(items, list):
        podcast_items = [item for item in items if isinstance(item, dict)]
        podcast_count = len(podcast_items)
    except Exception:
      pass
  signals["podcastManifestPath"] = "data/podcast-episodes.json" if podcast_manifest.exists() else ""
  signals["podcastManifestCount"] = podcast_count

  page_url_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
  transcript_urls: list[str] = []
  episode_dates: list[str] = []
  for item in podcast_items:
    page_url = (item.get("page_url") or item.get("pageUrl") or item.get("url") or "").strip()
    if page_url:
      page_url_groups[_route_or_url(page_url)].append(item)
    transcript_url = (item.get("transcript_url") or item.get("transcriptUrl") or "").strip()
    if transcript_url:
      transcript_urls.append(transcript_url)
    date_value = str(item.get("date") or item.get("published") or item.get("published_at") or "")[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_value):
      episode_dates.append(date_value)

  duplicate_page_urls = []
  for path, items in sorted(page_url_groups.items()):
    if len(items) > 1:
      duplicate_page_urls.append({
        "pageUrl": path,
        "count": len(items),
        "sessionIds": [str(item.get("session_id") or item.get("sessionId") or "") for item in items[:8]],
        "titles": [str(item.get("title") or "") for item in items[:8]],
      })
  signals["podcastPageUrlCount"] = sum(len(items) for items in page_url_groups.values())
  signals["podcastUniquePageUrlCount"] = len(page_url_groups)
  signals["duplicatePodcastPageUrls"] = duplicate_page_urls
  signals["podcastTranscriptUrlCount"] = len(transcript_urls)
  signals["podcastOldestDate"] = min(episode_dates) if episode_dates else ""
  signals["podcastLatestDate"] = max(episode_dates) if episode_dates else ""

  transcript_missing = []
  for transcript_url in transcript_urls:
    path = _route_or_url(transcript_url)
    if transcript_url not in sitemap_urls and path not in sitemap_paths:
      transcript_missing.append({"url": transcript_url, "path": path})
  signals["transcriptSitemapMissingCount"] = len(transcript_missing)
  signals["transcriptSitemapMissingSample"] = transcript_missing[:10]

  redirects_file = repo_root / "_redirects"
  known_redirects: list[dict[str, Any]] = []
  if redirects_file.exists():
    lines = redirects_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
      parts = line.strip().split()
      if len(parts) >= 2 and parts[0].startswith("/podcast/"):
        known_redirects.append({"from": parts[0], "to": parts[1]})
  signals["knownRedirects"] = known_redirects[:30]

  llms_txt = repo_root / "llms.txt"
  llm_index = repo_root / "llm-index.json"
  llms_scope = "unknown"
  llms_summary: dict[str, Any] = {}
  if llms_txt.exists():
    content = llms_txt.read_text(encoding="utf-8").lower()
    llms_summary["mentionsBlog"] = "blog" in content
    llms_summary["mentionsPodcast"] = "podcast" in content
    llms_summary["mentionsTranscript"] = "transcript" in content
    llms_summary["mentionsTopics"] = "topic" in content or "/topics/" in content
    if "ebook" in content and not any(llms_summary[key] for key in ("mentionsBlog", "mentionsPodcast", "mentionsTranscript")):
      llms_scope = "ebook-only"
    elif any(llms_summary.values()):
      llms_scope = "broad"
    else:
      llms_scope = "narrow"
  if llm_index.exists():
    try:
      index_data = json.loads(llm_index.read_text(encoding="utf-8"))
      llms_summary["llmIndexTopLevelKeys"] = sorted(index_data.keys()) if isinstance(index_data, dict) else []
    except Exception:
      llms_summary["llmIndexTopLevelKeys"] = []
  signals["llmsFiles"] = [f for f in ["llms.txt", "llm-index.json"] if (repo_root / f).exists()]
  signals["llmsScope"] = llms_scope
  signals["llmsCoverageHints"] = llms_summary

  generator_scripts = [
    str(path.relative_to(repo_root))
    for path in repo_root.rglob("*.py")
    if any(token in path.name for token in ("generate", "pipeline", "inject"))
  ] + [
    str(path.relative_to(repo_root))
    for path in repo_root.rglob("*.mjs")
    if "generate" in path.name
  ]
  signals["generatorScripts"] = sorted(generator_scripts)[:25]
  signals["functionsPresent"] = [
    str(path.relative_to(repo_root))
    for path in (repo_root / "functions").rglob("*.js")
  ] if (repo_root / "functions").exists() else []

  return signals


# ── Live dynamic URLs ─────────────────────────────────────────────────────────

def extract_live_dynamic_urls(pages: list[dict[str, Any]], discovered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
  """Build a structured list of dynamic URLs confirmed during the live crawl."""
  dynamic_families = {"blog article", "podcast episode", "podcast transcript"}
  result: list[dict[str, Any]] = []
  seen: set[str] = set()
  for page in pages:
    if page["pageType"] not in dynamic_families:
      continue
    url = page["url"]
    if url in seen:
      continue
    seen.add(url)
    entry = discovered.get(url, {})
    sources = sorted(entry.get("sources", set()))
    result.append({
      "url": url,
      "pageType": page["pageType"],
      "source": ", ".join(sources) if sources else "live-crawl",
      "httpStatus": page["status"],
      "inRepoManifest": "blog-manifest" in sources or "podcast-manifest" in sources,
      "keyObservation": (
        "duplicate standfirst block observed near top of page"
        if page["pageType"] == "blog article" and page["introText"] and len(page["introText"]) > 400
        else ""
      ),
    })
  return result


# ── Serialise page for API payload (no soup) ──────────────────────────────────

def serialise_page_for_analysis(page: dict[str, Any], is_priority: bool = False) -> dict[str, Any]:
  """Strip the BeautifulSoup object and build a clean dict for the analysis API."""
  soup = page.get("soup")
  h2_headings: list[str] = []
  schema_types: list[str] = []
  intro_text = page.get("introText", "")[:300]

  if soup:
    h2_headings = [h.get_text(" ", strip=True) for h in soup.select("h2")][:8]
    for script in soup.select("script[type='application/ld+json']"):
      try:
        data = json.loads(script.string or "")
        t = data.get("@type", "")
        if isinstance(t, list):
          schema_types.extend(t)
        elif t:
          schema_types.append(t)
      except Exception:
        pass

  result: dict[str, Any] = {
    "url": page["url"],
    "route": normalise_route(urlparse(page["url"]).path),
    "status": page["status"],
    "pageType": page["pageType"],
    "coverageState": page["coverageState"],
    "title": page["meta"]["title"],
    "metaDescription": page["meta"]["metaDescription"],
    "canonical": page["meta"]["canonical"],
    "h1": page["meta"]["h1"],
    "ogTitle": page["meta"].get("og", {}).get("og:title", ""),
    "schemaCount": page["meta"]["schemaCount"],
    "indexability": page["indexability"],
    "wordCount": page["wordCount"],
    "internalLinkCount": page["internalLinkCount"],
    "questionHeadings": page["questionHeadings"],
    "hasFaqSchema": page["hasFaqSchema"],
    "scores": page["scores"],
    "total": page["total"],
    "grade": page["grade"],
    "riskFlag": page["riskFlag"],
  }
  if is_priority:
    result["introText"] = intro_text
    result["h2Headings"] = h2_headings
    result["schemaTypes"] = schema_types
  return result


# ── OpenRouter / direct LLM integration ──────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "anthropic/claude-opus-4"

SYSTEM_PROMPT = """You are a senior forensic SEO + AEO + GEO auditor. You operate with the precision of a technical
SEO engineer, semantic search strategist, answer-engine analyst, and generative-search specialist.

You will receive a structured JSON context block containing pre-crawled page data, inventory
reconciliation results, workbook metadata, and heuristic issue flags collected from the jonathan-harris.online
estate. Your job is to interpret that data forensically and produce a complete, evidence-led audit report.

OPERATING RULES — NON-NEGOTIABLE:
1. No boilerplate. No filler. No invented evidence.
2. No vague statements such as "improve metadata", "enhance structured data", or "optimise content quality"
   unless you immediately name the exact page, file, element, current value, defect, and corrected target.
3. Every significant finding must cite the exact route, URL, file path, or template it applies to.
4. If a metric cannot be measured from the supplied data, write "Not verified from supplied context" and
   state why. Do not fabricate scores or invent crawl results.
5. Prefer exact values: current title tag text, exact canonical href, exact heading text, exact file path.
6. When the supplied data conflicts across sources (repo vs workbook vs live), state the conflict explicitly.
7. Do not silently skip page families. If podcast/blog/transcript data is thin in the supplied context, say so
   and flag it as a coverage limitation — do not pretend to have checked pages you have not seen.
8. Score using these exact weights: Technical SEO 20, On-Page Intent 15, AEO Readiness 20,
   GEO Readiness 20, Entity Authority 10, Internal Linking 10, Conversion Support 5.
   Grade: A=90-100, B=80-89, C=70-79, D=60-69, F<60.
9. Every Critical or High issue must include an exact remediation: the corrected value, code snippet,
   template change, or governance rule — not a description of what to change.
10. Use severity: Critical / High / Medium / Low. Use confidence: Confirmed / Probable / Needs verification.

OUTPUT FORMAT:
Return a single JSON object with the keys defined in the OUTPUT SCHEMA below.
Do not include markdown fences, preamble, or any text outside the JSON object.
All string values containing HTML must use valid inline HTML; no script tags.

ISSUE RECORD FORMAT (use for every entry in the `issues` array):
{
  "issueId": "JH-SEO-001",
  "severity": "Critical",
  "confidence": "Confirmed",
  "lens": "SEO / Technical",
  "rootCauseLevel": "system / route / template / page / data / content / schema",
  "affected": "exact route, URL, or file path",
  "evidenceObserved": "exact current value or behaviour observed in supplied data",
  "whyItMatters": "concrete impact on crawlability / ranking / extraction / retrieval",
  "exactRemediation": "exact corrected value, code change, or governance rule",
  "expectedGain": "specific measurable improvement",
  "estimatedEffort": "Low / Medium / High",
  "recommendedOwner": "Engineering / Content / Editorial / Frontend / Schema / Product",
  "verificationMethod": "specific rerun, curl, file check, schema validation, or coverage ledger check that proves the fix"
}

OUTPUT SCHEMA:
{
  "executiveSummary": {
    "overallVerdict": "<2-3 sentence estate verdict>",
    "scores": {
      "seo": { "score": 0, "grade": "?", "headline": "" },
      "aeo": { "score": 0, "grade": "?", "headline": "" },
      "geo": { "score": 0, "grade": "?", "headline": "" },
      "entityAuthority": { "score": 0, "grade": "?", "headline": "" },
      "conversionSupport": { "score": 0, "grade": "?", "headline": "" }
    },
    "topFivePriorities": ["", "", "", "", ""],
    "quickWins": ["", "", ""],
    "estateLabels": [""]
  },
  "findingsByLens": {
    "technicalSeo": "<forensic narrative — exact routes, files, defects>",
    "onPageSeo": "<forensic narrative>",
    "aeo": "<forensic narrative>",
    "geo": "<forensic narrative>",
    "entityAuthority": "<forensic narrative>",
    "structuredData": "<forensic narrative>",
    "internalLinking": "<forensic narrative>",
    "contentArchitecture": "<forensic narrative>",
    "conversionSupport": "<forensic narrative>",
    "blogPodcastTranscriptSystems": "<forensic narrative — mandatory, must cover each family>"
  },
  "issues": [],
  "pageTypeFindings": [
    {
      "pageType": "",
      "count": 0,
      "coverageState": "",
      "score": 0,
      "grade": "",
      "judgement": "",
      "keyNote": ""
    }
  ],
  "priorityPageAnnex": [
    {
      "url": "",
      "pageType": "",
      "templateSource": "",
      "titleStatus": "Healthy / Needs fix / Missing",
      "metaStatus": "Healthy / Needs fix / Missing",
      "canonicalStatus": "Healthy / Needs fix / Missing",
      "schemaStatus": "Healthy / Needs fix / Missing",
      "aeoStatus": "Healthy / Mixed / Weak",
      "geoStatus": "Healthy / Mixed / Weak",
      "score": 0,
      "grade": "",
      "confirmedIssueIds": [],
      "keyNote": ""
    }
  ],
  "templateAnnex": [
    {
      "sourceFile": "",
      "area": "",
      "observedLogic": "",
      "repeatedEffect": "",
      "fixPriority": "Critical / High / Medium / Low"
    }
  ],
  "codeRemediationAppendix": [
    {
      "target": "file path or template name",
      "issueId": "",
      "currentPattern": "",
      "correctedPattern": "",
      "rationale": ""
    }
  ],
  "bestPracticeGapMatrix": [
    {
      "pageType": "",
      "seo": "Strong / Moderate / Weak",
      "aeo": "Strong / Moderate / Weak",
      "geo": "Strong / Moderate / Weak",
      "confidence": "Confirmed / Probable / Needs verification",
      "topMissingElement": "",
      "businessImpact": ""
    }
  ],
  "implementationOrder": {
    "narrative": "<final verdict and reasoning>",
    "steps": ["", "", ""],
    "expectedGains": ["", "", ""]
  }
}"""


def _build_user_message(
  base_url: str,
  session_id: str,
  inventory: dict[str, Any],
  priority_pages_clean: list[dict[str, Any]],
  all_routes_condensed: list[dict[str, Any]],
  issues: list[dict[str, Any]],
  repo_signals: dict[str, Any],
  live_dynamic_urls: list[dict[str, Any]],
  source_ledger: list[dict[str, Any]] | None = None,
  source_mismatches: list[dict[str, Any]] | None = None,
  family_diagnostics: list[dict[str, Any]] | None = None,
  template_diagnostics: list[dict[str, Any]] | None = None,
) -> str:
  """Serialise collected audit data into the structured context block for the LLM."""
  return f"""FORENSIC SEO + AEO + GEO AUDIT — CONTEXT PACKAGE
Website: {base_url}
Session: {session_id}
Generated: {utc_now()}

---
SECTION 1: INVENTORY RECONCILIATION
{json.dumps(inventory, indent=2)}

---
SECTION 2: PRIORITY PAGE DATA (full per-page metadata for every priority route)
{json.dumps(priority_pages_clean, indent=2)}

---
SECTION 3: ALL DISCOVERED ROUTES (condensed — route, type, status, grade, risk only)
{json.dumps(all_routes_condensed, indent=2)}

---
SECTION 4: HEURISTIC ISSUES FLAGGED BY SCRIPT
{json.dumps(issues, indent=2)}

---
SECTION 5: REPO STRUCTURE SIGNALS
{json.dumps(repo_signals, indent=2)}

---
SECTION 6: LIVE DYNAMIC URLS CONFIRMED
{json.dumps(live_dynamic_urls, indent=2)}

---
SECTION 7: SOURCE LEDGER
{json.dumps(source_ledger or [], indent=2)}

---
SECTION 8: SOURCE MISMATCHES THAT MATTER
{json.dumps(source_mismatches or [], indent=2)}

---
SECTION 9: FAMILY DIAGNOSTICS
{json.dumps(family_diagnostics or [], indent=2)}

---
SECTION 10: TEMPLATE DIAGNOSTICS
{json.dumps(template_diagnostics or [], indent=2)}

---
SECTION 11: AUDIT INSTRUCTION

Perform the full forensic SEO + AEO + GEO audit using the context package above.

Apply these mandatory special rules:

BLOG ENFORCEMENT:
Analyse the blog family as a whole: governance drift between repo manifest and live archive, standfirst
duplication on post pages, whether the archive exposes a strong crawlable listing, whether feed-derived
posts carry full metadata and schema, and whether blog content is structured for passage extraction.

PODCAST ENFORCEMENT:
Separately analyse: podcast hub, episode pages, transcript archive, transcript leaf pages.
Flag only when supported by evidence: absence of server-rendered episode cards on the hub, thin episode pages, unchunked transcript
bodies, broken compatibility redirect chains, or canonical podcast/blog dynamic families absent from the generated dynamic route manifest.
Assess whether episode and transcript pages behave as answer hubs or as thin landing pages.

GEO ENFORCEMENT:
Assess llms.txt and llm-index.json scope explicitly. If ebook-only, flag as confirmed deficiency.
Assess whether topic guides, glossary, comparisons, blog posts, and transcript pages are machine-readable
discovery assets that are being wasted by omission from llms files.

EBOOK ENFORCEMENT:
If the supplied repo evidence shows hard heading truncation or passage-extraction loss in scripts/ebook_pipeline.py,
flag it with exact affected code. Do not carry forward historic H3 findings when the current evidence does not support them.

GOVERNANCE ENFORCEMENT:
If scripts/check_ungoverned_routes.py still blanket-excludes canonical blog/posts/ or podcast/episodes/ routes,
flag it as a Critical governance blind spot. If those route families are governed by data/dynamic-route-manifest.json,
record the manifest as a positive control rather than a defect.

ISSUE NUMBERING: Use JH-SEO-NNN, JH-AEO-NNN, JH-GEO-NNN, JH-TECH-NNN prefixes.
Start numbering at 001. Order issues Critical -> High -> Medium -> Low within each prefix group.

SCORE CALIBRATION:
- Static governed pages (topic guides, book pages, bio, homepage): expected range B to B+
- Dynamic families with confirmed governance gaps (podcast, blog): expected range D to C
- Dynamic families governed by a generated manifest and sitemap entries: expected range C+ to B, subject to page quality evidence
- Broken redirect target: F
- Adjust all scores relative to the evidence in the supplied data, not to generic benchmarks.

Now produce the complete JSON report. No preamble. No markdown fences. Pure JSON object only."""


def call_claude_audit_via_openrouter(
  api_key: str,
  session_id: str,
  base_url: str,
  pages: list[dict[str, Any]],
  priority_pages_raw: list[dict[str, Any]],
  issues: list[dict[str, Any]],
  coverage_rows: list[dict[str, Any]],
  repo_signals: dict[str, Any],
  live_dynamic_urls: list[dict[str, Any]],
  workbook: "WorkbookInfo",
  discovery_meta: dict[str, Any],
  model: str | None = None,
) -> dict[str, Any] | None:
  """Call Claude via OpenRouter and return the parsed forensic audit JSON, or None on failure."""
  import requests as _requests
  import time

  model = model or os.environ.get("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL)

  priority_urls = {p["url"] for p in priority_pages_raw}
  all_routes_condensed = [
    {
      "route": normalise_route(urlparse(p["url"]).path),
      "pageType": p["pageType"],
      "status": p["status"],
      "grade": p["grade"],
      "riskFlag": p["riskFlag"],
      "coverageState": p["coverageState"],
    }
    for p in pages
  ]
  priority_pages_clean = [
    serialise_page_for_analysis(p, is_priority=True)
    for p in pages if p["url"] in priority_urls
  ][:30]

  inventory: dict[str, Any] = {
    "workbookUrlCount": workbook.url_count,
    "repoRouteCount": discovery_meta["sourceCounts"].get("repo", 0),
    "discoveredRouteCount": len(pages),
    "pageTypeCounts": dict(Counter(p["pageType"] for p in pages)),
    "sourceCounts": discovery_meta["sourceCounts"],
    "workbookSheet": workbook.primary_sheet,
    "blogManifestCount": repo_signals.get("blogManifestCount", 0),
    "podcastManifestCount": repo_signals.get("podcastManifestCount", 0),
  }

  user_message = _build_user_message(
    base_url=base_url,
    session_id=session_id,
    inventory=inventory,
    priority_pages_clean=priority_pages_clean,
    all_routes_condensed=all_routes_condensed,
    issues=issues[:40],
    repo_signals=repo_signals,
    live_dynamic_urls=live_dynamic_urls[:50],
    source_ledger=[],
    source_mismatches=[],
    family_diagnostics=[],
    template_diagnostics=[],
  )

  print(f"[openrouter] calling {model} with {len(priority_pages_clean)} priority pages and {len(all_routes_condensed)} condensed routes", file=sys.stderr)

  raw = ""
  for attempt in range(1, 3):
    try:
      resp = _requests.post(
        OPENROUTER_API_URL,
        headers={
          "Authorization": f"Bearer {api_key}",
          "Content-Type": "application/json",
          "HTTP-Referer": base_url,
          "X-Title": "SEO AEO GEO Forensic Audit",
        },
        json={
          "model": model,
          "max_tokens": 8000,
          "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
          ],
        },
        timeout=300,
      )
      if not resp.ok:
        print(f"[openrouter] attempt {attempt} returned {resp.status_code}: {resp.text[:400]}", file=sys.stderr)
        time.sleep(attempt * 3)
        continue

      data = resp.json()
      raw = data["choices"][0]["message"]["content"].strip()

      # Strip accidental markdown fences
      if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
          raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

      result = json.loads(raw)
      print("[openrouter] forensic analysis received and parsed successfully", file=sys.stderr)
      return result

    except json.JSONDecodeError as exc:
      print(f"[openrouter] attempt {attempt} JSON parse failed: {exc}; raw response snippet: {raw[:300]}", file=sys.stderr)
    except Exception as exc:
      print(f"[openrouter] attempt {attempt} call failed: {exc}", file=sys.stderr)
    time.sleep(attempt * 3)
  return None


# ── Derive analysis URL ───────────────────────────────────────────────────────

def derive_analysis_url(callback_url: str | None, override: str | None = None) -> str | None:
  """Convert the SEO/AEO/GEO callback URL to its paired analysis endpoint URL."""
  if override:
    return override.rstrip("/")
  if not callback_url:
    return None
  value = callback_url.rstrip("/")
  expected_suffix = "/audits/seo-aeo-geo/callback"
  if not value.endswith(expected_suffix):
    return None
  return value[: -len("/callback")] + "/analysis"


def _analysis_response_detail(resp: Any, limit: int = 900) -> str:
  try:
    body = resp.text
  except Exception:
    body = ""
  return f"HTTP {getattr(resp, 'status_code', 'unknown')} :: {_safe_detail(body, limit=limit)}"


def _extract_analysis_payload(data: dict[str, Any]) -> dict[str, Any] | None:
  if not isinstance(data, dict):
    return None
  if isinstance(data.get("analysis"), dict):
    return data["analysis"]
  result = data.get("result") if isinstance(data.get("result"), dict) else {}
  if isinstance(result.get("analysis"), dict):
    return result["analysis"]
  job = data.get("job") if isinstance(data.get("job"), dict) else {}
  if isinstance(job.get("analysis"), dict):
    return job["analysis"]
  job_result = job.get("result") if isinstance(job.get("result"), dict) else {}
  if isinstance(job_result.get("analysis"), dict):
    return job_result["analysis"]
  return None


def _resolve_status_url(analysis_url: str, status_url: str | None) -> str | None:
  if not status_url:
    return None
  return urljoin(analysis_url, status_url)


def _poll_analysis_status(
  status_url: str,
  callback_token: str,
  max_wait_seconds: int,
  poll_seconds: int,
  request_timeout: int,
) -> dict[str, Any] | None:
  import requests as _requests
  import time

  deadline = time.monotonic() + max_wait_seconds
  last_detail = "analysis job did not complete before timeout"

  while time.monotonic() < deadline:
    try:
      resp = _requests.get(
        status_url,
        headers={"Authorization": f"Bearer {callback_token}"},
        timeout=request_timeout,
      )
      if resp.status_code == 200:
        data = resp.json()
        analysis = _extract_analysis_payload(data)
        if analysis:
          call_analysis_endpoint.last_detail = f"{status_url} :: completed"
          return analysis
        last_detail = f"{status_url} :: completed but no analysis payload"
        break
      if resp.status_code == 202:
        try:
          data = resp.json()
          status = data.get("status") or data.get("job", {}).get("status") or "running"
          last_detail = f"{status_url} :: {status}"
        except Exception:
          last_detail = f"{status_url} :: HTTP 202"
        time.sleep(poll_seconds)
        continue
      last_detail = f"{status_url} :: {_analysis_response_detail(resp)}"
      if resp.status_code >= 500:
        time.sleep(poll_seconds)
        continue
      break
    except Exception as exc:
      last_detail = f"{status_url} :: poll failed: {exc}"
      time.sleep(poll_seconds)

  call_analysis_endpoint.last_detail = last_detail
  return None


# ── LLM analysis call ─────────────────────────────────────────────────────────

def call_analysis_endpoint(
  analysis_url: str,
  callback_token: str,
  session_id: str,
  base_url: str,
  pages: list[dict[str, Any]],
  priority_pages_raw: list[dict[str, Any]],
  issues: list[dict[str, Any]],
  coverage_rows: list[dict[str, Any]],
  coverage_families: list[dict[str, Any]],
  repo_signals: dict[str, Any],
  live_dynamic_urls: list[dict[str, Any]],
  workbook: WorkbookInfo,
  discovery_meta: dict[str, Any],
  source_ledger: list[dict[str, Any]] | None = None,
  source_mismatches: list[dict[str, Any]] | None = None,
  family_diagnostics: list[dict[str, Any]] | None = None,
  template_diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
  """POST audit data to the AI-suite endpoint and poll async jobs until complete."""
  import requests as _requests

  call_analysis_endpoint.last_detail = analysis_url

  priority_urls = {p["url"] for p in priority_pages_raw}
  all_routes_clean = [serialise_page_for_analysis(p, is_priority=False) for p in pages]
  priority_pages_clean = [serialise_page_for_analysis(p, is_priority=True) for p in pages if p["url"] in priority_urls][:30]

  inventory = {
    "workbookUrlCount": workbook.url_count,
    "repoRouteCount": discovery_meta["sourceCounts"].get("repo", 0),
    "discoveredRouteCount": len(pages),
    "pageTypeCounts": dict(Counter(p["pageType"] for p in pages)),
    "sourceCounts": discovery_meta["sourceCounts"],
    "workbookSheet": workbook.primary_sheet,
    "blogManifestCount": repo_signals.get("blogManifestCount", 0),
    "podcastManifestCount": repo_signals.get("podcastManifestCount", 0),
  }

  payload = {
    "auditType": "seo-aeo-geo",
    "sessionId": session_id,
    "baseUrl": base_url,
    "generatedAt": utc_now(),
    "inventory": inventory,
    "priorityPages": priority_pages_clean,
    "allRoutes": all_routes_clean,
    "heuristicIssues": issues[:40],
    "repoSignals": repo_signals,
    "liveDynamicUrls": live_dynamic_urls[:50],
    "coverage": coverage_rows,
    "coverageFamilies": coverage_families,
    "sourceLedger": source_ledger or [],
    "sourceMismatchesThatMatter": source_mismatches or [],
    "familyDiagnostics": family_diagnostics or [],
    "templateDiagnostics": template_diagnostics or [],
    "dynamicRouteLedger": live_dynamic_urls[:50],
  }

  post_timeout = int(os.environ.get("AUDIT_ANALYSIS_POST_TIMEOUT_SECONDS", "45"))
  poll_timeout = int(os.environ.get("AUDIT_ANALYSIS_POLL_TIMEOUT_SECONDS", "30"))
  poll_seconds = max(2, int(os.environ.get("AUDIT_ANALYSIS_POLL_SECONDS", "8")))
  max_wait_seconds = max(30, int(os.environ.get("AUDIT_ANALYSIS_MAX_WAIT_SECONDS", "900")))

  try:
    resp = _requests.post(
      analysis_url,
      json=payload,
      headers={
        "Authorization": f"Bearer {callback_token}",
        "Content-Type": "application/json",
      },
      timeout=post_timeout,
    )
  except Exception as exc:
    call_analysis_endpoint.last_detail = f"{analysis_url} :: POST failed: {exc}"
    print(f"[analysis] endpoint post failed: {exc}", file=sys.stderr)
    return None

  if resp.status_code == 200:
    try:
      data = resp.json()
      analysis = _extract_analysis_payload(data)
      if analysis:
        call_analysis_endpoint.last_detail = f"{analysis_url} :: completed synchronously"
        return analysis
      call_analysis_endpoint.last_detail = f"{analysis_url} :: HTTP 200 but no analysis payload"
    except Exception as exc:
      call_analysis_endpoint.last_detail = f"{analysis_url} :: HTTP 200 JSON parse failed: {exc}"
    return None

  if resp.status_code == 202:
    try:
      data = resp.json()
    except Exception as exc:
      call_analysis_endpoint.last_detail = f"{analysis_url} :: HTTP 202 JSON parse failed: {exc}"
      return None
    status_url = _resolve_status_url(
      analysis_url,
      data.get("statusUrl") or data.get("analysisStatusUrl") or data.get("absoluteStatusUrl"),
    )
    if not status_url:
      call_analysis_endpoint.last_detail = f"{analysis_url} :: HTTP 202 without statusUrl"
      return None
    print(f"[analysis] async job accepted; polling {status_url}", file=sys.stderr)
    return _poll_analysis_status(
      status_url=status_url,
      callback_token=callback_token,
      max_wait_seconds=max_wait_seconds,
      poll_seconds=poll_seconds,
      request_timeout=poll_timeout,
    )

  call_analysis_endpoint.last_detail = f"{analysis_url} :: {_analysis_response_detail(resp)}"
  print(f"[analysis] endpoint returned {call_analysis_endpoint.last_detail}", file=sys.stderr)
  return None


call_analysis_endpoint.last_detail = "not attempted"


# ── HTML helpers for LLM analysis ─────────────────────────────────────────────

def _esc(value: Any) -> str:
  """HTML-escape a string value."""
  import html
  return html.escape(str(value or ""))


def _issue_value(item: dict[str, Any], *keys: str, default: Any = "") -> Any:
  for key in keys:
    value = item.get(key) if isinstance(item, dict) else None
    if value not in (None, "", [], {}):
      return value
  return default


def _compact_text(value: Any, limit: int = 170) -> str:
  text = " ".join(str(value or "").split())
  if len(text) <= limit:
    return text
  cut = text[:limit].rsplit(" ", 1)[0]
  return f"{cut}..." if cut else text[:limit]


def _issue_id(item: dict[str, Any]) -> str:
  return str(_issue_value(item, "issueId", "id", default=""))


def _issue_lens(item: dict[str, Any]) -> str:
  return str(_issue_value(item, "auditLens", "lens", default=""))


def _issue_affected(item: dict[str, Any]) -> str:
  return str(_issue_value(item, "affected", "affectedPagesTemplatesFilesOrRoutes", "affectedPages", "targets", default=""))


def _issue_evidence(item: dict[str, Any]) -> str:
  return str(_issue_value(item, "evidenceObserved", "evidence", "observedEvidence", default=""))


def _issue_remediation(item: dict[str, Any]) -> str:
  return str(_issue_value(item, "exactRemediation", "remediation", "fix", default=""))


def render_issue_summary_table(items: list[dict[str, Any]]) -> str:
  if not items:
    return "<p>No significant issues were confirmed from the available evidence.</p>"
  rows = ""
  for item in items:
    severity = str(_issue_value(item, "severity", default=""))
    severity_class = {"Critical": "sev-critical", "High": "sev-high", "Medium": "sev-medium"}.get(severity, "")
    rows += (
      f"<tr class='{severity_class}'>"
      f"<td>{_esc(_issue_id(item))}</td>"
      f"<td>{_esc(severity)}</td>"
      f"<td>{_esc(_issue_value(item, 'confidence', default=''))}</td>"
      f"<td>{_esc(_issue_lens(item))}</td>"
      f"<td><code>{_esc(_compact_text(_issue_affected(item), 130))}</code></td>"
      f"<td>{_esc(_compact_text(_issue_evidence(item), 220))}</td>"
      f"<td>{_esc(_compact_text(_issue_remediation(item), 240))}</td>"
      f"</tr>"
    )
  return (
    "<table class='tight issue-summary'>"
    "<thead><tr><th>ID</th><th>Severity</th><th>Confidence</th><th>Lens</th>"
    "<th>Affected</th><th>Evidence observed</th><th>Exact remediation</th></tr></thead>"
    f"<tbody>{rows}</tbody></table>"
  )


def render_issue_record_cards(items: list[dict[str, Any]]) -> str:
  if not items:
    return "<p>No full issue records were supplied by the analysis context.</p>"
  cards: list[str] = []
  for item in items:
    issue_id = _issue_id(item) or "Unnumbered issue"
    severity = str(_issue_value(item, "severity", default="Not classified"))
    fields = [
      ("Audit lens", _issue_lens(item)),
      ("Root cause level", _issue_value(item, "rootCauseLevel", "rootCause", default="")),
      ("Affected page(s), template(s), file(s), or route(s)", _issue_affected(item)),
      ("Evidence observed", _issue_evidence(item)),
      ("Why it matters", _issue_value(item, "whyItMatters", "impact", default="")),
      ("Exact remediation", _issue_remediation(item)),
      ("Expected gain", _issue_value(item, "expectedGain", default="")),
      ("Estimated effort", _issue_value(item, "estimatedEffort", "effort", default="")),
      ("Recommended owner", _issue_value(item, "recommendedOwner", "owner", default="")),
      ("Verification method", _issue_value(item, "verificationMethod", "verification", default="")),
    ]
    body = "".join(
      f"<div class='issue-field'><strong>{_esc(label)}:</strong> {_esc(value)}</div>"
      for label, value in fields
      if value not in (None, "", [], {})
    )
    chips = (
      f"<span class='issue-chip'>{_esc(severity)}</span>"
      f"<span class='issue-chip'>{_esc(_issue_value(item, 'confidence', default='Confidence not stated'))}</span>"
      f"<span class='issue-chip'>{_esc(_issue_value(item, 'estimatedEffort', 'effort', default='Effort not stated'))}</span>"
    )
    cards.append(
      f"<article class='issue-record'>"
      f"<h3>{_esc(issue_id)} - {_esc(severity)}</h3>"
      f"<div class='issue-meta'>{chips}</div>"
      f"{body}"
      f"</article>"
    )
  return "".join(cards)


def render_llm_issues_table(llm_issues: list[dict[str, Any]]) -> str:
  return render_issue_summary_table(llm_issues)


def render_llm_remediation_table(items: list[dict[str, Any]]) -> str:
  if not items:
    return ""
  cards: list[str] = []
  for item in items:
    issue_id = _esc(item.get("issueId", "Unmapped issue"))
    target = _esc(item.get("target", "Affected source path or route family"))
    current = _esc(item.get("currentPattern", "See issue evidence."))
    corrected = _esc(item.get("correctedPattern", "Apply the issue remediation exactly."))
    rationale = _esc(item.get("rationale", "This change resolves the affected audit issue."))
    verification = _esc(item.get("verificationMethod") or item.get("verification") or "Rerun the audit and confirm the issue-specific evidence changes in coverage.json and report.html.")
    cards.append(
      f"<article class='remediation-card'>"
      f"<h3>{issue_id}: <code>{target}</code></h3>"
      f"<p><strong>Current pattern:</strong> {current}</p>"
      f"<p><strong>Corrected pattern:</strong> {corrected}</p>"
      f"<p><strong>Rationale:</strong> {rationale}</p>"
      f"<p><strong>Verification:</strong> {verification}</p>"
      f"</article>"
    )
  return "".join(cards)

def render_llm_page_type_table(items: list[dict[str, Any]]) -> str:
  if not items:
    return ""
  rows = "".join(
    f"<tr>"
    f"<td>{_esc(item.get('pageType', ''))}</td>"
    f"<td>{_esc(item.get('count', ''))}</td>"
    f"<td>{_esc(item.get('coverageState', ''))}</td>"
    f"<td>{_esc(item.get('score', ''))}</td>"
    f"<td>{_esc(item.get('grade', ''))}</td>"
    f"<td>{_esc(item.get('judgement', ''))}</td>"
    f"<td>{_esc(item.get('keyNote', ''))}</td>"
    f"</tr>"
    for item in items
  )
  return (
    "<table class='tight'>"
    "<thead><tr><th>Page type</th><th>Count</th><th>Coverage</th>"
    "<th>Score</th><th>Grade</th><th>Judgement</th><th>Key note</th></tr></thead>"
    f"<tbody>{rows}</tbody></table>"
  )


def render_llm_gap_matrix(items: list[dict[str, Any]]) -> str:
  if not items:
    return ""
  rows = "".join(
    f"<tr>"
    f"<td>{_esc(item.get('pageType', ''))}</td>"
    f"<td>{_esc(item.get('seo', ''))}</td>"
    f"<td>{_esc(item.get('aeo', ''))}</td>"
    f"<td>{_esc(item.get('geo', ''))}</td>"
    f"<td>{_esc(item.get('confidence', ''))}</td>"
    f"<td>{_esc(item.get('topMissingElement', ''))}</td>"
    f"<td>{_esc(item.get('businessImpact', ''))}</td>"
    f"</tr>"
    for item in items
  )
  return (
    "<table class='tight'>"
    "<thead><tr><th>Page type</th><th>SEO</th><th>AEO</th><th>GEO</th>"
    "<th>Confidence</th><th>Top missing element</th><th>Business impact</th></tr></thead>"
    f"<tbody>{rows}</tbody></table>"
  )


def main() -> int:
  global args
  args = parse_args()
  base_url = args.base_url.rstrip("/")
  excludes = [item.strip() for item in args.exclude_prefixes.split(",") if item.strip()]
  output_dir = ensure_dir(Path(args.output_dir))

  workbook, discovered, discovery_meta = build_complete_inventory(base_url, excludes)
  pages = crawl_and_analyse(base_url, discovered, excludes)
  coverage_rows = family_coverage(pages)
  validate_full_coverage(coverage_rows)
  repo_signals = build_repo_signals(REPO_ROOT, base_url)
  family_diagnostics = build_family_diagnostics(pages)
  issues = collect_issues(pages, discovered, repo_signals=repo_signals, family_diagnostics=family_diagnostics)
  template_annex = build_template_annex(pages)
  template_diagnostics = build_template_diagnostics(template_annex, family_diagnostics)
  source_ledger = build_source_ledger(discovery_meta, workbook, repo_signals)
  source_mismatches = build_source_mismatches(discovered, pages, workbook, repo_signals)
  gap_matrix = build_gap_matrix(pages)
  page_type_findings = build_page_type_findings(pages)
  priority_pages = build_priority_pages(pages)

  # ── LLM forensic analysis ────────────────────────────────────────────────────
  live_dynamic_urls = extract_live_dynamic_urls(pages, discovered)
  claude_analysis: dict[str, Any] | None = None
  analysis_attempts: list[dict[str, str]] = []

  # 1. Preferred path: AI Management Suite /analysis endpoint backed by the shared AI service wrapper.
  if args.callback_url and args.callback_token:
    analysis_url = derive_analysis_url(args.callback_url, getattr(args, "analysis_url", None))
    if analysis_url:
      print(f"[analysis] calling external LLM analysis endpoint at {analysis_url}", file=sys.stderr)
      claude_analysis = call_analysis_endpoint(
        analysis_url=analysis_url,
        callback_token=args.callback_token,
        session_id=args.session_id,
        base_url=base_url,
        pages=pages,
        priority_pages_raw=priority_pages,
        issues=issues,
        coverage_rows=coverage_rows,
        coverage_families=family_coverage(pages),
        repo_signals=repo_signals,
        live_dynamic_urls=live_dynamic_urls,
        workbook=workbook,
        discovery_meta=discovery_meta,
        source_ledger=source_ledger,
        source_mismatches=source_mismatches,
        family_diagnostics=family_diagnostics,
        template_diagnostics=template_diagnostics,
      )
      if claude_analysis:
        analysis_attempts.append({"path": "AI Management Suite /analysis", "status": "success", "detail": analysis_url})
        print("[analysis] LLM analysis received successfully", file=sys.stderr)
      else:
        detail = getattr(call_analysis_endpoint, "last_detail", analysis_url) or analysis_url
        analysis_attempts.append({"path": "AI Management Suite /analysis", "status": "failed", "detail": detail})
        print("[analysis] endpoint failed; audit will not be marked complete unless another AI path succeeds", file=sys.stderr)
    else:
      analysis_attempts.append({"path": "AI Management Suite /analysis", "status": "not-configured", "detail": "callback_url did not produce an analysis endpoint"})

  # 2. Direct model calls from the website workflow are intentionally disabled.
  # Provider resolution is centralised in the AI Management Suite shared ai-config.js
  # so audit provider/env failures are diagnosed in one production runtime.
  if not claude_analysis:
    analysis_attempts.append({
      "path": "Direct OpenRouter model path",
      "status": "disabled",
      "detail": "Provider resolution is centralised in AI Management Suite services/shared/utils/ai-config.js",
    })

  missing_callback_reason = callback_config_missing_reason(args.callback_url, args.callback_token)
  if missing_callback_reason:
    analysis_attempts.append({"path": "AI Management Suite /analysis", "status": "not-configured", "detail": missing_callback_reason})

  if not claude_analysis:
    print("[analysis] AI forensic analysis unavailable — writing failed-gate report", file=sys.stderr)
  # ─────────────────────────────────────────────────────────────────────────────

  real_failed_url_count = sum(1 for row in coverage_rows if row.get("failed", 0))
  completion_state = "Complete" if claude_analysis and real_failed_url_count == 0 else ("Incomplete" if claude_analysis else "Failed-gate")
  analysis_state: dict[str, Any] = {
    "available": bool(claude_analysis),
    "completionState": completion_state,
    "statusLabel": "AI forensic analysis available" if claude_analysis else "AI FORENSIC ANALYSIS UNAVAILABLE",
    "failureReason": "" if claude_analysis else (
      next((attempt.get("detail") for attempt in analysis_attempts if attempt.get("path") == "AI Management Suite /analysis" and attempt.get("status") in {"failed", "not-configured"} and attempt.get("detail")), "")
      or "The AI-assisted forensic analysis did not return a validated JSON payload after the configured AI analysis paths were attempted."
    ),
    "attempts": analysis_attempts,
    "skippedSections": [] if claude_analysis else AI_REQUIRED_SECTIONS,
    "restoreSteps": [] if claude_analysis else AI_RESTORE_STEPS,
  }

  coverage_json = {
    "generatedAt": utc_now(),
    "websiteUrl": base_url,
    "workbook": {
      "path": workbook.path,
      "sheet": workbook.primary_sheet,
      "rows": workbook.url_count,
    },
    "sourceCounts": discovery_meta["sourceCounts"],
    "sourceLedger": source_ledger,
    "sourceMismatchesThatMatter": source_mismatches,
    "repoSignals": repo_signals,
    "familyDiagnostics": family_diagnostics,
    "templateDiagnostics": template_diagnostics,
    "pageFamilyCoverage": coverage_rows,
    "auditCompletionState": analysis_state["completionState"],
    "aiAnalysisStatus": analysis_state["statusLabel"],
    "aiAnalysisAttempts": analysis_state["attempts"],
    "urls": [make_url_entry(page) for page in pages],
  }
  summary = build_summary(base_url, pages, issues, coverage_rows, args.report_prefix, workbook, analysis_state, args.session_id)

  coverage_path = write_json(output_dir / "coverage.json", coverage_json)
  summary_path = write_json(output_dir / "summary.json", summary)

  # ── R2 upload — dedicated audits bucket only ────────────────────────────────
  uploaded: dict[str, str] = {}
  r2_bucket, r2_public_base = require_audit_r2_config(args.callback_url)
  if r2_bucket and r2_public_base:
    try:
      r2_client = build_r2_client()
      artefact_files: dict[str, Path] = {
        "summary.json": summary_path,
        "coverage.json": coverage_path,
      }
      uploaded = upload_selected_files_to_r2(
        r2_client, r2_bucket, args.report_prefix, artefact_files, r2_public_base
      )
    except Exception as exc:
      if args.callback_url:
        raise
      print(f"[r2] audit upload failed (non-fatal local run): {exc}", file=sys.stderr)
  else:
    print("[r2] R2_BUCKET_AUDITS/R2_PUBLIC_BASE_URL_AUDITS not set — skipping local R2 upload", file=sys.stderr)
  # ─────────────────────────────────────────────────────────────────────────────

  report_html = build_report(
    base_url, workbook, discovery_meta, pages, issues, coverage_rows,
    template_annex, gap_matrix, page_type_findings, priority_pages,
    uploaded, claude_analysis=claude_analysis, analysis_state=analysis_state,
    source_ledger=source_ledger, source_mismatches=source_mismatches, template_diagnostics=template_diagnostics,
  )
  report_path = write_text(output_dir / "report.html", report_html)
  print(f"[report] written to {report_path}", file=sys.stderr)

  # ── R2 upload report — dedicated audits bucket only ─────────────────────────
  if r2_bucket:
    try:
      r2_client = build_r2_client()
      uploaded = upload_selected_files_to_r2(
        r2_client, r2_bucket, args.report_prefix,
        {"summary.json": summary_path, "coverage.json": coverage_path, "report.html": report_path},
        r2_public_base,
      )
    except Exception as exc:
      if args.callback_url:
        raise
      print(f"[r2] audit report upload failed (non-fatal local run): {exc}", file=sys.stderr)

  # ── Callback — optional ───────────────────────────────────────────────────────
  callback_payload = {
    "auditType": "seo-aeo-geo",
    "sessionId": args.session_id,
    "status": "completed" if claude_analysis else "failed",
    "auditCompletionState": analysis_state["completionState"],
    "aiAnalysisStatus": analysis_state["statusLabel"],
    "message": "Full AI-assisted forensic analysis completed." if claude_analysis else "AI FORENSIC ANALYSIS UNAVAILABLE: failed-gate report generated; no release-ready verdict issued.",
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html", str(report_path)),
    "summaryUrl": uploaded.get("summary.json", str(summary_path)),
    "coverageUrl": uploaded.get("coverage.json", str(coverage_path)),
    "issueCount": len(issues),
    "auditedUrlCount": len(pages),
    "artefacts": uploaded,
    "auditBucket": r2_bucket,
    "auditPublicBaseUrl": r2_public_base,
    "finishedAt": utc_now(),
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  try:
    post_callback(args.callback_url, args.callback_token, callback_payload)
  except Exception as exc:
    print(f"[callback] post failed (non-fatal): {exc}", file=sys.stderr)

  return 0


if __name__ == "__main__":
  raise SystemExit(main())
