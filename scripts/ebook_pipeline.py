from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import openpyxl

from scripts.ebook_content_helpers import (
    audience_faq_answer,
    build_same_source_srcset,
    cover_sizes,
    default_short as helper_default_short,
    normalise_audience_copy,
    normalise_topic_copy,
    topic_intro as helper_topic_intro,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
EBOOKS_DIR = ROOT / "ebooks"
CATALOGUE_DIR = ROOT / "catalogue"
TOPICS_DIR = ROOT / "topics"
MASTER_PATH = DATA_DIR / "ebooks-master.json"
WORKBOOK_NORMALISATIONS_PATH = ROOT / "config" / "workbook-normalisations.json"
CRAWLER_CHECKSUMS_PATH = ROOT / "config" / "crawler-checksums.json"
CRAWLER_SNAPSHOTS_DIR = ROOT / "config" / "crawler-snapshots"
HEADER_PARTIAL = ROOT / "assets" / "partials" / "header.html"
FOOTER_PARTIAL = ROOT / "assets" / "partials" / "footer.html"
EBOOK_TEMPLATE_CSS = ROOT / "assets" / "css" / "ebook-template.css"
SITE_NAME = "Jonathan Harris"
SITE_URL = "https://jonathan-harris.online"
DEFAULT_AUDIENCE = "Readers who want practical, plain-English AI insight without the buzzwords."
DEFAULT_TONE = "Plain-English, practical, sceptical, no-hype"
BOOK_COVER_WIDTH = 2480
BOOK_COVER_HEIGHT = 3508
VALIDATION_REPORT = ROOT / "VALIDATION_OUTPUT.txt"
SHARED_INTER_FONT_HEAD_BLOCK = """<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap" rel="stylesheet"/>"""

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "book", "by", "for", "from", "how", "in", "into",
    "is", "it", "its", "of", "on", "or", "our", "that", "the", "this", "through", "to", "what",
    "when", "where", "why", "with", "your", "you", "ai", "artificial", "intelligence",
}


LEGACY_DETAIL_REDIRECT_LINES = [
    "/ebooks/*/detail  /ebooks/:splat/  301",
    "/ebooks/*/detail.html  /ebooks/:splat/  301",
    "/ebooks/*/details.html  /ebooks/:splat/  301",
]

LOCALE_ALIAS_REDIRECT_LINES = [
    f"/en-gb/*  {SITE_URL}/:splat  301",
    f"/en-us/*  {SITE_URL}/:splat  301",
    f"/en-ca/*  {SITE_URL}/:splat  301",
    f"/en-au/*  {SITE_URL}/:splat  301",
]

MALFORMED_SLUG_FIXES = [
    {
        "source": "/ebooks/artificial-intelligence-in-pharmaceuticalsrevolutionizing-healthcare",
        "target": "/ebooks/artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare/",
    },
    {
        "source": "/ebooks/artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement-k",
        "target": "/ebooks/artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement/",
    },
    {
        "source": "/ebooks/lights-camera-algorithm-ais-role-in-modern-filmmaking",
        "target": "/ebooks/lights-camera-algorithm-ai-s-role-in-modern-filmmaking/",
    },
    {
        "source": "/ebooks/the-architects-of-ai_-pioneers_-breakthroughs_-and-the-road-ahead",
        "target": "/ebooks/the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead/",
    },
]

EXTERNAL_CRAWLER_FILES = {
    "robots": f"{SITE_URL}/robots.txt",
    "sitemap": f"{SITE_URL}/sitemap.xml",
    "llms": f"{SITE_URL}/llms.txt",
}

CRAWLER_SNAPSHOT_FILENAMES = {
    "robots": "robots.txt",
    "sitemap": "sitemap.xml",
    "llms": "llms.txt",
}

TEMPLATE_REQUIRED_FRAGMENTS = [
    '<body class="ebook-detail">',
    '<nav aria-label="Breadcrumb" class="breadcrumbs">',
    '<section class="card ebook-section quick-facts">',
    '<section class="ebook-showcase">',
    '<section class="card ebook-section" id="deeper-overview">',
    '<section class="related-books card">',
    '<section class="faq card" aria-label="Frequently asked questions">',
    '<section class="jh-journey-panel">',
]

TEMPLATE_ORDERED_MARKERS = [
    '<section class="card ebook-section quick-facts">',
    '<section class="ebook-showcase">',
    '<h2>Who this book is for</h2>',
    '<h2>Key themes</h2>',
    '<h2>What you’ll learn</h2>',
    '<section class="card ebook-section" id="deeper-overview">',
    '<section class="related-books card">',
    '<section class="faq card" aria-label="Frequently asked questions">',
]

BROKEN_PHRASE_FRAGMENTS = [
    "AI in how ai shapes attention and thinking",
    "how AI changes the day-to-day reality of how ai shapes attention and thinking",
    "how AI changes how ai shapes attention and thinking in practice",
    "where AI fits inside how ai shapes attention and thinking",
    "AI is not arriving in how ai shapes attention and thinking",
]

TITLE_SUBSTITUTION_FIELD_NAMES = (
    "short",
    "description",
    "summary",
    "audience",
    "who_for",
    "what_this_book_covers",
    "why_it_matters",
)

SLUG_SUBJECT_PREFIXES = (
    "ai-revolution-in-",
    "ai-in-",
    "artificial-intelligence-revolution-in-",
    "artificial-intelligence-in-",
    "artificial-intelligence-for-",
    "artificial-intelligence-powered-",
    "digital-diagnosis-how-ai-is-revolutionizing-",
    "digital-defense-the-role-of-ai-in-",
    "from-reporters-to-robots-how-ai-is-reshaping-",
    "lights-camera-algorithm-ai-s-role-in-",
    "smart-buildings-ai-powered-",
    "beyond-earth-how-ai-is-transforming-",
    "the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-",
    "the-future-of-",
    "the-ai-behind-your-feed-",
    "the-ai-music-revolution-",
    "the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-",
)

SLUG_SUBJECT_STOP_WORDS = {
    "revolutionizing",
    "transforming",
    "modernizing",
    "redefining",
    "reimagining",
    "leveraging",
    "harnessing",
    "optimizing",
    "building",
    "navigating",
    "reshaping",
    "enhance",
    "enhancing",
    "through",
    "with",
    "for",
    "a",
    "an",
    "the",
    "future",
    "how",
    "what",
}

SLUG_SUBJECT_OVERRIDES = {
    "smart-buildings-ai-powered-efficiency-and-sustainability": "smart buildings",
    "digital-diagnosis-how-ai-is-revolutionizing-healthcare": "healthcare",
    "digital-defense-the-role-of-ai-in-modern-warfare": "modern warfare",
    "from-reporters-to-robots-how-ai-is-reshaping-journalism": "journalism",
    "lights-camera-algorithm-ai-s-role-in-modern-filmmaking": "modern filmmaking",
    "beyond-earth-how-ai-is-transforming-space-exploration": "space exploration",
    "the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media": "social media",
    "the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information": "government",
    "the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming": "gaming",
}


def infer_subject_phrase(slug: str, title: str, topic: str) -> str:
    slug_clean = slugify(slug)
    if slug_clean in SLUG_SUBJECT_OVERRIDES:
        return SLUG_SUBJECT_OVERRIDES[slug_clean]
    for prefix in SLUG_SUBJECT_PREFIXES:
        if slug_clean.startswith(prefix):
            remainder = slug_clean[len(prefix):]
            words = []
            for part in remainder.split("-"):
                if words and part in SLUG_SUBJECT_STOP_WORDS:
                    break
                words.append(part)
            candidate = clean_paragraph(" ".join(words))
            if candidate:
                return candidate

    title_core = clean_paragraph(title).split(":", 1)[0].strip()
    patterns = [
        r"^AI Revolution in (.+)$",
        r"^AI in (.+)$",
        r"^Artificial Intelligence Revolution in (.+)$",
        r"^Artificial Intelligence in (.+)$",
        r"^Artificial Intelligence for (.+)$",
        r"^Artificial Intelligence Powered (.+)$",
        r"^The Future of (.+)$",
    ]
    for title_pattern in patterns:
        title_match = re.match(title_pattern, title_core, flags=re.I)
        if title_match:
            candidate = clean_paragraph(title_match.group(1))
            if candidate:
                return candidate.lower()

    topic_candidate = clean_paragraph(topic)
    if topic_candidate:
        return topic_candidate.lower()
    return title_core.lower()



def normalise_title_substitution_text(value: str, *, slug: str, title: str, topic: str) -> str:
    cleaned = clean_paragraph(value)
    if not cleaned:
        return cleaned

    title_core = clean_paragraph(title).split(":", 1)[0].strip()
    if title_core:
        subject = infer_subject_phrase(slug, title, topic)
        replacements = [
            (rf"\bAI in {re.escape(title_core)}\b", f"AI in {subject}"),
            (rf"\bA practical overview of AI in {re.escape(title_core)}\b", f"A practical overview of AI in {subject}"),
            (rf"\bhow AI changes the day-to-day reality of {re.escape(title_core)}\b", f"how AI changes the day-to-day reality of {subject}"),
            (rf"\bhow AI changes {re.escape(title_core)} in practice\b", f"how AI changes {subject} in practice"),
            (rf"\bwhere AI fits inside {re.escape(title_core)}\b", f"where AI fits inside {subject}"),
            (rf"\bAI is not arriving in {re.escape(title_core)}\b", f"AI is not arriving in {subject}"),
        ]
        for phrase_pattern, replacement_text in replacements:
            cleaned = re.sub(phrase_pattern, replacement_text, cleaned, flags=re.I)
    return normalise_topic_copy(cleaned, topic)



def sanitise_record_copy(record: Dict[str, Any]) -> Dict[str, Any]:
    slug = clean_paragraph(record.get("slug", ""))
    title = clean_paragraph(record.get("title", ""))
    topic = clean_paragraph(record.get("topic", ""))
    for field in TITLE_SUBSTITUTION_FIELD_NAMES:
        if field in record:
            record[field] = replace_banned_ebook_phrases(
                normalise_title_substitution_text(record.get(field, ""), slug=slug, title=title, topic=topic),
                slug,
            )
    if "what_youll_learn" in record and isinstance(record.get("what_youll_learn"), list):
        record["what_youll_learn"] = [
            replace_banned_ebook_phrases(
                normalise_title_substitution_text(item, slug=slug, title=title, topic=topic),
                slug,
            )
            for item in record.get("what_youll_learn", [])
            if clean_paragraph(item)
        ]
    if "short" in record:
        record["short_description"] = record.get("short", "")
    if "audience" in record:
        record["audience"] = normalise_audience_copy(record.get("audience", ""), topic) or record.get("audience", "")
    if "who_for" in record:
        record["who_for"] = replace_banned_ebook_phrases(
            normalise_title_substitution_text(record.get("who_for", ""), slug=slug, title=title, topic=topic),
            slug,
        )
    faq_items = record.get("faq")
    if isinstance(faq_items, list):
        cleaned_faq = []
        for item in faq_items:
            if not isinstance(item, dict):
                continue
            question = clean_paragraph(item.get("name", ""))
            answer = clean_paragraph((item.get("acceptedAnswer") or {}).get("text", ""))
            if question.lower() == "who is this book for?":
                answer = audience_faq_answer(record.get("audience", ""), topic)
            else:
                answer = replace_banned_ebook_phrases(
                    normalise_title_substitution_text(answer, slug=slug, title=title, topic=topic),
                    slug,
                )
            cleaned_faq.append({
                "@type": item.get("@type") or "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": (item.get("acceptedAnswer") or {}).get("@type") or "Answer",
                    "text": answer,
                },
            })
        record["faq"] = cleaned_faq
    return record

def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))



def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def load_workbook_normalisations() -> Dict[str, Dict[str, Dict[str, str]]]:
    payload = read_json(WORKBOOK_NORMALISATIONS_PATH, default={}) or {}
    if not isinstance(payload, dict):
        return {}
    approved: Dict[str, Dict[str, Dict[str, str]]] = {}
    for slug, fields in payload.items():
        if not isinstance(fields, dict):
            continue
        field_map: Dict[str, Dict[str, str]] = {}
        for field_name, entry in fields.items():
            if not isinstance(entry, dict):
                continue
            field_map[clean_paragraph(field_name)] = {
                "raw": clean_paragraph(entry.get("raw", "")),
                "approved": clean_paragraph(entry.get("approved", "")),
            }
        approved[clean_paragraph(slug)] = field_map
    return approved



def utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def infer_build_timestamp() -> str:
    if MASTER_PATH.exists():
        return dt.datetime.fromtimestamp(MASTER_PATH.stat().st_mtime, tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return utc_now()


def parse_timestamp(value: Any) -> dt.datetime | None:
    cleaned = clean_paragraph(value)
    if not cleaned:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return dt.datetime.fromisoformat(cleaned).replace(tzinfo=dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", cleaned)
        if not match:
            return None
        return dt.datetime.fromisoformat(match.group(1)).replace(tzinfo=dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def governed_generated_utc(books: List[Dict[str, Any]]) -> str:
    timestamps = [
        parse_timestamp(book.get("dateModified") or book.get("datePublished"))
        for book in books
    ]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if timestamps:
        return max(timestamps).isoformat().replace("+00:00", "Z")
    return infer_build_timestamp()


def normalise_lastmod(value: Any) -> str:
    cleaned = clean_paragraph(value)
    if not cleaned:
        return dt.date.today().isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        return cleaned
    try:
        parsed = dt.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", cleaned)
        return match.group(1) if match else dt.date.today().isoformat()
    return parsed.date().isoformat()


def file_lastmod(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).date().isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()



def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("&", "and")
    value = re.sub(r"[’'`]", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")



def normalise_space(value: str) -> str:
    value = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()



def clean_paragraph(value: str) -> str:
    value = normalise_space(value)
    value = value.replace(" .", ".")
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    return value



def ensure_trailing_slash(url: str) -> str:
    url = clean_paragraph(url)
    if not url:
        return url
    return url if url.endswith("/") else url + "/"



def strip_pages_from_summary(text: str, pages: int | None = None) -> str:
    cleaned = clean_paragraph(text)
    cleaned = re.sub(r"\.?\s*Pages:\s*\d+\.?\s*$", ".", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+\.$", ".", cleaned)
    if pages:
        cleaned = re.sub(rf"\b{pages}\s*-?\s*page guide\.?$", "", cleaned, flags=re.I).strip()
    return clean_paragraph(cleaned)


def canonical_text_for_role_check(value: Any, *, pages: int | None = None) -> str:
    text = clean_paragraph(value)
    if pages:
        text = strip_pages_from_summary(text, pages)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_role_validation_errors(records: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    audience_counter = Counter()
    who_for_counter = Counter()

    for record in records:
        pages = record.get("pages")
        roles = {
            "short": canonical_text_for_role_check(record.get("short"), pages=pages),
            "description": canonical_text_for_role_check(record.get("description"), pages=pages),
            "summary": canonical_text_for_role_check(record.get("summary"), pages=pages),
            "what_this_book_covers": canonical_text_for_role_check(record.get("what_this_book_covers"), pages=pages),
            "audience": canonical_text_for_role_check(record.get("audience")),
            "who_for": canonical_text_for_role_check(record.get("who_for")),
            "why_it_matters": canonical_text_for_role_check(record.get("why_it_matters")),
        }

        identical_pairs = [
            ("short", "description"),
            ("description", "summary"),
            ("summary", "what_this_book_covers"),
            ("audience", "who_for"),
            ("summary", "why_it_matters"),
        ]
        for left, right in identical_pairs:
            if roles[left] and roles[left] == roles[right]:
                errors.append(f"{record['slug']} collapses the distinct workbook roles for {left} and {right}.")

        if roles["audience"]:
            audience_counter[roles["audience"]] += 1
        if roles["who_for"]:
            who_for_counter[roles["who_for"]] += 1

    repeated_audience = [count for count in audience_counter.values() if count > max(6, len(records) // 4)]
    repeated_who_for = [count for count in who_for_counter.values() if count > max(6, len(records) // 4)]
    if repeated_audience:
        errors.append("Workbook audience field is still over-reused across the catalogue; vary it more before publishing.")
    if repeated_who_for:
        errors.append("Workbook 'Who this book is for' field is still over-reused across the catalogue; vary it more before publishing.")
    return errors



def split_field(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_paragraph(v) for v in value if clean_paragraph(v)]
    text = str(value).replace("•", "\n")
    parts = re.split(r"\n|\||;", text)
    return [clean_paragraph(part) for part in parts if clean_paragraph(part)]



def unique_list(values: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        cleaned = clean_paragraph(value)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output



def choose_authoritative_text(workbook_content: Dict[str, Any], content_source: Dict[str, Any], field: str, *, allow_fallback: bool = False) -> Any:
    workbook_value = workbook_content.get(field)
    if isinstance(workbook_value, list):
        if any(clean_paragraph(item) for item in workbook_value):
            return workbook_value
    elif clean_paragraph(workbook_value):
        return workbook_value
    return content_source.get(field) if allow_fallback else None


def book_about_terms(book: Dict[str, Any]) -> List[str]:
    return unique_list([book.get("topic", ""), *(book.get("tags", [])[:5] or [])])


def template_contract_errors(page_text: str, book: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for fragment in TEMPLATE_REQUIRED_FRAGMENTS:
        if fragment not in page_text:
            errors.append(f"{book['slug']} is missing a governed template fragment: {fragment}")

    positions: List[int] = []
    for marker in TEMPLATE_ORDERED_MARKERS:
        pos = page_text.find(marker)
        if pos == -1:
            continue
        positions.append(pos)
    if positions != sorted(positions):
        errors.append(f"{book['slug']} breaks the governed section order for canonical ebook pages.")

    required_ctas = [
        f'href="{book["buy_route"]}"',
        'href="/ebooks/"',
        'href="#deeper-overview"',
    ]
    for cta in required_ctas:
        if cta not in page_text:
            errors.append(f"{book['slug']} is missing a governed CTA target: {cta}")
    return errors


def text_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", clean_paragraph(value).lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def stem_token(token: str) -> str:
    token = clean_paragraph(token).lower()
    for suffix in (
        "ization", "isation", "ational", "ability", "ibility", "ation", "ition",
        "fulness", "ousness", "iveness", "ingly", "ments", "ement", "ment",
        "able", "ible", "ness", "ship", "ance", "ence", "ally", "fully",
        "less", "iest", "ies", "ied", "ing", "ers", "er", "ed", "ly",
        "ity", "s",
    ):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def significant_tokens(value: str) -> set[str]:
    return {stem_token(token) for token in text_tokens(value)}


def book_token_groups(book: Dict[str, Any]) -> Dict[str, set[str]]:
    return {
        "topic": significant_tokens(book.get("topic", "")),
        "title": significant_tokens(book.get("title", "")),
        "tags": {token for item in book.get("tags", []) for token in significant_tokens(item)},
        "keywords": {token for item in book.get("keywords", []) for token in significant_tokens(item)},
    }


def related_book_score(candidate: Dict[str, Any], current: Dict[str, Any], current_tokens: Dict[str, set[str]], candidate_tokens: Dict[str, set[str]]) -> tuple[int, tuple[int, int, int, int, str]]:
    same_topic = int(candidate.get("topic") == current.get("topic"))
    title_overlap = len(current_tokens["title"] & candidate_tokens["title"])
    topic_overlap = len(current_tokens["topic"] & candidate_tokens["topic"])
    tag_overlap = len(current_tokens["tags"] & candidate_tokens["tags"])
    keyword_overlap = len(current_tokens["keywords"] & candidate_tokens["keywords"])
    score = (same_topic * 100) + (title_overlap * 35) + (topic_overlap * 30) + (tag_overlap * 18) + (keyword_overlap * 8)
    tie_breaker = (same_topic, title_overlap, topic_overlap + tag_overlap, keyword_overlap, candidate["title"].lower())
    return score, tie_breaker


def broken_phrase_errors(books: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for book in books:
        title_core = clean_paragraph(book.get("title", "")).split(":", 1)[0].strip().lower()
        if not title_core:
            continue
        suspicious_fragments: List[str] = []
        if "ai" in title_core or "artificial intelligence" in title_core:
            suspicious_fragments = [
                f"ai in {title_core}",
                f"day-to-day reality of {title_core}",
                f"{title_core} in practice",
                f"fits inside {title_core}",
                f"arriving in {title_core}",
            ]
        for field in TITLE_SUBSTITUTION_FIELD_NAMES:
            value = clean_paragraph(book.get(field, ""))
            lower = value.lower()
            for fragment in BROKEN_PHRASE_FRAGMENTS:
                if fragment.lower() in lower:
                    errors.append(f"Broken phrase lint failed for {book['slug']} field {field}: {fragment}")
            if " in ai in " in f" {lower} ":
                errors.append(f"Broken phrase lint failed for {book['slug']} field {field}: in ai in")
            for fragment in suspicious_fragments:
                if fragment in lower:
                    errors.append(f"Broken title-substitution phrase detected for {book['slug']} field {field}: {fragment}")
    return errors


def title_contract_errors(relative_path: str, repo_title: str, workbook_title: str) -> List[str]:
    errors: List[str] = []
    if repo_title != workbook_title:
        errors.append(f"Workbook Pages title mismatch for {relative_path}: workbook '{workbook_title}' != repo '{repo_title}'.")
    return errors


def workbook_title_parity_audit(workbook_path: Path) -> Tuple[List[str], Dict[str, int]]:
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    if "Pages" not in wb.sheetnames:
        return ["Workbook is missing the Pages sheet."], {"checked": 0, "passed": 0, "mismatched": 0}

    ws = wb["Pages"]
    header_row = 5
    headers = {clean_paragraph(ws.cell(header_row, col).value).lower(): col for col in range(1, ws.max_column + 1) if clean_paragraph(ws.cell(header_row, col).value)}
    required = {"relative file path", "page title"}
    if not required.issubset(headers):
        return [], {"checked": 0, "passed": 0, "mismatched": 0}

    errors: List[str] = []
    checked = 0
    passed = 0
    for row_idx in range(header_row + 1, ws.max_row + 1):
        relative_path = clean_paragraph(ws.cell(row_idx, headers["relative file path"]).value)
        workbook_title = clean_paragraph(ws.cell(row_idx, headers["page title"]).value)
        if not relative_path or not workbook_title or relative_path.startswith("/book/"):
            continue
        file_path = ROOT / relative_path
        if not file_path.exists() or file_path.suffix.lower() != ".html":
            continue
        checked += 1
        html_text = file_path.read_text(encoding="utf-8", errors="ignore")
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.I | re.S)
        if not title_match:
            errors.append(f"Workbook Pages title mismatch for {relative_path}: workbook '{workbook_title}' != repo '<missing title tag>'.")
            continue
        repo_title = clean_paragraph(html.unescape(re.sub(r"\s+", " ", title_match.group(1))))
        route_errors = title_contract_errors(relative_path, repo_title, workbook_title)
        if route_errors:
            errors.extend(route_errors)
            continue
        passed += 1
    return errors, {"checked": checked, "passed": passed, "mismatched": len(errors)}

def workbook_static_route_contract_errors(workbook_path: Path) -> List[str]:
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    if "Pages" not in wb.sheetnames:
        return ["Workbook is missing the Pages sheet."]

    ws = wb["Pages"]
    header_row = 5
    headers = {clean_paragraph(ws.cell(header_row, col).value).lower(): col for col in range(1, ws.max_column + 1) if clean_paragraph(ws.cell(header_row, col).value)}
    required = {"relative file path", "public url path", "page title"}
    if not required.issubset(headers):
        return []

    errors, _ = workbook_title_parity_audit(workbook_path)
    for row_idx in range(header_row + 1, ws.max_row + 1):
        relative_path = clean_paragraph(ws.cell(row_idx, headers["relative file path"]).value)
        public_path = clean_paragraph(ws.cell(row_idx, headers["public url path"]).value)
        if not relative_path or relative_path.startswith("/book/"):
            continue
        file_path = ROOT / relative_path
        if not file_path.exists() or file_path.suffix.lower() != ".html":
            continue
        html_text = file_path.read_text(encoding="utf-8", errors="ignore")
        canonical_match = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', html_text, re.I)
        if canonical_match and public_path:
            canonical_path = url_to_path(canonical_match.group(1))
            if canonical_path != public_path:
                errors.append(f"Workbook Pages canonical mismatch for {relative_path}: workbook path '{public_path}' != canonical '{canonical_path}'.")
    return errors


def related_book_contract_errors(books: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    books_by_slug = {book["slug"]: book for book in books}
    for book in books:
        same_topic_slugs = [candidate["slug"] for candidate in books if candidate["slug"] != book["slug"] and candidate.get("topic") == book.get("topic")]
        governed_related = [slug for slug in book.get("related_slugs", []) if slug in books_by_slug]
        expected_same_topic = min(4, len(same_topic_slugs))
        if expected_same_topic and any(books_by_slug[slug].get("topic") != book.get("topic") for slug in governed_related[:expected_same_topic]):
            errors.append(f"Related book contract drift for {book['slug']}: same-topic titles are not ranked first.")
    return errors



def url_to_path(value: str) -> str:
    value = clean_paragraph(value)
    if not value:
        return ""
    if value.startswith("/"):
        return value
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        return path
    return value



def humanise_slug(slug: str) -> str:
    return clean_paragraph(slug.replace("-", " ").title())



def format_date(value: str) -> str:
    if not value:
        return ""
    try:
        return dt.date.fromisoformat(value).strftime("%d %B %Y")
    except ValueError:
        return value



def escape_paragraphs(text: str) -> str:
    paragraphs = [clean_paragraph(p) for p in re.split(r"\n{2,}", str(text or "")) if clean_paragraph(p)]
    return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)



def json_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))



def render_header() -> str:
    return HEADER_PARTIAL.read_text(encoding="utf-8").strip()



def render_footer() -> str:
    return FOOTER_PARTIAL.read_text(encoding="utf-8").strip()



def render_tag_pills(tags: Iterable[str], class_name: str = "ebook-pill") -> str:
    return "".join(f'<span class="{class_name}">{html.escape(tag)}</span>' for tag in tags if clean_paragraph(tag))



def build_person_schema() -> Dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": f"{SITE_URL}/#person",
        "name": SITE_NAME,
        "url": f"{SITE_URL}/",
        "jobTitle": ["AI Author", "Podcast Host"],
        "description": "Jonathan Harris is an artificial intelligence author and host of the Turing’s Torch AI Weekly podcast. He writes plain-English books explaining how AI works across industries including healthcare, finance, law, manufacturing, and education.",
        "knowsAbout": ["Artificial Intelligence", "Machine Learning", "Generative AI", "AI Ethics", "Applied AI", "LLMs"],
        "sameAs": [
            "https://about.me/jonathan_harris",
            "https://youtube.com/@jonathanharris-r7i",
            "https://open.spotify.com/show/4NluRPjuAIGK59vVf7GcoF",
            "https://www.amazon.com/kindle-dbs/author?ref=dbs_G_A_C&asin=B0DNCHC337",
            "https://www.goodreads.com/author/show/54004095.Jonathan_Harris",
            "https://twitter.com/jonathan_harris_01",
        ],
    }



def build_website_schema() -> Dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{SITE_URL}/#website",
        "url": f"{SITE_URL}/",
        "name": "Jonathan Harris - AI Author & Podcast Host",
        "publisher": {"@id": f"{SITE_URL}/#person"},
        "about": {"@id": f"{SITE_URL}/#person"},
        "inLanguage": "en",
    }



def build_book_schema(book: Dict[str, Any]) -> Dict[str, Any]:
    about_terms = [{"@type": "Thing", "name": name} for name in book_about_terms(book)]
    return {
        "@context": "https://schema.org",
        "@type": "Book",
        "@id": f"{book['canonical_url']}#book",
        "name": book["title"],
        "url": book["canonical_url"],
        "description": book["description"],
        "image": [book["cover"]],
        "author": {"@type": "Person", "name": book["author"], "url": f"{SITE_URL}/bio/"},
        "bookFormat": "EBook",
        "datePublished": book["datePublished"],
        "dateModified": book.get("dateModified") or infer_build_timestamp(),
        "inLanguage": "en-GB",
        "numberOfPages": book["pages"],
        "sameAs": [book["buy_url"]] if book.get("buy_url") else [],
        "publisher": {"@type": "Person", "name": book["author"]},
        "identifier": [
            {"@type": "PropertyValue", "propertyID": "ASIN", "value": book["asin"]},
            {"@type": "PropertyValue", "propertyID": "Jonathan Harris internal identifier", "value": book["identifier"]},
        ],
        "about": about_terms,
    }


def build_breadcrumb_schema(book: Dict[str, Any]) -> Dict[str, Any]:
    items = [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
        {"@type": "ListItem", "position": 2, "name": "eBooks", "item": f"{SITE_URL}/ebooks/"},
    ]
    position = 3
    if book.get("topic_url"):
        items.append({"@type": "ListItem", "position": position, "name": book["topic"], "item": f"{SITE_URL}{book['topic_url']}"})
        position += 1
    items.append({"@type": "ListItem", "position": position, "name": book["title"], "item": book["canonical_url"]})
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}



def build_topic_breadcrumb_schema(topic: str) -> Dict[str, Any]:
    topic_slug = slugify(topic)
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Topics", "item": f"{SITE_URL}/topics/"},
            {"@type": "ListItem", "position": 3, "name": topic, "item": f"{SITE_URL}/catalogue/{topic_slug}/"},
        ],
    }



def render_topic_breadcrumbs(topic: str) -> str:
    return "".join([
        '<a href="/">Home</a>',
        '<span aria-hidden="true">›</span>',
        '<a href="/topics/">Topics</a>',
        '<span aria-hidden="true">›</span>',
        f'<span>{html.escape(topic)}</span>',
    ])



def parse_master_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    *,
    sanitise_content: bool = True,
) -> Dict[str, Dict[str, Any]]:
    headers = [clean_paragraph(cell.value).lower() for cell in ws[1]]
    index = {header: idx for idx, header in enumerate(headers) if header}
    required = {"slug", "title", "asin", "amazon ebook page count", "publication date", "book url", "buy now url", "redirect url", "cover art url", "legacy alias url"}
    missing = required - set(index)
    if missing:
        raise ValueError(f"Ebooks Master sheet is missing required columns: {', '.join(sorted(missing))}")

    field_map = {
        "slug": "slug",
        "title": "title",
        "short description": "short",
        "short": "short",
        "description": "description",
        "summary": "summary",
        "topic": "topic",
        "category": "topic",
        "tags": "tags",
        "keywords": "keywords",
        "audience": "audience",
        "who this book is for": "who_for",
        "who_for": "who_for",
        "what this book covers": "what_this_book_covers",
        "what_youll_learn": "what_youll_learn",
        "what you'll learn": "what_youll_learn",
        "why it matters": "why_it_matters",
        "tone": "tone",
        "author": "author",
        "identifier": "identifier",
        "showcase heading": "showcase_heading",
        "distinct angle": "distinct_angle",
        "asin": "asin",
        "amazon ebook page count": "pages",
        "publication date": "datePublished",
        "book url": "book_url",
        "buy now url": "buy_route_full",
        "redirect url": "buy_url",
        "cover art url": "cover",
        "legacy alias url": "legacy_alias_url",
    }
    list_fields = {"tags", "keywords", "what_youll_learn"}

    results: Dict[str, Dict[str, Any]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        slug = clean_paragraph(row[index["slug"]] if index.get("slug") is not None else "")
        if not slug:
            continue
        record: Dict[str, Any] = {}
        for header, idx in index.items():
            target = field_map.get(header)
            if not target:
                continue
            value = row[idx]
            if target in list_fields:
                record[target] = split_field(value)
            elif target == "pages":
                record[target] = int(value) if value not in (None, "") else None
            elif target == "datePublished":
                if isinstance(value, dt.datetime):
                    record[target] = value.date().isoformat()
                elif hasattr(value, "isoformat") and value is not None:
                    record[target] = value.isoformat()
                else:
                    record[target] = clean_paragraph(value)
            else:
                record[target] = clean_paragraph(value)
        record["book_url"] = ensure_trailing_slash(record.get("book_url") or f"{SITE_URL}/ebooks/{slug}/")
        buy_route_full = record.get("buy_route_full") or f"{SITE_URL}/ebooks/{slug}/buy-now"
        record["buy_route_full"] = buy_route_full
        record["buy_route"] = url_to_path(buy_route_full)
        record["legacy_alias_url"] = clean_paragraph(record.get("legacy_alias_url") or f"{SITE_URL}/book/{slug}/buy-now")
        record["cover"] = clean_paragraph(record.get("cover", "")).replace("https://images.Jonathan-harris.online", "https://images.jonathan-harris.online")
        if sanitise_content:
            record = sanitise_record_copy(record)
        results[slug] = record
    return results


def parse_workbook(
    workbook_path: Path,
    *,
    sanitise_content: bool = True,
) -> Tuple[List[str], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    if "Ebooks Master" not in wb.sheetnames:
        raise ValueError("Workbook is missing the Ebooks Master sheet")

    master_sheet = parse_master_sheet(wb["Ebooks Master"], sanitise_content=sanitise_content)
    if not master_sheet:
        raise ValueError("No ebook rows found in Ebooks Master")

    notes_by_slug: Dict[str, str] = {}
    if "BuyNow Redirects" in wb.sheetnames:
        ws = wb["BuyNow Redirects"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            slug = clean_paragraph(row[0] or "")
            if not slug:
                continue
            notes_by_slug[slug] = clean_paragraph(row[5] or "")

    order = list(master_sheet.keys())
    records: Dict[str, Dict[str, Any]] = {}
    for slug in order:
        row = dict(master_sheet[slug])
        row["slug"] = slug
        row["notes"] = notes_by_slug.get(slug, "")
        records[slug] = row
    return order, records, master_sheet


def validate_pages_sheet_operational_view(workbook_path: Path) -> List[str]:
    wb_values = openpyxl.load_workbook(workbook_path, data_only=True)
    wb_formulas = openpyxl.load_workbook(workbook_path, data_only=False)
    if "Pages" not in wb_values.sheetnames:
        return ["Workbook is missing the Pages sheet."]

    ws = wb_values["Pages"]
    ws_formula = wb_formulas["Pages"]
    header_row = 5
    headers = {clean_paragraph(ws.cell(header_row, col).value).lower(): col for col in range(1, ws.max_column + 1) if clean_paragraph(ws.cell(header_row, col).value)}
    required_headers = ["relative file path", "public url path", "full url", "url type", "buy now url", "redirect url", "asin", "amazon ebook page count", "publication date", "cover art url"]
    missing_headers = [header for header in required_headers if header not in headers]
    if missing_headers:
        return [f"Pages sheet is missing required columns: {', '.join(missing_headers)}"]

    base_domain = clean_paragraph(ws["B1"].value)
    errors: List[str] = []
    malformed_paths: List[str] = []
    missing_full_url: List[str] = []
    mismatched_full_url: List[str] = []
    missing_ebook_metadata: List[str] = []
    master_by_slug = {row["slug"]: row for row in load_master()}

    def has_formula(row_idx: int, header_name: str) -> bool:
        cell = ws_formula.cell(row_idx, headers[header_name])
        return isinstance(cell.value, str) and cell.value.startswith("=")

    def slug_from_relative_path(relative_path: str) -> str:
        if relative_path.startswith("ebooks/") and relative_path.endswith("/index.html"):
            return relative_path[len("ebooks/"):-len("/index.html")]
        return ""

    for row_idx in range(header_row + 1, ws.max_row + 1):
        relative_path = clean_paragraph(ws.cell(row_idx, headers["relative file path"]).value)
        if not relative_path:
            continue

        public_path = clean_paragraph(ws.cell(row_idx, headers["public url path"]).value)
        full_url = clean_paragraph(ws.cell(row_idx, headers["full url"]).value)
        url_type = clean_paragraph(ws.cell(row_idx, headers["url type"]).value).lower()
        buy_now_url = clean_paragraph(ws.cell(row_idx, headers["buy now url"]).value)
        redirect_url = clean_paragraph(ws.cell(row_idx, headers["redirect url"]).value)
        asin = clean_paragraph(ws.cell(row_idx, headers["asin"]).value)
        page_count = ws.cell(row_idx, headers["amazon ebook page count"]).value
        publication_date = ws.cell(row_idx, headers["publication date"]).value
        cover_art_url = clean_paragraph(ws.cell(row_idx, headers["cover art url"]).value)

        if public_path:
            path_without_leading_slash = public_path[1:] if public_path.startswith("/") else public_path
            if "//" in path_without_leading_slash:
                malformed_paths.append(relative_path)
            if not public_path.startswith("/"):
                malformed_paths.append(relative_path)
        else:
            malformed_paths.append(relative_path)

        if public_path:
            expected_full_url = f"{base_domain}{public_path}" if base_domain else ""
            if not full_url and not has_formula(row_idx, "full url"):
                missing_full_url.append(relative_path)
            elif full_url and expected_full_url and full_url != expected_full_url:
                mismatched_full_url.append(relative_path)

        is_canonical_ebook_row = url_type == "canonical ebook route"
        if is_canonical_ebook_row:
            slug = slug_from_relative_path(relative_path)
            master_row = master_by_slug.get(slug, {})
            metadata_checks = [
                (buy_now_url, "buy now url", clean_paragraph(master_row.get("buy_route", ""))),
                (redirect_url, "redirect url", clean_paragraph(master_row.get("buy_url", ""))),
                (asin, "asin", clean_paragraph(master_row.get("asin", ""))),
                (page_count, "amazon ebook page count", master_row.get("pages")),
                (publication_date, "publication date", clean_paragraph(master_row.get("datePublished", ""))),
                (cover_art_url, "cover art url", clean_paragraph(master_row.get("cover", ""))),
            ]
            for value, header_name, derived_value in metadata_checks:
                if value not in (None, ""):
                    continue
                if has_formula(row_idx, header_name) and derived_value not in (None, ""):
                    continue
                missing_ebook_metadata.append(relative_path)
                break

    if malformed_paths:
        sample = ", ".join(malformed_paths[:5])
        errors.append(f"Workbook Pages sheet has {len(malformed_paths)} malformed public URL path value(s) with double-slash or missing leading slash drift. Sample rows: {sample}")
    if missing_full_url:
        sample = ", ".join(missing_full_url[:5])
        errors.append(f"Workbook Pages sheet has {len(missing_full_url)} row(s) with missing cached Full URL values. Sample rows: {sample}")
    if mismatched_full_url:
        sample = ", ".join(mismatched_full_url[:5])
        errors.append(f"Workbook Pages sheet has {len(mismatched_full_url)} row(s) where Full URL does not match Base domain + Public URL path. Sample rows: {sample}")
    if missing_ebook_metadata:
        sample = ", ".join(missing_ebook_metadata[:5])
        errors.append(f"Workbook Pages sheet has {len(missing_ebook_metadata)} canonical ebook row(s) missing cached metadata lookup values. Sample rows: {sample}")
    return errors


def topic_intro(topic: str) -> str:
    return helper_topic_intro(topic)



def default_learning_points(topic: str) -> List[str]:
    topic_lc = topic.lower()
    return [
        f"How AI is already being used in {topic_lc} and where the claims run ahead of the evidence.",
        f"The workflows, trade-offs, and decision points that matter in {topic_lc}.",
        f"The awkward questions around risk, adoption, governance, and long-term impact in {topic_lc}.",
    ]


BOOK_SPECIFIC_LEARN_TAILS: Dict[str, str] = {'ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology': 'where milliseconds beat marketing '
                                                                               'myths',
 'ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future': 'where weather, margins, and soil matter',
 'ai-in-aviation-transforming-safety-and-sustainability': 'where safety systems meet hard limits',
 'ai-in-education-reimagining-learning-for-every-student': 'where classroom goals beat shiny demos',
 'ai-in-maritime-revolutionizing-shipping-for-sustainability': 'where ports, fleets, and costs collide',
 'ai-powered-smart-grid-revolutionizing-electricity-distribution-and-generation': 'where grid maths meets field '
                                                                                  'reality',
 'ai-revolution-in-railways-modernizing-travel-for-a-smarter-future': 'where signalling meets service reality',
 'artificial-intelligence-and-the-law-case-studies-and-future-trends': 'where precedent meets messy deployment',
 'artificial-intelligence-for-cyber-security-a-practical-guide-to-data-breach-prevention': 'where attacks outpace '
                                                                                           'slide decks',
 'artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology': 'where '
                                                                                                                 'field '
                                                                                                                 'data '
                                                                                                                 'meets '
                                                                                                                 'habitat '
                                                                                                                 'limits',
 'artificial-intelligence-in-banking-revolutionizing-finance-and-data-security': 'where fraud models meet compliance '
                                                                                 'desks',
 'artificial-intelligence-in-construction-building-a-sustainable-future': 'where sites, crews, and delays decide',
 'artificial-intelligence-in-industry-a-comprehensive-guide': 'where plant floors test every promise',
 'artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability': 'where routing models hit warehouse '
                                                                                  'floors',
 'artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare': 'where lab promise meets regulation',
 'artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement': 'where performance data meets '
                                                                                     'human nerves',
 'artificial-intelligence-in-veterinary-medicine-transforming-animal-healthcare-through-innovation': 'where '
                                                                                                     'diagnostics meet '
                                                                                                     'day-to-day care',
 'artificial-intelligence-powered-retail-revolutionizing-customer-experience-for-a-sustainable-future': 'where basket '
                                                                                                        'data meets '
                                                                                                        'buyer '
                                                                                                        'patience',
 'artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery': 'where '
                                                                                                                'uptime, '
                                                                                                                'scrap, '
                                                                                                                'and '
                                                                                                                'margins '
                                                                                                                'bite',
 'beyond-earth-how-ai-is-transforming-space-exploration': 'where mission risk beats sci-fi gloss',
 'climate-intelligence-harnessing-ai-for-a-greener-future': 'where emissions maths meets policy friction',
 'digital-defense-the-role-of-ai-in-modern-warfare': 'where autonomy meets command risk',
 'digital-diagnosis-how-ai-is-revolutionizing-healthcare': 'where clinical use meets human judgement',
 'from-reporters-to-robots-how-ai-is-reshaping-journalism': 'where deadlines meet verification pressure',
 'game-ai-unleashed-from-finite-state-machines-to-machine-learning': 'where design tricks meet player intent',
 'lights-camera-algorithm-ai-s-role-in-modern-filmmaking': 'where production budgets meet creative calls',
 'smart-buildings-ai-powered-efficiency-and-sustainability': 'where sensors meet maintenance budgets',
 'the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media': 'where feeds meet moderation '
                                                                                      'blowback',
 'the-ai-music-revolution-creativity-controversy-and-collaboration': 'where new tools meet old rights fights',
 'the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead': 'where breakthroughs meet the human cost',
 'the-artificial-intelligence-job-shift-navigating-the-future-of-work': 'where job redesign beats slogan fog',
 'the-artificial-intelligence-revolution-from-algorithms-to-consciousness': 'where theory collides with deployment',
 'the-autonomous-revolution-artificial-intelligence-and-the-future-of-the-automotive-industry': 'where sensors meet '
                                                                                                'traffic and liability',
 'the-dumbening-how-ai-is-reshaping-our-minds': 'where convenience starts taxing attention',
 'the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information': 'where services meet scrutiny '
                                                                                         'and budget',
 'the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming': 'where optimisation meets ethical lines'}

BOOK_SPECIFIC_ADVANCED_TAILS: Dict[str, str] = {'ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology': 'strategy calls, telemetry, and pace',
 'ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future': 'yield data, labour, and seasons',
 'ai-in-aviation-transforming-safety-and-sustainability': 'flight safety, failure modes, and ops',
 'ai-in-education-reimagining-learning-for-every-student': 'learning design, bias, and outcomes',
 'ai-in-maritime-revolutionizing-shipping-for-sustainability': 'port systems, delays, and fuel use',
 'ai-powered-smart-grid-revolutionizing-electricity-distribution-and-generation': 'grid load, faults, and resilience',
 'ai-revolution-in-railways-modernizing-travel-for-a-smarter-future': 'signalling, safety, and uptime',
 'artificial-intelligence-and-the-law-case-studies-and-future-trends': 'case law, compliance, and grey areas',
 'artificial-intelligence-for-cyber-security-a-practical-guide-to-data-breach-prevention': 'attack paths, defence, and '
                                                                                           'risk',
 'artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology': 'field '
                                                                                                                 'sensing, '
                                                                                                                 'habitat, '
                                                                                                                 'and '
                                                                                                                 'risk',
 'artificial-intelligence-in-banking-revolutionizing-finance-and-data-security': 'fraud controls, models, and trust',
 'artificial-intelligence-in-construction-building-a-sustainable-future': 'site ops, safety, and delays',
 'artificial-intelligence-in-industry-a-comprehensive-guide': 'industrial systems, risk, and return',
 'artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability': 'routing logic, stock flow, and '
                                                                                  'timing',
 'artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare': 'trials, regulation, and lab friction',
 'artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement': 'performance data, tactics, and '
                                                                                     'nerves',
 'artificial-intelligence-in-veterinary-medicine-transforming-animal-healthcare-through-innovation': 'case triage, '
                                                                                                     'trust, and '
                                                                                                     'treatment',
 'artificial-intelligence-powered-retail-revolutionizing-customer-experience-for-a-sustainable-future': 'customer '
                                                                                                        'data, stock, '
                                                                                                        'and margin',
 'artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery': 'uptime, '
                                                                                                                'quality, '
                                                                                                                'and '
                                                                                                                'plant '
                                                                                                                'reality',
 'beyond-earth-how-ai-is-transforming-space-exploration': 'mission risk, autonomy, and delay',
 'climate-intelligence-harnessing-ai-for-a-greener-future': 'carbon maths, policy, and scale',
 'digital-defense-the-role-of-ai-in-modern-warfare': 'command risk, autonomy, and doctrine',
 'digital-diagnosis-how-ai-is-revolutionizing-healthcare': 'clinical judgement, data, and harm',
 'from-reporters-to-robots-how-ai-is-reshaping-journalism': 'verification, deadlines, and pressure',
 'game-ai-unleashed-from-finite-state-machines-to-machine-learning': 'npc logic, difficulty, and design',
 'lights-camera-algorithm-ai-s-role-in-modern-filmmaking': 'workflows, budgets, and authorship',
 'smart-buildings-ai-powered-efficiency-and-sustainability': 'building ops, costs, and comfort',
 'the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media': 'feeds, moderation, and '
                                                                                      'influence',
 'the-ai-music-revolution-creativity-controversy-and-collaboration': 'rights fights, tools, and taste',
 'the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead': 'history, motives, and fallout',
 'the-artificial-intelligence-job-shift-navigating-the-future-of-work': 'job design, skills, and leverage',
 'the-artificial-intelligence-revolution-from-algorithms-to-consciousness': 'theory, limits, and real deployment',
 'the-autonomous-revolution-artificial-intelligence-and-the-future-of-the-automotive-industry': 'road risk, autonomy, '
                                                                                                'and liability',
 'the-dumbening-how-ai-is-reshaping-our-minds': 'attention, habits, and drift',
 'the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information': 'public trust, systems, and '
                                                                                         'budgets',
 'the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming': 'risk scoring, consent, and harm'}

CATALOGUE_INTRO_VARIANTS: Dict[str, str] = {'Agriculture': 'These books cut through ag-tech waffle and focus on yields, soil, labour, and what works in the '
                'field.',
 'Artificial Intelligence': 'These titles zoom out from slogans and look at how AI behaves once theory meets products, '
                            'decisions, and people.',
 'Construction': 'These books stay grounded in sites, schedules, safety, and the stubborn reality of getting '
                 'technology to work.',
 'Creativity': 'These titles treat creative work as craft and business, not pixie dust, from studios and sets to the '
               'rights mess behind them.',
 'Cyber Security': 'These books focus on defensive reality: attack surfaces, breach prevention, response pressure, and '
                   'what actually improves resilience.',
 'Defence': 'These titles keep one eye on capability and the other on doctrine, escalation, reliability, and the risks '
            'nobody can spin away.',
 'Education': 'These books look at learning, teaching, and assessment with more classroom realism and less '
              'shiny-edtech theatre.',
 'Energy': 'These titles dig into grids, demand, resilience, and the engineering headaches hiding underneath clean '
           'strategic slogans.',
 'Environment': 'These books stay practical about biodiversity, climate, monitoring, and the gap between good intent '
                'and field conditions.',
 'Ethics': 'These titles lean into the awkward bits: incentives, consent, addiction, cognition, and the costs of '
           'pretending AI is neutral.',
 'Finance': 'These books deal in fraud, risk, security, and trust, not fintech smoke and mirrors.',
 'Future of Work': 'These titles examine what changes in jobs, skills, power, and management once AI leaves the '
                   'keynote stage.',
 'Gaming': 'These books look past gamer jargon and get into design logic, player behaviour, and the machinery behind '
           'believable systems.',
 'Government': 'These titles focus on service delivery, security, accountability, and the bureaucratic plumbing that '
               'makes or breaks adoption.',
 'Healthcare': 'These books keep the focus on diagnosis, care, evidence, and the human judgement that software still '
               'cannot replace.',
 'History': 'These titles trace how AI got here, who shaped it, and why the old breakthroughs still cast a long '
            'shadow.',
 'Industry': 'These books centre on operations, reliability, process change, and the difference between automation '
             'talk and plant-floor reality.',
 'Law': 'These titles deal with precedent, liability, evidence, and the legal friction that appears when code meets '
        'institutions.',
 'Manufacturing': 'These books concentrate on uptime, quality, maintenance, and the grimly practical details that '
                  'decide whether rollout pays off.',
 'Media': 'These titles unpack how AI collides with journalism, feeds, moderation, and the attention economy that '
          'warps the whole lot.',
 'Retail': 'These books stay close to customer behaviour, stock flow, pricing, and the commercial trade-offs behind '
           'personalisation.',
 'Science': 'These titles look at exploration, discovery, uncertainty, and what happens when ambitious models meet '
            'real-world constraints.',
 'Sports': 'These books cut through performance hype and get into coaching decisions, analytics, fan dynamics, and '
           'pressure.',
 'Transportation': 'These titles track how AI changes movement systems in the wild: roads, rails, fleets, ports, and '
                   'split-second decisions.'}

CATALOGUE_CTA_VARIANTS: Dict[str, str] = {'Agriculture': 'Open the full breakdown, then decide whether it earns a place on your Kindle.',
 'Artificial Intelligence': 'Read the detailed page, then see the current Amazon listing when you are ready.',
 'Construction': 'Start with the full overview, then check the live Amazon page for the latest details.',
 'Creativity': 'Open the full description first, then head to Amazon if the angle fits what you need.',
 'Cyber Security': 'Read the deeper summary, then inspect the Amazon page for the current edition and price.',
 'Defence': 'Check the complete book page, then use Amazon for the latest buying details.',
 'Education': 'Open the full breakdown, then decide whether it earns a place on your Kindle.',
 'Energy': 'Read the detailed page, then see the current Amazon listing when you are ready.',
 'Environment': 'Start with the full overview, then check the live Amazon page for the latest details.',
 'Ethics': 'Open the full description first, then head to Amazon if the angle fits what you need.',
 'Finance': 'Read the deeper summary, then inspect the Amazon page for the current edition and price.',
 'Future of Work': 'Check the complete book page, then use Amazon for the latest buying details.',
 'Gaming': 'Open the full breakdown, then decide whether it earns a place on your Kindle.',
 'Government': 'Read the detailed page, then see the current Amazon listing when you are ready.',
 'Healthcare': 'Start with the full overview, then check the live Amazon page for the latest details.',
 'History': 'Open the full description first, then head to Amazon if the angle fits what you need.',
 'Industry': 'Read the deeper summary, then inspect the Amazon page for the current edition and price.',
 'Law': 'Check the complete book page, then use Amazon for the latest buying details.',
 'Manufacturing': 'Open the full breakdown, then decide whether it earns a place on your Kindle.',
 'Media': 'Read the detailed page, then see the current Amazon listing when you are ready.',
 'Retail': 'Start with the full overview, then check the live Amazon page for the latest details.',
 'Science': 'Open the full description first, then head to Amazon if the angle fits what you need.',
 'Sports': 'Read the deeper summary, then inspect the Amazon page for the current edition and price.',
 'Transportation': 'Check the complete book page, then use Amazon for the latest buying details.'}

SUMMARY_VARIANT_OPENERS: List[str] = [
    "Instead, it stays with the real sticking points in",
    "It keeps its eye on the pressure points inside",
    "Rather than puffery, it follows the live fault lines in",
    "It sticks to the decisions and bottlenecks shaping",
    "This one stays close to the hard realities inside",
    "It tracks the moments that actually decide whether AI works in",
    "It keeps the spotlight on the practical pressure points across",
    "It follows the places where deployment gets real in",
    "It stays with the awkward but useful details inside",
    "It maps the parts of adoption that actually bite in",
    "It keeps to the practical judgement calls running through",
    "It follows the working pressures that define",
    "It keeps the focus on the stubborn realities inside",
    "It tracks the places where theory collides with operating reality in",
    "It stays with the decisions, constraints, and side-effects shaping",
    "It follows the practical friction points running through",
    "It keeps the argument tied to what really happens inside",
    "It tracks the real-world pressure points shaping",
]

WORKFLOW_VARIANT_OPENERS: List[str] = [
    "The operational detail that matters:",
    "The practical mechanics worth watching:",
    "The decision points that actually count:",
    "The grounded view of deployment comes through:",
    "The useful detail sits here:",
    "The sharper operational lens is on",
    "The reality check comes from",
    "The practical argument turns on",
    "The nuts-and-bolts angle covers",
    "The working detail is in",
    "The less glamorous but more useful part is",
    "The serious implementation view covers",
    "The day-to-day pressure points are",
    "The operational story really sits in",
    "The meaningful detail runs through",
    "The practical reading starts with",
    "The thing worth paying attention to is",
    "The grounded takeaway centres on",
]

SUMMARY_VARIANT_OVERRIDES: Dict[str, int] = {
    "ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology": 4,
    "artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability": 4,
    "the-artificial-intelligence-revolution-from-algorithms-to-consciousness": 12,
    "artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare": 14,
    "artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery": 12,
    "ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future": 4,
    "digital-diagnosis-how-ai-is-revolutionizing-healthcare": 10,
    "the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information": 11,
    "artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology": 13,
    "artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement": 11,
    "the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead": 13,
    "from-reporters-to-robots-how-ai-is-reshaping-journalism": 1,
}

WORKFLOW_VARIANT_OVERRIDES: Dict[str, int] = {
    "ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology": 4,
    "artificial-intelligence-in-veterinary-medicine-transforming-animal-healthcare-through-innovation": 7,
    "ai-powered-smart-grid-revolutionizing-electricity-distribution-and-generation": 0,
    "artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability": 4,
    "artificial-intelligence-and-the-law-case-studies-and-future-trends": 0,
    "artificial-intelligence-for-cyber-security-a-practical-guide-to-data-breach-prevention": 9,
    "the-artificial-intelligence-revolution-from-algorithms-to-consciousness": 12,
    "ai-in-aviation-transforming-safety-and-sustainability": 16,
    "ai-in-maritime-revolutionizing-shipping-for-sustainability": 15,
    "artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare": 14,
    "the-autonomous-revolution-artificial-intelligence-and-the-future-of-the-automotive-industry": 11,
    "artificial-intelligence-powered-retail-revolutionizing-customer-experience-for-a-sustainable-future": 3,
    "artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery": 12,
    "artificial-intelligence-in-industry-a-comprehensive-guide": 12,
    "the-dumbening-how-ai-is-reshaping-our-minds": 6,
    "ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future": 4,
    "ai-in-education-reimagining-learning-for-every-student": 2,
    "artificial-intelligence-in-banking-revolutionizing-finance-and-data-security": 1,
    "digital-diagnosis-how-ai-is-revolutionizing-healthcare": 10,
    "artificial-intelligence-in-construction-building-a-sustainable-future": 10,
    "the-artificial-intelligence-job-shift-navigating-the-future-of-work": 17,
    "the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information": 11,
    "smart-buildings-ai-powered-efficiency-and-sustainability": 10,
    "digital-defense-the-role-of-ai-in-modern-warfare": 6,
    "artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology": 13,
    "climate-intelligence-harnessing-ai-for-a-greener-future": 8,
    "ai-revolution-in-railways-modernizing-travel-for-a-smarter-future": 6,
    "artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement": 11,
    "lights-camera-algorithm-ai-s-role-in-modern-filmmaking": 4,
    "the-ai-music-revolution-creativity-controversy-and-collaboration": 4,
    "the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead": 13,
    "the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming": 5,
    "beyond-earth-how-ai-is-transforming-space-exploration": 11,
    "from-reporters-to-robots-how-ai-is-reshaping-journalism": 1,
    "the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media": 2,
    "game-ai-unleashed-from-finite-state-machines-to-machine-learning": 0,
}


def stable_variant_index(key: str, size: int) -> int:
    if size <= 0:
        raise ValueError("Variant collections must not be empty")
    digest = hashlib.sha256(clean_paragraph(key).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size



def variant_index_for_slug(slug: str, variants: List[str], overrides: Dict[str, int]) -> int:
    override = overrides.get(clean_paragraph(slug))
    if override is not None and 0 <= override < len(variants):
        return override
    return stable_variant_index(slug, len(variants))



def replace_banned_ebook_phrases(value: str, slug: str) -> str:
    cleaned = clean_paragraph(value)
    if not cleaned:
        return cleaned
    learn_tail = BOOK_SPECIFIC_LEARN_TAILS.get(slug)
    advanced_tail = BOOK_SPECIFIC_ADVANCED_TAILS.get(slug)
    if learn_tail:
        cleaned = cleaned.replace("where the claims are running ahead of reality", learn_tail)
        summary_prefix = "This book follows the workflows, trade-offs, and decision points shaping "
        summary_suffix = ", so readers can separate useful systems from glossy nonsense."
        if summary_prefix in cleaned and summary_suffix in cleaned:
            start = cleaned.index(summary_prefix)
            end = cleaned.index(summary_suffix, start) + len(summary_suffix)
            topic_fragment = cleaned[start + len(summary_prefix): cleaned.index(summary_suffix, start)].strip().rstrip(',')
            opener = SUMMARY_VARIANT_OPENERS[variant_index_for_slug(slug, SUMMARY_VARIANT_OPENERS, SUMMARY_VARIANT_OVERRIDES)]
            summary_sentence = f"{opener} {topic_fragment}, especially {learn_tail}."
            cleaned = cleaned[:start] + summary_sentence + cleaned[end:]
    if advanced_tail:
        cleaned = cleaned.replace("trade-offs, and implementation angles", advanced_tail)
        workflow_prefix = "The workflows, systems, and trade-offs behind practical "
        workflow_suffix = " use cases, explained in plain English."
        if cleaned.startswith(workflow_prefix) and cleaned.endswith(workflow_suffix):
            opener = WORKFLOW_VARIANT_OPENERS[variant_index_for_slug(slug, WORKFLOW_VARIANT_OPENERS, WORKFLOW_VARIANT_OVERRIDES)]
            if opener.endswith(":"):
                cleaned = f"{opener} {advanced_tail}."
            else:
                cleaned = f"{opener} {advanced_tail}."
    return cleaned

def catalogue_intro_copy(topic: str) -> str:
    return CATALOGUE_INTRO_VARIANTS.get(topic, f"These books stay practical about {topic.lower()}, with less hype and more on how the work actually gets done.")

def catalogue_cta_copy(topic: str) -> str:
    return CATALOGUE_CTA_VARIANTS.get(topic, "Read the detailed page, then see the current Amazon listing when you are ready.")



def default_why_it_matters(topic: str) -> str:
    topic_lc = topic.lower()
    return f"Because AI in {topic_lc} changes decisions, workflows, and risk. Getting the basics right matters before the hype machine starts throwing confetti."


TOPIC_FAMILY_GROUPS = {
    "regulated": {"Healthcare", "Law", "Finance", "Government", "Education", "Defence"},
    "operations": {"Manufacturing", "Industry", "Transportation", "Construction", "Energy", "Agriculture", "Retail"},
    "security": {"Cyber Security"},
    "creative": {"Creativity", "Media", "Gaming"},
    "foundation": {"Artificial Intelligence", "Ethics", "History", "Science", "Future of Work"},
    "environment": {"Environment"},
    "sports": {"Sports"},
}


def topic_family(topic: str) -> str:
    topic_name = clean_paragraph(topic)
    for family, topics in TOPIC_FAMILY_GROUPS.items():
        if topic_name in topics:
            return family
    return "general"


TOPIC_GUIDE_DIRECTORY = {
    "ai-for-beginners": {
        "title": "AI for Beginners",
        "summary": "Plain-English foundations covering how AI works, where it is used, and what to pay attention to before the hype swallows the basics.",
    },
    "ai-in-business": {
        "title": "AI in Business",
        "summary": "Strategy, adoption, risk, and practical decisions for organisations implementing AI in the real world rather than in a slide deck.",
    },
    "ai-in-healthcare": {
        "title": "AI in Healthcare",
        "summary": "Clinical AI, diagnostics, NHS deployment pressures, and the regulatory questions that decide whether the tools help or hinder care.",
    },
    "ai-ethics": {
        "title": "AI Ethics",
        "summary": "Bias, accountability, transparency, safety, and the governance questions that matter when AI decisions affect real people.",
    },
    "ai-in-education": {
        "title": "AI in Education",
        "summary": "Personalised learning, classroom tools, assessment, and what the evidence actually says once the marketing smoke clears.",
    },
    "ai-in-finance": {
        "title": "AI in Finance",
        "summary": "Fraud detection, credit, trading, regulation, and the awkward trade-off between speed, risk, and accountability.",
    },
    "deep-learning": {
        "title": "Deep Learning",
        "summary": "Neural networks, training, pattern recognition, and where the models earn their reputation versus where they still fail noisily.",
    },
    "generative-ai": {
        "title": "Generative AI",
        "summary": "LLMs, image generation, content automation, and the difference between a useful tool and an expensive hallucination machine.",
    },
    "machine-learning": {
        "title": "Machine Learning",
        "summary": "Core machine-learning ideas, real-world use cases, and the data-quality problems that decide whether a model is useful or decorative.",
    },
    "robotics-automation": {
        "title": "Robotics & Automation",
        "summary": "Industrial robotics, autonomous systems, and the point where AI leaves the screen and starts affecting physical operations.",
    },
}

CATEGORY_TO_TOPIC_GUIDE = {
    "Agriculture": "machine-learning",
    "Artificial Intelligence": "ai-for-beginners",
    "Construction": "robotics-automation",
    "Creativity": "generative-ai",
    "Cyber Security": "machine-learning",
    "Defence": "ai-ethics",
    "Education": "ai-in-education",
    "Energy": "machine-learning",
    "Environment": "machine-learning",
    "Ethics": "ai-ethics",
    "Finance": "ai-in-finance",
    "Future of Work": "ai-in-business",
    "Gaming": "generative-ai",
    "Government": "ai-in-business",
    "Healthcare": "ai-in-healthcare",
    "History": "ai-for-beginners",
    "Industry": "ai-in-business",
    "Law": "ai-ethics",
    "Manufacturing": "robotics-automation",
    "Media": "generative-ai",
    "Retail": "ai-in-business",
    "Science": "deep-learning",
    "Sports": "machine-learning",
    "Transportation": "robotics-automation",
}


def topic_guide_record(slug: str | None) -> Dict[str, str] | None:
    if not slug:
        return None
    return TOPIC_GUIDE_DIRECTORY.get(slug)


def category_question_heading(topic: str) -> str:
    topic_name = clean_paragraph(topic)
    if topic_name.lower() == "artificial intelligence":
        return "What does this category actually cover?"
    return f"What is AI in {topic_name}?"


def category_answer_first_copy(topic: str, books: List[Dict[str, Any]]) -> str:
    topic_name = clean_paragraph(topic)
    intro = topic_intro(topic_name)
    featured = books[0]
    if len(books) == 1:
        return f"{intro} This page is the cleanest starting point in this part of the catalogue because it centres on {featured['title']}, which gives you one grounded route into the main use cases, trade-offs, and implementation questions."
    return f"{intro} This category brings together {len(books)} books, so you can move from the broad question into the title that best matches your use case instead of wandering around the shelves like a lost intern."


def category_scope_copy(topic: str, books: List[Dict[str, Any]]) -> str:
    topic_name = clean_paragraph(topic)
    family = topic_family(topic_name)
    if len(books) == 1:
        return {
            "regulated": f"The {topic_name.lower()} category focuses on evidence, adoption pressure, oversight, and the point where AI convenience collides with accountability. It is useful when you need more than a glossy vendor promise.",
            "operations": f"The {topic_name.lower()} category focuses on workflow, reliability, cost, and what happens once AI has to survive contact with real operations instead of a keynote stage.",
            "security": f"The {topic_name.lower()} category focuses on signal, attacker behaviour, operational noise, and where automation genuinely improves defence rather than just moving the mess around.",
            "creative": f"The {topic_name.lower()} category focuses on speed, craft, control, and the rights-shaped complications that appear the moment AI output starts looking commercially useful.",
            "foundation": f"The {topic_name.lower()} category focuses on first principles, practical claims, sharper judgement, and the context readers need before treating broad AI arguments as settled fact.",
            "environment": f"The {topic_name.lower()} category focuses on measurable environmental outcomes, data quality, and the difference between genuine optimisation and eco-flavoured marketing copy.",
            "sports": f"The {topic_name.lower()} category focuses on performance analysis, decision-making, and the stubborn fact that data still has to coexist with human judgement.",
        }.get(family, f"The {topic_name.lower()} category focuses on practical use cases, trade-offs, and the questions worth asking before anyone treats AI as a magic trick.")
    titles = ", ".join(book["title"] for book in books[:2])
    if len(books) > 2:
        titles += ", and more"
    return f"This category spans {len(books)} titles, starting with {titles}. Together they cover the main use cases, trade-offs, and adjacent decisions readers normally need before choosing a narrower book."


def category_best_start_copy(topic: str, books: List[Dict[str, Any]]) -> str:
    featured = books[0]
    if len(books) == 1:
        return f"If you want one grounded entry point, start with <a href='/ebooks/{html.escape(featured['slug'])}/'>{html.escape(featured['title'])}</a>. It is the clearest way into this topic without having to untangle three tabs, two buzzword decks, and someone's suspiciously cheerful vendor PDF."
    return f"Start with <a href='/ebooks/{html.escape(featured['slug'])}/'>{html.escape(featured['title'])}</a>, then use the related titles below to go narrower once you know which part of the subject matters most to you."


def category_faq_markup(topic: str, books: List[Dict[str, Any]]) -> str:
    topic_name = clean_paragraph(topic)
    family = topic_family(topic_name)
    questions = [
        (
            f"What does the {topic_name} category help me understand?",
            category_scope_copy(topic_name, books),
        ),
        (
            "Who should start here?",
            f"Readers who want a grounded overview of {topic_name.lower()} before picking a specific title, plus professionals who need a fast way to identify the book most relevant to their role.",
        ),
        (
            "Where should I go next after the featured title?",
            {
                "regulated": "Move into the glossary for key terms, then use the comparison page to pressure-test claims, risks, and implementation trade-offs across sectors.",
                "operations": "Move into the glossary for core terms, then use the comparison page and related topic guide to compare workflow gains against real-world constraints.",
                "security": "Move into the glossary for technical language, then use the comparison page and topic guide to keep the tooling anchored to risk rather than hype.",
                "creative": "Move into the glossary for the core concepts, then use the comparison page and topic guide to separate useful creative acceleration from rights and trust problems.",
                "foundation": "Move into the glossary for definitions, then use the comparison page and topic guide to connect the broad theory with specific use cases and trade-offs.",
                "environment": "Move into the glossary for the key concepts, then use the comparison page and topic guide to separate measurable gains from greenwashed claims.",
                "sports": "Move into the glossary for the core terms, then use the comparison page and topic guide to connect performance data with real-world judgement.",
            }.get(family, "Move into the glossary, comparison page, and related topic guide to connect this category with the wider AI estate."),
        ),
    ]
    parts = []
    for idx, (question, answer) in enumerate(questions, start=1):
        open_attr = " open" if idx == 1 else ""
        parts.append(
            f'<details class="ebook-faq-item"{open_attr}><summary>{html.escape(question)}</summary><div><p>{html.escape(answer)}</p></div></details>'
        )
    return "\n".join(parts)


def category_internal_links(topic: str, books: List[Dict[str, Any]]) -> str:
    topic_name = clean_paragraph(topic)
    family = topic_family(topic_name)
    featured = books[0]
    guide_slug = CATEGORY_TO_TOPIC_GUIDE.get(topic_name)
    guide = topic_guide_record(guide_slug)
    compare_anchor = {
        "regulated": "Compare AI risks, evidence, and trust trade-offs",
        "operations": "Compare AI use cases across operational sectors",
        "security": "Compare AI applications, risks, and adoption patterns",
        "creative": "Compare generative AI use cases and trade-offs",
        "foundation": "Compare core AI concepts, claims, and use cases",
        "environment": "Compare AI use cases, risks, and measurable outcomes",
        "sports": "Compare AI use cases, judgement calls, and trade-offs",
    }.get(family, "Compare AI use cases and trade-offs")
    links = [
        (
            f"/ebooks/{featured['slug']}/",
            f"Start with {featured['title']}",
            "Featured book page with the full summary, FAQ, and buy route.",
        ),
        (
            "/glossary/",
            f"Use the AI glossary to decode {topic_name.lower()} terms",
            "Definitions and plain-English explanations for the jargon this category keeps bumping into.",
        ),
        (
            "/compare/",
            compare_anchor,
            "Side-by-side context for how different AI areas solve different problems and create different headaches.",
        ),
    ]
    if guide:
        links.append(
            (
                f"/topics/{guide_slug}/",
                f"Read the {guide['title']} guide",
                guide["summary"],
            )
        )
    links.append(
        (
            "/podcast/",
            f"Listen to the podcast for wider {topic_name.lower()} context",
            "Editorial context and broader AI commentary beyond the catalogue pages.",
        )
    )
    links.append(
        (
            "/newsletter/",
            "Get the newsletter for ongoing AI developments",
            "Useful if you want the moving story, not just the evergreen version.",
        )
    )
    return "\n".join(
        f'<li><a href="{html.escape(href)}">{html.escape(label)}</a><span>{html.escape(description)}</span></li>'
        for href, label, description in links[:5]
    )


def topic_guide_cards_markup() -> str:
    cards = []
    for slug, payload in TOPIC_GUIDE_DIRECTORY.items():
        cards.append(
            f'<article class="card topic-card topic-card--guide"><h2><a href="/topics/{slug}/">{html.escape(payload["title"])}</a></h2><p>{html.escape(payload["summary"])}</p></article>'
        )
    return "\n".join(cards)


def topics_index_support_links() -> str:
    links = [
        ("/glossary/", "Use the AI glossary for key terms", "Start here if the language gets dense or suspiciously overconfident."),
        ("/compare/", "Compare AI use cases and trade-offs", "Useful for seeing how different AI categories solve different problems."),
        ("/podcast/", "Listen to the podcast for wider AI context", "Weekly editorial context for the bigger shifts around the catalogue."),
        ("/newsletter/", "Join the newsletter for ongoing AI developments", "The moving story, minus the usual noise and confetti."),
    ]
    return "\n".join(
        f'<li><a href="{html.escape(href)}">{html.escape(label)}</a><span>{html.escape(description)}</span></li>'
        for href, label, description in links
    )


def book_unique_evidence_passage(book: Dict[str, Any]) -> str:
    topic_lc = clean_paragraph(book.get("topic", "")).lower() or "the field"
    learn_line = clean_paragraph(book["what_youll_learn"][0] if book.get("what_youll_learn") else "")
    family = topic_family(book.get("topic", ""))
    tradeoff = {
        "regulated": f"the awkward point where speed, evidence, and accountability stop pretending to be friends in {topic_lc}",
        "operations": f"the point where promised efficiency in {topic_lc} meets maintenance logs, handovers, and failure modes",
        "security": f"the trade-off between stronger signal in {topic_lc} and a fresh layer of operational noise",
        "creative": f"the clash between convenience in {topic_lc} and the control, ownership, and trust questions it drags in behind it",
        "foundation": f"the distance between broad AI claims in {topic_lc} and what the systems can actually justify",
        "environment": f"the gap between environmental promise in {topic_lc} and what can be measured without flattering the numbers",
        "sports": f"the tension between data-led gains in {topic_lc} and the human judgement that still decides outcomes",
    }.get(family, f"the gap between impressive claims in {topic_lc} and what the work actually demands")
    audience = clean_paragraph(book.get("audience", "")).rstrip(".")
    if audience:
        audience_sentence = audience[0].lower() + audience[1:] if len(audience) > 1 else audience.lower()
        audience_sentence = f"It is written for {audience_sentence},"
    else:
        audience_sentence = "It is written as a grounded briefing,"
    if learn_line:
        learn_sentence = learn_line[0].lower() + learn_line[1:]
        learning_sentence = f"and it tackles questions such as {learn_sentence}"
    else:
        learning_sentence = "and it keeps the focus on the decisions that matter once AI leaves the demo stage"
    return f"In practice, {book['title']} is most useful when the real issue is {tradeoff}. {audience_sentence} {learning_sentence}, which makes it more useful than a generic explainer when someone has to decide what happens next in an actual workflow, classroom, policy setting, or team."


def book_semantic_journey_links(book: Dict[str, Any]) -> str:
    guide_slug = CATEGORY_TO_TOPIC_GUIDE.get(clean_paragraph(book.get("topic", "")))
    guide = topic_guide_record(guide_slug)
    links = [
        ("/ebooks/", "Browse all books"),
        (book.get("topic_url") or "/topics/", f'Browse {clean_paragraph(book.get("topic", "AI"))} books'),
        ("/glossary/", "Glossary"),
        ("/compare/", "Comparisons"),
    ]
    if guide:
        links.append((f"/topics/{guide_slug}/", guide["title"] + " guide"))
    links.extend([
        ("/podcast/", "Podcast"),
        ("/newsletter/", "Newsletter"),
    ])
    return "\n".join(f'<a href="{html.escape(href)}">{html.escape(label)}</a>' for href, label in links[:6])


def showcase_subhead(book: Dict[str, Any]) -> str:
    family = topic_family(book.get("topic", ""))
    topic_lc = clean_paragraph(book.get("topic", "")).lower() or "the field"
    return {
        "regulated": f"From real deployment in {topic_lc} to evidence, oversight, and real-world consequence.",
        "operations": f"From day-to-day work in {topic_lc} to gains, failure modes, and trade-offs.",
        "security": f"From active defence in {topic_lc} to attacker adaptation, blind spots, and operational noise.",
        "creative": f"From creative speed in {topic_lc} to ownership, control, and the compromises buried inside convenience.",
        "foundation": f"From first principles in {topic_lc} to practical claims, limitations, and sharper judgement.",
        "environment": f"From environmental promise in {topic_lc} to measurable outcomes, constraints, and trade-offs.",
        "sports": f"From performance decisions in {topic_lc} to human judgement, edge cases, and competitive trade-offs.",
    }.get(family, f"From practical deployment in {topic_lc} to trade-offs, judgement, and real-world constraints.")


def showcase_note(book: Dict[str, Any]) -> str:
    family = topic_family(book.get("topic", ""))
    topic_lc = clean_paragraph(book.get("topic", "")).lower() or "the field"
    return {
        "regulated": f"Built for readers who need {topic_lc} explained as a real operating environment, not a compliance-free demo.",
        "operations": f"Built for people who care whether AI in {topic_lc} survives contact with the workflow rather than just the keynote.",
        "security": f"Built for readers who know the tooling only matters if it improves the signal without burying the team in noise.",
        "creative": f"Built for people who want the upside in {topic_lc} without politely ignoring the rights, trust, and control problems.",
        "foundation": f"Built for readers who want the claims around {topic_lc} translated, tested, and relieved of their marketing costume.",
        "environment": f"Built for readers who want environmental realism in {topic_lc}, not green-tinted dashboards and applause.",
        "sports": f"Built for people who know the numbers can help in {topic_lc}, but not more than the humans making the call.",
    }.get(family, f"Built for readers who want practical judgement in {topic_lc} rather than brochure copy.")


def practical_outcomes_intro(book: Dict[str, Any]) -> str:
    family = topic_family(book.get("topic", ""))
    topic_lc = clean_paragraph(book.get("topic", "")).lower() or "the field"
    return {
        "regulated": f"You should finish it better able to separate usable AI in {topic_lc} from risky shortcuts, loose governance, and expensive confidence.",
        "operations": f"You should finish it with a clearer feel for where AI in {topic_lc} improves the workflow, where it adds fragility, and what to pilot before anyone starts chest-thumping.",
        "security": f"You should finish it better at separating useful automation in {topic_lc} from noisy promises and more alert to where attackers or blind spots creep in.",
        "creative": f"You should finish it with a sharper sense of where AI in {topic_lc} genuinely helps the work and where it starts borrowing tomorrow's headache.",
        "foundation": f"You should finish it with the jargon around {topic_lc} translated, the stronger claims stress-tested, and a better map of where to dig deeper.",
        "environment": f"You should finish it better able to tell the difference between measurable gains in {topic_lc}, modelling optimism, and plain old green lipstick on a dashboard.",
        "sports": f"You should finish it able to judge which parts of {topic_lc} belong to data, which still belong to people, and where the line keeps moving.",
    }.get(family, f"You should leave this one with clearer judgement about {topic_lc}, fewer lazy assumptions, and a better sense of where to press further or walk away.")


def default_distinct_angle(title: str, topic: str) -> str:
    family = topic_family(topic)
    topic_lc = topic.lower()
    return {
        "regulated": f"{title} keeps its eye on evidence, accountability, and the point where a slick demo meets real-world responsibility in {topic_lc}.",
        "operations": f"{title} keeps its boots on the ground, looking at workflow, failure modes, and whether the gains survive contact with real operations in {topic_lc}.",
        "security": f"{title} keeps the focus on signal, defence, and the cost of getting the call wrong in {topic_lc}.",
        "creative": f"{title} keeps one eye on craft and the other on ownership, control, and the compromises hiding inside convenience in {topic_lc}.",
        "foundation": f"{title} keeps the applause to a minimum and asks what the systems actually do, what they break, and what they are being oversold to solve in {topic_lc}.",
        "environment": f"{title} keeps the focus on measurable environmental value in {topic_lc} rather than eco-flavoured marketing copy.",
        "sports": f"{title} keeps the focus on performance, judgement, and how data changes decisions in {topic_lc} without pretending sport becomes an equation.",
    }.get(family, f"{title} keeps the focus on practical judgement in {topic_lc} rather than drifting into brochure-speak.")


WORKBOOK_GOVERNED_COPY_FIELDS = (
    ("title", "title"),
    ("short", "short"),
    ("short", "short_description"),
    ("description", "description"),
    ("summary", "summary"),
    ("topic", "topic"),
    ("audience", "audience"),
    ("who_for", "who_for"),
    ("what_this_book_covers", "what_this_book_covers"),
    ("why_it_matters", "why_it_matters"),
)



def default_short(topic: str, pages: int | None) -> str:
    return helper_default_short(topic, pages)


SEO_TITLE_OVERRIDES = {
    "ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology": "AI and Formula 1",
    "ai-powered-smart-grid-revolutionizing-electricity-distribution-and-generation": "AI-Powered Smart Grid",
    "artificial-intelligence-and-the-law-case-studies-and-future-trends": "AI and the Law",
    "artificial-intelligence-for-cyber-security-a-practical-guide-to-data-breach-prevention": "AI for Cyber Security",
    "artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology": "AI for Wildlife Conservation",
    "artificial-intelligence-in-banking-revolutionizing-finance-and-data-security": "AI in Banking",
    "artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability": "AI in Logistics",
    "artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement": "AI in Sports",
    "artificial-intelligence-in-veterinary-medicine-transforming-animal-healthcare-through-innovation": "AI in Veterinary Medicine",
    "artificial-intelligence-powered-retail-revolutionizing-customer-experience-for-a-sustainable-future": "AI-Powered Retail",
    "artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery": "AI Revolution in Manufacturing",
    "the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media": "The AI Behind Your Feed",
    "the-autonomous-revolution-artificial-intelligence-and-the-future-of-the-automotive-industry": "The Autonomous Revolution",
    "the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information": "The Future of Government and AI",
    "the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming": "The House Always Knows",
    "ai-in-aviation-transforming-safety-and-sustainability": "AI in Aviation",
    "ai-in-maritime-revolutionizing-shipping-for-sustainability": "AI in Maritime",
    "ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future": "AI in Agriculture",
    "ai-in-education-reimagining-learning-for-every-student": "AI in Education: Reimagining Learning for Every Student",
    "ai-revolution-in-railways-modernizing-travel-for-a-smarter-future": "AI Revolution in Railways",
    "artificial-intelligence-in-construction-building-a-sustainable-future": "AI in Construction",
    "artificial-intelligence-in-industry-a-comprehensive-guide": "AI in Industry",
    "artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare": "AI in Pharmaceuticals",
    "beyond-earth-how-ai-is-transforming-space-exploration": "Beyond Earth: AI in Space",
    "climate-intelligence-harnessing-ai-for-a-greener-future": "Climate Intelligence",
    "digital-defense-the-role-of-ai-in-modern-warfare": "Digital Defense and AI",
    "digital-diagnosis-how-ai-is-revolutionizing-healthcare": "Digital Diagnosis",
    "from-reporters-to-robots-how-ai-is-reshaping-journalism": "From Reporters to Robots",
    "game-ai-unleashed-from-finite-state-machines-to-machine-learning": "Game AI Unleashed",
    "lights-camera-algorithm-ai-s-role-in-modern-filmmaking": "Lights, Camera, Algorithm",
    "smart-buildings-ai-powered-efficiency-and-sustainability": "Smart Buildings and AI",
    "the-ai-music-revolution-creativity-controversy-and-collaboration": "The AI Music Revolution",
    "the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead": "The Architects of AI",
    "the-artificial-intelligence-job-shift-navigating-the-future-of-work": "The AI Job Shift",
    "the-artificial-intelligence-revolution-from-algorithms-to-consciousness": "The AI Revolution",
}


def book_meta_title(book: Dict[str, Any]) -> str:
    slug = clean_paragraph(book.get("slug", ""))
    if slug in SEO_TITLE_OVERRIDES:
        return SEO_TITLE_OVERRIDES[slug]
    return clean_paragraph(book.get("title", ""))



def book_meta_description(book: Dict[str, Any]) -> str:
    primary = clean_paragraph(book.get("description", ""))
    if primary and len(primary) <= 155:
        return primary
    fallback = clean_paragraph(book.get("short") or book.get("short_description") or book.get("summary") or primary)
    return fallback or primary



def catalogue_meta_description(topic: str) -> str:
    topic_name = clean_paragraph(topic).lower() or "artificial intelligence"
    return f"Browse Jonathan Harris AI books on {topic_name} with plain-English guides, practical analysis, clear summaries, and direct Amazon routes."



def topics_index_meta_description() -> str:
    return "Explore AI topics across Jonathan Harris's ebook library, with practical guides, grounded summaries, and direct routes into each catalogue page."



def extract_html_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.S | re.I)
    return html.unescape(clean_paragraph(match.group(1))) if match else ""



def extract_meta_description(text: str) -> str:
    for meta_tag in re.findall(r"<meta\b[^>]*>", text, flags=re.I | re.S):
        name_match = re.search(r'\bname=(["\'])(.*?)\1', meta_tag, flags=re.I | re.S)
        if not name_match or name_match.group(2).strip().lower() != "description":
            continue
        content_match = re.search(r'\bcontent=(["\'])(.*?)\1', meta_tag, flags=re.I | re.S)
        if content_match:
            return html.unescape(clean_paragraph(content_match.group(2)))
    return ""

def extract_img_src(tag: str) -> str:
    match = re.search(r'\bsrc="([^"]+)"', tag, re.I)
    return clean_paragraph(match.group(1)) if match else ""


def is_remote_image_src(src: str) -> bool:
    cleaned = clean_paragraph(src)
    return cleaned.startswith(("http://", "https://"))


def metadata_budget_errors(
    label: str,
    text: str,
    *,
    max_title: int | None = None,
    min_description: int | None = None,
    max_description: int | None = None,
) -> List[str]:
    errors: List[str] = []
    title = extract_html_title(text)
    description = extract_meta_description(text)
    if not title:
        errors.append(f"{label} is missing a title tag.")
    elif max_title is not None and len(title) > max_title:
        errors.append(f"{label} title tag exceeds {max_title} characters ({len(title)}).")
    if not description:
        errors.append(f"{label} is missing a meta description.")
    else:
        if min_description is not None and len(description) < min_description:
            errors.append(f"{label} meta description is shorter than {min_description} characters ({len(description)}).")
        if max_description is not None and len(description) > max_description:
            errors.append(f"{label} meta description exceeds {max_description} characters ({len(description)}).")
    return errors



def build_default_faq(book: Dict[str, Any]) -> List[Dict[str, Any]]:
    learn_line = book["what_youll_learn"][0] if book.get("what_youll_learn") else topic_intro(book["topic"])
    topic_name = clean_paragraph(book.get("topic", "Artificial Intelligence"))
    topic_lc = topic_name.lower()
    topic_phrase = "artificial intelligence" if topic_name.lower() == "artificial intelligence" else f"AI in {topic_lc}"
    return [
        {
            "@type": "Question",
            "name": f"What does this book explain about {topic_phrase}?",
            "acceptedAnswer": {"@type": "Answer", "text": learn_line},
        },
        {
            "@type": "Question",
            "name": f"Who gets the most value from this {topic_lc} guide?",
            "acceptedAnswer": {"@type": "Answer", "text": audience_faq_answer(book["audience"], book["topic"])},
        },
        {
            "@type": "Question",
            "name": "How detailed is the coverage?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": f"It runs to {book['pages']} pages and focuses on {clean_paragraph(book.get('what_this_book_covers', '')).rstrip('.')}.",
            },
        },
        {
            "@type": "Question",
            "name": "Where can I get the eBook?",
            "acceptedAnswer": {"@type": "Answer", "text": "Available as an eBook via Amazon using the buy link on this page."},
        },
    ]


def build_master_from_workbook(workbook_path: Path) -> List[Dict[str, Any]]:
    order, workbook_map, workbook_content = parse_workbook(workbook_path, sanitise_content=False)
    if not order:
        raise ValueError("No ebook rows found in workbook")

    required_master_fields = [
        "title", "short", "description", "summary", "topic", "tags", "keywords", "audience",
        "who_for", "what_this_book_covers", "what_youll_learn", "why_it_matters", "tone", "author",
        "identifier", "asin", "pages", "datePublished", "book_url", "buy_route_full", "buy_url",
        "cover", "legacy_alias_url",
    ]

    build_timestamp = utc_now()
    records: List[Dict[str, Any]] = []
    missing_fields: List[str] = []
    for idx, slug in enumerate(order, start=1):
        workbook = workbook_map[slug]
        content = workbook_content.get(slug, {})

        for field in required_master_fields:
            value = workbook.get(field) if field in workbook else content.get(field)
            if isinstance(value, list):
                has_value = any(clean_paragraph(item) for item in value)
            else:
                has_value = bool(clean_paragraph(value))
            if not has_value:
                missing_fields.append(f"{slug}: missing canonical workbook field '{field}'")

        title = clean_paragraph(content.get("title")) or humanise_slug(slug)
        topic = clean_paragraph(content.get("topic")) or "Artificial Intelligence"
        tags = unique_list(content.get("tags") or [topic, "Artificial Intelligence", "AI Trends"])
        keywords = unique_list(content.get("keywords") or [topic, title, *tags])
        pages = workbook.get("pages")
        summary_seed = clean_paragraph(content.get("summary")) or clean_paragraph(content.get("description")) or topic_intro(topic)
        description_seed = clean_paragraph(content.get("description")) or summary_seed
        summary = strip_pages_from_summary(summary_seed, pages)
        description = clean_paragraph(description_seed)
        what_this_book_covers = clean_paragraph(content.get("what_this_book_covers")) or summary
        audience = clean_paragraph(content.get("audience")) or clean_paragraph(content.get("who_for")) or DEFAULT_AUDIENCE
        who_for = clean_paragraph(content.get("who_for")) or audience
        what_youll_learn = unique_list(content.get("what_youll_learn") or default_learning_points(topic))
        why_it_matters = clean_paragraph(content.get("why_it_matters")) or default_why_it_matters(topic)
        short = strip_pages_from_summary(content.get("short"), pages) or default_short(topic, pages)
        canonical_url = ensure_trailing_slash(workbook.get("book_url") or f"{SITE_URL}/ebooks/{slug}/")
        topic_slug = slugify(topic)
        topic_url = f"/catalogue/{topic_slug}/"
        identifier = clean_paragraph(content.get("identifier")) or f"JH-AI-EBOOK-{idx:02d}"
        author = clean_paragraph(content.get("author")) or SITE_NAME
        tone = clean_paragraph(content.get("tone")) or DEFAULT_TONE
        cover = workbook.get("cover") or clean_paragraph(content.get("cover") or content.get("image") or "")

        book: Dict[str, Any] = {
            "id": idx,
            "key": f"{idx}-ebook",
            "slug": slug,
            "title": title,
            "short": short,
            "short_description": short,
            "description": description,
            "summary": summary,
            "topic": topic,
            "topic_slug": topic_slug,
            "topic_url": topic_url,
            "filter": topic,
            "tags": tags,
            "keywords": keywords,
            "cover": cover,
            "main_image": cover,
            "image": cover,
            "buy_url": workbook.get("buy_url", ""),
            "buy_route": workbook.get("buy_route") or f"/ebooks/{slug}/buy-now",
            "buy_route_full": workbook.get("buy_route_full") or f"{SITE_URL}/ebooks/{slug}/buy-now",
            "canonical_url": canonical_url,
            "book_url": canonical_url,
            "legacy_alias_url": workbook.get("legacy_alias_url", ""),
            "pages": pages,
            "asin": workbook.get("asin", ""),
            "datePublished": workbook.get("datePublished", ""),
            "dateModified": "",
            "author": author,
            "tone": tone,
            "audience": audience,
            "identifier": identifier,
            "what_this_book_covers": what_this_book_covers,
            "who_for": who_for,
            "what_youll_learn": what_youll_learn,
            "why_it_matters": why_it_matters,
            "showcase_heading": clean_paragraph(content.get("showcase_heading")) or (f"How AI is reshaping {topic.lower()}" if topic.lower() != "artificial intelligence" else "AI without the carnival barker routine"),
            "distinct_angle": clean_paragraph(content.get("distinct_angle")) or default_distinct_angle(title, topic),
            "notes": workbook.get("notes", ""),
        }
        book = sanitise_record_copy(book)
        faq_payload = content.get("faq")
        book["faq"] = faq_payload if isinstance(faq_payload, list) else build_default_faq(book)
        book = sanitise_record_copy(book)
        records.append(book)

    if missing_fields:
        raise ValueError("Canonical workbook is missing required live fields:\n- " + "\n- ".join(missing_fields))

    role_errors = content_role_validation_errors(records)
    if role_errors:
        raise ValueError("Canonical workbook content roles are collapsing:\n- " + "\n- ".join(role_errors))

    add_related_books(records)
    existing_master = {
        clean_paragraph(item.get("slug")): item
        for item in (read_json(MASTER_PATH, default=[]) or [])
        if isinstance(item, dict) and clean_paragraph(item.get("slug"))
    }
    for record in records:
        existing = existing_master.get(record["slug"])
        if existing and {k: v for k, v in existing.items() if k != "dateModified"} == {k: v for k, v in record.items() if k != "dateModified"}:
            record["dateModified"] = clean_paragraph(existing.get("dateModified")) or build_timestamp
        else:
            record["dateModified"] = build_timestamp
    return records


def add_related_books(records: List[Dict[str, Any]]) -> None:
    token_map = {record["slug"]: book_token_groups(record) for record in records}

    def sort_key(current: Dict[str, Any], candidate: Dict[str, Any]) -> tuple[int, int, int, int, int, str]:
        score, tie_breaker = related_book_score(candidate, current, token_map[current["slug"]], token_map[candidate["slug"]])
        same_topic, title_overlap, grouped_overlap, keyword_overlap, candidate_title = tie_breaker
        return (-same_topic, -score, -title_overlap, -grouped_overlap, -keyword_overlap, candidate_title)

    for current in records:
        ranked = sorted(
            [candidate for candidate in records if candidate["slug"] != current["slug"]],
            key=lambda candidate: sort_key(current, candidate),
        )
        current["related_slugs"] = [book["slug"] for book in ranked[:4]]
        current["title_tokens"] = sorted(token_map[current["slug"]]["title"])
        current["topic_tokens"] = sorted(token_map[current["slug"]]["topic"])



def load_master() -> List[Dict[str, Any]]:
    master = read_json(MASTER_PATH, default=[])
    if not master:
        raise ValueError(f"Master file not found: {MASTER_PATH}")
    fallback_timestamp = infer_build_timestamp()
    for book in master:
        book.setdefault("dateModified", fallback_timestamp)
        book.setdefault("short_description", book.get("short", ""))
        sanitise_record_copy(book)
    add_related_books(master)
    return master



def save_master(records: List[Dict[str, Any]]) -> None:
    build_timestamp = utc_now()
    for book in records:
        book.setdefault("dateModified", build_timestamp)
    write_json(MASTER_PATH, records)



def book_to_public_record(book: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": book["id"],
        "key": book["key"],
        "title": book["title"],
        "short": book["short"],
        "short_description": book["short"],
        "cover": book["cover"],
        "main_image": book["main_image"],
        "tags": book["tags"],
        "filter": book["filter"],
        "keywords": book["keywords"],
        "buy_url": book["buy_url"],
        "buy_target_url": book["buy_url"],
        "slug": book["slug"],
        "asin": book["asin"],
        "pages": book["pages"],
        "datePublished": book["datePublished"],
        "dateModified": book.get("dateModified") or infer_build_timestamp(),
        "canonical_url": book["canonical_url"],
        "buy_route": book["buy_route"],
        "buy_route_full": book["buy_route_full"],
        "topic_url": book["topic_url"],
        "related_slugs": book.get("related_slugs", []),
        "title_tokens": book.get("title_tokens", []),
        "topic_tokens": book.get("topic_tokens", []),
    }



def featured_rotation_selection(now: dt.datetime | None = None) -> Dict[str, int | str]:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current_utc = current.astimezone(dt.timezone.utc)
    iso_year, iso_week, _ = current_utc.date().isocalendar()
    return {
        "method": "iso_week_rotation",
        "iso_week": iso_week,
        "year": iso_year,
    }



def select_featured_book_record(public_records: List[Dict[str, Any]], now: dt.datetime | None = None) -> tuple[Dict[str, Any] | None, Dict[str, int | str]]:
    selection = featured_rotation_selection(now=now)
    if not public_records:
        return None, selection
    return public_records[selection["iso_week"] % len(public_records)], selection



def build_podcast_sponsor_payload(book: Dict[str, Any]) -> Dict[str, str]:
    title = clean_paragraph(book.get("title"))
    short = clean_paragraph(book.get("short"))
    topic = clean_paragraph(book.get("filter"))
    canonical_url = clean_paragraph(book.get("canonical_url"))
    buy_route_full = clean_paragraph(book.get("buy_route_full"))
    pages = book.get("pages")
    tags = [clean_paragraph(tag) for tag in (book.get("tags") or []) if clean_paragraph(tag)]
    tags_text = ", ".join(tags[:3])

    page_sentence = f" It runs {pages} pages." if isinstance(pages, int) and pages > 0 else ""
    topic_sentence = f" It focuses on {topic}." if topic else ""
    tags_sentence = f" Topics include {tags_text}." if tags_text else ""
    short_sentence = short if short.endswith((".", "!", "?")) else (f"{short}." if short else "")

    return {
        "label": "This week's sponsor",
        "headline": f"This week's sponsor is {title}",
        "cta": f"See the book at {canonical_url} or buy on Amazon at {buy_route_full}",
        "midroll_15": f"This week's sponsor is {title}. {short_sentence} Read more at {canonical_url}".strip(),
        "midroll_30": (
            f"This week's sponsor is {title}."
            f" {short_sentence}"
            f"{topic_sentence}"
            f"{page_sentence}"
            f"{tags_sentence}"
            f" See the full book page at {canonical_url} or go straight to Amazon at {buy_route_full}."
        ).replace("  ", " ").strip(),
    }



def build_featured_book_payload(public_records: List[Dict[str, Any]], now: dt.datetime | None = None) -> Dict[str, Any]:
    book, selection = select_featured_book_record(public_records, now=now)
    return {
        "version": "v1",
        "selection": selection,
        "book": book or {},
        "podcast_sponsor": build_podcast_sponsor_payload(book or {}),
    }



def render_related_links(book: Dict[str, Any], all_books: List[Dict[str, Any]]) -> str:
    by_slug = {item["slug"]: item for item in all_books}
    items = []
    for slug in book.get("related_slugs", [])[:4]:
        related = by_slug.get(slug)
        if not related:
            continue
        items.append(
            '<li><a href="/ebooks/{slug}/">{title}</a><span>{topic} · {pages} pages</span></li>'.format(
                slug=html.escape(related["slug"]),
                title=html.escape(related["title"]),
                topic=html.escape(related["topic"]),
                pages=related["pages"],
            )
        )
    return "\n".join(items)

def render_faq_markup(book: Dict[str, Any]) -> str:
    parts = []
    for idx, item in enumerate(book.get("faq", []), start=1):
        question = clean_paragraph(item.get("name", ""))
        answer = clean_paragraph(item.get("acceptedAnswer", {}).get("text", ""))
        open_attr = " open" if idx == 1 else ""
        parts.append(
            "<details class=\"ebook-faq-item\"%s><summary>%s</summary><div><p>%s</p></div></details>"
            % (open_attr, html.escape(question), html.escape(answer))
        )
    return "\n".join(parts)



def render_breadcrumbs(book: Dict[str, Any]) -> str:
    crumbs = [
        '<a href="/">Home</a>',
        '<span aria-hidden="true">›</span>',
        '<a href="/ebooks/">eBooks</a>',
    ]
    if book.get("topic_url"):
        crumbs.extend([
            '<span aria-hidden="true">›</span>',
            '<a href="{url}">{topic}</a>'.format(url=html.escape(book["topic_url"]), topic=html.escape(book["topic"])),
        ])
    crumbs.extend([
        '<span aria-hidden="true">›</span>',
        '<span>{title}</span>'.format(title=html.escape(book["title"])),
    ])
    return "".join(crumbs)

def render_image_tag(*, src: str, alt: str, class_name: str, loading: str = "lazy", width: int | None = None, height: int | None = None, srcset: str | None = None, sizes: str | None = None, fetchpriority: str | None = None) -> str:
    attrs = [
        f'alt="{html.escape(alt)}"',
        f'class="{html.escape(class_name)}"',
        f'decoding="async"',
        f'loading="{html.escape(loading)}"',
        f'src="{html.escape(src)}"',
    ]
    if srcset:
        attrs.append(f'srcset="{html.escape(srcset)}"')
        if sizes:
            attrs.append(f'sizes="{html.escape(sizes)}"')
    if fetchpriority:
        attrs.append(f'fetchpriority="{html.escape(fetchpriority)}"')
    if width is not None:
        attrs.append(f'width="{width}"')
    if height is not None:
        attrs.append(f'height="{height}"')
    return "<img " + " ".join(attrs) + "/>"


def render_cover_image(book: Dict[str, Any], class_name: str, loading: str = "lazy") -> str:
    return render_image_tag(
        src=book["cover"],
        alt=f"{book['title']} cover",
        class_name=class_name,
        loading=loading,
        width=BOOK_COVER_WIDTH,
        height=BOOK_COVER_HEIGHT,
        srcset=build_same_source_srcset(book["cover"], BOOK_COVER_WIDTH),
        sizes=cover_sizes(class_name),
        fetchpriority="high" if loading == "eager" else None,
    )


def audience_bullets(book: Dict[str, Any]) -> List[str]:
    topic_name = clean_paragraph(book.get("topic", "Artificial Intelligence"))
    topic_lc = topic_name.lower()
    title_stem = clean_paragraph(book.get("title", "")).split(":", 1)[0]
    family = topic_family(topic_name)
    learn_items = book.get("what_youll_learn", [])
    first_signal = clean_paragraph(learn_items[0] if learn_items else "").rstrip(".")
    second_signal = clean_paragraph(learn_items[1] if len(learn_items) > 1 else "").rstrip(".")
    family_line = {
        "regulated": f"Readers working in or around {topic_lc} who need the practical trade-offs explained before policy, procurement, or implementation decisions harden.",
        "operations": f"Operators, managers, and curious readers who want to know whether AI in {topic_lc} improves the workflow or just adds another dashboard to ignore.",
        "security": f"Security-minded readers who need a clearer feel for where AI helps defenders in {topic_lc} and where it simply reshuffles the noise.",
        "creative": f"People working around {topic_lc} who want the upside explained without pretending the ownership and control questions vanished overnight.",
        "foundation": f"Readers who want the bigger arguments around {topic_lc} translated into plain English and tested against how the systems behave in practice.",
        "environment": f"Readers who want environmental claims in {topic_lc} measured against evidence, costs, and real deployment constraints.",
        "sports": f"Readers interested in how AI changes judgement, preparation, and performance in {topic_lc} without turning humans into footnotes.",
    }.get(family, f"Readers who want a practical, grounded route into {topic_lc} rather than another brochure about inevitable disruption.")
    slug = clean_paragraph(book.get("slug", ""))
    signal_line = first_signal or f"How AI is being used in {topic_lc} today"
    follow_on = second_signal or clean_paragraph(book.get("what_this_book_covers", "")).split(".")[0]
    signal_line = signal_line[0].lower() + signal_line[1:] if signal_line else topic_lc
    follow_on = follow_on[0].lower() + follow_on[1:] if follow_on else topic_lc
    bullets = [
        replace_banned_ebook_phrases(f"Curious readers who want a grounded view of {title_stem} without the applause soundtrack.", slug),
        replace_banned_ebook_phrases(family_line, slug),
        replace_banned_ebook_phrases(f"Anyone who wants clear context on {signal_line} before they trust the louder claims.", slug),
        replace_banned_ebook_phrases(f"Readers looking for sharper judgement on {follow_on} rather than recycled buzzwords.", slug),
    ]
    return bullets


def chapter_signal_cards(book: Dict[str, Any]) -> str:
    cards = []
    for item in book.get("what_youll_learn", [])[:3]:
        heading = re.sub(r"[\.:].*", "", item).strip()
        heading = heading[:64].rstrip(" ,.;:") or "Chapter signal"
        cards.append(
            f'<article class="ebook-signal-card"><h3>{html.escape(heading)}</h3><p>{html.escape(item)}</p></article>'
        )
    return "\n".join(cards)



def problem_framing(book: Dict[str, Any]) -> str:
    topic_lc = clean_paragraph(book.get("topic", "")).lower() or "the field"
    family = topic_family(book.get("topic", ""))
    learn_line = clean_paragraph(book["what_youll_learn"][0] if book.get("what_youll_learn") else "").rstrip(".")
    framing_tail = f" It keeps coming back to {learn_line[0].lower() + learn_line[1:] if learn_line else 'the practical decisions that expose weak claims fastest'}."
    frames = {
        "regulated": f"{book['topic']} is where speed, evidence, compliance, and accountability all start elbowing each other for room. This title keeps the focus on what AI is genuinely doing in {topic_lc}, where oversight has to tighten, and where the expensive mistakes tend to hide.{framing_tail}",
        "operations": f"{book['topic']} is where efficiency claims meet maintenance logs, handovers, failure modes, and people who still have to run the place. This title looks at what AI is actually changing in {topic_lc}, which gains are solid, and where the shiny promise falls apart under operational pressure.{framing_tail}",
        "security": f"{book['topic']} is one of those domains where signal, false positives, attacker behaviour, and tool sprawl all collide at speed. This title looks at what AI is really doing in {topic_lc}, where it strengthens the work, and where automation simply changes the shape of the problem.{framing_tail}",
        "creative": f"{book['topic']} gets messy fast because speed, originality, ownership, and platform incentives do not naturally get along. This title looks at what AI is really doing in {topic_lc}, what it improves, and what it muddies the moment the convenience starts looking irresistible.{framing_tail}",
        "foundation": f"{book['topic']} is one of those areas where the argument gets noisy very quickly: claims versus evidence, fluency versus substance, novelty versus context. This title cuts through that din and looks at what AI is actually doing in {topic_lc}, where it helps, and where it starts creating fresh headaches.{framing_tail}",
        "environment": f"{book['topic']} attracts hopeful claims because everyone likes a cleaner future and a clever dashboard. This title looks at what AI is actually doing in {topic_lc}, where the measurable gains are, and where the story outruns the evidence.{framing_tail}",
        "sports": f"{book['topic']} sits in that awkward space where numbers can sharpen judgement or flatten it into false certainty. This title looks at what AI is actually doing in {topic_lc}, where the edge is real, and where the human part still refuses to disappear.{framing_tail}",
    }
    return frames.get(
        family,
        f"{book['topic']} is one of those areas where the argument gets noisy: efficiency versus judgement, convenience versus control, automation versus accountability. This title cuts through that din and looks at what AI is actually doing in {topic_lc}, where it helps, and where it starts to create fresh headaches.{framing_tail}",
    )


def practical_outcomes(book: Dict[str, Any]) -> List[str]:
    """Return practical, decision-oriented outcomes distinct from what_youll_learn bullets.
    
    These are action-framed: what can the reader DO or DECIDE differently after reading?
    Derived from why_it_matters, audience, and topic — NOT from what_youll_learn items.
    """
    topic = book.get("topic", "AI")
    topic_lc = topic.lower()
    audience = book.get("audience", "")
    why = book.get("why_it_matters", "")
    
    # Build decision-framed outcomes from distinct source fields
    outcomes = []
    
    # Outcome 1: from why_it_matters (if available and not empty)
    if why and len(why) > 20:
        # Extract first sentence as an action-frame
        first_sentence = why.split(".")[0].strip()
        if first_sentence and len(first_sentence) > 15:
            outcomes.append(f"Understand why {topic_lc} matters now and what the evidence actually says.")
    
    # Outcome 2: from audience/use-case context
    if audience and len(audience) > 10:
        outcomes.append(f"Assess whether {topic_lc} is applicable to your context before committing resources.")
    else:
        outcomes.append(f"Identify the specific use cases where {topic_lc} delivers measurable value.")
    
    # Outcome 3: always a governance/decision frame
    outcomes.append(f"Ask the right governance and implementation questions before adoption decisions become expensive.")
    
    return outcomes[:3] or default_learning_points(topic)[:3]



def render_book_page(book: Dict[str, Any], all_books: List[Dict[str, Any]]) -> str:
    header = render_header()
    footer = render_footer()
    hero_summary = book["summary"] or strip_pages_from_summary(book["description"], book.get("pages"))
    title = html.escape(book["title"])
    meta_title = html.escape(book_meta_title(book))
    description = html.escape(book_meta_description(book))
    canonical = html.escape(book["canonical_url"])
    cover = html.escape(book["cover"])
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": f"{book['canonical_url']}#faq",
        "mainEntity": book.get("faq", []),
    }
    learn_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in book.get("what_youll_learn", []))
    audience_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in audience_bullets(book))
    key_theme_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in book.get("tags", []))
    signal_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in practical_outcomes(book))

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>
<link href="https://images.jonathan-harris.online" rel="preconnect"/>
<link href="https://assets.jonathan-harris.online" rel="preconnect"/>
<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport"/>
<title>{meta_title} | Jonathan Harris</title>
<meta content="@jonathan_harris_01" name="twitter:site"/>
<meta content="@jonathan_harris_01" name="twitter:creator"/>
<meta content="#0D1420" name="theme-color"/>
{SHARED_INTER_FONT_HEAD_BLOCK}
<link as="style" href="/assets/css/site.css" rel="preload"/>
<link href="/assets/css/site.css" rel="stylesheet"/>


<link href="/assets/css/ebook-template.css" rel="stylesheet"/>
<meta content="GB" name="geo.region"/>
<link href="{canonical}" rel="canonical"/>
<link href="{canonical}" hreflang="en" rel="alternate"/>
<link href="{canonical}" hreflang="x-default" rel="alternate"/>
<meta content="{description}" name="description"/>
<meta content="index,follow" name="robots"/>
<meta content="{html.escape(book['asin'])}" name="book:asin"/>
<meta content="{html.escape(book['datePublished'])}" name="datePublished"/>
<meta content="{html.escape(book['datePublished'])}" property="book:release_date"/>
<meta content="books.book" property="og:type"/>
<meta content="{canonical}" property="og:url"/>
<meta content="{meta_title} | Jonathan Harris" property="og:title"/>
<meta content="{description}" property="og:description"/>
<meta content="{cover}" property="og:image"/>
<meta content="{title} cover" property="og:image:alt"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="{cover}" name="twitter:image"/>
<meta content="{meta_title} | Jonathan Harris" name="twitter:title"/>
<meta content="{description}" name="twitter:description"/>
<meta content="{title}" name="ai:topic"/>
<meta content="Artificial Intelligence" name="ai:primary"/>
<meta content="Book" name="ai:entity"/>
<meta content="{html.escape(book['identifier'])}" name="ai:identifier"/>
<meta content="book" name="ai:content_type"/>
<meta content="{html.escape(', '.join(book['keywords']))}" name="ai:keywords"/>
<meta content="{html.escape(book['tone'])}" name="ai-style"/>
<meta content="{html.escape(book['audience'])}" name="ai-target-audience"/>
<meta content="search=y, train-ai=y, citation-preferred=y" name="content-usage"/>
<script type="application/ld+json">{json_script(build_breadcrumb_schema(book))}</script>
<script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script>
<script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script>
<script type="application/ld+json">{json_script(build_book_schema(book))}</script>
<script type="application/ld+json">{json_script(faq_schema)}</script>
<link href="https://cdn-cookieyes.com" rel="dns-prefetch"/>
<link href="https://tracker.metricool.com" rel="dns-prefetch"/>
<script async="" id="cookieyes" src="https://cdn-cookieyes.com/client_data/c981d18033783598d2216add/script.js" type="text/javascript"></script>
<script defer="" src="/assets/js/consent-managed-scripts.js"></script>
</head>
<body class="ebook-detail">
{header}
<div aria-hidden="false" class="page-loader" id="pageLoader">
  <div aria-label="Preparing page" aria-live="polite" class="loader-card" role="status">
    <div aria-hidden="true" class="spinner"></div>
  </div>
</div>
<header aria-label="Book header" class="hero ebook-hero" role="region">
  <div class="wrap">
    <img alt="Jonathan Harris site logo" class="logo-plain" height="120" src="https://images.jonathan-harris.online/site-logo" width="120"/>
    <h1>{title}</h1>
    <p>{html.escape(hero_summary)} <span class="muted">See latest price on Amazon.</span></p>
  </div>
</header>
<main aria-label="Book content" class="main" id="main" role="main">
  <div class="wrap ebook-shell">
    <nav aria-label="Breadcrumb" class="breadcrumbs">{render_breadcrumbs(book)}</nav>

    <section class="card ebook-section quick-facts">
      <h2>Quick facts</h2>
      <ul class="ebook-facts">
        <li><strong>Topic:</strong> {html.escape(book['topic'])}</li>
        <li><strong>Tags:</strong> {html.escape(', '.join(book['tags']))}</li>
        <li><strong>Length:</strong> {book['pages']} pages</li>
        <li><strong>Best for:</strong> {html.escape(book['audience'])}</li>
      </ul>
    </section>

    <section class="ebook-showcase">
      <article class="card ebook-showcase__media">
        {render_cover_image(book, class_name="cover ebook-showcase__cover", loading="eager")}
        <div class="ebook-actions">
          <a class="button" href="{html.escape(book['buy_route'])}">Buy on Amazon</a>
          <a class="button secondary" href="/ebooks/">Browse related books</a>
        </div>
        <p class="meta">ASIN: {html.escape(book['asin'])} · Published {html.escape(format_date(book['datePublished']))}</p>
      </article>
      <article class="card ebook-showcase__content">
        <h2>{html.escape(book['showcase_heading'])}</h2>
        <p class="ebook-showcase__lead">{html.escape(book['what_this_book_covers'])}</p>
        <p class="ebook-showcase__subhead">{html.escape(showcase_subhead(book))}</p>
        <ul class="ebook-signal-list">
          {''.join(f'<li>► {html.escape(item)}</li>' for item in book.get('what_youll_learn', [])[:3])}
        </ul>
        <p class="ebook-showcase__note">{html.escape(showcase_note(book))}</p>
        <div class="ebook-inline-actions">
          <a href="{html.escape(book['buy_route'])}">Buy on Amazon</a>
          <a href="#deeper-overview">Read full overview</a>
          <a href="/ebooks/">Browse related books</a>
        </div>
      </article>
    </section>

    <section class="card ebook-section">
      <h2>Who this book is for</h2>
      <ul class="ebook-audience-list">
        {audience_items}
      </ul>
    </section>

    <section class="card ebook-section">
      <h2>Key themes</h2>
      <ul class="ebook-key-themes">
        {key_theme_items}
      </ul>
      <div class="ebook-theme-pills">{render_tag_pills(book['tags'])}</div>
    </section>

    <section class="card ebook-section">
      <h2>What you’ll learn</h2>
      <ul class="ebook-learn-list">
        {learn_items}
      </ul>
    </section>

    <section class="card ebook-section">
      <h2>Audience fit</h2>
      {escape_paragraphs(book['who_for'])}
    </section>

    <section class="card ebook-section" id="deeper-overview">
      <h2>Deeper overview</h2>
      {escape_paragraphs(book['summary'])}
    </section>

    <section class="card ebook-section">
      <h2>Why this title is useful in practice</h2>
      <p>{html.escape(book_unique_evidence_passage(book))}</p>
    </section>

    <section class="card ebook-section ebook-section--accent">
      <h2>Problem framing: where this topic gets messy</h2>
      {escape_paragraphs(problem_framing(book))}
    </section>

    <section class="card ebook-section">
      <h2>Practical outcomes</h2>
      <p>{html.escape(practical_outcomes_intro(book))}</p>
      <ul class="ebook-learn-list">
        {signal_items}
      </ul>
    </section>

    <section class="card ebook-section">
      <h2>Chapter-level signals</h2>
      <div class="ebook-signal-grid">
        {chapter_signal_cards(book)}
      </div>
    </section>

    <section class="card ebook-section">
      <h2>What makes this title distinct</h2>
      {escape_paragraphs(book['distinct_angle'])}
      {escape_paragraphs(book['why_it_matters'])}
    </section>

    <section class="related-books card">
      <h2>Related books</h2>
      <ul>
        {render_related_links(book, all_books)}
      </ul>
      <p class="jh-related-callout">Related titles are chosen from the catalogue based on topic and tag overlap, so the next step stays relevant instead of wandering off into the weeds.</p>
    </section>

    <section class="faq card" aria-label="Frequently asked questions">
      <h2>FAQ</h2>
      <div class="ebook-faq-list">
        {render_faq_markup(book)}
      </div>
    </section>

    <section class="jh-journey-panel">
      <h2>Keep exploring the Jonathan Harris AI library</h2>
      <p>Use the links below to carry on browsing the wider catalogue, the glossary, comparisons, podcast coverage, or a related guide.</p>
      <div class="jh-journey-actions">
        {book_semantic_journey_links(book)}
      </div>
    </section>
  </div>
</main>
<script defer="" src="/assets/js/related-books.min.js"></script>
{footer}
<script defer="" src="/assets/js/site-ui.min.js"></script>
</body>
</html>
'''



def render_catalogue_card(book: Dict[str, Any], cta_copy: str) -> str:
    tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in book.get("tags", [])[:4])
    return f'''
<article class="card ebook-card" aria-label="{html.escape(book['title'])}">
  {render_cover_image(book, class_name="cover")}
  <h2>{html.escape(book['title'])}</h2>
  <div class="topic-chip-wrap"><span class="topic-chip">{html.escape(book['filter'])}</span></div>
  <p>{html.escape(book['short'])}</p>
  <div class="tags">{tags}</div>
  <div class="book-avail"><span class="book-avail__badge">🛍️ Available on Amazon Kindle</span></div>
  <details class="more">
    <summary aria-expanded="false">More details</summary>
    <div class="meta">{html.escape(cta_copy)}</div>
    <div class="actions">
      <a class="button secondary" href="/ebooks/{html.escape(book['slug'])}/">Full description</a>
      <a class="button" href="{html.escape(book['buy_route'])}">View on Amazon</a>
    </div>
  </details>
</article>'''.strip()



def render_topic_hub_links(books: List[Dict[str, Any]]) -> str:
    topics = sorted({(book["topic"], book["topic_slug"]) for book in books}, key=lambda item: item[0].lower())
    return "\n".join(f'<a href="/catalogue/{slug}/">{html.escape(name)}</a>' for name, slug in topics[:12])



def render_ebooks_index(books: List[Dict[str, Any]]) -> str:
    header = render_header()
    footer = render_footer()
    canonical = f"{SITE_URL}/ebooks/"
    description = f"Ebook catalogue: {len(books)} AI titles by Jonathan Harris covering industries, ethics, safety, and practical adoption."
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Jonathan Harris eBooks library",
        "itemListElement": [
            {"@type": "ListItem", "position": idx, "url": book["canonical_url"], "name": book["title"]}
            for idx, book in enumerate(books, start=1)
        ],
    }
    static_cards = "\n".join(render_catalogue_card(book, catalogue_cta_copy(book["topic"])) for book in books)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>
<link href="https://images.jonathan-harris.online" rel="preconnect"/>
<link href="https://assets.jonathan-harris.online" rel="preconnect"/>
<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport"/>
<title>AI eBooks Catalogue | Jonathan Harris</title>
<meta content="{description}" name="description"/>
<meta content="index,follow" name="robots"/>
<meta content="{description}" name="ai:summary"/>
<meta content="#0D1420" name="theme-color"/>
{SHARED_INTER_FONT_HEAD_BLOCK}
<link as="style" href="/assets/css/site.css" rel="preload"/>
<link href="/assets/css/site.css" rel="stylesheet"/>


<link href="/assets/css/ebook-template.css" rel="stylesheet"/>
<meta content="GB" name="geo.region"/>
<meta content="website" property="og:type"/>
<meta content="Jonathan Harris eBooks" property="og:site_name"/>
<meta content="{canonical}" property="og:url"/>
<meta content="AI eBooks Catalogue | Jonathan Harris" property="og:title"/>
<meta content="{description}" property="og:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" property="og:image"/>
<meta content="Jonathan Harris site logo" property="og:image:alt"/>
<meta content="1200" property="og:image:width"/>
<meta content="630" property="og:image:height"/>
<meta content="@jonathan_harris_01" name="twitter:site"/>
<meta content="@jonathan_harris_01" name="twitter:creator"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="AI eBooks Catalogue | Jonathan Harris" name="twitter:title"/>
<meta content="{description}" name="twitter:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" name="twitter:image"/>
<meta content="AI ebook catalogue and practical AI guide" name="ai-role"/>
<meta content="Curious professionals, entrepreneurs, and non-technical readers who want practical AI insight" name="ai-target-audience"/>
<meta content="Plain-English, practical, sceptical, no-hype" name="ai-style"/>
<meta content="search=y, train-ai=y" name="content-usage"/>
<link href="{canonical}" rel="canonical"/>
<link href="{canonical}" hreflang="en" rel="alternate"/>
<link href="{canonical}" hreflang="x-default" rel="alternate"/>
<script type="application/ld+json">{json_script(item_list)}</script>
<script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script>
<script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script>
<link href="https://cdn-cookieyes.com" rel="dns-prefetch"/>
<link href="https://tracker.metricool.com" rel="dns-prefetch"/>
<script async="" id="cookieyes" src="https://cdn-cookieyes.com/client_data/c981d18033783598d2216add/script.js" type="text/javascript"></script>
<script defer="" src="/assets/js/consent-managed-scripts.js"></script>
</head>
<body class="ebooks-catalogue">
{header}
<div aria-hidden="false" class="page-loader is-active" id="pageLoader">
  <div aria-label="Preparing page" aria-live="polite" class="loader-card" role="status">
    <div aria-hidden="true" class="spinner"></div>
  </div>
</div>
<header class="hero ebook-hero" role="region" aria-label="eBook catalogue intro">
  <div class="wrap">
    <img alt="Jonathan Harris site logo" class="logo-plain" height="120" src="https://images.jonathan-harris.online/site-logo" width="120"/>
    <h1>AI eBooks Catalogue</h1>
    <p>Browse all {len(books)} titles from the ebook library. Each book page keeps the summary, FAQ, and Amazon route in one clear place.</p>
  </div>
</header>
<main class="main" id="main" role="main" aria-label="eBook catalogue">
  <div class="wrap">
    <section class="card ebook-index-intro">
      <h2>Find the right title without the faff</h2>
      <p>Search the catalogue, filter by topic, and jump straight into a book page with the full description, FAQ, and buy link in one place.</p>
      <div class="jh-topic-links">
        {render_topic_hub_links(books)}
      </div>
    </section>

    <section class="toolbar" aria-label="Catalogue controls">
      <input aria-label="Search books" class="search" id="search" placeholder="Search by title, topic, or keyword" type="search"/>
      <div class="chips" id="chips"></div>
    </section>

    <p class="meta ebook-count" id="count">{len(books)} of {len(books)} books</p>

    <section aria-label="eBook grid" class="grid" id="booksGrid">
      {static_cards}
    </section>

    <nav aria-label="Pagination" class="pager u-s24" id="pager">
      <button class="button secondary" id="prevPage" type="button">Previous</button>
      <span class="meta" id="pageInfo"></span>
      <button class="button" id="nextPage" type="button">Next</button>
    </nav>

    <section class="jh-journey-panel">
      <h2>Keep exploring the wider library</h2>
      <p>Every ebook page links back into the catalogue, but you can also hop out to the podcast, newsletter, or topic guides when you want the broader view.</p>
      <div class="jh-journey-actions">
        <a href="/podcast/">Listen to the podcast</a>
        <a href="/newsletter/">Join the newsletter</a>
        <a href="/topics/">Explore topic guides</a>
      </div>
    </section>
  </div>
</main>
{footer}
<script defer="" src="/assets/js/books.min.js"></script>
<script defer="" src="/assets/js/site-ui.min.js"></script>
</body>
</html>
'''



def render_topic_page(topic: str, books: List[Dict[str, Any]]) -> str:
    header = render_header()
    footer = render_footer()
    cards = "\n".join(render_catalogue_card(book, catalogue_cta_copy(topic)) for book in books)
    topic_slug = slugify(topic)
    canonical = f"{SITE_URL}/catalogue/{topic_slug}/"
    description = catalogue_meta_description(topic)
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"{topic} books by Jonathan Harris",
        "itemListElement": [
            {"@type": "ListItem", "position": idx, "url": book["canonical_url"], "name": book["title"]}
            for idx, book in enumerate(books, start=1)
        ],
    }
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>
<link href="https://images.jonathan-harris.online" rel="preconnect"/>
<link href="https://assets.jonathan-harris.online" rel="preconnect"/>
<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport"/>
<title>{html.escape(topic)} AI Books | Jonathan Harris</title>
<meta content="{html.escape(description)}" name="description"/>
<meta content="index,follow" name="robots"/>
<meta content="#0D1420" name="theme-color"/>
{SHARED_INTER_FONT_HEAD_BLOCK}
<link as="style" href="/assets/css/site.css" rel="preload"/>
<link href="/assets/css/site.css" rel="stylesheet"/>


<link href="/assets/css/ebook-template.css" rel="stylesheet"/>
<meta content="GB" name="geo.region"/>
<meta content="website" property="og:type"/>
<meta content="{canonical}" property="og:url"/>
<meta content="{html.escape(topic)} AI Books | Jonathan Harris" property="og:title"/>
<meta content="{html.escape(description)}" property="og:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" property="og:image"/>
<meta content="Jonathan Harris site logo" property="og:image:alt"/>
<meta content="@jonathan_harris_01" name="twitter:site"/>
<meta content="@jonathan_harris_01" name="twitter:creator"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="{html.escape(topic)} AI Books | Jonathan Harris" name="twitter:title"/>
<meta content="{html.escape(description)}" name="twitter:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" name="twitter:image"/>
<link href="{canonical}" rel="canonical"/>
<link href="{canonical}" hreflang="en" rel="alternate"/>
<link href="{canonical}" hreflang="x-default" rel="alternate"/>
<script type="application/ld+json">{json_script(item_list)}</script>
<script type="application/ld+json">{json_script(build_topic_breadcrumb_schema(topic))}</script>
<script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script>
<script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script>
</head>
<body class="ebooks-catalogue topic-catalogue">
{header}
<header class="hero ebook-hero" role="region" aria-label="Topic catalogue intro">
  <div class="wrap">
    <img alt="Jonathan Harris site logo" class="logo-plain" height="120" src="https://images.jonathan-harris.online/site-logo" width="120"/>
    <h1>{html.escape(topic)} AI Books</h1>
    <p>{html.escape(topic_intro(topic))}</p>
  </div>
</header>
<main class="main" id="main" role="main">
  <div class="wrap ebook-shell">
    <nav aria-label="Breadcrumb" class="breadcrumbs">{render_topic_breadcrumbs(topic)}</nav>
    <section class="card ebook-index-intro">
      <h2>{category_question_heading(topic)}</h2>
      <p>{html.escape(category_answer_first_copy(topic, books))}</p>
    </section>
    <section class="card ebook-index-intro">
      <h2>What this category covers</h2>
      <p>{html.escape(category_scope_copy(topic, books))}</p>
    </section>
    <section class="card ebook-index-intro">
      <h2>Best place to start</h2>
      <p>{category_best_start_copy(topic, books)}</p>
    </section>
    <section class="faq card" aria-label="Category questions">
      <h2>Common questions</h2>
      <div class="ebook-faq-list">
        {category_faq_markup(topic, books)}
      </div>
    </section>
    <section class="related-books card">
      <h2>Keep exploring this topic</h2>
      <ul>
        {category_internal_links(topic, books)}
      </ul>
    </section>
    <section class="card ebook-index-intro">
      <h2>{len(books)} title{'s' if len(books) != 1 else ''} in this topic</h2>
      <p>{html.escape(catalogue_intro_copy(topic))}</p>
    </section>
    <section aria-label="Topic book grid" class="grid" id="booksGrid">
      {cards}
    </section>
  </div>
</main>
{footer}
<script defer="" src="/assets/js/site-ui.min.js"></script>
</body>
</html>
'''


def render_topics_index(topic_map: Dict[str, List[Dict[str, Any]]]) -> str:
    header = render_header()
    footer = render_footer()
    canonical = f"{SITE_URL}/topics/"
    description = topics_index_meta_description()
    cards = []
    for topic in sorted(topic_map, key=str.lower):
        slug = slugify(topic)
        cards.append(
            f'<article class="card topic-card"><h2><a href="/catalogue/{slug}/">{html.escape(topic)}</a></h2><p>{len(topic_map[topic])} title{'s' if len(topic_map[topic]) != 1 else ''}</p></article>'
        )
    cards_html = "\n".join(cards)
    guide_cards_html = topic_guide_cards_markup()
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>
<link href="https://images.jonathan-harris.online" rel="preconnect"/>
<link href="https://assets.jonathan-harris.online" rel="preconnect"/>
<meta content="width=device-width, initial-scale=1, viewport-fit=cover" name="viewport"/>
<title>AI Topics | Jonathan Harris</title>
<meta content="{description}" name="description"/>
<meta content="index,follow" name="robots"/>
<meta content="#0D1420" name="theme-color"/>
{SHARED_INTER_FONT_HEAD_BLOCK}
<link as="style" href="/assets/css/site.css" rel="preload"/>
<link href="/assets/css/site.css" rel="stylesheet"/>


<link href="/assets/css/ebook-template.css" rel="stylesheet"/>
<meta content="GB" name="geo.region"/>
<meta content="website" property="og:type"/>
<meta content="{canonical}" property="og:url"/>
<meta content="AI Topics | Jonathan Harris" property="og:title"/>
<meta content="{description}" property="og:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" property="og:image"/>
<meta content="Jonathan Harris site logo" property="og:image:alt"/>
<meta content="@jonathan_harris_01" name="twitter:site"/>
<meta content="@jonathan_harris_01" name="twitter:creator"/>
<meta content="summary_large_image" name="twitter:card"/>
<meta content="AI Topics | Jonathan Harris" name="twitter:title"/>
<meta content="{description}" name="twitter:description"/>
<meta content="https://images.jonathan-harris.online/site-logo" name="twitter:image"/>
<link href="{canonical}" rel="canonical"/>
<link href="{canonical}" hreflang="en" rel="alternate"/>
<link href="{canonical}" hreflang="x-default" rel="alternate"/>
<script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script>
<script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script>
</head>
<body class="ebooks-catalogue topics-index">
{header}
<header class="hero ebook-hero" role="region">
  <div class="wrap">
    <img alt="Jonathan Harris site logo" class="logo-plain" height="120" src="https://images.jonathan-harris.online/site-logo" width="120"/>
    <h1>Explore AI topics</h1>
    <p>Use this hub as the truthful cluster map for the site: topic guides for the educational layer, catalogue pages for the book shelves, and cleaner routes into glossary, comparisons, podcast, and newsletter coverage.</p>
  </div>
</header>
<main class="main" id="main" role="main">
  <div class="wrap ebook-shell">
    <section class="card ebook-index-intro">
      <h2>How to use this page</h2>
      <p>Start with a topic guide if you want the plain-English explanation first. Use the catalogue grid if you already know the lane you care about and want the relevant books without playing hide-and-seek with broken routes. Charming hobby, broken discovery paths. Terrible publishing strategy.</p>
    </section>
    <section class="card ebook-index-intro">
      <h2>Topic guides</h2>
      <p>These pages carry the educational layer of the estate and are meant to explain the subject before the catalogue starts making commercial suggestions.</p>
    </section>
    <section class="grid topic-grid" aria-label="Topic guides">{guide_cards_html}</section>
    <section class="card ebook-index-intro u-mt40">
      <h2>Browse by catalogue</h2>
      <p>These category pages group the books by subject and now work as real landing pages rather than one-book shelves wearing a fake moustache.</p>
    </section>
    <section class="grid topic-grid" aria-label="Catalogue pages">{cards_html}</section>
    <section class="related-books card">
      <h2>Keep exploring the wider AI estate</h2>
      <ul>
        {topics_index_support_links()}
      </ul>
    </section>
  </div>
</main>
{footer}
<script defer="" src="/assets/js/site-ui.min.js"></script>
</body>
</html>
'''


def path_to_public_url(relative_path: Path) -> str:
    if relative_path == Path("index.html"):
        return f"{SITE_URL}/"
    if relative_path.name == "index.html":
        return f"{SITE_URL}/{relative_path.parent.as_posix()}/"
    return f"{SITE_URL}/{relative_path.as_posix()}"



def html_declares_noindex(file_path: Path) -> bool:
    if file_path.suffix.lower() != ".html" or not file_path.exists():
        return False
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return bool(re.search(r"<meta[^>]+(?:name=[\"']robots[\"'][^>]*content=[\"'][^\"']*noindex|content=[\"'][^\"']*noindex[^>]*name=[\"']robots[\"'])", text, re.I))



def build_public_route_registry(books: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    governed_lastmod = normalise_lastmod(governed_generated_utc(books))
    generated_paths = {Path("ebooks/index.html"), Path("topics/index.html")}
    generated_paths.update(Path("catalogue") / slugify(book["topic"]) / "index.html" for book in books)
    book_paths = {Path("ebooks") / book["slug"] / "index.html": book for book in books}
    excluded_paths = {
        Path("404.html"),
        Path("assets/partials/header.html"),
        Path("assets/partials/footer.html"),
        Path("scripts/templates/blog-post.html"),
    }

    routes: List[Dict[str, str]] = []
    for file_path in sorted(ROOT.rglob("*.html")):
        if "node_modules" in file_path.parts:
            continue
        relative_path = file_path.relative_to(ROOT)
        if relative_path in excluded_paths:
            continue
        if relative_path.parts and relative_path.parts[0] == "scripts":
            continue
        if html_declares_noindex(file_path):
            continue

        if relative_path in book_paths:
            lastmod = normalise_lastmod(book_paths[relative_path].get("dateModified") or book_paths[relative_path].get("datePublished") or governed_lastmod)
        else:
            lastmod = governed_lastmod

        routes.append({
            "path": f"/{relative_path.as_posix()}",
            "loc": path_to_public_url(relative_path),
            "lastmod": lastmod,
        })
    return routes



def build_sitemap_xml(books: List[Dict[str, Any]]) -> str:
    urls = []
    for route in build_public_route_registry(books):
        urls.append(
            "  <url>\n"
            f"    <loc>{html.escape(route['loc'])}</loc>\n"
            f"    <lastmod>{html.escape(route['lastmod'])}</lastmod>\n"
            "  </url>"
        )
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + "\n".join(urls) + "\n</urlset>\n"



def build_robots_txt() -> str:
    return "\n".join([
        "# Robots rules (generated source snapshot)",
        f"# Canonical publication target: {EXTERNAL_CRAWLER_FILES['robots']}",
        f"# Canonical sitemap target: {EXTERNAL_CRAWLER_FILES['sitemap']}",
        "",
        "User-agent: *",
        "Allow: /",
        "",
        "# Explicit AI crawler allowances",
        "User-agent: GPTBot",
        "Allow: /",
        "User-agent: Google-Extended",
        "Allow: /",
        "User-agent: ClaudeBot",
        "Allow: /",
        "User-agent: CCBot",
        "Allow: /",
        "User-agent: Applebot",
        "Allow: /",
        "",
        "# Sitemap",
        f"Sitemap: {EXTERNAL_CRAWLER_FILES['sitemap']}",
        "",
    ])



def build_llms_txt(books: List[Dict[str, Any]]) -> str:
    lines = [
        "# Jonathan Harris ebook library",
        f"# Canonical publication target: {EXTERNAL_CRAWLER_FILES['llms']}",
        "# Canonical ebook routes only",
        f"Homepage: {SITE_URL}/ebooks/",
        "",
        "## Canonical books",
    ]
    for book in books:
        lines.append(f"- {book['title']}: {book['canonical_url']}")
    lines.append("")
    return "\n".join(lines)

def build_crawler_snapshot_payloads(books: List[Dict[str, Any]]) -> Dict[str, str]:
    return {
        CRAWLER_SNAPSHOT_FILENAMES["robots"]: build_robots_txt(),
        CRAWLER_SNAPSHOT_FILENAMES["sitemap"]: build_sitemap_xml(books),
        CRAWLER_SNAPSHOT_FILENAMES["llms"]: build_llms_txt(books),
    }



def build_crawler_snapshot_paths(books: List[Dict[str, Any]]) -> Dict[Path, str]:
    payloads = build_crawler_snapshot_payloads(books)
    return {
        CRAWLER_SNAPSHOTS_DIR / name: content
        for name, content in payloads.items()
    }



def build_published_crawler_paths(books: List[Dict[str, Any]]) -> Dict[Path, str]:
    payloads = build_crawler_snapshot_payloads(books)
    sitemap_payload = payloads[CRAWLER_SNAPSHOT_FILENAMES["sitemap"]]
    return {
        ROOT / "robots.txt": payloads[CRAWLER_SNAPSHOT_FILENAMES["robots"]],
        ROOT / "sitemap.xml": sitemap_payload,
        ROOT / "llms.txt": payloads[CRAWLER_SNAPSHOT_FILENAMES["llms"]],
    }




def build_route_manifest(books: List[Dict[str, Any]]) -> Dict[str, Any]:
    manifest_books = []
    for book in books:
        manifest_books.append({
            "slug": book["slug"],
            "title": book["title"],
            "canonical": {
                "path": f"/ebooks/{book['slug']}/",
                "url": book["canonical_url"],
            },
            "buy": {
                "path": book["buy_route"],
                "full_url": book["buy_route_full"],
                "target": book["buy_url"],
            },
            "topic_page": book["topic_url"],
            "legacy_routes": [
                f"/book/{book['slug']}/",
                f"/book/{book['slug']}/buy-now",
                f"/ebooks/{book['slug']}/detail",
                f"/ebooks/{book['slug']}/detail.html",
                f"/ebooks/{book['slug']}/details.html",
            ],
            "legacy_alias_url": book.get("legacy_alias_url") or "",
            "domain_redirect_families": [
                "books.jonathan-harris.online",
                "ebooks.jonathan-harris.online",
            ],
        })

    return {
        "generated_utc": governed_generated_utc(books),
        "base_url": SITE_URL,
        "ebook_count": len(books),
        "external_crawler_files": EXTERNAL_CRAWLER_FILES,
        "host_redirect_files": {
            "books_domain": "_redirects.books-domain",
            "ebooks_domain": "_redirects.ebooks-domain",
        },
        "malformed_slug_fixes": MALFORMED_SLUG_FIXES,
        "ebooks": manifest_books,
    }


def build_books_domain_redirects() -> str:
    return "\n".join([
        "# ============================================================",
        "# books.jonathan-harris.online — Domain redirects (generated)",
        "# Redirect governed legacy book paths to the main domain",
        "# ============================================================",
        "",
        "# Canonical host (no www)",
        "https://www.books.jonathan-harris.online/*  https://books.jonathan-harris.online/:splat  301",
        "",
        "# Root → ebooks catalogue",
        "/  https://jonathan-harris.online/ebooks/  301",
        "",
        "# Canonical and legacy ebook families",
        "/ebooks          https://jonathan-harris.online/ebooks/                  301",
        "/ebooks/         https://jonathan-harris.online/ebooks/                  301",
        "/ebooks/*        https://jonathan-harris.online/ebooks/:splat           301",
        "/book            https://jonathan-harris.online/ebooks/                  301",
        "/book/           https://jonathan-harris.online/ebooks/                  301",
        "/book/*          https://jonathan-harris.online/ebooks/:splat           301",
        "/category/*      https://jonathan-harris.online/catalogue/:splat        301",
        "/catalogue/*     https://jonathan-harris.online/catalogue/:splat        301",
        "/topics/*        https://jonathan-harris.online/topics/:splat           301",
        "/author          https://jonathan-harris.online/bio/                    301",
        "/author/         https://jonathan-harris.online/bio/                    301",
        "/author/*        https://jonathan-harris.online/bio/                    301",
        "",
        "# Crawler files resolve on the main domain",
        f"/robots.txt     {EXTERNAL_CRAWLER_FILES['robots']}   301",
        f"/sitemap.xml    {EXTERNAL_CRAWLER_FILES['sitemap']}  301",
        f"/site-map.xml   {EXTERNAL_CRAWLER_FILES['sitemap']}  301",
        "",
        "# Catch-all",
        "/*  https://jonathan-harris.online/:splat  301",
        "",
    ])


def build_ebooks_domain_redirects() -> str:
    return "\n".join([
        "# ============================================================",
        "# ebooks.jonathan-harris.online — Domain redirects (generated)",
        "# Redirect governed ebook and discovery paths to the main domain",
        "# ============================================================",
        "",
        "# Canonical host (no www)",
        "https://www.ebooks.jonathan-harris.online/*  https://ebooks.jonathan-harris.online/:splat  301",
        "",
        "# Root → ebooks catalogue",
        "/          https://jonathan-harris.online/ebooks/  301",
        "/ebooks    https://jonathan-harris.online/ebooks/  301",
        "/ebooks/   https://jonathan-harris.online/ebooks/  301",
        "",
        "# Old paths → new site",
        "/book         https://jonathan-harris.online/ebooks/             301",
        "/book/        https://jonathan-harris.online/ebooks/             301",
        "/book/*       https://jonathan-harris.online/ebooks/:splat       301",
        "/catalogue/*  https://jonathan-harris.online/catalogue/:splat    301",
        "/category/*   https://jonathan-harris.online/catalogue/:splat    301",
        "/author       https://jonathan-harris.online/bio/                301",
        "/author/      https://jonathan-harris.online/bio/                301",
        "/author/*     https://jonathan-harris.online/bio/                301",
        "/topics/*     https://jonathan-harris.online/topics/:splat       301",
        "/glossary/*   https://jonathan-harris.online/glossary/:splat     301",
        "/api/*        https://jonathan-harris.online/api/:splat          301",
        "",
        "# Crawler files resolve on the main domain",
        f"/robots.txt   {EXTERNAL_CRAWLER_FILES['robots']}  301",
        f"/sitemap.xml  {EXTERNAL_CRAWLER_FILES['sitemap']}  301",
        f"/site-map.xml {EXTERNAL_CRAWLER_FILES['sitemap']}  301",
        "",
        "# Catch-all",
        "/*  https://jonathan-harris.online/:splat  301",
        "",
    ])


def build_derivatives(books: List[Dict[str, Any]]) -> None:
    public_records = [book_to_public_record(book) for book in books]
    write_json(EBOOKS_DIR / "books.json", public_records)
    write_json(ROOT / "assets" / "js" / "books.json", public_records)
    write_json(ROOT / "api" / "v1" / "books.json", public_records)
    write_json(ROOT / "api" / "v1" / "featured-book.json", build_featured_book_payload(public_records))

    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Jonathan Harris eBooks Catalogue",
        "home_page_url": f"{SITE_URL}/ebooks/",
        "feed_url": f"{SITE_URL}/feed.json",
        "items": [
            {
                "id": book["canonical_url"],
                "url": book["canonical_url"],
                "title": book["title"],
                "summary": book["short"],
                "image": book["cover"],
                "tags": book["tags"],
            }
            for book in books
        ],
    }
    write_json(ROOT / "feed.json", feed)

    generated_utc = governed_generated_utc(books)

    entity_map = {
        "generated_utc": generated_utc,
        "person": {"id": f"{SITE_URL}/#person", "name": SITE_NAME},
        "podcast": {"title": "Turing’s Torch: AI Weekly", "url": f"{SITE_URL}/podcast/"},
        "books": [
            {
                "title": book["title"],
                "slug": book["slug"],
                "url": book["canonical_url"],
                "topic": book["topic"],
                "tags": book["tags"],
                "identifier": book["identifier"],
            }
            for book in books
        ],
    }
    write_json(ROOT / "ai" / "entity-map.json", entity_map)

    llm_index = {
        "generated_utc": generated_utc,
        "books": [
            {
                "title": book["title"],
                "slug": book["slug"],
                "url": f"/ebooks/{book['slug']}/",
                "summary": book["short"],
                "topic": book["topic"],
                "tags": book["tags"],
                "keywords": [clean_paragraph(k).lower() for k in book["keywords"]],
                "buy_url": book["buy_url"],
                "buy_target_url": book["buy_url"],
                "buy_route": book["buy_route"],
                "buy_route_full": book["buy_route_full"],
                "cover": book["cover"],
                "identifier": book["identifier"],
                "entity_id": f"{book['canonical_url']}#book",
                "asin": book["asin"],
                "pages": book["pages"],
                "datePublished": book["datePublished"],
                "dateModified": book.get("dateModified") or infer_build_timestamp(),
                "related_slugs": book.get("related_slugs", []),
            }
            for book in books
        ],
        "topic_authority_pages": [f"/catalogue/{slugify(topic)}/" for topic in sorted({book['topic'] for book in books})],
    }
    write_json(ROOT / "llm-index.json", llm_index)

    write_json(EBOOKS_DIR / "url-manifest.json", build_route_manifest(books))
    (EBOOKS_DIR / "index.html").write_text(render_ebooks_index(books), encoding="utf-8")

    topic_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for book in books:
        topic_map[book["topic"]].append(book)
    for topic, topic_books in topic_map.items():
        topic_dir = CATALOGUE_DIR / slugify(topic)
        topic_dir.mkdir(parents=True, exist_ok=True)
        (topic_dir / "index.html").write_text(render_topic_page(topic, topic_books), encoding="utf-8")
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    (TOPICS_DIR / "index.html").write_text(render_topics_index(topic_map), encoding="utf-8")

    for file_path, content in build_crawler_snapshot_paths(books).items():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    for file_path, content in build_published_crawler_paths(books).items():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    legacy_crawler_duplicates = [
        ROOT / "site-map.xml",
        ROOT / "Sitemap.xml",
        ROOT / "sitemap (1).xml",
        CRAWLER_SNAPSHOTS_DIR / "site-map.xml",
    ]
    for legacy_path in legacy_crawler_duplicates:
        if legacy_path.exists():
            legacy_path.unlink()

    write_json(CRAWLER_CHECKSUMS_PATH, build_crawler_checksums(books))



def build_book_files(books: List[Dict[str, Any]]) -> None:
    for book in books:
        book_dir = EBOOKS_DIR / book["slug"]
        book_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "title": book["title"],
            "slug": book["slug"],
            "description": book["description"],
            "short_description": book["short"],
            "topic": book["topic"],
            "tags": book["tags"],
            "cover": book["cover"],
            "image": book["cover"],
            "buy_url": book["buy_url"],
            "buy_route": book["buy_route"],
            "pages": book["pages"],
            "asin": book["asin"],
            "datePublished": book["datePublished"],
        "dateModified": book.get("dateModified") or infer_build_timestamp(),
            "author": book["author"],
            "tone": book["tone"],
            "audience": book["audience"],
            "canonical_url": book["canonical_url"],
            "identifier": book["identifier"],
        }
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "@id": f"{book['canonical_url']}#faq",
            "mainEntity": book["faq"],
        }
        summary_md = "\n".join([
            f"# {book['title']}",
            "",
            "## Summary",
            "",
            book["summary"],
            "",
            "## What this book covers",
            "",
            book["what_this_book_covers"],
            "",
            "## Who this book is for",
            "",
            book["who_for"],
            "",
            "## What you’ll learn",
            "",
            *[f"- {item}" for item in book["what_youll_learn"]],
            "",
            "## Why it matters",
            "",
            book["why_it_matters"],
            "",
            "## Topics and tags",
            "",
            f"- Topic: {book['topic']}",
            f"- Tags: {', '.join(book['tags'])}",
            f"- Length: {book['pages']} pages",
            "",
            "## Buy",
            "",
            f"- {book['buy_url']}",
            "",
        ])
        write_json(book_dir / "metadata.json", metadata)
        write_json(book_dir / "faq-schema.json", faq_schema)
        (book_dir / "structured-summary.md").write_text(summary_md, encoding="utf-8")
        (book_dir / "index.html").write_text(render_book_page(book, books), encoding="utf-8")



def build_redirect_block(books: List[Dict[str, Any]]) -> str:
    lines = ["# 6A) Branded buy-now redirects"]
    for book in books:
        lines.append(f"{book['buy_route']}   {book['buy_url']}   302")
        lines.append(f"/book/{book['slug']}/buy-now   {book['buy_route']}   301")
    return "\n".join(lines)



def sync_redirects(books: List[Dict[str, Any]]) -> None:
    primary_path = ROOT / "_redirects"
    mirror_path = ROOT / "_redirects.txt"
    block = build_redirect_block(books)
    pattern = re.compile(r"# 6A\) Branded buy-now redirects.*?(?=\n# 7\) CANONICAL: old /book URLs permanently redirect to /ebooks)", re.S)
    legacy_anchor = "# retire legacy detail routes to the canonical ebook page\n"
    malformed_lines = [f"{item['source']}   {item['target']}  301" for item in MALFORMED_SLUG_FIXES]
    crawler_alias_anchor = "# SEO files: serve governed crawler assets from the primary domain root\n"
    crawler_alias_lines = [
        "/robot.txt    /robots.txt   301",
        "/Sitemap.xml  /sitemap.xml  301",
        "/site-map.xml  /sitemap.xml  301",
    ]
    crawler_alias_pattern = re.compile(r"# SEO files: serve governed crawler assets from the primary domain root\n(?:[^#].*\n?)*", re.M)

    text = primary_path.read_text(encoding="utf-8")
    new_text, count = pattern.subn(block + "\n", text)
    if count != 1:
        raise ValueError(f"Could not replace branded redirect block in {primary_path}")
    for line in LEGACY_DETAIL_REDIRECT_LINES + malformed_lines:
        if line not in new_text:
            if legacy_anchor not in new_text:
                raise ValueError(f"Could not find legacy detail redirect anchor in {primary_path}")
            new_text = new_text.replace(legacy_anchor, legacy_anchor + line + "\n", 1)
    alias_block = crawler_alias_anchor + "\n".join(crawler_alias_lines) + "\n"
    if crawler_alias_anchor not in new_text:
        raise ValueError(f"Could not find crawler alias anchor in {primary_path}")
    new_text, alias_count = crawler_alias_pattern.subn(alias_block, new_text, count=1)
    if alias_count != 1:
        raise ValueError(f"Could not refresh crawler alias block in {primary_path}")

    primary_path.write_text(new_text, encoding="utf-8")
    mirror_path.write_text(new_text, encoding="utf-8")
    (ROOT / "_redirects.books-domain").write_text(build_books_domain_redirects(), encoding="utf-8")
    (ROOT / "_redirects.ebooks-domain").write_text(build_ebooks_domain_redirects(), encoding="utf-8")


def ensure_css_file() -> None:
    css = """
.ebook-shell{display:grid;gap:20px}
.ebook-hero .muted{opacity:.88}
.ebook-section h2,.related-books h2,.faq h2,.ebook-index-intro h2{margin-top:0}
.quick-facts ul.ebook-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 20px;list-style:none;padding:0;margin:0}
.quick-facts li{color:#374151}
.ebook-showcase{display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:20px;align-items:start}
.ebook-showcase__media,.ebook-showcase__content{height:100%}
.ebook-showcase__cover{background:#0D1420}
.ebook-showcase__lead{font-size:1.03rem;line-height:1.75;color:#111827}
.ebook-showcase__subhead,.ebook-showcase__note{color:#4B5563}
.ebook-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.ebook-inline-actions{display:flex;flex-wrap:wrap;gap:12px;margin-top:18px}
.ebook-inline-actions a{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:10px 14px;border-radius:999px;text-decoration:none;font-weight:700;border:1px solid rgba(15,23,42,.12);background:#fff;color:#111827}
.ebook-signal-list{list-style:none;padding:0;margin:16px 0 0;display:grid;gap:10px}
.ebook-signal-list li{color:#111827;font-weight:600}
.ebook-theme-pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.ebook-pill{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#EEF2FF;border:1px solid rgba(79,70,229,.18);color:#312E81;font-size:.9rem;font-weight:700}
.ebook-pill--dark{background:#111827;color:#E5E7EB;border-color:rgba(255,255,255,.12)}
.ebook-learn-list,.ebook-audience-list,.ebook-key-themes{margin:0;padding-left:20px;display:grid;gap:10px}
.ebook-section--accent{background:linear-gradient(180deg,#111827 0%,#0F172A 100%);color:#E5E7EB;border-color:rgba(255,255,255,.08)}
.ebook-section--accent h2{color:#fff}
.ebook-section--accent p,.ebook-section--accent li{color:#E5E7EB}
.related-books ul{list-style:none;padding:0;margin:0;display:grid;gap:12px}
.related-books li{display:flex;justify-content:space-between;gap:16px;align-items:baseline;padding:12px 0;border-bottom:1px solid rgba(15,23,42,.08)}
.related-books li:last-child{border-bottom:none;padding-bottom:0}
.related-books li span{font-size:.92rem;color:#6B7280}
.ebook-faq-list{display:grid;gap:12px}
.ebook-faq-item{border:1px solid rgba(15,23,42,.10);border-radius:14px;padding:0 14px;background:#F8FAFC}
.ebook-faq-item summary{cursor:pointer;font-weight:800;padding:14px 0;color:#111827}
.ebook-faq-item p{margin:0 0 14px;color:#374151}
.ebook-index-intro p{max-width:72ch}
.ebook-count{margin:6px 0 18px}
.pager{margin:24px 0 0;display:flex;align-items:center;justify-content:center;gap:14px}
.topic-chip-wrap{margin:2px 0 8px}
.topic-chip{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:#EEF2FF;color:#312E81;font-size:.88rem;font-weight:700;border:1px solid rgba(79,70,229,.18)}
.book-avail{margin:12px 0 0}
.book-avail__badge{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;background:#ECFDF5;color:#166534;border:1px solid rgba(22,101,52,.12);font-size:.88rem;font-weight:700}
.ebook-signal-grid,.topic-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.ebook-signal-card h3,.topic-card h2{margin-top:0}
.ebook-signal-card p,.topic-card p{margin:0;color:#4B5563}
.ebooks-catalogue .grid{grid-template-columns:repeat(3,minmax(0,1fr))}
@media (max-width:980px){
  .ebook-showcase{grid-template-columns:1fr}
  .quick-facts ul.ebook-facts,.ebook-signal-grid,.topic-grid{grid-template-columns:1fr}
  .ebooks-catalogue .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width:620px){
  .ebooks-catalogue .grid{grid-template-columns:1fr}
  .ebook-actions,.ebook-inline-actions{flex-direction:column}
  .ebook-actions .button,.pager .button,.ebook-inline-actions a{width:100%;text-align:center}
  .related-books li{flex-direction:column;align-items:flex-start}
}
""".strip() + "\n"
    EBOOK_TEMPLATE_CSS.write_text(css, encoding="utf-8")



def faq_is_semantically_relevant(book: Dict[str, Any]) -> bool:
    content_tokens = text_tokens(book["summary"]) | text_tokens(book["what_this_book_covers"])
    for item in book.get("what_youll_learn", []):
        content_tokens |= text_tokens(item)
    for item in book.get("faq", []):
        question = clean_paragraph(item.get("name", "")).lower()
        answer = clean_paragraph(item.get("acceptedAnswer", {}).get("text", ""))
        if any(term in question for term in ["how long", "format", "buy", "where can i get", "who is this book for", "who gets the most value", "how detailed is the coverage", "suitable for"]):
            continue
        if not (text_tokens(answer) & content_tokens):
            return False
    return True



def build_crawler_checksums(books: List[Dict[str, Any]]) -> Dict[str, Any]:
    generated_at = governed_generated_utc(books)
    files = build_crawler_snapshot_payloads(books)
    name_to_key = {value: key for key, value in CRAWLER_SNAPSHOT_FILENAMES.items()}
    return {
        "generated_utc": generated_at,
        "files": {
            name: {
                "url": EXTERNAL_CRAWLER_FILES[name_to_key[name]],
                "sha256": sha256_text(content),
            }
            for name, content in files.items()
        },
    }


def build_validation_report(
    errors: List[str],
    books: List[Dict[str, Any]],
    *,
    workbook_title_stats: Dict[str, int] | None = None,
    workbook_content_stats: Dict[str, int] | None = None,
) -> str:
    topics = Counter(book["topic"] for book in books)
    lines = [
        f"Validation run: {governed_generated_utc(books)}",
        f"Book count: {len(books)}",
        f"Topic count: {len(topics)}",
    ]
    if workbook_title_stats:
        lines.append(
            "Workbook title parity: "
            f"{workbook_title_stats['passed']}/{workbook_title_stats['checked']} passed, "
            f"{workbook_title_stats['mismatched']} mismatched"
        )
    if workbook_content_stats:
        lines.append(
            "Workbook content parity: "
            f"{workbook_content_stats['exact_matches']} exact field matches, "
            f"{workbook_content_stats['approved_transformations']} approved transformations, "
            f"{workbook_content_stats['mismatched']} mismatches across "
            f"{workbook_content_stats['checked_fields']} governed field checks"
        )
    lines.extend([
        "",
        "Topics:",
    ])
    for topic, count in sorted(topics.items(), key=lambda item: item[0].lower()):
        lines.append(f"- {topic}: {count}")
    lines.append("")
    if errors:
        lines.append(f"Status: FAILED ({len(errors)} issue(s))")
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("Status: PASSED")
        lines.append("- Route registry complete")
        lines.append("- Route manifest and host redirect coverage checks passed")
        lines.append("- Topic discovery pages exist for every book")
        lines.append("- Metadata and FAQ checks passed")
        lines.append("- Generated crawler snapshots and redirect governance checks passed")
    lines.append("")
    return "\n".join(lines)



def workbook_content_parity_audit(
    workbook_path: Path,
    books: List[Dict[str, Any]] | None = None,
) -> Tuple[List[str], Dict[str, int]]:
    if books is None:
        books = load_master()
    stats = {
        "books": 0,
        "checked_fields": 0,
        "exact_matches": 0,
        "approved_transformations": 0,
        "mismatched": 0,
        "missing_books": 0,
    }
    errors: List[str] = []

    order, workbook_map, workbook_content = parse_workbook(workbook_path, sanitise_content=False)
    master_by_slug = {book["slug"]: book for book in books}
    approved_normalisations = load_workbook_normalisations()

    if order != [book["slug"] for book in books]:
        errors.append("Workbook row order does not match the master record order.")

    for slug, workbook in workbook_map.items():
        stats["books"] += 1
        book = master_by_slug.get(slug)
        if not book:
            stats["missing_books"] += 1
            errors.append(f"Workbook contains slug not found in master record: {slug}")
            continue
        for workbook_field, master_field in [
            ("book_url", "canonical_url"),
            ("buy_url", "buy_url"),
            ("buy_route", "buy_route"),
            ("legacy_alias_url", "legacy_alias_url"),
            ("asin", "asin"),
            ("pages", "pages"),
            ("datePublished", "datePublished"),
            ("cover", "cover"),
        ]:
            if clean_paragraph(str(workbook.get(workbook_field, ""))) != clean_paragraph(str(book.get(master_field, ""))):
                errors.append(f"Workbook mismatch for {slug}: {workbook_field} does not match {master_field}.")

        content = workbook_content.get(slug)
        if not content:
            continue
        for workbook_field, master_field in WORKBOOK_GOVERNED_COPY_FIELDS:
            stats["checked_fields"] += 1
            workbook_value = clean_paragraph(str(content.get(workbook_field, "")))
            master_value = clean_paragraph(str(book.get(master_field, "")))
            if workbook_field in {"description", "summary"}:
                workbook_value = strip_pages_from_summary(workbook_value, book.get("pages"))
                master_value = strip_pages_from_summary(master_value, book.get("pages"))
            if workbook_value == master_value:
                stats["exact_matches"] += 1
                continue
            approved_entry = (approved_normalisations.get(slug) or {}).get(workbook_field)
            if approved_entry and approved_entry.get("raw") == workbook_value and approved_entry.get("approved") == master_value:
                stats["approved_transformations"] += 1
                continue
            stats["mismatched"] += 1
            errors.append(f"Workbook content mismatch for {slug}: {workbook_field} does not match {master_field}.")

    return errors, stats


def run_release_checks(books: List[Dict[str, Any]] | None = None, workbook_path: Path | None = None) -> List[str]:
    if books is None:
        books = load_master()
    errors: List[str] = []

    slugs = [book["slug"] for book in books]
    if not books:
        errors.append("Master record is empty.")
    if len(slugs) != len(set(slugs)):
        errors.append("Duplicate slugs found in the master record.")

    asins = [book["asin"] for book in books if book.get("asin")]
    if len(asins) != len(set(asins)):
        errors.append("Duplicate ASIN values found in the master record.")

    identifiers = [book["identifier"] for book in books if book.get("identifier")]
    if len(identifiers) != len(set(identifiers)):
        errors.append("Duplicate internal identifiers found in the master record.")
    errors.extend(content_role_validation_errors(books))
    errors.extend(broken_phrase_errors(books))
    errors.extend(related_book_contract_errors(books))

    legacy_data_files = [ROOT / "data" / "ebook-content-source.json", ROOT / "data" / "ebook-source-overrides.json"]
    for legacy_path in legacy_data_files:
        if legacy_path.exists():
            errors.append(f"Legacy data source still exists: {legacy_path.relative_to(ROOT)}")

    detail_files = list(EBOOKS_DIR.glob("**/detail.html")) + list(EBOOKS_DIR.glob("**/details.html"))
    if detail_files:
        errors.append("Legacy detail source files still exist under /ebooks/.")

    books_index_path = EBOOKS_DIR / "index.html"
    if not books_index_path.exists():
        errors.append("ebooks/index.html is missing.")
    else:
        index_html = books_index_path.read_text(encoding="utf-8")
        for book in books:
            if f'/ebooks/{book["slug"]}/' not in index_html:
                errors.append(f"ebooks/index.html does not link to /ebooks/{book['slug']}/.")

    seen_serp_titles: Dict[str, str] = {}
    duplicate_serp_titles: Dict[str, List[str]] = defaultdict(list)
    for book in books:
        page_path = EBOOKS_DIR / book["slug"] / "index.html"
        metadata_path = EBOOKS_DIR / book["slug"] / "metadata.json"
        faq_path = EBOOKS_DIR / book["slug"] / "faq-schema.json"
        if not page_path.exists():
            errors.append(f"Book page missing: {page_path}")
            continue
        text = page_path.read_text(encoding="utf-8")
        if f'<link href="{book["canonical_url"]}" rel="canonical"/>' not in text:
            errors.append(f"{book['slug']} is missing the expected canonical link.")
        if text.count('"@type":"FAQPage"') != 1:
            errors.append(f"{book['slug']} should emit exactly one FAQPage JSON-LD block.")
        if text.count('"@type":"Book"') != 1:
            errors.append(f"{book['slug']} should emit exactly one Book JSON-LD block.")
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        if not title_match:
            errors.append(f"{book['slug']} page head title is missing.")
        else:
            actual_title = clean_paragraph(html.unescape(re.sub(r"\s+", " ", title_match.group(1))))
            if not actual_title.endswith(f" | {SITE_NAME}"):
                errors.append(f"{book['slug']} page title is missing the brand suffix.")
            # March 2026 title policy: canonical ebook pages keep full workbook-governed titles.
            # Length is advisory here because the workbook remains the governing source of truth.
            if actual_title in seen_serp_titles and seen_serp_titles[actual_title] != book['slug']:
                duplicate_serp_titles[actual_title].extend([seen_serp_titles[actual_title], book['slug']])
            else:
                seen_serp_titles[actual_title] = book['slug']
        expected_social_title = html.escape(f"{book_meta_title(book)} | {SITE_NAME}", quote=False)
        for marker in [
            f'<meta content="{expected_social_title}" property="og:title"/>',
            f'<meta content="{expected_social_title}" name="twitter:title"/>',
        ]:
            if marker not in text:
                errors.append(f"{book['slug']} page social title drift detected.")
                break
        expected_desc = html.escape(book_meta_description(book), quote=True)
        for marker in [
            f'<meta content="{expected_desc}" name="description"/>',
            f'<meta content="{expected_desc}" property="og:description"/>',
            f'<meta content="{expected_desc}" name="twitter:description"/>',
        ]:
            if marker not in text:
                errors.append(f"{book['slug']} page head description drift detected.")
                break
        errors.extend(metadata_budget_errors(f"ebooks/{book['slug']}/index.html", text, max_description=155))
        errors.extend(template_contract_errors(text, book))
        if f'href="/book/{book["slug"]}/' in text or f'href="/ebooks/{book["slug"]}/detail' in text:
            errors.append(f"{book['slug']} still links to a retired route.")
        if not faq_is_semantically_relevant(book):
            errors.append(f"{book['slug']} has FAQ content that looks off-topic.")
        if not metadata_path.exists() or not faq_path.exists():
            errors.append(f"{book['slug']} is missing metadata.json or faq-schema.json.")
        else:
            metadata = read_json(metadata_path, default={}) or {}
            faq_schema = read_json(faq_path, default={}) or {}
            if metadata.get("canonical_url") != book["canonical_url"]:
                errors.append(f"{book['slug']} metadata.json canonical_url does not match the master record.")
            if metadata.get("buy_url") != book["buy_url"]:
                errors.append(f"{book['slug']} metadata.json buy_url does not match the master record.")
            if faq_schema.get("mainEntity") != book.get("faq"):
                errors.append(f"{book['slug']} faq-schema.json does not match the master record.")

        topic_page = ROOT / book["topic_url"].strip("/") / "index.html"
        if not book.get("topic_url") or not topic_page.exists():
            errors.append(f"{book['slug']} is missing a governed topic discovery page.")

    for title, slugs in duplicate_serp_titles.items():
        unique_slugs = sorted(set(slugs))
        if len(unique_slugs) > 1:
            errors.append(f"Duplicate ebook SERP title '{title}' used by: {', '.join(unique_slugs)}")

    discovery_pages = [
        {
            "path": EBOOKS_DIR / "index.html",
            "label": "ebooks/index.html",
            "required": [
                '<meta content="index,follow" name="robots"/>',
                '<meta content="website" property="og:type"/>',
                f'<meta content="{SITE_URL}/ebooks/" property="og:url"/>',
                '<meta content="AI eBooks Catalogue | Jonathan Harris" property="og:title"/>',
                '<meta content="summary_large_image" name="twitter:card"/>',
                '<meta content="AI eBooks Catalogue | Jonathan Harris" name="twitter:title"/>',
            ],
            "description": f"Ebook catalogue: {len(books)} AI titles by Jonathan Harris covering industries, ethics, safety, and practical adoption.",
            "max_description": 155,
        },
        {
            "path": TOPICS_DIR / "index.html",
            "label": "topics/index.html",
            "required": [
                '<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>',
                '<link href="https://images.jonathan-harris.online" rel="preconnect"/>',
                '<link href="https://assets.jonathan-harris.online" rel="preconnect"/>',
                '<meta content="#0D1420" name="theme-color"/>',
                '<meta content="index,follow" name="robots"/>',
                '<meta content="website" property="og:type"/>',
                f'<meta content="{SITE_URL}/topics/" property="og:url"/>',
                '<meta content="AI Topics | Jonathan Harris" property="og:title"/>',
                '<meta content="summary_large_image" name="twitter:card"/>',
                '<meta content="AI Topics | Jonathan Harris" name="twitter:title"/>',
            ],
            "description": topics_index_meta_description(),
            "min_description": 120,
            "max_description": 155,
        },
    ]
    for topic in sorted({book["topic"] for book in books}, key=str.lower):
        topic_slug = slugify(topic)
        discovery_pages.append({
            "path": CATALOGUE_DIR / topic_slug / "index.html",
            "label": f"catalogue/{topic_slug}/index.html",
            "required": [
                '<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>',
                '<link href="https://images.jonathan-harris.online" rel="preconnect"/>',
                '<link href="https://assets.jonathan-harris.online" rel="preconnect"/>',
                '<meta content="#0D1420" name="theme-color"/>',
                '<meta content="index,follow" name="robots"/>',
                '<meta content="website" property="og:type"/>',
                f'<meta content="{SITE_URL}/catalogue/{topic_slug}/" property="og:url"/>',
                f'<meta content="{html.escape(topic)} AI Books | Jonathan Harris" property="og:title"/>',
                '<meta content="summary_large_image" name="twitter:card"/>',
                f'<meta content="{html.escape(topic)} AI Books | Jonathan Harris" name="twitter:title"/>',
            ],
            "description": catalogue_meta_description(topic),
            "min_description": 120,
            "max_description": 155,
        })

    for page in discovery_pages:
        if not page["path"].exists():
            errors.append(f"Discovery page missing: {page['label']}")
            continue
        page_text = page["path"].read_text(encoding="utf-8")
        canonical_match = re.search(r'<link[^>]+href="([^"]+)"[^>]+rel="canonical"', page_text, re.I)
        canonical_href = canonical_match.group(1) if canonical_match else ""
        if canonical_href:
            expected_hreflang = [
                f'<link href="{canonical_href}" hreflang="en" rel="alternate"/>',
                f'<link href="{canonical_href}" hreflang="x-default" rel="alternate"/>',
            ]
            for marker in expected_hreflang:
                if marker not in page_text:
                    errors.append(f"Discovery hreflang metadata missing from {page['label']}: {marker}")
        for marker in page["required"]:
            if marker not in page_text:
                errors.append(f"Discovery metadata missing from {page['label']}: {marker}")
        expected_description = page.get("description")
        if expected_description:
            description_variants = {
                expected_description,
                html.escape(expected_description, quote=False),
                html.escape(expected_description, quote=True),
            }
            required_tags = ['name="description"', 'property="og:description"', 'name="twitter:description"']
            for tag in required_tags:
                if not any(f'<meta content="{variant}" {tag}/>' in page_text for variant in description_variants):
                    errors.append(f"Discovery description drift detected for {page['label']}: {tag}")
                    break
        errors.extend(metadata_budget_errors(page["label"], page_text, min_description=page.get("min_description"), max_description=page.get("max_description")))

    redirects_text = (ROOT / "_redirects").read_text(encoding="utf-8")
    redirects_mirror_path = ROOT / "_redirects.txt"
    if not redirects_mirror_path.exists():
        errors.append("_redirects.txt is missing. Run scripts/sync_redirects.py to regenerate the governed mirror.")
        redirects_mirror = ""
    else:
        redirects_mirror = redirects_mirror_path.read_text(encoding="utf-8")
        if redirects_text != redirects_mirror:
            errors.append("_redirects.txt is not an exact generated mirror of _redirects.")
    redirect_block_pattern = re.compile(r"# 6A\) Branded buy-now redirects.*?(?=\n# 7\) CANONICAL: old /book URLs permanently redirect to /ebooks)", re.S)
    existing_redirect_block = redirect_block_pattern.search(redirects_text)
    expected_redirect_block = build_redirect_block(books).strip()
    if not existing_redirect_block or existing_redirect_block.group(0).strip() != expected_redirect_block:
        errors.append("The governed branded buy-now redirect block in _redirects has drifted from the generated source.")
    for line in LEGACY_DETAIL_REDIRECT_LINES:
        if line not in redirects_text:
            errors.append(f"Redirect family missing from _redirects: {line}")
        if line not in redirects_mirror:
            errors.append(f"Redirect family missing from _redirects.txt: {line}")
    for legacy_alias in ("/en-gb/*  /:splat  200", "/en-us/*  /:splat  200", "/en-ca/*  /:splat  200", "/en-au/*  /:splat  200"):
        if legacy_alias in redirects_text or legacy_alias in redirects_mirror:
            errors.append(f"Locale alias pass-through must not remain live: {legacy_alias}")
    for line in LOCALE_ALIAS_REDIRECT_LINES:
        if line not in redirects_text:
            errors.append(f"Locale alias redirect missing from _redirects: {line}")
        if line not in redirects_mirror:
            errors.append(f"Locale alias redirect missing from _redirects.txt: {line}")
    malformed_lines = [f"{item['source']}   {item['target']}  301" for item in MALFORMED_SLUG_FIXES]
    for line in malformed_lines:
        if line not in redirects_text:
            errors.append(f"Malformed slug fix missing from _redirects: {line}")
        if line not in redirects_mirror:
            errors.append(f"Malformed slug fix missing from _redirects.txt: {line}")
    for book in books:
        required_lines = [
            f"{book['buy_route']}   {book['buy_url']}   302",
            f"/book/{book['slug']}/buy-now   {book['buy_route']}   301",
        ]
        for line in required_lines:
            if line not in redirects_text:
                errors.append(f"Redirect rule missing from _redirects: {line}")
            if line not in redirects_mirror:
                errors.append(f"Redirect rule missing from _redirects.txt: {line}")

    forbidden_main_redirects = [
        f"/robots.txt    {EXTERNAL_CRAWLER_FILES['robots']}   301",
        f"/sitemap.xml   {EXTERNAL_CRAWLER_FILES['sitemap']}  301",
        f"/site-map.xml {EXTERNAL_CRAWLER_FILES['sitemap']} 301",
    ]
    for snippet in forbidden_main_redirects:
        if snippet in redirects_text:
            errors.append(f"Main redirect file still redirects a governed crawler asset instead of serving it directly: {snippet}")
        if snippet in redirects_mirror:
            errors.append(f"Main redirect mirror still redirects a governed crawler asset instead of serving it directly: {snippet}")

    legacy_typo_alias = "/robot.txt    /robots.txt   301"
    legacy_sitemap_alias = "/Sitemap.xml  /sitemap.xml  301"
    legacy_site_map_alias = "/site-map.xml  /sitemap.xml  301"
    if legacy_typo_alias not in redirects_text or legacy_typo_alias not in redirects_mirror:
        errors.append("Legacy /robot.txt crawler alias is missing from the main redirect files.")
    if legacy_sitemap_alias not in redirects_text or legacy_sitemap_alias not in redirects_mirror:
        errors.append("Legacy /Sitemap.xml crawler alias is missing from the main redirect files.")
    if legacy_site_map_alias not in redirects_text or legacy_site_map_alias not in redirects_mirror:
        errors.append("Legacy /site-map.xml crawler alias is missing from the main redirect files.")

    books_domain = (ROOT / "_redirects.books-domain").read_text(encoding="utf-8")
    ebooks_domain = (ROOT / "_redirects.ebooks-domain").read_text(encoding="utf-8")
    if books_domain != build_books_domain_redirects():
        errors.append("_redirects.books-domain has drifted from the generated host redirect source.")
    if ebooks_domain != build_ebooks_domain_redirects():
        errors.append("_redirects.ebooks-domain has drifted from the generated host redirect source.")
    host_expectations = [
        f"/robots.txt   {EXTERNAL_CRAWLER_FILES['robots']}",
        f"/sitemap.xml  {EXTERNAL_CRAWLER_FILES['sitemap']}",
        f"/site-map.xml {EXTERNAL_CRAWLER_FILES['sitemap']}",
        "/book/*",
        "/catalogue/*",
    ]
    for snippet in host_expectations:
        if snippet not in ebooks_domain:
            errors.append(f"Host redirect coverage missing from _redirects.ebooks-domain: {snippet}")
    books_domain_expectations = ["/book/*", "/ebooks/*", "/catalogue/*"]
    for snippet in books_domain_expectations:
        if snippet not in books_domain:
            errors.append(f"Host redirect coverage missing from _redirects.books-domain: {snippet}")

    generated_crawler_files = build_crawler_snapshot_paths(books)
    for file_path, expected in generated_crawler_files.items():
        if not file_path.exists():
            errors.append(f"Generated crawler snapshot missing: {file_path.relative_to(ROOT)}")
            continue
        actual = file_path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"Generated crawler snapshot drift detected: {file_path.relative_to(ROOT)}")

    published_crawler_files = build_published_crawler_paths(books)
    for file_path, expected in published_crawler_files.items():
        if not file_path.exists():
            errors.append(f"Published crawler file missing: {file_path.relative_to(ROOT)}")
            continue
        actual = file_path.read_text(encoding="utf-8")
        if actual != expected:
            errors.append(f"Published crawler file drift detected: {file_path.relative_to(ROOT)}")

    sitemap_routes = build_public_route_registry(books)
    expected_sitemap_locations = {route["loc"] for route in sitemap_routes}
    actual_sitemap = build_crawler_snapshot_payloads(books)[CRAWLER_SNAPSHOT_FILENAMES["sitemap"]]
    actual_sitemap_locations = set(re.findall(r"<loc>([^<]+)</loc>", actual_sitemap))
    missing_sitemap_locations = sorted(expected_sitemap_locations - actual_sitemap_locations)
    unexpected_sitemap_locations = sorted(actual_sitemap_locations - expected_sitemap_locations)
    if missing_sitemap_locations:
        errors.append(f"Sitemap coverage missing {len(missing_sitemap_locations)} public route(s); first missing: {missing_sitemap_locations[0]}")
    if unexpected_sitemap_locations:
        errors.append(f"Sitemap includes unexpected route(s); first unexpected: {unexpected_sitemap_locations[0]}")

    sitemap_text = actual_sitemap
    for book in books:
        book_loc = html.escape(book["canonical_url"])
        pattern = re.compile(rf"<loc>{re.escape(book_loc)}</loc>\s*<lastmod>([^<]+)</lastmod>")
        match = pattern.search(sitemap_text)
        expected_lastmod = normalise_lastmod(book.get("dateModified") or book.get("datePublished"))
        if not match:
            errors.append(f"Sitemap entry missing for canonical book page {book['slug']}.")
            continue
        if match.group(1) != expected_lastmod:
            errors.append(f"Sitemap lastmod drift detected for {book['slug']}: expected {expected_lastmod}, found {match.group(1)}.")

    stray_catalogue_file = CATALOGUE_DIR / "cyber-security" / "1"
    if stray_catalogue_file.exists():
        errors.append("Stray catalogue artefact still exists: catalogue/cyber-security/1")

    manifest = read_json(EBOOKS_DIR / "url-manifest.json", default={}) or {}
    manifest_books = manifest.get("ebooks", [])
    if len(manifest_books) != len(books):
        errors.append("ebooks/url-manifest.json does not contain one route record per book.")
    if manifest.get("malformed_slug_fixes") != MALFORMED_SLUG_FIXES:
        errors.append("ebooks/url-manifest.json does not fully declare malformed slug fixes.")
    manifest_by_slug = {item.get("slug"): item for item in manifest_books}
    for book in books:
        entry = manifest_by_slug.get(book["slug"])
        if not entry:
            errors.append(f"Route manifest missing slug {book['slug']}.")
            continue
        legacy_routes = entry.get("legacy_routes", [])
        expected_legacy = {f"/book/{book['slug']}/", f"/book/{book['slug']}/buy-now", f"/ebooks/{book['slug']}/detail", f"/ebooks/{book['slug']}/detail.html", f"/ebooks/{book['slug']}/details.html"}
        if set(legacy_routes) != expected_legacy:
            errors.append(f"Route manifest legacy route coverage is incomplete for {book['slug']}.")
        if entry.get("buy", {}).get("target") != book["buy_url"]:
            errors.append(f"Route manifest buy target mismatch for {book['slug']}.")

    html_files = [p for p in ROOT.rglob("*.html") if "node_modules" not in p.parts]
    css_bundle = "\n".join(css_path.read_text(encoding="utf-8", errors="ignore") for css_path in (ROOT / "assets" / "css").glob("*.css"))
    if any(re.search(r"class=[\"']([^\"']*\bsr-only\b[^\"']*)[\"']", p.read_text(encoding="utf-8", errors="ignore"), re.I) for p in html_files):
        if not re.search(r"(^|[\s,{])\.sr-only\b", css_bundle, re.M):
            errors.append("Shared CSS is missing a governed .sr-only utility while HTML still references sr-only.")
    for file_path in html_files:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if file_path == ROOT / "index.html" and "\"@type\": \"Organization\"" not in text:
            errors.append("Homepage Organisation schema is missing from index.html.")
        if re.search(r'href="/book/', text):
            errors.append(f"Retired /book/ link found in HTML: {file_path.relative_to(ROOT)}")
        if re.search(r'href="[^"]*/detail(?:\.html)?"', text):
            errors.append(f"Retired /detail link found in HTML: {file_path.relative_to(ROOT)}")
        if "style=" in text:
            errors.append(f"Inline style attribute found in HTML: {file_path.relative_to(ROOT)}")

    static_metadata_pages = [
        (ROOT / "index.html", "index.html", None, None, 155),
        (ROOT / "bio" / "index.html", "bio/index.html", None, None, 155),
        (ROOT / "podcast" / "index.html", "podcast/index.html", 60, None, 155),
        (ROOT / "blog" / "weekly" / "index.html", "blog/weekly/index.html", 60, None, 155),
    ]
    for page_path, label, max_title, min_description, max_description in static_metadata_pages:
        if not page_path.exists():
            errors.append(f"Static page missing: {label}")
            continue
        page_text = page_path.read_text(encoding="utf-8", errors="ignore")
        errors.extend(
            metadata_budget_errors(
                label,
                page_text,
                max_title=max_title,
                min_description=min_description,
                max_description=max_description,
            )
        )

    for topic in sorted({book["topic"] for book in books}, key=str.lower):
        topic_slug = slugify(topic)
        page_path = CATALOGUE_DIR / topic_slug / "index.html"
        if not page_path.exists():
            errors.append(f"Catalogue topic page missing for breadcrumb validation: {page_path.relative_to(ROOT)}")
            continue
        page_text = page_path.read_text(encoding="utf-8", errors="ignore")
        expected_nav = f'<nav aria-label="Breadcrumb" class="breadcrumbs"><a href="/">Home</a><span aria-hidden="true">›</span><a href="/topics/">Topics</a><span aria-hidden="true">›</span><span>{html.escape(topic)}</span></nav>'
        if expected_nav not in page_text:
            errors.append(f"Catalogue breadcrumb trail drift detected for {page_path.relative_to(ROOT)}.")
        breadcrumb_payload = json.dumps(build_topic_breadcrumb_schema(topic), ensure_ascii=False, separators=(",", ":"))
        if breadcrumb_payload not in page_text:
            errors.append(f"Catalogue breadcrumb schema missing or drifted for {page_path.relative_to(ROOT)}.")
        for cover_match in re.finditer(r'<img\b[^>]*class="([^"]*\bcover\b[^"]*)"[^>]*>', page_text, re.I):
            tag = cover_match.group(0)
            src = extract_img_src(tag)
            if is_remote_image_src(src):
                if 'srcset="' in tag:
                    errors.append(f"Remote cover should not emit generated srcset markup in {page_path.relative_to(ROOT)}.")
                    break
                continue
            if 'srcset="' not in tag or 'sizes="' not in tag:
                errors.append(f"Responsive cover markup missing from {page_path.relative_to(ROOT)}.")
                break
            if not all(f" {width}w" in tag for width in (400, 800, 1200)):
                errors.append(f"Responsive cover widths drift detected for {page_path.relative_to(ROOT)}.")
                break

    homepage_text = (ROOT / "index.html").read_text(encoding="utf-8", errors="ignore")
    featured_cover_match = re.search(r'<img\b[^>]*id="featuredEbookCover"[^>]*>', homepage_text, re.I)
    if not featured_cover_match:
        errors.append("Homepage featured cover image is missing.")
    else:
        featured_tag = featured_cover_match.group(0)
        featured_src = extract_img_src(featured_tag)
        if is_remote_image_src(featured_src):
            if 'srcset="' in featured_tag:
                errors.append("Homepage featured cover should not emit generated srcset markup for a remote image.")
        else:
            if 'srcset="' not in featured_tag or 'sizes="' not in featured_tag:
                errors.append("Homepage featured cover is missing responsive srcset/sizes markup.")
            elif not all(f" {width}w" in featured_tag for width in (400, 800, 1200)):
                errors.append("Homepage featured cover responsive widths drifted from the governed 400/800/1200 contract.")

    for book in books:
        page_path = EBOOKS_DIR / book["slug"] / "index.html"
        if not page_path.exists():
            continue
        page_text = page_path.read_text(encoding="utf-8", errors="ignore")
        cover_match = re.search(r'<img\b[^>]*class="([^"]*\bebook-showcase__cover\b[^"]*)"[^>]*>', page_text, re.I)
        if not cover_match:
            errors.append(f"Book cover block missing from {page_path.relative_to(ROOT)}.")
            continue
        cover_tag = cover_match.group(0)
        cover_src = extract_img_src(cover_tag)
        if is_remote_image_src(cover_src):
            if 'srcset="' in cover_tag:
                errors.append(f"Remote book cover should not emit generated srcset markup in {page_path.relative_to(ROOT)}.")
            continue
        if 'srcset="' not in cover_tag or 'sizes="' not in cover_tag:
            errors.append(f"Responsive book cover markup missing from {page_path.relative_to(ROOT)}.")
            continue
        if not all(f" {width}w" in cover_tag for width in (400, 800, 1200)):
            errors.append(f"Responsive book cover widths drift detected for {page_path.relative_to(ROOT)}.")

    js_responsive_checks = {
        ROOT / "assets" / "js" / "featured-book.min.js": ["/cdn-cgi/image/width=", "[400,800,1200]"],
        ROOT / "assets" / "js" / "books.min.js": ["/cdn-cgi/image/width=", "[400,800,1200]"],
    }
    for file_path, required_snippets in js_responsive_checks.items():
        file_text = file_path.read_text(encoding="utf-8", errors="ignore")
        compact_text = re.sub(r"\s+", "", file_text)
        for snippet in required_snippets:
            if snippet not in compact_text:
                errors.append(f"Responsive image helper drift detected in {file_path.relative_to(ROOT)}: missing {snippet}")

    removal_plan_path = ROOT / "docs" / "search-console-stale-url-removal-plan.md"
    if not removal_plan_path.exists():
        errors.append("Search Console stale URL remediation plan is missing: docs/search-console-stale-url-removal-plan.md")
    else:
        removal_plan_text = removal_plan_path.read_text(encoding="utf-8", errors="ignore")
        for snippet in ["/en-gb/", "/en-au/", "/book/", "Search Console", "Request indexing", "Removals"]:
            if snippet not in removal_plan_text:
                errors.append(f"Search Console stale URL remediation plan is missing required guidance: {snippet}")

    static_topic_pages = [
        ROOT / "topics" / "ai-for-beginners" / "index.html",
        ROOT / "topics" / "ai-in-business" / "index.html",
        ROOT / "topics" / "ai-in-healthcare" / "index.html",
        ROOT / "topics" / "generative-ai" / "index.html",
        ROOT / "topics" / "robotics-automation" / "index.html",
    ]
    for page_path in static_topic_pages:
        if not page_path.exists():
            errors.append(f"Static topic page missing: {page_path.relative_to(ROOT)}")
            continue
        page_text = page_path.read_text(encoding="utf-8", errors="ignore")
        for marker in [
            '<link href="https://assets.jonathan-harris.online/favicon.ico" rel="icon" type="image/x-icon"/>',
            '<link href="https://images.jonathan-harris.online" rel="preconnect"/>',
            '<link href="https://assets.jonathan-harris.online" rel="preconnect"/>',
            '<meta content="#0D1420" name="theme-color"/>',
        ]:
            if marker not in page_text:
                errors.append(f"Static topic page head baseline drift detected for {page_path.relative_to(ROOT)}: {marker}")

    checksum_payload = read_json(CRAWLER_CHECKSUMS_PATH, default={}) or {}
    checksum_files = checksum_payload.get("files", {})
    expected_crawler_content = build_crawler_snapshot_payloads(books)
    if set(checksum_files.keys()) != set(expected_crawler_content.keys()):
        errors.append("config/crawler-checksums.json does not declare the governed crawler snapshots.")
    for name, expected_text in expected_crawler_content.items():
        file_payload = checksum_files.get(name, {})
        expected_hash = sha256_text(expected_text)
        if file_payload.get("sha256") != expected_hash:
            errors.append(f"Crawler checksum drift detected for {name}.")

    blog_manifest = read_json(ROOT / "blog" / "posts.json", default={}) or {}
    blog_manifest_items = blog_manifest.get("items") if isinstance(blog_manifest, dict) else None
    if not isinstance(blog_manifest, dict):
        errors.append("blog/posts.json must remain a JSON object.")
    else:
        if blog_manifest.get("schema_version") != 1:
            errors.append("blog/posts.json must declare schema_version = 1.")
        if not isinstance(blog_manifest_items, list):
            errors.append("blog/posts.json must expose an items array.")
        else:
            for item in blog_manifest_items:
                if not isinstance(item, dict):
                    errors.append("blog/posts.json contains a non-object entry.")
                    continue
                slug = clean_paragraph(item.get("slug"))
                url = clean_paragraph(item.get("url") or item.get("canonical_url"))
                path = clean_paragraph(item.get("path"))
                published_at = clean_paragraph(item.get("published_at") or item.get("datePublished") or item.get("pubDate"))
                if not slug:
                    errors.append("blog/posts.json contains an entry without a slug.")
                    continue
                expected_path = f"/blog/posts/{slug}/"
                expected_url = f"https://jonathan-harris.online{expected_path}"
                if path and path != expected_path:
                    errors.append(f"blog/posts.json entry for {slug} must use path {expected_path}.")
                if url and url != expected_url:
                    errors.append(f"blog/posts.json entry for {slug} must use url {expected_url}.")
                if published_at and not re.match(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)?$", published_at):
                    errors.append(f"blog/posts.json entry for {slug} has an invalid published date shape.")

    weekly_archive_html = (ROOT / "blog" / "weekly" / "index.html").read_text(encoding="utf-8")
    site_ui_js = (ROOT / "assets" / "js" / "site-ui.min.js").read_text(encoding="utf-8")
    blog_js = (ROOT / "assets" / "js" / "blog.bundle.min.js").read_text(encoding="utf-8")
    weekly_archive_runtime_js = ROOT / "functions" / "blog" / "weekly" / "index.js"
    sitemap_runtime_js = ROOT / "functions" / "sitemap.xml.js"
    if "manifest stack" in weekly_archive_html or "published manifest" in weekly_archive_html or "falls back to" in weekly_archive_html:
        errors.append("blog/weekly/index.html still exposes runtime publication language instead of deterministic archive copy.")
    if "cfg.R2_PUBLIC_BASE_URL_BLOG" in blog_js or "cfg.RSS_URL" in blog_js:
        errors.append("assets/js/blog.bundle.min.js still depends on remote manifest or RSS fallback instead of the same-origin weekly publication surface.")
    if "createElement(\"style\")" in site_ui_js or "createElement('style')" in site_ui_js:
        errors.append("assets/js/site-ui.min.js still injects runtime style tags instead of relying on governed CSS.")
    if not weekly_archive_runtime_js.exists():
        errors.append("functions/blog/weekly/index.js is missing; weekly archive robots state would drift from the live publication manifest.")
    else:
        weekly_runtime_text = weekly_archive_runtime_js.read_text(encoding="utf-8")
        if "/blog/posts.json" not in weekly_runtime_text:
            errors.append("functions/blog/weekly/index.js must read the same-origin /blog/posts.json publication manifest.")
    if not sitemap_runtime_js.exists():
        errors.append("functions/sitemap.xml.js is missing; sitemap visibility would drift from the live publication manifest.")
    else:
        sitemap_runtime_text = sitemap_runtime_js.read_text(encoding="utf-8")
        if "/blog/posts.json" not in sitemap_runtime_text:
            errors.append("functions/sitemap.xml.js must read the same-origin /blog/posts.json publication manifest.")

    llm_index_payload = read_json(ROOT / "llm-index.json", default={}) or {}
    llm_index_books = llm_index_payload.get("books") if isinstance(llm_index_payload, dict) else None
    if not isinstance(llm_index_books, list) or len(llm_index_books) != len(books):
        errors.append("llm-index.json is missing book records or is out of sync with the master record.")
    else:
        llm_index_by_slug = {clean_paragraph(item.get("slug")): item for item in llm_index_books if isinstance(item, dict) and clean_paragraph(item.get("slug"))}
        for book in books:
            indexed = llm_index_by_slug.get(book["slug"])
            if not indexed:
                errors.append(f"llm-index.json is missing record for {book['slug']}")
                continue
            if indexed.get("related_slugs", []) != book.get("related_slugs", []):
                errors.append(f"llm-index.json related_slugs drift detected for {book['slug']}")

    errors.extend(static_blog_archive_errors())
    errors.extend(blog_related_link_errors())
    errors.extend(json_ld_validation_errors())

    featured_payload = read_json(ROOT / "api" / "v1" / "featured-book.json", default={}) or {}
    expected_featured_payload = build_featured_book_payload([book_to_public_record(book) for book in books])
    if featured_payload != expected_featured_payload:
        errors.append("Derivative featured-book API payload drift detected for api/v1/featured-book.json.")

    page_404 = ROOT / "404.html"
    if not page_404.exists():
        errors.append("404.html is missing.")
    else:
        not_found_text = page_404.read_text(encoding="utf-8")
        title_match = re.search(r"<title>(.*?)</title>", not_found_text, re.I | re.S)
        og_title_match = re.search(r'<meta[^>]+(?:property="og:title"[^>]+content="([^"]+)"|content="([^"]+)"[^>]+property="og:title")', not_found_text, re.I)
        canonical_match = re.search(r'<link[^>]+href="([^"]+)"[^>]+rel="canonical"', not_found_text, re.I)
        title_value = clean_paragraph(html.unescape(title_match.group(1))) if title_match else ""
        og_title_value = clean_paragraph(html.unescape(og_title_match.group(1) or og_title_match.group(2))) if og_title_match else ""
        canonical_href = canonical_match.group(1) if canonical_match else ""
        if not title_value:
            errors.append("404.html title tag is missing.")
        if not og_title_value:
            errors.append("404.html og:title is missing.")
        if title_value and og_title_value and title_value != og_title_value:
            errors.append("404.html og:title does not match the title tag.")
        if canonical_href:
            expected_hreflang = [
                f'<link href="{canonical_href}" hreflang="en" rel="alternate"/>',
                f'<link href="{canonical_href}" hreflang="x-default" rel="alternate"/>',
            ]
            for marker in expected_hreflang:
                if marker not in not_found_text:
                    errors.append(f"404.html is missing hreflang metadata: {marker}")

    if workbook_path and workbook_path.exists():
        errors.extend(validate_pages_sheet_operational_view(workbook_path))
        errors.extend(workbook_static_route_contract_errors(workbook_path))
        workbook_content_errors, _ = workbook_content_parity_audit(workbook_path, books)
        errors.extend(workbook_content_errors)

    return errors


def run_import_command(args: argparse.Namespace) -> int:
    try:
        workbook_path = Path(args.workbook).expanduser().resolve()
        order, workbook_map, _ = parse_workbook(workbook_path)
    except Exception as exc:
        print(f"Import check failed: {exc}")
        return 1

    if args.check:
        if not workbook_map:
            print("Workbook check failed: no ebook rows found.")
            return 1
        print(f"Workbook check passed: {len(order)} ebook rows found.")
        return 0

    records = build_master_from_workbook(workbook_path)
    save_master(records)
    print(f"Wrote {len(records)} records to {MASTER_PATH.relative_to(ROOT)}")
    return 0



def run_fix_pages_command(args: argparse.Namespace) -> int:
    books = load_master()
    ensure_css_file()
    build_book_files(books)
    if args.check:
        errors = [
            err
            for err in run_release_checks(books, Path(args.workbook).resolve() if getattr(args, "workbook", None) else None)
            if "canonical link" in err or "FAQPage" in err or "Book JSON-LD" in err or "Book page missing" in err
        ]
        if errors:
            for error in errors:
                print(error)
            return 1
        print("Page metadata check passed.")
        return 0
    print(f"Generated {len(books)} canonical ebook pages.")
    return 0



def run_build_derivatives_command(args: argparse.Namespace) -> int:
    books = load_master()
    ensure_css_file()
    build_derivatives(books)
    if args.check:
        errors = [
            err
            for err in run_release_checks(books, Path(args.workbook).resolve() if getattr(args, "workbook", None) else None)
            if "Derivative" in err or "topic discovery" in err or "url-manifest" in err or "host redirect" in err
        ]
        if errors:
            for error in errors:
                print(error)
            return 1
        print("Derivative build check passed.")
        return 0
    print("Derivative JSON, manifests, crawler files, and governed discovery pages rebuilt.")
    return 0



def run_sync_redirects_command(args: argparse.Namespace) -> int:
    books = load_master()
    sync_redirects(books)
    if args.check:
        errors = [err for err in run_release_checks(books) if "Redirect rule missing" in err]
        if errors:
            for error in errors:
                print(error)
            return 1
        print("Redirect sync check passed.")
        return 0
    print("Redirect files synchronised.")
    return 0





def json_ld_validation_errors() -> List[str]:
    errors: List[str] = []
    for path in sorted(ROOT.rglob("*.html")):
        relative = path.relative_to(ROOT)
        if "node_modules" in path.parts or "assets" in path.parts or "templates" in path.parts or "partials" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.I | re.S)
        for index, raw in enumerate(blocks, start=1):
            payload = clean_paragraph(raw)
            if not payload:
                continue
            try:
                json.loads(payload)
            except Exception as exc:
                errors.append(f"Invalid JSON-LD in {relative} block #{index}: {exc}")
    return errors


def static_blog_archive_errors() -> List[str]:
    errors: List[str] = []
    manifest = read_json(ROOT / "blog" / "posts.json", default={}) or {}
    items = manifest.get("items") if isinstance(manifest, dict) else None
    if not isinstance(items, list) or not items:
        return errors
    expected_paths = []
    for item in items:
        if not isinstance(item, dict):
            continue
        slug = clean_paragraph(item.get("slug"))
        if slug:
            expected_paths.append(f"/blog/posts/{slug}/")
    for rel in [Path("blog/index.html"), Path("blog/weekly/index.html")]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if "Published briefings appear here" in text or "The latest briefings appear here" in text:
            errors.append(f"{rel} still ships placeholder archive copy instead of static post discovery.")
        missing = [path for path in expected_paths[:3] if path not in text]
        if missing:
            errors.append(f"{rel} is missing static links for published briefings. First missing: {missing[0]}")
    return errors


def blog_related_link_errors() -> List[str]:
    errors: List[str] = []
    for path in sorted((ROOT / "blog" / "posts").glob("*/index.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for href, label in re.findall(r'<a href="([^"]+)">([^<]+)</a>', text):
            href_clean = clean_paragraph(href)
            label_clean = clean_paragraph(html.unescape(label))
            if href_clean and not href_clean.startswith(("/", "http://", "https://", "#", "mailto:", "tel:")):
                errors.append(f"Blog post malformed link href in {path.relative_to(ROOT)}: {href_clean}")
                break
            if label_clean.startswith("/ebooks/") and href_clean and not href_clean.startswith("/ebooks/"):
                errors.append(f"Blog post related-book anchor text/href reversal detected in {path.relative_to(ROOT)}")
                break
    return errors

def rebuild_all(workbook_path: Path) -> List[str]:
    books = build_master_from_workbook(workbook_path)
    save_master(books)
    ensure_css_file()
    build_book_files(books)
    build_derivatives(books)
    sync_redirects(books)
    errors = run_release_checks(books, workbook_path)
    VALIDATION_REPORT.write_text(build_validation_report(errors, books), encoding="utf-8")
    return errors



def detect_governed_workbook_path() -> Path | None:
    candidates = sorted(ROOT.glob("*.xlsx")) + sorted(ROOT.glob("*.xlsm"))
    if len(candidates) == 1:
        return candidates[0].resolve()

    xlsx_candidates = {path.stem: path for path in ROOT.glob("*.xlsx")}
    xlsm_candidates = {path.stem: path for path in ROOT.glob("*.xlsm")}
    shared_stems = sorted(set(xlsx_candidates) & set(xlsm_candidates))
    if len(candidates) == 2 and len(shared_stems) == 1:
        return xlsx_candidates[shared_stems[0]].resolve()

    return None

def ebook_title_length_warnings(books: List[Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    for book in books:
        page_path = EBOOKS_DIR / book["slug"] / "index.html"
        if not page_path.exists():
            continue
        text = page_path.read_text(encoding="utf-8", errors="ignore")
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        if not title_match:
            continue
        actual_title = clean_paragraph(html.unescape(re.sub(r"\s+", " ", title_match.group(1))))
        if 90 < len(actual_title) <= 120:
            warnings.append(f"{book['slug']} page title is {len(actual_title)} characters; warning threshold is 90.")
    return warnings

def run_validate_command(workbook_path: Path | None = None) -> int:
    effective_workbook = workbook_path or detect_governed_workbook_path()
    errors = run_release_checks(workbook_path=effective_workbook)
    books = load_master()
    warnings = ebook_title_length_warnings(books)
    workbook_title_stats = None
    workbook_content_stats = None
    if effective_workbook and effective_workbook.exists():
        _, workbook_title_stats = workbook_title_parity_audit(effective_workbook)
        _, workbook_content_stats = workbook_content_parity_audit(effective_workbook, books)
    VALIDATION_REPORT.write_text(
        build_validation_report(
            errors,
            books,
            workbook_title_stats=workbook_title_stats,
            workbook_content_stats=workbook_content_stats,
        ),
        encoding="utf-8",
    )
    if workbook_title_stats:
        print(f"Workbook title parity checked {workbook_title_stats['checked']} routes; {workbook_title_stats['passed']} passed.")
    if workbook_content_stats:
        print(
            "Workbook content parity checked "
            f"{workbook_content_stats['checked_fields']} governed fields across {workbook_content_stats['books']} books; "
            f"{workbook_content_stats['exact_matches']} exact matches, "
            f"{workbook_content_stats['approved_transformations']} approved transformations, "
            f"{workbook_content_stats['mismatched']} mismatches."
        )
    for warning in warnings:
        print(f"[WARN] {warning}")
    if errors:
        for error in errors:
            print(error)
        print(f"Validation failed with {len(errors)} issue(s).")
        return 1
    print("Release validation passed.")
    return 0
