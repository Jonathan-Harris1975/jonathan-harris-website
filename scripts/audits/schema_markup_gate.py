#!/usr/bin/env python3
"""Phase 4A schema-markup gate for the static website repo.

This gate is deliberately deterministic: it validates existing JSON-LD blocks and
fails closed for invalid or incomplete generated article/blog pages. It does not
fetch podcast episode data, because the podcast hub is embed-led and the R2
podcast estate remains the source of truth.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

SCRIPT_RE = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
ARTICLE_PATH_RE = re.compile(r"/(?:blog|topics|glossary|ebooks|newsletter|bio|compare|catalogue)/|index\.html$", re.I)
REQUIRED_FIELDS = ("@context", "@type")
BLOG_REQUIRED_FIELDS = ("headline", "description", "datePublished", "author", "mainEntityOfPage")


@dataclass
class SchemaGateFinding:
    path: str
    severity: str
    message: str


def _repo_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _jsonld_blocks(html: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in SCRIPT_RE.finditer(html):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            blocks.append({"__parse_error": str(exc)})
            continue
        if isinstance(parsed, list):
            blocks.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


def _types(block: Any) -> list[str]:
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            value = node.get("@type")
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list):
                out.extend(str(item) for item in value)
            walk(node.get("@graph"))

    walk(block)
    return out


def validate_html_file(path: Path, root: Path) -> list[SchemaGateFinding]:
    rel = _repo_path(path, root)
    if ".git" in path.parts or path.name.startswith("."):
        return []

    # The podcast area is embed-led. Previous episodes and transcripts are
    # governed by the embedded player/R2 podcast estate, not by collected static
    # episode data in this repo. Do not turn those legacy files into schema
    # blockers here.
    if rel.startswith("podcast/TT-") or rel.startswith("podcast/episodes/"):
        return []

    html = path.read_text(encoding="utf-8", errors="replace")
    blocks = _jsonld_blocks(html)
    findings: list[SchemaGateFinding] = []

    if not blocks:
        # Not every utility page requires schema, so this is advisory except for
        # generated knowledge/content surfaces.
        if ARTICLE_PATH_RE.search(f"/{rel}"):
            findings.append(SchemaGateFinding(rel, "advisory", "No JSON-LD block found."))
        return findings

    for block in blocks:
        if "__parse_error" in block:
            findings.append(SchemaGateFinding(rel, "critical", f"Invalid JSON-LD: {block['__parse_error']}"))
            continue
        for field in REQUIRED_FIELDS:
            if field not in block:
                findings.append(SchemaGateFinding(rel, "critical", f"Missing JSON-LD field: {field}"))
        if block.get("@context") != "https://schema.org":
            findings.append(SchemaGateFinding(rel, "critical", "JSON-LD @context must be https://schema.org."))

        schema_types = set(_types(block))
        if schema_types.intersection({"BlogPosting", "Article", "PodcastEpisode"}):
            for field in BLOG_REQUIRED_FIELDS:
                if not block.get(field):
                    findings.append(SchemaGateFinding(rel, "critical", f"Missing article schema field: {field}"))

    return findings


def run_schema_gate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    html_files = sorted(path for path in root.rglob("*.html") if ".git" not in path.parts)
    findings: list[SchemaGateFinding] = []
    checked = 0

    for path in html_files:
        checked += 1
        findings.extend(validate_html_file(path, root))

    critical = [finding for finding in findings if finding.severity == "critical"]
    return {
        "ok": not critical,
        "phase": "4A",
        "skill": "schema-markup",
        "mode": "auto-apply-template-only-fail-closed",
        "checkedHtmlFiles": checked,
        "criticalCount": len(critical),
        "advisoryCount": sum(1 for finding in findings if finding.severity == "advisory"),
        "findings": [asdict(finding) for finding in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate website JSON-LD structured data.")
    parser.add_argument("--root", default=".", help="Website repo root")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    report = run_schema_gate(Path(args.root))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"schema-markup gate: checked={report['checkedHtmlFiles']} critical={report['criticalCount']} advisory={report['advisoryCount']}")
        for finding in report["findings"][:50]:
            print(f"{finding['severity'].upper()}: {finding['path']}: {finding['message']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
