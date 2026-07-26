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
NEXT_CHAPTER_RE = re.compile(
    r"(?im)^\s*chapter\s+(?:2|two|ii)\b[^\n]{0,140}\s*$"
)
PDF_MAGIC = b"%PDF-"


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


def find_first_chapter(page_texts: list[str]) -> tuple[int, str, int | None]:
    candidates: list[tuple[int, str]] = []
    for index, raw in enumerate(page_texts):
        text = normalise_text(raw)
        if not text:
            continue
        match = CHAPTER_HEADING_RE.search(text)
        if not match:
            continue
        heading = re.sub(r"\s+", " ", match.group(1)).strip()
        # Contents pages commonly contain many chapter headings. Prefer a page with
        # one or two headings and a meaningful body after the first heading.
        heading_count = len(CHAPTER_HEADING_RE.findall(text))
        body_after = text[match.end() :]
        body_words = len(re.findall(r"\b\w+\b", body_after))
        if heading_count <= 2 and body_words >= 80:
            candidates.append((index, heading))
    if not candidates:
        raise ValueError("Could not locate a substantive chapter heading in extracted PDF text")

    start_page, heading = candidates[0]
    end_page: int | None = None
    for index in range(start_page + 1, len(page_texts)):
        text = normalise_text(page_texts[index])
        if NEXT_CHAPTER_RE.search(text):
            end_page = index
            break
        match = CHAPTER_HEADING_RE.search(text)
        if match and index > start_page:
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

    if failures:
        raise RuntimeError("Manuscript sample extraction failed:\n- " + "\n- ".join(failures))

    output_records.sort(key=lambda item: str(item["slug"]))
    payload = {
        "schema_version": 1,
        "book_count": len(output_records),
        "books": output_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)} with {len(output_records)} genuine chapter samples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
