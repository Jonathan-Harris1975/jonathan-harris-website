#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://jonathan-harris.online"
DEFAULT_OUTPUT = Path("artifacts/search-visibility-baseline/search-visibility-baseline.json")

BATCH_1_SKILLS = [
    {
        "name": "seo-audit",
        "source": "coreyhaines31/marketingskills",
        "installCommand": "npx --yes skills@latest add coreyhaines31/marketingskills --skill seo-audit ai-seo -y",
        "purpose": "Search visibility baseline for crawlability, indexation, technical foundations, on-page signals, content quality and authority evidence.",
    },
    {
        "name": "ai-seo",
        "source": "coreyhaines31/marketingskills",
        "installCommand": "npx --yes skills@latest add coreyhaines31/marketingskills --skill seo-audit ai-seo -y",
        "purpose": "AEO/GEO/LLMO baseline for extractable answers, entity clarity, AI citation readiness, llms.txt coverage and structured context.",
    },
]

KEY_ROUTE_CANDIDATES = [
    "index.html",
    "bio/index.html",
    "ebooks/index.html",
    "blog/index.html",
    "blog/weekly/index.html",
    "podcast/index.html",
    "transcripts/index.html",
    "newsletter/index.html",
    "topics/index.html",
    "glossary/index.html",
    "compare/index.html",
]

SKIP_DIR_PARTS = {
    ".git",
    ".github",
    ".agents",
    "assets",
    "node_modules",
    "artifacts",
    "config",
}


@dataclass(slots=True)
class PageSignals:
    path: str
    url: str
    title: str
    metaDescription: str
    canonical: str
    jsonLdCount: int
    h1Count: int
    h2Count: int
    hasDirectAnswerCue: bool
    hasEntityCue: bool
    findings: list[dict[str, str]]


class HeadSignalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta_description = ""
        self.canonical = ""
        self.json_ld_count = 0
        self.h1_count = 0
        self.h2_count = 0
        self._current_heading: str | None = None
        self.heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta" and attr_map.get("name", "").lower() == "description":
            self.meta_description = attr_map.get("content", "").strip()
        elif tag == "link" and attr_map.get("rel", "").lower() == "canonical":
            self.canonical = attr_map.get("href", "").strip()
        elif tag == "script" and attr_map.get("type", "").lower() == "application/ld+json":
            self.json_ld_count += 1
        elif tag in {"h1", "h2"}:
            if tag == "h1":
                self.h1_count += 1
            else:
                self.h2_count += 1
            self._current_heading = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag in {"h1", "h2"}:
            self._current_heading = None

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self._current_heading:
            cleaned = " ".join(data.split())
            if cleaned:
                self.heading_text.append(cleaned)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split()).strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def route_url(path: Path, repo_root: Path, base_url: str) -> str:
    relative = path.relative_to(repo_root).as_posix()
    if relative == "index.html":
        route = "/"
    elif relative.endswith("/index.html"):
        route = f"/{relative[:-10]}"
    else:
        route = f"/{relative}"
    return urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))


def is_html_route(path: Path, repo_root: Path) -> bool:
    if path.suffix.lower() != ".html":
        return False
    relative_parts = set(path.relative_to(repo_root).parts[:-1])
    return not (relative_parts & SKIP_DIR_PARTS)


def discover_sample_pages(repo_root: Path, limit: int = 80) -> list[Path]:
    selected: list[Path] = []
    for candidate in KEY_ROUTE_CANDIDATES:
        path = repo_root / candidate
        if path.exists() and path.is_file():
            selected.append(path)

    for path in sorted(repo_root.rglob("index.html")):
        if len(selected) >= limit:
            break
        if path in selected or not is_html_route(path, repo_root):
            continue
        selected.append(path)
    return selected


def parse_page(path: Path, repo_root: Path, base_url: str) -> PageSignals:
    parser = HeadSignalParser()
    raw = path.read_text(encoding="utf-8", errors="replace")
    parser.feed(raw)
    lower = raw.lower()
    heading_blob = " ".join(parser.heading_text).lower()
    findings: list[dict[str, str]] = []

    if not parser.title:
        findings.append({"severity": "high", "issue": "Missing title", "evidence": path.relative_to(repo_root).as_posix()})
    if not parser.meta_description:
        findings.append({"severity": "medium", "issue": "Missing meta description", "evidence": path.relative_to(repo_root).as_posix()})
    if not parser.canonical:
        findings.append({"severity": "medium", "issue": "Missing canonical link", "evidence": path.relative_to(repo_root).as_posix()})
    if parser.h1_count != 1:
        findings.append({"severity": "medium", "issue": "Unexpected H1 count", "evidence": f"{parser.h1_count} H1 elements"})
    if parser.json_ld_count == 0:
        findings.append({"severity": "low", "issue": "No JSON-LD detected in static HTML", "evidence": path.relative_to(repo_root).as_posix()})

    direct_answer_cue = bool(re.search(r"\b(what is|how to|why|guide|faq|key takeaways|summary|in short)\b", heading_blob))
    entity_cue = "jonathan harris" in lower or "turing's torch" in lower or "ai edge" in lower

    if not direct_answer_cue:
        findings.append({"severity": "low", "issue": "No obvious answer-extraction heading cue", "evidence": path.relative_to(repo_root).as_posix()})
    if not entity_cue:
        findings.append({"severity": "low", "issue": "Weak Jonathan Harris entity cue", "evidence": path.relative_to(repo_root).as_posix()})

    return PageSignals(
        path=path.relative_to(repo_root).as_posix(),
        url=route_url(path, repo_root, base_url),
        title=unescape(parser.title),
        metaDescription=unescape(parser.meta_description),
        canonical=parser.canonical,
        jsonLdCount=parser.json_ld_count,
        h1Count=parser.h1_count,
        h2Count=parser.h2_count,
        hasDirectAnswerCue=direct_answer_cue,
        hasEntityCue=entity_cue,
        findings=findings,
    )


def file_check(repo_root: Path, relative: str, description: str) -> dict[str, Any]:
    path = repo_root / relative
    exists = path.exists()
    return {
        "name": relative,
        "description": description,
        "exists": exists,
        "severityIfMissing": "high" if relative in {"robots.txt", "sitemap.xml", "llms.txt"} else "medium",
    }


def summarise_pages(pages: list[PageSignals]) -> dict[str, int]:
    all_findings = [finding for page in pages for finding in page.findings]
    return {
        "pagesSampled": len(pages),
        "pagesWithTitle": sum(1 for page in pages if page.title),
        "pagesWithMetaDescription": sum(1 for page in pages if page.metaDescription),
        "pagesWithCanonical": sum(1 for page in pages if page.canonical),
        "pagesWithJsonLd": sum(1 for page in pages if page.jsonLdCount > 0),
        "pagesWithAnswerCue": sum(1 for page in pages if page.hasDirectAnswerCue),
        "pagesWithEntityCue": sum(1 for page in pages if page.hasEntityCue),
        "findingsTotal": len(all_findings),
        "highFindings": sum(1 for finding in all_findings if finding["severity"] == "high"),
        "mediumFindings": sum(1 for finding in all_findings if finding["severity"] == "medium"),
        "lowFindings": sum(1 for finding in all_findings if finding["severity"] == "low"),
    }


def build_search_visibility_baseline_report(
    repo_root: Path = REPO_ROOT,
    base_url: str = DEFAULT_BASE_URL,
    sample_limit: int = 80,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    pages = [parse_page(path, repo_root, base_url) for path in discover_sample_pages(repo_root, sample_limit)]
    crawler_files = [
        file_check(repo_root, "robots.txt", "Crawler access and policy file"),
        file_check(repo_root, "sitemap.xml", "Canonical XML sitemap"),
        file_check(repo_root, "llms.txt", "AI/LLM context file"),
        file_check(repo_root, "llm-index.json", "Machine-readable AI context index"),
    ]
    missing_files = [row for row in crawler_files if not row["exists"]]
    summary = summarise_pages(pages)
    summary["missingCrawlerContextFiles"] = len(missing_files)

    return {
        "generatedAt": utc_now(),
        "batch": "Batch 1 - Search visibility baseline",
        "lane": "Lane 1 - Autonomous",
        "mode": "reports-only",
        "baseUrl": base_url,
        "repoRoot": str(repo_root),
        "skills": BATCH_1_SKILLS,
        "guardrails": [
            "Reports only; no public page edits.",
            "No commits, pushes, pull requests, deployments, DNS changes, Cloudflare changes, or outreach sends.",
            "Any recommended remediation must move to a separate Lane 2 approval-gated patch.",
        ],
        "crawlerContextFiles": crawler_files,
        "summary": summary,
        "pages": [asdict(page) for page in pages],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Batch 1 search visibility baseline report")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--sample-limit", type=int, default=80)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report = build_search_visibility_baseline_report(repo_root, args.base_url, args.sample_limit)
    output_path = Path(args.out)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = report["summary"]
    print(
        "Batch 1 search visibility baseline written to "
        f"{output_path} ({summary['pagesSampled']} sampled pages, {summary['findingsTotal']} report-only findings)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
