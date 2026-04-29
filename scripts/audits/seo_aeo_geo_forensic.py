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
COVERED_STATES = {"Fully analysed", "Analysed through shared template plus page-specific checks"}
SHARED_TEMPLATE_FAMILIES = {"book page", "category / hub", "topic hub", "archive / pagination / utility"}


def coverage_state_for_page(page_type: str, status_code: int) -> str:
  if status_code != 200:
    return "Failed to fetch"
  if page_type in SHARED_TEMPLATE_FAMILIES:
    return "Analysed through shared template plus page-specific checks"
  return "Fully analysed"


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run the full-estate forensic SEO + AEO + GEO audit")
  parser.add_argument("--base-url", required=True)
  parser.add_argument("--session-id", required=True)
  parser.add_argument("--report-prefix", required=True)
  parser.add_argument("--callback-url")
  parser.add_argument("--callback-token")
  parser.add_argument("--output-dir", default="artifacts/seo-aeo-geo")
  parser.add_argument("--exclude-prefixes", default="")
  return parser.parse_args()


def base_host(base_url: str) -> str:
  return (urlparse(base_url).hostname or "").lower()


def is_in_scope_url(url: str, base_url: str) -> bool:
  parsed = urlparse(urljoin(base_url.rstrip("/") + "/", url))
  host = (parsed.hostname or "").lower()
  allowed_host = base_host(base_url)
  if not host or not allowed_host:
    return False
  return host == allowed_host or host.endswith(f".{allowed_host}")


def normalise_absolute_url(url: str, base_url: str) -> str:
  absolute = urljoin(base_url.rstrip("/") + "/", url)
  parsed = urlparse(absolute)
  scheme = parsed.scheme or "https"
  host = (parsed.netloc or base_host(base_url)).lower()
  path = parsed.path or "/"
  path = normalise_route(path)
  return f"{scheme}://{host}{path}"


def clean_link_candidate(href: str, base_url: str) -> str | None:
  href = (href or "").strip()
  if not href or href.startswith("#"):
    return None
  if href.startswith(("mailto:", "tel:", "javascript:")):
    return None
  absolute = normalise_absolute_url(href, base_url)
  parsed = urlparse(absolute)
  suffix = Path(parsed.path).suffix.lower()
  if suffix and suffix in BLOCKED_PATH_SUFFIXES:
    return None
  if not is_in_scope_url(absolute, base_url):
    return None
  return absolute


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
  if path.startswith("/podcast/episodes/"):
    return "podcast episode"
  if path.startswith("/podcast"):
    return "podcast hub"
  if path.startswith("/ebooks/") and path.count("/") > 2:
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
  if path.startswith("/podcast/episodes/"):
    return "/podcast/episodes"
  if path.startswith("/podcast"):
    return "/podcast"
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
      if candidate and is_in_scope_url(candidate, base_url):
        urls.append(normalise_absolute_url(candidate, base_url))
  return urls


def extract_internal_links(url: str, soup: BeautifulSoup, base_url: str) -> list[str]:
  discovered: list[str] = []
  for tag in soup.select("a[href], link[rel='canonical'][href]"):
    href = tag.get("href", "").strip()
    cleaned = clean_link_candidate(href, base_url)
    if cleaned:
      discovered.append(cleaned)
  return discovered


def add_discovered(discovered: dict[str, dict[str, Any]], url: str, source: str, base_url: str, **metadata: Any) -> str:
  normalised = normalise_absolute_url(url, base_url)
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


def inspect_url(entry: dict[str, Any], base_url: str) -> dict[str, Any]:
  url = entry["url"]
  fetched = fetch_html(url)
  challenge_reason = detect_challenge_page(fetched.get("status", 0), fetched.get("text", ""))
  if challenge_reason:
    raise RuntimeError(f"Live audit blocked on {url}: {challenge_reason}")

  soup = parse_html(fetched.get("text", ""))
  meta = extract_meta(soup)
  body_text = soup.get_text(" ", strip=True)
  main_node = soup.select_one("main") or soup.body or soup
  intro_text = " ".join(p.get_text(" ", strip=True) for p in main_node.select("p")[:3]).strip()
  question_headings = [h.get_text(" ", strip=True) for h in main_node.select("h2, h3") if "?" in h.get_text(" ", strip=True)]
  robots_tag = soup.select_one("meta[name='robots']")
  robots_content = robots_tag.get("content", "").lower() if robots_tag else ""
  canonical_target = meta["canonical"]
  canonical_normalised = normalise_absolute_url(canonical_target, base_url) if canonical_target else ""
  links = extract_internal_links(url, soup, base_url)
  cta_candidates = [
    a for a in soup.select("a[href]")
    if any(token in (a.get_text(" ", strip=True).lower() + " " + a.get("href", "").lower()) for token in ("contact", "newsletter", "amazon", "buy", "subscribe", "listen"))
  ]
  page_type = classify_page(url)
  page = {
    **entry,
    "status": fetched.get("status", 0),
    "finalUrl": fetched.get("url", url),
    "redirectChain": fetched.get("history", []),
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
  }


def collect_issues(pages: list[dict[str, Any]], discovered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
  issues: list[dict[str, Any]] = []
  counter = 1

  failed_pages = [page for page in pages if page["status"] != 200]
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
  repo_only = [entry for entry in discovered.values() if "repo" in entry["sources"] and "workbook" not in entry["sources"] and entry["pageType"] != "podcast episode"]
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
    family_groups[page["pageType"]].append(page)

  for page_type, family_pages in sorted(family_groups.items()):
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


def family_coverage(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  rows: list[dict[str, Any]] = []
  for family in ROUTE_FAMILY_ORDER:
    family_pages = family_map.get(family, [])
    if not family_pages:
      continue
    analysed = len([page for page in family_pages if page["coverageState"] in COVERED_STATES])
    rows.append({
      "pageType": family,
      "discovered": len(family_pages),
      "analysed": analysed,
      "failed": len(family_pages) - analysed,
      "coveragePercent": round((analysed / len(family_pages)) * 100, 1) if family_pages else 0,
      "averageScore": round(mean(page["total"] for page in family_pages), 1),
      "lowestScore": min(page["total"] for page in family_pages),
      "highestScore": max(page["total"] for page in family_pages),
    })
  return rows


def build_template_annex(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  rows: list[dict[str, Any]] = []
  for page_type, family_pages in sorted(family_map.items()):
    avg_score = round(mean(page["total"] for page in family_pages), 1)
    repeated_strengths = []
    repeated_defects = []
    if all(page["meta"]["canonical"] for page in family_pages):
      repeated_strengths.append("Canonical coverage is present across the family.")
    if all(page["meta"]["metaDescription"] for page in family_pages):
      repeated_strengths.append("Meta descriptions are present across the family.")
    if any(not page["questionHeadings"] for page in family_pages):
      repeated_defects.append("Question-led headings are missing on part of the family.")
    if any(len(page["introText"].split()) < 35 for page in family_pages):
      repeated_defects.append("Openings are too thin for strong answer-first extraction on some pages.")
    rows.append({
      "pageType": page_type,
      "pagesAffected": len(family_pages),
      "sourceFile": representative_family_source(page_type),
      "averageScore": avg_score,
      "repeatedStrengths": repeated_strengths or ["No repeated strengths confirmed beyond baseline rendering and metadata."],
      "repeatedDefects": repeated_defects or ["No repeated family-level defect was strong enough to elevate into a template issue."],
      "fixPriority": "High" if avg_score < 75 else ("Medium" if avg_score < 85 else "Low"),
    })
  return rows


def build_gap_matrix(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
  for page in pages:
    family_map[page["pageType"]].append(page)
  rows: list[dict[str, Any]] = []
  for page_type, family_pages in sorted(family_map.items()):
    avg_seo = mean(page["scores"]["technicalSeo"] + page["scores"]["onPageIntent"] for page in family_pages)
    avg_aeo = mean(page["scores"]["aeo"] for page in family_pages)
    avg_geo = mean(page["scores"]["geo"] for page in family_pages)
    top_missing = "Question-led headings" if sum(1 for page in family_pages if not page["questionHeadings"]) >= max(1, len(family_pages) // 2) else "Stronger opening summaries"
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
    scores = [page["total"] for page in family_pages]
    findings.append({
      "pageType": page_type,
      "count": len(family_pages),
      "averageScore": round(mean(scores), 1),
      "lowestScore": min(scores),
      "highestScore": max(scores),
      "exampleUrl": family_pages[0]["url"],
      "coverageState": "Fully analysed" if all(page["coverageState"] in COVERED_STATES for page in family_pages) else "Partial / failed",
    })
  return findings


def build_priority_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  family_best: dict[str, dict[str, Any]] = {}
  family_worst: dict[str, dict[str, Any]] = {}
  for page in pages:
    page_type = page["pageType"]
    if page_type not in family_best or page["total"] > family_best[page_type]["total"]:
      family_best[page_type] = page
    if page_type not in family_worst or page["total"] < family_worst[page_type]["total"]:
      family_worst[page_type] = page
  selected = {page["url"]: page for page in family_worst.values()}
  for page in pages:
    if page["pageType"] in IMPORTANT_PAGE_TYPES:
      selected.setdefault(page["url"], page)
  return sorted(selected.values(), key=lambda page: (page["total"], page["pageType"]))[:30]


def make_url_entry(page: dict[str, Any]) -> dict[str, Any]:
  return {
    "url": page["url"],
    "path": page["path"],
    "pageType": page["pageType"],
    "sources": sorted(page["sources"]),
    "canonical": page["canonicalNormalised"] or page["meta"]["canonical"] or "",
    "indexability": page["indexability"],
    "coverageState": page["coverageState"],
    "status": page["status"],
    "score": page["total"],
    "grade": page["grade"],
    "riskFlag": page["riskFlag"],
  }


def build_report(base_url: str, workbook: WorkbookInfo, discovery_meta: dict[str, Any], pages: list[dict[str, Any]], issues: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], template_annex: list[dict[str, Any]], gap_matrix: list[dict[str, Any]], page_type_findings: list[dict[str, Any]], priority_pages: list[dict[str, Any]], artefacts: dict[str, str]) -> str:
  overall_seo = round(mean((page["scores"]["technicalSeo"] + page["scores"]["onPageIntent"]) / 35 * 100 for page in pages))
  overall_aeo = round(mean(page["scores"]["aeo"] / 20 * 100 for page in pages))
  overall_geo = round(mean(page["scores"]["geo"] / 20 * 100 for page in pages))
  overall_entity = round(mean(page["scores"]["entity"] / 10 * 100 for page in pages))
  overall_conversion = round(mean((page["scores"]["conversion"] / 5 * 100) if page["scores"]["conversion"] else 100 for page in pages if page["pageType"] in {"lead generation", "comparison", "book hub", "book page", "service / product"})) if any(page["pageType"] in {"lead generation", "comparison", "book hub", "book page", "service / product"} for page in pages) else 0

  family_rows = "".join(
    f"<tr><td>{row['pageType']}</td><td>{row['discovered']}</td><td>{row['analysed']}</td><td>{row['failed']}</td><td>{row['coveragePercent']}%</td><td>{row['averageScore']}</td></tr>"
    for row in coverage_rows
  )
  issue_rows = "".join(
    f"<tr><td>{item['issueId']}</td><td>{item['severity']}</td><td>{item['auditLens']}</td><td>{item['affected']}</td><td>{item['whyItMatters']}</td><td>{item['exactRemediation']}</td></tr>"
    for item in issues
  ) or "<tr><td colspan='6'>No significant issues were confirmed from the available evidence.</td></tr>"
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

  labels = []
  if overall_seo >= 85 and overall_geo >= 85:
    labels.append("citation-ready")
  if overall_aeo < 70:
    labels.append("answer-engine weak")
  if any(row['coveragePercent'] < 100 for row in coverage_rows):
    labels.append("structurally weak")
  if not labels:
    labels.append("partially ready")

  quick_wins = issues[:5]
  top_actions = issues[:5]
  strongest_areas = sorted(coverage_rows, key=lambda row: row["averageScore"], reverse=True)[:3]
  weakest_areas = sorted(coverage_rows, key=lambda row: row["averageScore"])[:3]

  body = f"""
  <section id="cover">
    <h2>Cover page</h2>
    <p><strong>Report title:</strong> Full-Estate Forensic SEO + AEO + GEO Audit</p>
    <p><strong>Website:</strong> <a href="{base_url}">{base_url}</a></p>
    <p><strong>Workbook:</strong> <code>{Path(workbook.path).name}</code></p>
    <p><strong>Scope inspected:</strong> Full in-scope website estate including homepage, books, catalogue, topics, blog, podcast, archives, utilities, and programmatic families discovered from repo, workbook, sitemap, feed, and live internal links.</p>
    <p><strong>Analyst mode:</strong> Full-estate evidence-led HTML audit</p>
  </section>

  <section id="summary">
    <h2>Executive summary</h2>
    <div class="grid">
      <div class="kpi"><strong>Overall SEO</strong><div>{overall_seo}</div></div>
      <div class="kpi"><strong>Overall AEO</strong><div>{overall_aeo}</div></div>
      <div class="kpi"><strong>Overall GEO</strong><div>{overall_geo}</div></div>
      <div class="kpi"><strong>Entity Authority</strong><div>{overall_entity}</div></div>
      <div class="kpi"><strong>Conversion Support</strong><div>{overall_conversion}</div></div>
      <div class="kpi"><strong>Discovered URLs</strong><div>{len(pages)}</div></div>
    </div>
    <p>{' '.join(f'<span class="pill">{label}</span>' for label in labels)}</p>
    <p><strong>Top five priorities:</strong> {'; '.join(item['issueId'] + ' ' + item['whyItMatters'] for item in top_actions) if top_actions else 'No Critical or High issue required escalation from the available evidence.'}</p>
    <p><strong>Quick wins:</strong> {'; '.join(item['exactRemediation'] for item in quick_wins[:3]) if quick_wins else 'No immediate quick-win issue was confirmed.'}</p>
    <p><strong>Major risks:</strong> {'; '.join(item['whyItMatters'] for item in issues[:3]) if issues else 'No estate-wide blocker was confirmed.'}</p>
    <p><strong>Strongest areas:</strong> {'; '.join(f"{row['pageType']} ({row['averageScore']})" for row in strongest_areas)}</p>
    <p><strong>Weakest areas:</strong> {'; '.join(f"{row['pageType']} ({row['averageScore']})" for row in weakest_areas)}</p>
  </section>

  <section id="method">
    <h2>Scope, inputs, and method</h2>
    <p><strong>Inspected inputs:</strong> repository routes, live route responses, workbook inventory, sitemap sources, podcast feed sources, blog and podcast manifest files, and live internal links.</p>
    <p><strong>Known limitations:</strong> metrics such as Core Web Vitals, Search Console, and analytics exports were not supplied, so they are marked as not verified rather than invented.</p>
    <p><strong>Chain of truth:</strong> repo and source files, live HTML responses, workbook inventory, sitemap and feed sources, and user context.</p>
  </section>

  <section id="inventory">
    <h2>Inventory and reconciliation summary</h2>
    <p><strong>Workbook rows:</strong> {workbook.url_count}</p>
    <p><strong>Discovery source counts:</strong> {'; '.join(f"{key}: {value}" for key, value in sorted(discovery_meta['sourceCounts'].items()))}</p>
    <table class="tight"><thead><tr><th>Page family</th><th>Discovered</th><th>Analysed</th><th>Failed</th><th>Coverage</th><th>Average score</th></tr></thead><tbody>{family_rows}</tbody></table>
    <p class="section-note">Every discovered in-scope URL was assigned a coverage state. This audit hard-fails if a mandatory family is only partly covered.</p>
  </section>

  <section id="lens">
    <h2>Findings by audit lens</h2>
    <div class="grid">
      <div><h3>Technical SEO</h3><p>Canonicals, titles, descriptions, indexability, redirect histories, and route normalisation were inspected page by page.</p></div>
      <div><h3>On-page SEO and intent match</h3><p>Openings, heading structures, visible copy depth, and title-to-page alignment were scored across the estate.</p></div>
      <div><h3>AEO</h3><p>Answer-first summaries, extractable question headings, FAQs, tables, and snippet-friendly structures were measured family by family.</p></div>
      <div><h3>GEO</h3><p>Entity clarity, summary safety, schema support, and reusable explanatory passages were assessed for citation readiness.</p></div>
      <div><h3>Entity authority</h3><p>Jonathan Harris, book, podcast, and topic relationships were checked for visible reinforcement and schema support.</p></div>
      <div><h3>Blog, podcast, transcript, and programmatic systems</h3><p>Blog article, podcast, archive, topic, catalogue, and book families were inventoried and fully analysed rather than silently sampled.</p></div>
    </div>
  </section>

  <section id="issues">
    <h2>Ranked issue ledger</h2>
    <table class="tight"><thead><tr><th>ID</th><th>Severity</th><th>Lens</th><th>Affected</th><th>Why it matters</th><th>Exact remediation</th></tr></thead><tbody>{issue_rows}</tbody></table>
  </section>

  <section id="page-types">
    <h2>Page-type findings</h2>
    <table class="tight"><thead><tr><th>Page type</th><th>Count</th><th>Coverage state</th><th>Average score</th><th>Range</th><th>Example</th></tr></thead><tbody>{page_type_rows}</tbody></table>
  </section>

  <section id="priority">
    <h2>Priority page annex</h2>
    <table class="tight"><thead><tr><th>URL</th><th>Type</th><th>Status</th><th>Title</th><th>Meta</th><th>Canonical</th><th>AEO</th><th>GEO</th><th>Total</th><th>Grade</th></tr></thead><tbody>{priority_rows}</tbody></table>
  </section>

  <section id="templates">
    <h2>Template / component / generator annex</h2>
    <table class="tight"><thead><tr><th>Page family</th><th>Pages</th><th>Source</th><th>Average score</th><th>Repeated strengths</th><th>Repeated defects</th><th>Fix priority</th></tr></thead><tbody>{template_rows}</tbody></table>
  </section>

  <section id="gap-matrix">
    <h2>Best-practice gap matrix</h2>
    <table class="tight"><thead><tr><th>Page type</th><th>SEO</th><th>AEO</th><th>GEO</th><th>Confidence</th><th>Top missing element</th><th>Business impact</th></tr></thead><tbody>{gap_rows}</tbody></table>
  </section>

  <section id="implementation">
    <h2>Final verdict and implementation order</h2>
    <p><strong>Overall verdict:</strong> {'Full-estate coverage completed with no material family omitted.' if all(row['coveragePercent'] == 100 for row in coverage_rows) else 'Coverage was materially incomplete and should be rerun after the missing family is fixed.'}</p>
    <p><strong>What to fix first:</strong> {'; '.join(item['issueId'] + ' ' + item['exactRemediation'] for item in issues[:5]) if issues else 'No urgent remediation item exceeded the evidence threshold.'}</p>
    <p><strong>Implementation sequence:</strong> 1) source-of-truth reconciliation, 2) template-level metadata and canonical fixes, 3) answer-first and citation-ready copy upgrades, 4) internal linking reinforcement, 5) final validation rerun.</p>
    <p><strong>Expected gains:</strong> better route governance, stronger answer-engine extractability, cleaner generative summaries, and tighter internal topical signals.</p>
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
  mandatory_families = {"blog archive", "blog article", "podcast hub", "podcast episode", "podcast transcript", "archive / pagination / utility", "book page", "category / hub", "topic hub"}
  rows_by_type = {row["pageType"]: row for row in coverage_rows}
  missing = [family for family in mandatory_families if family in rows_by_type and rows_by_type[family]["coveragePercent"] < 100]
  if missing:
    raise RuntimeError(f"Full-estate coverage incomplete. Families below 100% coverage: {', '.join(missing)}")


def build_summary(base_url: str, pages: list[dict[str, Any]], issues: list[dict[str, Any]], coverage_rows: list[dict[str, Any]], report_prefix: str, workbook: WorkbookInfo) -> dict[str, Any]:
  return {
    "ok": True,
    "sessionId": args.session_id,
    "status": "completed",
    "reportPrefix": report_prefix,
    "websiteUrl": base_url,
    "generatedAt": utc_now(),
    "auditedUrlCount": len(pages),
    "issueCount": len(issues),
    "familyCoverage": coverage_rows,
    "workbookRows": workbook.url_count,
    "pageTypeCounts": dict(Counter(page["pageType"] for page in pages)),
  }


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
    "urls": [make_url_entry(page) for page in pages],
  }
  summary = build_summary(base_url, pages, issues, coverage_rows, args.report_prefix, workbook)

  coverage_path = write_json(output_dir / "coverage.json", coverage_json)
  summary_path = write_json(output_dir / "summary.json", summary)

  client = build_r2_client()
  artefact_files = {
    "summary.json": summary_path,
    "coverage.json": coverage_path,
  }
  uploaded = upload_selected_files_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, artefact_files)

  report_html = build_report(base_url, workbook, discovery_meta, pages, issues, coverage_rows, template_annex, gap_matrix, page_type_findings, priority_pages, uploaded)
  report_path = write_text(output_dir / "report.html", report_html)
  artefact_files["report.html"] = report_path
  uploaded = upload_selected_files_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, artefact_files)

  callback_payload = {
    "auditType": "seo-aeo-geo",
    "sessionId": args.session_id,
    "status": "completed",
    "reportPrefix": args.report_prefix,
    "reportUrl": uploaded.get("report.html"),
    "summaryUrl": uploaded.get("summary.json"),
    "coverageUrl": uploaded.get("coverage.json"),
    "issueCount": len(issues),
    "auditedUrlCount": len(pages),
    "artefacts": uploaded,
    "finishedAt": utc_now(),
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  post_callback(args.callback_url, args.callback_token, callback_payload)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
