#!/usr/bin/env python3
"""Download manuscript PDFs and extract one genuine chapter per ebook.

Input manuscript URLs are private build-time data. The committed/public cache contains
only extracted chapter text and non-sensitive provenance such as source filename and
page range; Drive URLs and file IDs are deliberately excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import urllib.request
import urllib.parse
import http.cookiejar
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "scripts" / "data" / "manuscripts.json"
DEFAULT_OUTPUT = ROOT / "data" / "book-sample-chapters.json"
MASTER_BOOKS_PATH = ROOT / "data" / "ebooks-master.json"
CHAPTER_HEADING_RE = re.compile(
    r"(?im)^(?:\s*)(chapter\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|i{1,3}|iv|v|vi{0,3}|ix|x)\b[^\n]{0,140})\s*$"
)
NUMBERED_HEADING_RE = re.compile(
    r"(?m)^\s*((?:\d{1,2}|[IVXLCDMivxlcdm]{1,8})[.)]?\s*(?:[-:–—]\s*)?[A-Z][^\n]{3,140})\s*$"
)
BARE_CHAPTER_HEADING_RE = re.compile(
    r"(?i)^chapter\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|i{1,3}|iv|v|vi{0,3}|ix|x)\s*$"
)
NAMED_SECTION_RE = re.compile(r"(?im)^\s*((?:introduction|preface|foreword))\s*$")
NEXT_CHAPTER_RE = re.compile(
    r"(?im)^\s*chapter\s+(?:2|two|ii)\b[^\n]{0,140}\s*$"
)
FIRST_CHAPTER_RE = re.compile(
    r"(?i)^chapter\s+(?:1|one|i)\b"
)
PDF_MAGIC = b"%PDF-"

FRONT_MATTER_TITLES = {
    "contents",
    "table of contents",
    "copyright",
    "acknowledgements",
    "acknowledgments",
    "about the author",
}


def _request_bytes(opener: urllib.request.OpenerDirector, url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JonathanHarrisBuild/1.0)",
            "Accept": "application/pdf,application/octet-stream,text/html;q=0.8,*/*;q=0.1",
            "Referer": "https://drive.google.com/",
        },
    )
    with opener.open(request, timeout=90) as response:
        return response.read(), response.geturl()


def _drive_confirmation_url(html_text: str, response_url: str, file_id: str) -> str | None:
    """Extract Drive's virus-scan/large-file confirmation form when present."""
    form = re.search(r'<form[^>]+action=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</form>', html_text, re.I)
    if form:
        action = urllib.parse.urljoin(response_url, form.group(1))
        fields: dict[str, str] = {}
        for name, value in re.findall(r'<input[^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', form.group(2), re.I):
            fields[name] = value
        fields.setdefault("id", file_id)
        fields.setdefault("export", "download")
        if fields:
            return action + ("&" if "?" in action else "?") + urllib.parse.urlencode(fields)

    token = re.search(r'(?:confirm=|name=["\']confirm["\'][^>]+value=["\'])([0-9A-Za-z_-]+)', html_text, re.I)
    if token:
        return f"https://drive.usercontent.google.com/download?id={urllib.parse.quote(file_id)}&export=download&confirm={urllib.parse.quote(token.group(1))}"
    return None


def fetch_pdf(url: str, destination: Path, file_id: str = "") -> None:
    """Fetch a public/shared Drive PDF, including Drive confirmation flows.

    A production sample must be sourced from the manuscript. HTML interstitials are
    followed only to obtain the real file; they are never treated as sample content.
    """
    file_id = (file_id or "").strip()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    candidates = [url]
    if file_id:
        candidates.extend([
            f"https://drive.usercontent.google.com/download?id={urllib.parse.quote(file_id)}&export=download&confirm=t",
            f"https://drive.google.com/uc?export=download&id={urllib.parse.quote(file_id)}&confirm=t",
        ])

    seen: set[str] = set()
    diagnostics: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            data, final_url = _request_bytes(opener, candidate)
        except Exception as exc:
            diagnostics.append(f"{candidate}: {type(exc).__name__}: {exc}")
            continue
        if data.startswith(PDF_MAGIC):
            destination.write_bytes(data)
            return
        html_text = data.decode("utf-8", errors="replace")
        if file_id:
            confirm_url = _drive_confirmation_url(html_text, final_url, file_id)
            if confirm_url and confirm_url not in seen:
                seen.add(confirm_url)
                try:
                    confirmed, confirmed_url = _request_bytes(opener, confirm_url)
                    if confirmed.startswith(PDF_MAGIC):
                        destination.write_bytes(confirmed)
                        return
                    preview = confirmed[:160].decode("utf-8", errors="replace").replace("\n", " ")
                    diagnostics.append(f"{confirmed_url}: confirmation response was not PDF: {preview!r}")
                except Exception as exc:
                    diagnostics.append(f"{confirm_url}: {type(exc).__name__}: {exc}")
        preview = data[:160].decode("utf-8", errors="replace").replace("\n", " ")
        diagnostics.append(f"{final_url}: response was not PDF: {preview!r}")

    detail = " | ".join(diagnostics[-4:])
    raise ValueError(f"Google Drive manuscript download did not return a PDF. {detail}")


def normalise_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def meaningful_paragraphs(text: str) -> list[str]:
    chunks = [re.sub(r"\s+", " ", chunk).strip() for chunk in re.split(r"\n\s*\n", text)]
    return [chunk for chunk in chunks if len(chunk) >= 25]


def _top_lines(text: str, limit: int = 12) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:limit])


def _find_heading(text: str) -> tuple[str, str] | None:
    """Return (heading, kind), preferring explicit chapter headings.

    Older manuscripts often put the chapter heading on a dedicated title page,
    while newer manuscripts put the heading and body on the same page. Numbered
    and named-section fallbacks are restricted to the top of a page to avoid
    mistaking ordinary numbered lists for chapter boundaries.
    """
    match = CHAPTER_HEADING_RE.search(text)
    if match:
        heading = re.sub(r"\s+", " ", match.group(1)).strip()
        # A common PDF layout is "Chapter 1" on one line and the chapter title
        # on the next. Preserve that title when it is short and clearly heading-like.
        tail = text[match.end() :].lstrip(" \t\n")
        next_line = tail.splitlines()[0].strip() if tail else ""
        if (
            BARE_CHAPTER_HEADING_RE.fullmatch(heading)
            and next_line
            and len(next_line) <= 140
            and len(next_line.split()) <= 18
            and next_line.lower() not in FRONT_MATTER_TITLES
        ):
            heading = f"{heading}: {next_line}"
        return heading, "chapter"

    top = _top_lines(text)
    match = NUMBERED_HEADING_RE.search(top)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip(), "numbered"

    match = NAMED_SECTION_RE.search(top)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip().title(), "named"
    return None


def _lookahead_body_words(page_texts: list[str], start_page: int, pages: int = 3) -> int:
    """Count nearby body words so chapter-title-only pages remain valid."""
    total = 0
    for index in range(start_page, min(len(page_texts), start_page + pages)):
        text = normalise_text(page_texts[index])
        if not text:
            continue
        if index == start_page:
            explicit = CHAPTER_HEADING_RE.search(text)
            if explicit:
                text = text[explicit.end() :]
        total += len(re.findall(r"\b\w+\b", text))
    return total


def _numbered_heading_value(heading: str) -> int | None:
    """Return the leading chapter-style number for a fallback numbered heading."""
    match = re.match(r"^\s*(\d{1,2}|[IVXLCDMivxlcdm]{1,8})(?:[.)]|\s|$)", heading)
    if not match:
        return None
    token = match.group(1).upper()
    if token.isdigit():
        return int(token)
    roman_values = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
    return roman_values.get(token)


def find_first_chapter(page_texts: list[str]) -> tuple[int, str, int | None, str]:
    candidates: list[tuple[int, str, str]] = []
    for index, raw in enumerate(page_texts):
        text = normalise_text(raw)
        if not text:
            continue
        found = _find_heading(text)
        if not found:
            continue
        heading, kind = found
        top_text = _top_lines(text, limit=24)
        top_lines = [line.strip().lower() for line in top_text.splitlines()]
        if any(line in {"contents", "table of contents"} for line in top_lines):
            continue

        # Explicit chapter headings are only credible starts when they appear near
        # the top of the page. This blocks chapter references buried in front matter.
        if kind == "chapter" and not CHAPTER_HEADING_RE.search(top_text):
            continue

        # Contents pages can be split across several PDF pages and may expose only
        # Chapter 1 + Chapter 2 on a given page. Treat two or more explicit chapter
        # headings on the same page as navigation, not manuscript body.
        heading_count = len(CHAPTER_HEADING_RE.findall(text))
        if kind == "chapter" and heading_count >= 2:
            continue
        if kind == "numbered" and len(NUMBERED_HEADING_RE.findall(_top_lines(text))) > 2:
            continue
        body_words = _lookahead_body_words(page_texts, index)
        if body_words >= 80:
            candidates.append((index, heading, kind))

    if not candidates:
        raise ValueError("Could not locate a substantive chapter heading in extracted PDF text")

    # Prefer a real Chapter 1 over front matter or generic numbered fallbacks.
    # This avoids treating an Introduction as the sample when a conventional
    # Chapter 1 appears later in the manuscript.
    first_chapter_candidates = [
        item for item in candidates
        if item[2] == "chapter" and FIRST_CHAPTER_RE.match(item[1])
    ]
    numbered_one_candidates = [
        item for item in candidates
        if item[2] == "numbered" and _numbered_heading_value(item[1]) == 1
    ]
    if first_chapter_candidates:
        start_page, heading, start_kind = first_chapter_candidates[0]
    elif numbered_one_candidates:
        start_page, heading, start_kind = numbered_one_candidates[0]
    else:
        start_page, heading, start_kind = candidates[0]

    end_page: int | None = None
    accumulated_words = 0
    for index in range(start_page + 1, len(page_texts)):
        previous_text = normalise_text(page_texts[index - 1])
        accumulated_words += len(re.findall(r"\b\w+\b", previous_text))

        text = normalise_text(page_texts[index])
        if not text:
            continue

        # Explicit Chapter 1 manuscripts must only end at an explicit Chapter 2.
        # Numbered subsection headings inside Chapter 1 are not chapter boundaries.
        if start_kind == "chapter":
            if NEXT_CHAPTER_RE.search(text):
                end_page = index
                break
            continue

        found = _find_heading(text)
        if not found:
            continue
        heading_text, kind = found

        # If a fallback-numbered manuscript later exposes an explicit Chapter 2,
        # that is authoritative.
        if kind == "chapter" and NEXT_CHAPTER_RE.search(text):
            end_page = index
            break

        if start_kind == "numbered" and kind == "numbered":
            # Only a top-level-looking "2 ..." can end a "1 ..." chapter, and
            # never before enough body text has accumulated to satisfy the
            # genuine-sample floor. This blocks 1.1/1.2-style section headings
            # and early numbered lists from truncating the chapter.
            top = _top_lines(text)
            if (
                _numbered_heading_value(heading_text) == 2
                and heading_text in top
                and accumulated_words >= 350
                and _lookahead_body_words(page_texts, index, pages=2) >= 80
            ):
                end_page = index
                break

        if start_kind == "named" and kind in {"chapter", "numbered"}:
            # Named front matter is only a last-resort fallback. Stop when the
            # next substantive structural section begins.
            top = _top_lines(text)
            if heading_text in top and accumulated_words >= 350:
                end_page = index
                break

    return start_page, heading, end_page, start_kind


def extract_chapter(pdf_path: Path) -> dict[str, object]:
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError(f"Encrypted PDF cannot be read: {exc}") from exc
    page_texts = [(page.extract_text() or "") for page in reader.pages]
    start_page, heading, end_page, _start_kind = find_first_chapter(page_texts)
    stop = end_page if end_page is not None else min(len(page_texts), start_page + 30)
    selected = page_texts[start_page:stop]
    combined = normalise_text("\n\n".join(selected))
    match = CHAPTER_HEADING_RE.search(combined)
    if match:
        combined = normalise_text(combined[match.end() :])
    paragraphs = meaningful_paragraphs(combined)
    word_count = sum(len(re.findall(r"\b\w+\b", paragraph)) for paragraph in paragraphs)
    if word_count < 350:
        raise ValueError(f"Extracted chapter is too short ({word_count} words)")
    return {
        "chapter_title": heading,
        "page_start": start_page + 1,
        "page_end": stop,
        "word_count": word_count,
        "paragraphs": paragraphs,
    }


def load_existing(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(item["slug"]): item for item in data.get("books", []) if item.get("slug")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch manuscript PDFs and build genuine chapter samples")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh", action="store_true", help="Re-extract chapters even when the source filename is unchanged")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write successful samples and continue when individual manuscripts cannot be extracted.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = manifest.get("books", [])
    if not isinstance(records, list) or not records:
        raise RuntimeError("Manuscript manifest contains no book records")
    master = json.loads(MASTER_BOOKS_PATH.read_text(encoding="utf-8"))
    master_books = master.get("books", []) if isinstance(master, dict) else master
    expected_slugs = {str(item.get("slug", "")).strip() for item in master_books if isinstance(item, dict) and item.get("slug")}
    manifest_slugs = {str(item.get("slug", "")).strip() for item in records if isinstance(item, dict) and item.get("slug")}
    if manifest_slugs != expected_slugs:
        missing = sorted(expected_slugs - manifest_slugs)
        extra = sorted(manifest_slugs - expected_slugs)
        details = []
        if missing: details.append(f"missing {len(missing)} governed book(s): {', '.join(missing[:5])}")
        if extra: details.append(f"contains {len(extra)} unknown book(s): {', '.join(extra[:5])}")
        raise RuntimeError("Manuscript manifest does not cover the full governed catalogue; " + "; ".join(details))
    existing = load_existing(args.output)
    output_records: list[dict[str, object]] = []
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="jh-manuscripts-") as temp_dir:
        temp = Path(temp_dir)
        for position, record in enumerate(records, start=1):
            slug = str(record["slug"])
            filename = str(record["filename"])
            previous = existing.get(slug)
            if previous and not args.refresh and previous.get("source_filename") == filename and previous.get("paragraphs"):
                output_records.append(previous)
                print(f"[{position}/{len(records)}] {slug}: cached")
                continue
            try:
                pdf_path = temp / f"{position:02d}.pdf"
                print(f"[{position}/{len(records)}] {slug}: downloading")
                fetch_pdf(str(record["download_url"]), pdf_path, str(record.get("file_id", "")))
                extracted = extract_chapter(pdf_path)
                output_records.append(
                    {
                        "slug": slug,
                        "title": str(record["title"]),
                        "source_filename": filename,
                        "source_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        **extracted,
                    }
                )
            except Exception as exc:
                failures.append(f"{slug}: {exc}")

    output_records.sort(key=lambda item: str(item["slug"]))
    payload = {
        "schema_version": 1,
        "book_count": len(output_records),
        "books": output_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)} with {len(output_records)} genuine chapter samples.")

    if failures:
        message = "Manuscript sample extraction failed:\n- " + "\n- ".join(failures)
        if not args.allow_partial:
            raise RuntimeError(message)
        print(f"WARN: {len(failures)} manuscript sample(s) could not be extracted; continuing without sample routes for those titles.")
        print("WARN: " + "\nWARN: ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
