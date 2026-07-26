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
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "scripts" / "data" / "manuscripts.json"
DEFAULT_OUTPUT = ROOT / "data" / "book-sample-chapters.json"
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
PDF_MAGIC = b"%PDF-"

FRONT_MATTER_TITLES = {
    "contents",
    "table of contents",
    "copyright",
    "acknowledgements",
    "acknowledgments",
    "about the author",
}


def fetch_pdf(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JonathanHarrisBuild/1.0)",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if not data.startswith(PDF_MAGIC):
        preview = data[:120].decode("utf-8", errors="replace").replace("\n", " ")
        raise ValueError(f"Google Drive did not return a PDF (response starts: {preview!r})")
    destination.write_bytes(data)


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


def find_first_chapter(page_texts: list[str]) -> tuple[int, str, int | None]:
    candidates: list[tuple[int, str, str]] = []
    for index, raw in enumerate(page_texts):
        text = normalise_text(raw)
        if not text:
            continue
        found = _find_heading(text)
        if not found:
            continue
        heading, kind = found
        top_lines = [line.strip().lower() for line in _top_lines(text).splitlines()]
        if any(line in {"contents", "table of contents"} for line in top_lines[:5]):
            continue

        # Contents pages commonly contain many explicit chapter headings. The
        # older manuscript layout may put a chapter heading on an otherwise sparse
        # title page, so assess substance across the following two pages as well.
        heading_count = len(CHAPTER_HEADING_RE.findall(text))
        if kind == "chapter" and heading_count > 2:
            continue
        if kind == "numbered" and len(NUMBERED_HEADING_RE.findall(_top_lines(text))) > 2:
            continue
        body_words = _lookahead_body_words(page_texts, index)
        if body_words >= 80:
            candidates.append((index, heading, kind))

    if not candidates:
        raise ValueError("Could not locate a substantive chapter heading in extracted PDF text")

    start_page, heading, _kind = candidates[0]
    end_page: int | None = None
    for index in range(start_page + 1, len(page_texts)):
        text = normalise_text(page_texts[index])
        if not text:
            continue
        if NEXT_CHAPTER_RE.search(text):
            end_page = index
            break
        found = _find_heading(text)
        if found:
            # Do not treat a body page containing an incidental numbered list as a
            # chapter boundary. Fallback headings must appear near the top and the
            # page must have enough following body text or be a sparse title page.
            heading_text, kind = found
            if kind == "chapter":
                end_page = index
                break
            top = _top_lines(text)
            if heading_text in top and (_lookahead_body_words(page_texts, index, pages=2) >= 80):
                end_page = index
                break
    return start_page, heading, end_page


def extract_chapter(pdf_path: Path) -> dict[str, object]:
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError(f"Encrypted PDF cannot be read: {exc}") from exc
    page_texts = [(page.extract_text() or "") for page in reader.pages]
    start_page, heading, end_page = find_first_chapter(page_texts)
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
                fetch_pdf(str(record["download_url"]), pdf_path)
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
        print(f"WARN: {len(failures)} manuscript sample(s) could not be extracted; continuing with noindex fallback pages for those titles.")
        print("WARN: " + "\nWARN: ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
