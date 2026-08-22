#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADERS = ROOT / "_headers"
NON_EXECUTABLE_TYPES = {"application/ld+json", "application/json"}


class ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.current: list[str] | None = None
        self.current_type = ""
        self.has_src = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        values = {str(name).lower(): value for name, value in attrs}
        self.has_src = bool(values.get("src"))
        self.current_type = str(values.get("type") or "").lower()
        self.current = []

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or self.current is None:
            return
        body = "".join(self.current)
        if not self.has_src and self.current_type not in NON_EXECUTABLE_TYPES and body.strip():
            self.scripts.append(body)
        self.current = None
        self.current_type = ""
        self.has_src = False


def sha256_source(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


def main() -> int:
    header_text = HEADERS.read_text(encoding="utf-8")
    failures: list[str] = []
    if re.search(r"(?:script-src|script-src-elem)[^;]*'unsafe-inline'", header_text):
        failures.append("Executable-script CSP still permits 'unsafe-inline'.")

    declared = set(re.findall(r"'sha256-[A-Za-z0-9+/=]+'", header_text))
    required: dict[str, list[str]] = {}
    for path in ROOT.rglob("*.html"):
        parser = ScriptCollector()
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
        for body in parser.scripts:
            required.setdefault(sha256_source(body), []).append(path.relative_to(ROOT).as_posix())

    for source, pages in sorted(required.items()):
        if source not in declared:
            failures.append(f"Missing CSP hash {source} for inline script used by {pages[0]} ({len(pages)} page(s)).")

    # Dynamic Pages Functions emit this tiny executable bootstrap in generated HTML.
    dynamic_bootstrap = "document.documentElement.classList.add('js-enabled');"
    dynamic_hash = sha256_source(dynamic_bootstrap)
    if dynamic_hash not in declared:
        failures.append(f"Missing CSP hash {dynamic_hash} for dynamic podcast page bootstrap.")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print(f"CSP inline-script gate passed: {len(required)} static executable script hash(es) governed; unsafe-inline is absent for scripts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
