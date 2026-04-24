#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html as html_mod
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

import requests

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


def _xml_root(xml_text: str) -> ET.Element | None:
  payload = (xml_text or "").strip()
  if not payload:
    return None
  try:
    return ET.fromstring(payload)
  except ET.ParseError:
    return None


def _local_name(tag: str) -> str:
  return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[str]]:
  root = _xml_root(xml_text)
  if root is None:
    return [], []

  sitemap_links: list[str] = []
  url_links: list[str] = []

  for node in root.iter():
    name = _local_name(node.tag)
    if name not in {"sitemap", "url"}:
      continue
    for child in node:
      if _local_name(child.tag) != "loc":
        continue
      value = (child.text or "").strip()
      if not value:
        continue
      if name == "sitemap":
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

  root = _xml_root(fetched["text"])
  if root is None:
    return []

  urls: list[str] = []
  for item in root.iter():
    if _local_name(item.tag) != "item":
      continue

    candidates: list[str] = []
    for child in item:
      child_name = _local_name(child.tag)
      text_value = (child.text or "").strip()

      if child_name in {"link", "guid"} and text_value:
        candidates.append(text_value)
        continue

      if "transcript" in child_name.lower():
        href = (child.attrib.get("url") or child.attrib.get("href") or text_value).strip()
        if href:
          candidates.append(href)

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
    "pageType": classify_page(url),
    "coverageState": "Fully analysed" if fetched.get("status") == 200 else "Failed to fetch",
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
    analysed = len([page for page in family_pages if page["coverageState"] == "Fully analysed"])
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
      "coverageState": "Fully analysed" if all(page["coverageState"] == "Fully analysed" for page in family_pages) else "Partial / failed",
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


def analysis_url_from_callback(callback_url: str | None) -> str | None:
  if not callback_url:
    return None
  callback_url = str(callback_url).strip()
  if callback_url.endswith("/callback"):
    return callback_url[:-len("/callback")] + "/analysis"
  return callback_url.rstrip("/") + "/analysis"


def parse_governance_excludes(repo_root: Path) -> list[str]:
  target = repo_root / "scripts" / "check_ungoverned_routes.py"
  if not target.exists():
    return []
  text = target.read_text(encoding="utf-8")
  match = re.search(r"EXCLUDED_ROUTE_PREFIXES\s*=\s*\((.*?)\)", text, re.S)
  if not match:
    return []
  return re.findall(r'"([^"]+)"', match.group(1))


def parse_ebook_trim_limit(repo_root: Path) -> int | None:
  target = repo_root / "scripts" / "ebook_pipeline.py"
  if not target.exists():
    return None
  text = target.read_text(encoding="utf-8")
  match = re.search(r"heading\s*=\s*heading\[:(\d+)\]", text)
  if match:
    return int(match.group(1))
  return None


def detect_llms_scope(repo_root: Path) -> str:
  llms_path = repo_root / "llms.txt"
  if not llms_path.exists():
    return "missing"
  lines = [line.strip() for line in llms_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
  urls = [line for line in lines if line.startswith("http")]
  if not urls:
    return "unclear"
  ebook_urls = [line for line in urls if "/ebooks/" in line or line.rstrip("/").endswith("/ebooks")]
  return "ebook-only" if len(ebook_urls) == len(urls) else "mixed"


def build_repo_signals(repo_root: Path, pages: list[dict[str, Any]], discovery_meta: dict[str, Any]) -> dict[str, Any]:
  broken_redirects = []
  for page in pages:
    if "/podcast/TT-" in page["url"] and (page["status"] != 200 or page["redirectChain"]):
      target = page["redirectChain"][-1]["url"] if page["redirectChain"] else page["finalUrl"]
      broken_redirects.append({
        "from": page["url"],
        "to": target,
        "targetStatus": page["status"],
      })
  generator_candidates = [
    "scripts/generate_podcast_episodes.py",
    "scripts/ebook_pipeline.py",
    "scripts/generate-blog-from-rss.mjs",
  ]
  function_candidates = [
    "functions/transcripts/[[slug]].js",
  ]
  return {
    "governanceScriptExcludes": parse_governance_excludes(repo_root),
    "ebookPipelineTrimLimit": parse_ebook_trim_limit(repo_root),
    "blogManifestPath": "blog/posts.json" if (repo_root / "blog" / "posts.json").exists() else "",
    "podcastManifestPath": "data/podcast-episodes.json" if (repo_root / "data" / "podcast-episodes.json").exists() else "",
    "knownBrokenRedirects": broken_redirects,
    "llmsFiles": [name for name in ("llms.txt", "llm-index.json") if (repo_root / name).exists()],
    "llmsScope": detect_llms_scope(repo_root),
    "buildScriptName": "build.sh" if (repo_root / "build.sh").exists() else "",
    "functionsPresent": [item for item in function_candidates if (repo_root / item).exists()],
    "generatorScripts": [item for item in generator_candidates if (repo_root / item).exists()],
    "sourceCounts": discovery_meta.get("sourceCounts", {}),
  }


def build_inventory_context(workbook: WorkbookInfo, discovered: dict[str, dict[str, Any]], discovery_meta: dict[str, Any]) -> dict[str, Any]:
  repo_only = []
  workbook_only = []
  for entry in discovered.values():
    path = entry["path"]
    if "repo" in entry["sources"] and "workbook" not in entry["sources"]:
      repo_only.append(path)
    if "workbook" in entry["sources"] and "repo" not in entry["sources"]:
      workbook_only.append(path)

  known_drift = []
  if repo_only:
    known_drift.append(f"Repo-only routes remain: {', '.join(repo_only[:8])}")
  if workbook_only:
    known_drift.append(f"Workbook-only routes remain: {', '.join(workbook_only[:8])}")
  if discovery_meta.get("sourceCounts", {}).get("blog-manifest", 0) < 1:
    known_drift.append("Blog manifest did not yield any URLs from the supplied repo snapshot")
  if discovery_meta.get("sourceCounts", {}).get("podcast-manifest", 0) < 1:
    known_drift.append("Podcast manifest did not yield any URLs from the supplied repo snapshot")

  page_type_counts = Counter(entry.get("pageType") or classify_page(entry["url"]) for entry in discovered.values())
  return {
    "workbookUrlCount": workbook.url_count,
    "repoRouteCount": sum(1 for entry in discovered.values() if "repo" in entry["sources"]),
    "discoveredRouteCount": len(discovered),
    "repoOnlyRoutes": sorted(set(repo_only)),
    "workbookOnlyRoutes": sorted(set(workbook_only)),
    "pageTypeCounts": dict(page_type_counts),
    "sitemapUrlCount": int(discovery_meta.get("sourceCounts", {}).get("sitemap", 0)),
    "blogManifestCount": int(discovery_meta.get("sourceCounts", {}).get("blog-manifest", 0)),
    "podcastManifestCount": int(discovery_meta.get("sourceCounts", {}).get("podcast-manifest", 0)),
    "knownDriftIssues": known_drift,
  }


def make_priority_payload(page: dict[str, Any]) -> dict[str, Any]:
  soup = page.get("soup")
  intro_text = page.get("introText", "")
  h2_headings: list[str] = []
  schema_types: list[str] = []
  if soup is not None:
    h2_headings = [h.get_text(" ", strip=True) for h in soup.select("h2")][:10]
    for script in soup.select("script[type='application/ld+json']"):
      try:
        payload = json.loads(script.string or "")
      except Exception:
        continue
      stack = payload if isinstance(payload, list) else [payload]
      for item in stack:
        if not isinstance(item, dict):
          continue
        schema_type = item.get("@type")
        if isinstance(schema_type, list):
          schema_types.extend(str(value) for value in schema_type)
        elif schema_type:
          schema_types.append(str(schema_type))
  return {
    "route": page["path"],
    "url": page["url"],
    "status": page["status"],
    "pageType": page["pageType"],
    "title": page["meta"]["title"],
    "metaDescription": page["meta"]["metaDescription"],
    "canonical": page["meta"]["canonical"],
    "h1": page["meta"]["h1"],
    "ogTitle": page["meta"]["og"].get("og:title", ""),
    "schemaTypes": sorted(set(schema_types)),
    "schemaCount": page["meta"]["schemaCount"],
    "wordCount": page["wordCount"],
    "internalLinkCount": page["internalLinkCount"],
    "questionHeadings": page["questionHeadings"],
    "hasFaqSchema": page["hasFaqSchema"],
    "hasTable": page["tableCount"] > 0,
    "introText": intro_text[:500],
    "h2Headings": h2_headings,
    "scores": page["scores"],
    "total": page["total"],
    "grade": page["grade"],
    "riskFlag": page["riskFlag"],
    "coverageState": page["coverageState"],
  }


def build_all_routes_condensed(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [{
    "route": page["path"],
    "url": page["url"],
    "pageType": page["pageType"],
    "status": page["status"],
    "grade": page["grade"],
    "riskFlag": page["riskFlag"],
    "coverageState": page["coverageState"],
    "sources": sorted(page.get("sources", [])),
  } for page in pages]


def build_live_dynamic_urls(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
  results = []
  for page in pages:
    if page["pageType"] not in {"blog article", "blog archive", "podcast hub", "podcast episode", "podcast transcript"}:
      continue
    observation_bits = []
    if page["status"] != 200:
      observation_bits.append(f"HTTP {page['status']}")
    if len(page["introText"].split()) < 35:
      observation_bits.append("opening summary is thin")
    if page["pageType"] == "blog article" and not page["questionHeadings"]:
      observation_bits.append("no question-led subheadings detected")
    if page["pageType"] == "podcast episode" and page["wordCount"] < 260:
      observation_bits.append("episode page is summary-thin")
    if page["pageType"] == "podcast transcript" and page["paragraphCount"] < 4:
      observation_bits.append("transcript structure is weak")
    results.append({
      "url": page["url"],
      "pageType": page["pageType"],
      "source": ", ".join(sorted(page.get("sources", []))) or "discovered",
      "httpStatus": page["status"],
      "inRepoManifest": "repo" in page.get("sources", []),
      "keyObservation": "; ".join(observation_bits) or "No material dynamic-family defect was mechanically observed on this URL.",
    })
  return results


def call_analysis_service(base_url: str, session_id: str, callback_url: str | None, callback_token: str | None, inventory: dict[str, Any], priority_pages: list[dict[str, Any]], all_routes: list[dict[str, Any]], heuristic_issues: list[dict[str, Any]], repo_signals: dict[str, Any], live_dynamic_urls: list[dict[str, Any]], coverage: list[dict[str, Any]], coverage_families: list[dict[str, Any]]) -> dict[str, Any]:
  analysis_url = analysis_url_from_callback(callback_url)
  if not analysis_url:
    raise RuntimeError("AI analysis endpoint could not be derived because callback_url is missing")

  headers = {"Content-Type": "application/json"}
  if callback_token:
    headers["Authorization"] = f"Bearer {callback_token}"
    headers["X-Audit-Callback-Token"] = callback_token

  payload = {
    "auditType": "seo-aeo-geo",
    "sessionId": session_id,
    "baseUrl": base_url,
    "generatedAt": utc_now(),
    "inventory": inventory,
    "priorityPages": priority_pages,
    "allRoutes": all_routes,
    "heuristicIssues": heuristic_issues,
    "repoSignals": repo_signals,
    "liveDynamicUrls": live_dynamic_urls,
    "coverage": coverage,
    "coverageFamilies": coverage_families,
  }

  response = requests.post(analysis_url, headers=headers, data=json.dumps(payload), timeout=180)
  response.raise_for_status()
  envelope = response.json()
  if not envelope.get("ok") or not isinstance(envelope.get("analysis"), dict):
    raise RuntimeError("AI analysis service returned an invalid response envelope")
  return envelope["analysis"]


def esc(value: Any) -> str:
  return html_mod.escape(str(value or ""))


def render_paragraphs(text: str) -> str:
  paragraphs = [segment.strip() for segment in re.split(r"\n\s*\n", str(text or "").strip()) if segment.strip()]
  if not paragraphs:
    return "<p>Not verified from supplied context.</p>"
  return "".join(f"<p>{esc(paragraph)}</p>" for paragraph in paragraphs)


def render_string_list(items: list[Any]) -> str:
  cleaned = [str(item).strip() for item in items if str(item).strip()]
  if not cleaned:
    return "<p>None confirmed from supplied context.</p>"
  return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in cleaned) + "</ul>"


def health_label(value: str) -> str:
  value = str(value or "").strip()
  if not value:
    return "Needs verification"
  return value


def render_issue_rows(items: list[dict[str, Any]]) -> str:
  rows = []
  for item in items:
    rows.append(
      f"<tr><td><strong>{esc(item.get('issueId'))}</strong></td>"
      f"<td>{esc(item.get('severity'))}</td>"
      f"<td>{esc(item.get('lens') or item.get('auditLens'))}</td>"
      f"<td><code>{esc(item.get('affected'))}</code></td>"
      f"<td>{esc(item.get('whyItMatters'))}</td>"
      f"<td>{esc(item.get('exactRemediation'))}</td></tr>"
    )
  return "".join(rows)


def render_page_type_rows(items: list[dict[str, Any]]) -> str:
  rows = []
  for item in items:
    rows.append(
      f"<tr><td>{esc(item.get('pageType'))}</td><td>{esc(item.get('count'))}</td>"
      f"<td>{esc(item.get('coverageState'))}</td><td>{esc(item.get('score') or item.get('averageScore'))}</td>"
      f"<td>{esc(item.get('grade') or '')}</td><td>{esc(item.get('judgement') or item.get('keyNote') or '')}</td></tr>"
    )
  return "".join(rows)


def render_priority_rows(items: list[dict[str, Any]]) -> str:
  rows = []
  for item in items:
    issue_ids = item.get("confirmedIssueIds") or []
    issue_text = ", ".join(str(value) for value in issue_ids)
    rows.append(
      f"<tr><td><code>{esc(urlparse(str(item.get('url') or '')).path or item.get('url'))}</code></td>"
      f"<td>{esc(item.get('pageType'))}</td><td>{esc(item.get('templateSource'))}</td>"
      f"<td>{esc(health_label(item.get('titleStatus')))}</td><td>{esc(health_label(item.get('metaStatus')))}</td>"
      f"<td>{esc(health_label(item.get('canonicalStatus')))}</td><td>{esc(health_label(item.get('schemaStatus')))}</td>"
      f"<td>{esc(health_label(item.get('aeoStatus')))}</td><td>{esc(health_label(item.get('geoStatus')))}</td>"
      f"<td>{esc(item.get('score'))}</td><td>{esc(item.get('grade'))}</td><td>{esc(issue_text)}</td><td>{esc(item.get('keyNote'))}</td></tr>"
    )
  return "".join(rows)


def render_template_rows(items: list[dict[str, Any]]) -> str:
  rows = []
  for item in items:
    rows.append(
      f"<tr><td><code>{esc(item.get('sourceFile') or item.get('pageType'))}</code></td>"
      f"<td>{esc(item.get('area') or '')}</td><td>{esc(item.get('observedLogic') or '')}</td>"
      f"<td>{esc(item.get('repeatedEffect') or '')}</td><td>{esc(item.get('fixPriority'))}</td></tr>"
    )
  return "".join(rows)


def render_code_blocks(items: list[dict[str, Any]]) -> str:
  blocks = []
  for item in items:
    blocks.append(
      f"<section><h3>{esc(item.get('issueId') or item.get('target'))}</h3>"
      f"<p><strong>Target:</strong> <code>{esc(item.get('target'))}</code></p>"
      f"<p>{esc(item.get('rationale'))}</p>"
      f"<p><strong>Current pattern</strong></p><pre><code>{esc(item.get('currentPattern'))}</code></pre>"
      f"<p><strong>Corrected pattern</strong></p><pre><code>{esc(item.get('correctedPattern'))}</code></pre></section>"
    )
  return "".join(blocks) if blocks else "<p>No code-level remediation block was returned.</p>"


def render_gap_rows(items: list[dict[str, Any]]) -> str:
  rows = []
  for item in items:
    rows.append(
      f"<tr><td>{esc(item.get('pageType'))}</td><td>{esc(item.get('seo'))}</td><td>{esc(item.get('aeo'))}</td><td>{esc(item.get('geo'))}</td>"
      f"<td>{esc(item.get('confidence'))}</td><td>{esc(item.get('topMissingElement') or item.get('topMissing'))}</td><td>{esc(item.get('businessImpact'))}</td></tr>"
    )
  return "".join(rows)


def render_coverage_rows(items: list[dict[str, Any]]) -> str:
  rows = []
  for item in items:
    rows.append(
      f"<tr><td><code>{esc(urlparse(item['url']).path or item['url'])}</code></td><td>{esc(item.get('pageType'))}</td>"
      f"<td>{esc(', '.join(item.get('sources', [])))}</td><td>{esc(item.get('status'))}</td>"
      f"<td>{esc(item.get('canonical'))}</td><td>{esc(item.get('indexability'))}</td>"
      f"<td>{esc(item.get('coverageState'))}</td><td>{esc(item.get('score'))}</td><td>{esc(item.get('riskFlag'))}</td></tr>"
    )
  return "".join(rows)


def build_report(base_url: str, workbook: WorkbookInfo, discovery_meta: dict[str, Any], pages: list[dict[str, Any]], analysis: dict[str, Any], coverage_rows: list[dict[str, Any]], coverage_entries: list[dict[str, Any]], artefacts: dict[str, str]) -> str:
  executive = analysis["executiveSummary"]
  scores = executive["scores"]
  limitations = []
  partial_rows = [row for row in coverage_rows if row["coveragePercent"] < 100]
  if partial_rows:
    limitations.append("Coverage was partial for: " + ", ".join(f"{row['pageType']} ({row['coveragePercent']}%)" for row in partial_rows))
  limitations.append("Search Console, analytics exports, and Core Web Vitals were not supplied, so they remain not verified from supplied context.")

  score_cards = "".join(
    f"<div class='kpi'><strong>{esc(label)}</strong><div>{esc(block.get('score'))} / 100 ({esc(block.get('grade'))})</div><div class='muted'>{esc(block.get('headline'))}</div></div>"
    for label, block in [
      ("SEO", scores["seo"]),
      ("AEO", scores["aeo"]),
      ("GEO", scores["geo"]),
      ("Entity Authority", scores["entityAuthority"]),
      ("Conversion Support", scores["conversionSupport"]),
      ("Discovered URLs", {"score": len(pages), "grade": "", "headline": f"Workbook rows: {workbook.url_count}"}),
    ]
  )

  family_rows = "".join(
    f"<tr><td>{esc(row['pageType'])}</td><td>{esc(row['discovered'])}</td><td>{esc(row['analysed'])}</td><td>{esc(row['failed'])}</td><td>{esc(row['coveragePercent'])}%</td><td>{esc(row['averageScore'])}</td></tr>"
    for row in coverage_rows
  )

  body = f"""
  <section id="cover">
    <h2>Forensic SEO + AEO + GEO Audit</h2>
    <p><strong>Website:</strong> <a href="{esc(base_url)}">{esc(base_url)}</a></p>
    <p><strong>Date:</strong> {esc(utc_now())}</p>
    <p><strong>Audit mode:</strong> full-estate, evidence-led, repo + live + workbook reconciliation</p>
    <p><strong>Front-page material limitation:</strong> {esc(' '.join(limitations))}</p>
  </section>

  <section id="contents" class="toc">
    <h2>Contents</h2>
    <ul>
      <li><a href="#summary">1. Executive Summary</a></li>
      <li><a href="#method">2. Scope, Inputs, and Method</a></li>
      <li><a href="#inventory">3. Inventory and Reconciliation Summary</a></li>
      <li><a href="#lens">4. Findings by Audit Lens</a></li>
      <li><a href="#issues">5. Ranked Issue Ledger</a></li>
      <li><a href="#page-types">6. Page-Type Findings</a></li>
      <li><a href="#priority">7. Priority Page Annex</a></li>
      <li><a href="#templates">8. Template / Component / Generator Annex</a></li>
      <li><a href="#code">9. Code-Level / Markup / Content Remediation Appendix</a></li>
      <li><a href="#gap-matrix">10. Best-Practice Gap Matrix</a></li>
      <li><a href="#implementation">11. Final Verdict and Implementation Order</a></li>
      <li><a href="#coverage">12. Full URL Coverage Appendix</a></li>
    </ul>
  </section>

  <section id="summary">
    <h2>1. Executive Summary</h2>
    {render_paragraphs(executive.get('overallVerdict'))}
    <div class="grid">{score_cards}</div>
    <h3>Top five priorities</h3>
    {render_string_list(executive.get('topFivePriorities', []))}
    <h3>Quick wins</h3>
    {render_string_list(executive.get('quickWins', []))}
    <p>{''.join(f'<span class="pill">{esc(label)}</span>' for label in executive.get('estateLabels', []))}</p>
  </section>

  <section id="method">
    <h2>2. Scope, Inputs, and Method</h2>
    <p><strong>What was inspected:</strong> repository routes and templates, workbook inventory, live route responses, sitemap and feed sources, and live internal links discovered during the crawl.</p>
    <p><strong>Source ledger:</strong> {'; '.join(f'{esc(key)}: {esc(value)}' for key, value in sorted(discovery_meta.get('sourceCounts', {}).items()))}</p>
    <p><strong>Workbook:</strong> <code>{esc(Path(workbook.path).name)}</code> using sheet <code>{esc(workbook.primary_sheet)}</code> with {esc(workbook.url_count)} URL rows.</p>
    <p><strong>Known limitations:</strong> {' '.join(esc(item) for item in limitations)}</p>
  </section>

  <section id="inventory">
    <h2>3. Inventory and Reconciliation Summary</h2>
    <p><strong>Discovered routes:</strong> {esc(len(pages))}</p>
    <p><strong>Workbook routes:</strong> {esc(workbook.url_count)}</p>
    <p><strong>Coverage assurance:</strong> every discovered in-scope URL received a coverage state and condensed verdict in <code>coverage.json</code>.</p>
    <table class="tight"><thead><tr><th>Page family</th><th>Discovered</th><th>Analysed</th><th>Failed</th><th>Coverage</th><th>Average score</th></tr></thead><tbody>{family_rows}</tbody></table>
  </section>

  <section id="lens">
    <h2>4. Findings by Audit Lens</h2>
    <h3>4.1 Technical SEO</h3>{render_paragraphs(analysis['findingsByLens']['technicalSeo'])}
    <h3>4.2 On-Page SEO and Intent Match</h3>{render_paragraphs(analysis['findingsByLens']['onPageSeo'])}
    <h3>4.3 AEO</h3>{render_paragraphs(analysis['findingsByLens']['aeo'])}
    <h3>4.4 GEO</h3>{render_paragraphs(analysis['findingsByLens']['geo'])}
    <h3>4.5 Entity Authority</h3>{render_paragraphs(analysis['findingsByLens']['entityAuthority'])}
    <h3>4.6 Structured Data</h3>{render_paragraphs(analysis['findingsByLens']['structuredData'])}
    <h3>4.7 Internal Linking</h3>{render_paragraphs(analysis['findingsByLens']['internalLinking'])}
    <h3>4.8 Content Architecture</h3>{render_paragraphs(analysis['findingsByLens']['contentArchitecture'])}
    <h3>4.9 Conversion Support</h3>{render_paragraphs(analysis['findingsByLens']['conversionSupport'])}
    <h3>4.10 Blog, Podcast, Transcript, and Programmatic Systems</h3>{render_paragraphs(analysis['findingsByLens']['blogPodcastTranscriptSystems'])}
  </section>

  <section id="issues">
    <h2>5. Ranked Issue Ledger</h2>
    <table class="tight"><thead><tr><th>ID</th><th>Severity</th><th>Lens</th><th>Affected</th><th>Why it matters</th><th>Exact remediation</th></tr></thead><tbody>{render_issue_rows(analysis['issues'])}</tbody></table>
  </section>

  <section id="page-types">
    <h2>6. Page-Type Findings</h2>
    <table class="tight"><thead><tr><th>Page type</th><th>Count</th><th>Coverage state</th><th>Score</th><th>Grade</th><th>Judgement</th></tr></thead><tbody>{render_page_type_rows(analysis['pageTypeFindings'])}</tbody></table>
  </section>

  <section id="priority">
    <h2>7. Priority Page Annex</h2>
    <table class="tight"><thead><tr><th>URL</th><th>Type</th><th>Template</th><th>Title</th><th>Meta</th><th>Canonical</th><th>Schema</th><th>AEO</th><th>GEO</th><th>Score</th><th>Grade</th><th>Issue IDs</th><th>Key note</th></tr></thead><tbody>{render_priority_rows(analysis['priorityPageAnnex'])}</tbody></table>
  </section>

  <section id="templates">
    <h2>8. Template / Component / Generator Annex</h2>
    <table class="tight"><thead><tr><th>Source file</th><th>Area</th><th>Observed logic</th><th>Repeated effect</th><th>Fix priority</th></tr></thead><tbody>{render_template_rows(analysis['templateAnnex'])}</tbody></table>
  </section>

  <section id="code">
    <h2>9. Code-Level / Markup / Content Remediation Appendix</h2>
    {render_code_blocks(analysis['codeRemediationAppendix'])}
  </section>

  <section id="gap-matrix">
    <h2>10. Best-Practice Gap Matrix</h2>
    <table class="tight"><thead><tr><th>Page type</th><th>SEO</th><th>AEO</th><th>GEO</th><th>Confidence</th><th>Top missing element</th><th>Business impact</th></tr></thead><tbody>{render_gap_rows(analysis['bestPracticeGapMatrix'])}</tbody></table>
  </section>

  <section id="implementation">
    <h2>11. Final Verdict and Implementation Order</h2>
    {render_paragraphs(analysis['implementationOrder'].get('narrative', ''))}
    <h3>Implementation sequence</h3>
    {render_string_list(analysis['implementationOrder'].get('steps', []))}
    <h3>Expected gains</h3>
    {render_string_list(analysis['implementationOrder'].get('expectedGains', []))}
  </section>

  <section id="coverage">
    <h2>12. Full URL Coverage Appendix</h2>
    <table class="tight"><thead><tr><th>URL</th><th>Page type</th><th>Discovered from</th><th>Status</th><th>Canonical</th><th>Indexability</th><th>Coverage state</th><th>Score</th><th>Risk</th></tr></thead><tbody>{render_coverage_rows(coverage_entries)}</tbody></table>
    <p class="section-note">Machine-friendly full-estate ledger is preserved separately in <code>coverage.json</code>.</p>
  </section>

  <section id="artefacts">
    <h2>Final artefacts</h2>
    <ul>
      <li><a href="{esc(artefacts.get('report.html', '#'))}">report.html</a></li>
      <li><a href="{esc(artefacts.get('summary.json', '#'))}">summary.json</a></li>
      <li><a href="{esc(artefacts.get('coverage.json', '#'))}">coverage.json</a></li>
    </ul>
  </section>
  """
  return html_report_shell("Forensic SEO + AEO + GEO Audit", body)


def validate_full_coverage(coverage_rows: list[dict[str, Any]]) -> None:
  mandatory_families = {"blog archive", "blog article", "podcast hub", "podcast episode", "podcast transcript", "archive / pagination / utility", "book page", "category / hub", "topic hub"}
  rows_by_type = {row["pageType"]: row for row in coverage_rows}
  missing = [family for family in mandatory_families if family in rows_by_type and rows_by_type[family]["coveragePercent"] < 100]
  if missing:
    raise RuntimeError(f"Full-estate coverage incomplete. Families below 100% coverage: {', '.join(missing)}")


def build_summary(base_url: str, pages: list[dict[str, Any]], analysis: dict[str, Any], coverage_rows: list[dict[str, Any]], report_prefix: str, workbook: WorkbookInfo) -> dict[str, Any]:
  scores = analysis["executiveSummary"]["scores"]
  return {
    "ok": True,
    "sessionId": args.session_id,
    "status": "completed",
    "reportPrefix": report_prefix,
    "websiteUrl": base_url,
    "generatedAt": utc_now(),
    "auditedUrlCount": len(pages),
    "issueCount": len(analysis.get("issues", [])),
    "familyCoverage": coverage_rows,
    "workbookRows": workbook.url_count,
    "pageTypeCounts": dict(Counter(page["pageType"] for page in pages)),
    "scores": {
      "seo": scores["seo"],
      "aeo": scores["aeo"],
      "geo": scores["geo"],
      "entityAuthority": scores["entityAuthority"],
      "conversionSupport": scores["conversionSupport"],
    },
    "estateLabels": analysis["executiveSummary"].get("estateLabels", []),
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
  heuristic_issues = collect_issues(pages, discovered)
  priority_pages = build_priority_pages(pages)

  coverage_entries = [make_url_entry(page) for page in pages]
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
    "urls": coverage_entries,
  }

  inventory_context = build_inventory_context(workbook, discovered, discovery_meta)
  repo_signals = build_repo_signals(REPO_ROOT, pages, discovery_meta)
  live_dynamic_urls = build_live_dynamic_urls(pages)
  analysis = call_analysis_service(
    base_url=base_url,
    session_id=args.session_id,
    callback_url=args.callback_url,
    callback_token=args.callback_token,
    inventory=inventory_context,
    priority_pages=[make_priority_payload(page) for page in priority_pages],
    all_routes=build_all_routes_condensed(pages),
    heuristic_issues=heuristic_issues,
    repo_signals=repo_signals,
    live_dynamic_urls=live_dynamic_urls,
    coverage=coverage_entries,
    coverage_families=coverage_rows,
  )

  summary = build_summary(base_url, pages, analysis, coverage_rows, args.report_prefix, workbook)

  coverage_path = write_json(output_dir / "coverage.json", coverage_json)
  summary_path = write_json(output_dir / "summary.json", summary)

  client = build_r2_client()
  artefact_files = {
    "summary.json": summary_path,
    "coverage.json": coverage_path,
  }
  uploaded = upload_selected_files_to_r2(client, os.environ["R2_BUCKET_BRAND_ASSETS"], args.report_prefix, artefact_files)

  report_html = build_report(base_url, workbook, discovery_meta, pages, analysis, coverage_rows, coverage_entries, uploaded)
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
    "issueCount": len(analysis.get("issues", [])),
    "auditedUrlCount": len(pages),
    "artefacts": uploaded,
    "finishedAt": utc_now(),
    "workflowRunUrl": os.environ.get("WORKFLOW_RUN_URL", ""),
  }
  post_callback(args.callback_url, args.callback_token, callback_payload)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
