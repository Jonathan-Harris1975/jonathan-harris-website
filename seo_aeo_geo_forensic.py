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
  args = parser.parse_args()
  resolve_runtime_callback_config(args)
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
    "evidenceObserved": evidence,
    "whyItMatters": why,
    "exactRemediation": remediation,
    "expectedGain": "Stronger crawl, answer extraction, and generative retrieval quality",
    "estimatedEffort": effort,
    "recommendedOwner": owner,
    "verificationMethod": "Rerun the SEO + AEO + GEO audit and confirm the affected URL, template, or route returns the expected evidence state in coverage.json and report.html.",
  }


def collect_issues(pages: list[dict[str, Any]], discovered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
  issues: list[dict[str, Any]] = []
  counter = 1

  failed_pages = [page for page in pages if page.get("coverageState") == "Failed to fetch"]
  if failed_pages:
    issues.append(issue_record(
      f"SEO-{counter:03d}",
      "Critical",
      "Confirmed",
      "Technical",
      "route",
      ", ".join(page["url"] for page in failed_pages[:5]),
      f"{len(failed_pages)} in-scope URLs did not return 200.",
      "Non-200 in-scope pages break full-estate coverage and weaken crawl reliability.",
      "Fix the failing routes or explicitly exclude them with evidence before rerunning the audit.",
      "Medium",
    ))
    counter += 1

  workbook_only = [entry for entry in discovered.values() if "workbook" in entry["sources"] and "repo" not in entry["sources"]]
  repo_only = [entry for entry in discovered.values() if "repo" in entry["sources"] and "workbook" not in entry["sources"] and classify_page(entry["url"]) != "podcast episode"]
  if workbook_only:
    issues.append(issue_record(
      f"SEO-{counter:03d}",
      "High",
      "Confirmed",
      "Technical",
      "workbook mismatch",
      ", ".join(item["path"] for item in workbook_only[:5]),
      f"Workbook-only URLs remain: {', '.join(item['path'] for item in workbook_only[:8])}.",
      "Workbook-governed routes missing from the repo weaken source-of-truth integrity.",
      "Restore or retire the workbook-only URLs and keep the workbook aligned to the published estate.",
      "Low",
    ))
    counter += 1
  if repo_only:
    issues.append(issue_record(
      f"SEO-{counter:03d}",
      "Medium",
      "Confirmed",
      "Technical",
      "workbook mismatch",
      ", ".join(item["path"] for item in repo_only[:5]),
      f"Repo-only URLs remain: {', '.join(item['path'] for item in repo_only[:8])}.",
      "Repo routes that are absent from the workbook dilute governance and estate reconciliation quality.",
      "Add the missing repo routes to the workbook when they are intended to remain live.",
      "Low",
    ))
    counter += 1

  family_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    if is_analysed_state(page.get("coverageState", "")):
      family_groups[page["pageType"]].append(page)

  for page_type, family_pages in sorted(family_groups.items()):
    if not family_pages:
      continue
    avg_aeo = mean(page["scores"]["aeo"] for page in family_pages)
    avg_geo = mean(page["scores"]["geo"] for page in family_pages)
    missing_desc = [page for page in family_pages if not page["meta"]["metaDescription"]]
    missing_canonical = [page for page in family_pages if not page["meta"]["canonical"]]
    weak_intro = [page for page in family_pages if len(page["introText"].split()) < 35]
    no_questions = [page for page in family_pages if not page["questionHeadings"]]

    if missing_desc:
      issues.append(issue_record(
        f"SEO-{counter:03d}",
        "Medium",
        "Confirmed",
        "SEO",
        "template",
        f"{page_type} ({len(missing_desc)} URLs)",
        f"Missing meta descriptions on {len(missing_desc)} {page_type} URL(s).",
        "Missing descriptions reduce SERP control and weaken answer-engine summaries.",
        "Add unique meta descriptions to the affected template or page family and align them to the opening summary.",
        "Medium",
        "SEO",
      ))
      counter += 1
    if missing_canonical:
      issues.append(issue_record(
        f"SEO-{counter:03d}",
        "Medium",
        "Confirmed",
        "Technical",
        "template",
        f"{page_type} ({len(missing_canonical)} URLs)",
        f"Canonical tags are missing on {len(missing_canonical)} {page_type} URL(s).",
        "Canonical gaps weaken route normalisation and duplication control.",
        "Emit absolute canonical tags from the affected template family.",
        "Medium",
      ))
      counter += 1
    if avg_aeo < 10 and len(family_pages) >= 1:
      issues.append(issue_record(
        f"SEO-{counter:03d}",
        "Medium",
        "Confirmed",
        "AEO",
        "template",
        f"{page_type} ({len(family_pages)} URLs)",
        f"Average AEO score for {page_type} is {avg_aeo:.1f}/20. {len(no_questions)} URLs lack question-led headings and {len(weak_intro)} have weak opening summaries.",
        "Weak answer formatting makes the family less extractable for answer engines and zero-click surfaces.",
        "Add answer-first summaries, extractable subheadings, and direct response blocks to the affected family.",
        "Medium",
        "Content",
      ))
      counter += 1
    if avg_geo < 12 and len(family_pages) >= 1:
      issues.append(issue_record(
        f"SEO-{counter:03d}",
        "Medium",
        "Confirmed",
        "GEO",
        "template",
        f"{page_type} ({len(family_pages)} URLs)",
        f"Average GEO score for {page_type} is {avg_geo:.1f}/20.",
        "Low generative-search readiness weakens citation likelihood and summarisation quality.",
        "Strengthen opening context, entity cues, schema support, and reusable explanatory passages across the family.",
        "Medium",
        "Content",
      ))
      counter += 1

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
    rows.append({
      "pageType": page_type,
      "pagesAffected": len(family_pages),
      "sourceFile": representative_family_source(page_type),
      "averageScore": avg_score,
      "repeatedStrengths": repeated_strengths or ["No repeated strengths confirmed beyond baseline rendering and metadata."],
      "repeatedDefects": repeated_defects or ["No repeated family-level defect was strong enough to elevate into a template issue."],
      "fixPriority": "High" if avg_score and avg_score < 75 else ("Medium" if avg_score and avg_score < 85 else "Low"),
    })
  return rows

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
    top_missing = "Question-led headings" if sum(1 for page in score_pages if not page["questionHeadings"]) >= max(1, len(score_pages) // 2) else "Stronger opening summaries"
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
    findings.append({
      "pageType": page_type,
      "count": len(family_pages),
      "averageScore": round(mean(scores), 1) if scores else 0,
      "lowestScore": min(scores) if scores else 0,
      "highestScore": max(scores) if scores else 0,
      "exampleUrl": family_pages[0]["url"],
      "coverageState": coverage_state,
    })
  return findings

def build_priority_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  candidate_pages = [page for page in pages if is_analysed_state(page["coverageState"]) or page["coverageState"] == "Failed to fetch"]
  family_best: dict[str, dict[str, Any]] = {}
  family_worst: dict[str, dict[str, Any]] = {}
  for page in candidate_pages:
    page_type = page["pageType"]
    if page_type not in family_best or page["total"] > family_best[page_type]["total"]:
      family_best[page_type] = page
    if page_type not in family_worst or page["total"] < family_worst[page_type]["total"]:
      family_worst[page_type] = page
  selected = {page["url"]: page for page in family_worst.values()}
  for page in candidate_pages:
    if page["pageType"] in IMPORTANT_PAGE_TYPES:
      selected.setdefault(page["url"], page)
  return sorted(selected.values(), key=lambda page: (page["total"], page["pageType"]))[:30]

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
    "workbookSource": "jonathan-harris-site-url-inventory-remediated-release-ready.xlsx",
    "sitemapFeedSource": "sitemap.xml, local sitemap snapshot, podcast RSS feed, blog and podcast manifests, live internal links",
    "liveFetchStatus": "Live route responses fetched during workflow execution; fetch failures are recorded URL-by-URL.",
    "generatedArtefactPaths": artefacts,
  }


def build_report(base_url: str, workbook: WorkbookInfo, discovery_meta: dict[str, Any], pages: list[dict[str, Any]], issues: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], template_annex: list[dict[str, Any]], gap_matrix: list[dict[str, Any]], page_type_findings: list[dict[str, Any]], priority_pages: list[dict[str, Any]], artefacts: dict[str, str], claude_analysis: dict[str, Any] | None = None, analysis_state: dict[str, Any] | None = None) -> str:
  analysis_state = analysis_state or {
    "available": bool(claude_analysis),
    "completionState": "Complete" if claude_analysis else "Failed-gate",
    "statusLabel": "AI forensic analysis available" if claude_analysis else "AI FORENSIC ANALYSIS UNAVAILABLE",
    "failureReason": "",
    "attempts": [],
  }
  ai_available = bool(claude_analysis)
  failed_gate = not ai_available
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

  # Issue and remediation tables
  active_issues_html = render_llm_issues_table(llm_issues_list) if llm_issues_list else (
    "<table class='tight'><thead><tr><th>ID</th><th>Severity</th><th>Confidence</th><th>Lens</th><th>Root cause</th><th>Affected</th><th>Evidence</th><th>Why it matters</th><th>Exact remediation</th><th>Expected gain</th><th>Effort</th><th>Owner</th><th>Verification</th></tr></thead>"
    f"<tbody>{issue_rows}</tbody></table>"
  )
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
    pre code{{display:block;white-space:pre-wrap;word-break:break-all;font-size:11px;background:#f3f4f6;padding:8px;border-radius:6px;}}
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

  <section id="page-types">
    <h2>Page-type findings</h2>
    {active_page_types_html if active_page_types_html else f"<table class='tight'><thead><tr><th>Page type</th><th>Count</th><th>Coverage state</th><th>Average score</th><th>Range</th><th>Example</th></tr></thead><tbody>{page_type_rows}</tbody></table>"}
  </section>

  <section id="priority">
    <h2>Priority page annex</h2>
    <table class="tight"><thead><tr><th>URL</th><th>Type</th><th>Status</th><th>Title</th><th>Meta</th><th>Canonical</th><th>AEO</th><th>GEO</th><th>Total</th><th>Grade</th></tr></thead><tbody>{priority_rows}</tbody></table>
  </section>

  <section id="templates">
    <h2>Template / component / generator annex</h2>
    <table class="tight"><thead><tr><th>Page family</th><th>Pages</th><th>Source</th><th>Average score</th><th>Repeated strengths</th><th>Repeated defects</th><th>Fix priority</th></tr></thead><tbody>{template_rows}</tbody></table>
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

def build_repo_signals(repo_root: Path) -> dict:
  """Extracts known repo-level signals relevant to the LLM audit context."""
  signals: dict[str, Any] = {}

  governance_script = repo_root / "scripts" / "check_ungoverned_routes.py"
  excludes_in_governance: list[str] = []
  if governance_script.exists():
    src = governance_script.read_text(encoding="utf-8")
    excludes_in_governance = re.findall(r'["\']([^"\']+/)["\']', src)
  signals["governanceScriptExcludes"] = excludes_in_governance

  ebook_pipeline = repo_root / "scripts" / "ebook_pipeline.py"
  ebook_trim = None
  if ebook_pipeline.exists():
    src = ebook_pipeline.read_text(encoding="utf-8")
    m = re.search(r'\[:(\d+)\]', src)
    if m:
      ebook_trim = int(m.group(1))
  signals["ebookPipelineTrimLimit"] = ebook_trim

  blog_manifest = repo_root / "blog" / "posts.json"
  blog_count = 0
  if blog_manifest.exists():
    try:
      data = json.loads(blog_manifest.read_text(encoding="utf-8"))
      items = data.get("items") or data.get("posts") or []
      blog_count = len(items)
    except Exception:
      pass
  signals["blogManifestPath"] = "blog/posts.json"
  signals["blogManifestCount"] = blog_count

  podcast_manifest = repo_root / "data" / "podcast-episodes.json"
  podcast_count = 0
  known_broken_redirects: list[dict[str, Any]] = []
  if podcast_manifest.exists():
    try:
      data = json.loads(podcast_manifest.read_text(encoding="utf-8"))
      items = data if isinstance(data, list) else data.get("items") or data.get("episodes") or []
      podcast_count = len(items)
    except Exception:
      pass
  signals["podcastManifestPath"] = "data/podcast-episodes.json"
  signals["podcastManifestCount"] = podcast_count

  redirects_file = repo_root / "_redirects"
  if redirects_file.exists():
    lines = redirects_file.read_text(encoding="utf-8").splitlines()
    for line in lines:
      parts = line.strip().split()
      if len(parts) >= 2 and parts[0].startswith("/podcast/"):
        known_broken_redirects.append({"from": parts[0], "to": parts[1]})
  signals["knownRedirects"] = known_broken_redirects[:20]

  llms_txt = repo_root / "llms.txt"
  llm_index = repo_root / "llm-index.json"
  llms_scope = "unknown"
  if llms_txt.exists():
    content = llms_txt.read_text(encoding="utf-8").lower()
    if "ebook" in content and "podcast" not in content and "blog" not in content:
      llms_scope = "ebook-only"
    elif "podcast" in content or "transcript" in content or "blog" in content:
      llms_scope = "broad"
    else:
      llms_scope = "narrow"
  signals["llmsFiles"] = [f for f in ["llms.txt", "llm-index.json"] if (repo_root / f).exists()]
  signals["llmsScope"] = llms_scope

  generator_scripts = [
    str(p.relative_to(repo_root))
    for p in repo_root.rglob("*.py")
    if any(token in p.name for token in ("generate", "pipeline", "inject"))
  ] + [
    str(p.relative_to(repo_root))
    for p in repo_root.rglob("*.mjs")
    if "generate" in p.name
  ]
  signals["generatorScripts"] = generator_scripts[:15]
  signals["functionsPresent"] = [
    str(p.relative_to(repo_root))
    for p in (repo_root / "functions").rglob("*.js")
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
SECTION 7: AUDIT INSTRUCTION

Perform the full forensic SEO + AEO + GEO audit using the context package above.

Apply these mandatory special rules:

BLOG ENFORCEMENT:
Analyse the blog family as a whole: governance drift between repo manifest and live archive, standfirst
duplication on post pages, whether the archive exposes a strong crawlable listing, whether feed-derived
posts carry full metadata and schema, and whether blog content is structured for passage extraction.

PODCAST ENFORCEMENT:
Separately analyse: podcast hub, episode pages, transcript archive, transcript leaf pages.
Flag: absence of server-rendered episode cards on the hub, thin episode pages, unchunked transcript
bodies, broken compatibility redirect chains, exemption of podcast/episodes/ from release governance.
Assess whether episode and transcript pages behave as answer hubs or as thin landing pages.

GEO ENFORCEMENT:
Assess llms.txt and llm-index.json scope explicitly. If ebook-only, flag as confirmed deficiency.
Assess whether topic guides, glossary, comparisons, blog posts, and transcript pages are machine-readable
discovery assets that are being wasted by omission from llms files.

EBOOK ENFORCEMENT:
The hard 64-character H3 trim in scripts/ebook_pipeline.py is a confirmed defect affecting all ebook
detail pages. Treat this as a High issue with exact code remediation required.

GOVERNANCE ENFORCEMENT:
The exclusion of blog/posts/ and podcast/episodes/ from scripts/check_ungoverned_routes.py is a
confirmed Critical governance blind spot. Exact remediation must name the file, the exclusion list variable,
and the corrected logic.

ISSUE NUMBERING: Use JH-SEO-NNN, JH-AEO-NNN, JH-GEO-NNN, JH-TECH-NNN prefixes.
Start numbering at 001. Order issues Critical -> High -> Medium -> Low within each prefix group.

SCORE CALIBRATION:
- Static governed pages (topic guides, book pages, bio, homepage): expected range B to B+
- Dynamic families with governance gaps (podcast, blog): expected range D to C
- Podcast hub (no server-rendered episode list, exempted from governance): expected D
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


def render_llm_issues_table(llm_issues: list[dict[str, Any]]) -> str:
  if not llm_issues:
    return "<p>No issues returned from LLM analysis.</p>"
  rows = ""
  for item in llm_issues:
    severity_class = {"Critical": "sev-critical", "High": "sev-high", "Medium": "sev-medium"}.get(item.get("severity", ""), "")
    rows += (
      f"<tr class='{severity_class}'>"
      f"<td>{_esc(item.get('issueId', ''))}</td>"
      f"<td>{_esc(item.get('severity', ''))}</td>"
      f"<td>{_esc(item.get('confidence', ''))}</td>"
      f"<td>{_esc(item.get('lens', ''))}</td>"
      f"<td><code>{_esc(item.get('affected', ''))}</code></td>"
      f"<td>{_esc(item.get('evidenceObserved', ''))}</td>"
      f"<td>{_esc(item.get('whyItMatters', ''))}</td>"
      f"<td>{_esc(item.get('exactRemediation', ''))}</td>"
      f"<td>{_esc(item.get('expectedGain', ''))}</td>"
      f"<td>{_esc(item.get('estimatedEffort', ''))}</td>"
      f"<td>{_esc(item.get('recommendedOwner', ''))}</td>"
      f"<td>{_esc(item.get('verificationMethod', item.get('verification', '')))}</td>"
      f"</tr>"
    )
  return (
    "<table class='tight'>"
    "<thead><tr><th>ID</th><th>Severity</th><th>Confidence</th><th>Lens</th>"
    "<th>Affected</th><th>Evidence</th><th>Why it matters</th><th>Exact remediation</th><th>Expected gain</th><th>Effort</th><th>Owner</th><th>Verification</th>"
    "</tr></thead>"
    f"<tbody>{rows}</tbody></table>"
  )


def render_llm_remediation_table(items: list[dict[str, Any]]) -> str:
  if not items:
    return ""
  rows = "".join(
    f"<tr>"
    f"<td><code>{_esc(item.get('target', ''))}</code></td>"
    f"<td>{_esc(item.get('issueId', ''))}</td>"
    f"<td><pre><code>{_esc(item.get('currentPattern', ''))}</code></pre></td>"
    f"<td><pre><code>{_esc(item.get('correctedPattern', ''))}</code></pre></td>"
    f"<td>{_esc(item.get('rationale', ''))}</td>"
    f"</tr>"
    for item in items
  )
  return (
    "<table class='tight'>"
    "<thead><tr><th>Target file</th><th>Issue ID</th><th>Current pattern</th>"
    "<th>Corrected pattern</th><th>Rationale</th></tr></thead>"
    f"<tbody>{rows}</tbody></table>"
  )


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
  issues = collect_issues(pages, discovered)
  template_annex = build_template_annex(pages)
  gap_matrix = build_gap_matrix(pages)
  page_type_findings = build_page_type_findings(pages)
  priority_pages = build_priority_pages(pages)

  # ── LLM forensic analysis ────────────────────────────────────────────────────
  repo_signals = build_repo_signals(REPO_ROOT)
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
    "pageFamilyCoverage": coverage_rows,
    "auditCompletionState": analysis_state["completionState"],
    "aiAnalysisStatus": analysis_state["statusLabel"],
    "aiAnalysisAttempts": analysis_state["attempts"],
    "urls": [make_url_entry(page) for page in pages],
  }
  summary = build_summary(base_url, pages, issues, coverage_rows, args.report_prefix, workbook, analysis_state, args.session_id)

  coverage_path = write_json(output_dir / "coverage.json", coverage_json)
  summary_path = write_json(output_dir / "summary.json", summary)

  # ── R2 upload — optional; skip gracefully if credentials are absent ──────────
  uploaded: dict[str, str] = {}
  r2_bucket = os.environ.get("R2_BUCKET_BRAND_ASSETS")
  if r2_bucket:
    try:
      r2_client = build_r2_client()
      artefact_files: dict[str, Path] = {
        "summary.json": summary_path,
        "coverage.json": coverage_path,
      }
      uploaded = upload_selected_files_to_r2(r2_client, r2_bucket, args.report_prefix, artefact_files)
    except Exception as exc:
      print(f"[r2] upload failed (non-fatal): {exc}", file=sys.stderr)
  else:
    print("[r2] R2_BUCKET_BRAND_ASSETS not set — skipping R2 upload", file=sys.stderr)
  # ─────────────────────────────────────────────────────────────────────────────

  report_html = build_report(
    base_url, workbook, discovery_meta, pages, issues, coverage_rows,
    template_annex, gap_matrix, page_type_findings, priority_pages,
    uploaded, claude_analysis=claude_analysis, analysis_state=analysis_state,
  )
  report_path = write_text(output_dir / "report.html", report_html)
  print(f"[report] written to {report_path}", file=sys.stderr)

  # ── R2 upload report — optional ───────────────────────────────────────────────
  if r2_bucket and uploaded:
    try:
      r2_client = build_r2_client()
      uploaded = upload_selected_files_to_r2(
        r2_client, r2_bucket, args.report_prefix,
        {"summary.json": summary_path, "coverage.json": coverage_path, "report.html": report_path},
      )
    except Exception as exc:
      print(f"[r2] report upload failed (non-fatal): {exc}", file=sys.stderr)

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
