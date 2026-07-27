#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ebook_pipeline import (
    ROOT, SITE_URL, build_person_schema, build_website_schema, json_script,
    load_master, render_footer, render_header, render_inline_newsletter_form,
)
from scripts.ebook_content_helpers import build_same_source_srcset, cover_sizes

DATA = ROOT / "data"
FONT_HEAD = '''<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap" rel="stylesheet"/>'''


EVIDENCE_PODCAST_LINKS = {
    "workplace-ai-literacy": (
        "/podcast/episodes/navigating-ais-future-balancing-innovation-and-human-needs/",
        "AI innovation, work and human needs",
    ),
    "ai-agents-for-ordinary-work": (
        "/podcast/episodes/turings-torch-unpacking-ais-promise-and-pitfalls/",
        "AI promise, pitfalls and practical automation",
    ),
    "ai-for-small-business": (
        "/podcast/episodes/turings-torch-unpacking-ais-promise-and-pitfalls/",
        "AI promise, pitfalls and practical adoption",
    ),
    "deepfake-detection-and-synthetic-media": (
        "/podcast/episodes/artificial-intelligence-weekly/",
        "Turing’s Torch: current AI risks and verification context",
    ),
    "ai-in-healthcare": (
        "/podcast/episodes/navigating-ais-future-balancing-innovation-and-human-needs/",
        "AI innovation balanced against human needs",
    ),
    "ai-in-finance": (
        "/podcast/episodes/ai-safety-in-finance-robot-integration-multilingual-models/",
        "AI safety in finance, robotics and multilingual models",
    ),
    "ai-governance-and-law": (
        "/podcast/episodes/openais-four-day-week-ai-governance-and-memory-problems/",
        "AI governance, accountability and memory problems",
    ),
    "eu-ai-act-article-50-transparency": (
        "/podcast/episodes/openais-four-day-week-ai-governance-and-memory-problems/",
        "AI governance, accountability and implementation",
    ),
}

TOPIC_CONTEXT_LINKS = {
    "ai-in-business": ("/evidence/ai-for-small-business/",) + EVIDENCE_PODCAST_LINKS["ai-for-small-business"],
    "ai-in-healthcare": ("/evidence/ai-in-healthcare/",) + EVIDENCE_PODCAST_LINKS["ai-in-healthcare"],
    "ai-in-finance": ("/evidence/ai-in-finance/",) + EVIDENCE_PODCAST_LINKS["ai-in-finance"],
    "ai-ethics": ("/evidence/ai-governance-and-law/",) + EVIDENCE_PODCAST_LINKS["ai-governance-and-law"],
    "robotics-automation": ("/evidence/ai-agents-for-ordinary-work/",) + EVIDENCE_PODCAST_LINKS["ai-agents-for-ordinary-work"],
}


def render_contextual_podcast_link(slug: str) -> str:
    match = EVIDENCE_PODCAST_LINKS.get(slug)
    if not match:
        return '<a href="/podcast/">Browse Turing’s Torch</a> <a href="/transcripts/">Browse transcripts</a>'
    href, label = match
    return (
        f'<a href="{html.escape(href, quote=True)}">Listen: {html.escape(label)}</a> '
        '<a href="/transcripts/">Browse episode transcripts</a>'
    )


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    if start in text and end in text:
        a = text.index(start)
        b = text.index(end, a) + len(end)
        return text[:a] + replacement + text[b:]
    return text


BOOK_COUNT_PATTERNS = [
    (r"\b\d+ plain-English (AI )?books\b", lambda count, m: f"{count} plain-English " + ("AI " if m.group(1) else "") + "books"),
    (r"\b\d+ plain-English ebooks\b", lambda count, m: f"{count} plain-English ebooks"),
    (r"\b\d+-book (catalogue|library)\b", lambda count, m: f"{count}-book {m.group(1)}"),
    (r"\bBrowse \d+ AI Books\b", lambda count, m: f"Browse {count} AI Books"),
    (r"\bSee all \d+ books\b", lambda count, m: f"See all {count} books"),
    (r"\b\d+ AI eBooks\b", lambda count, m: f"{count} AI eBooks"),
    (r"\b\d+ eBooks\b", lambda count, m: f"{count} eBooks"),
    (r"\bHis \d+ books\b", lambda count, m: f"His {count} books"),
    (r"\bWriter of \d+ Plain-English AI Books\b", lambda count, m: f"Writer of {count} Plain-English AI Books"),
    (r"\bwith \d+ plain-English books\b", lambda count, m: f"with {count} plain-English books"),
    (r"\bpublishes \d+ plain-English ebooks\b", lambda count, m: f"publishes {count} plain-English ebooks"),
    (r"\bacross the \d+-book library\b", lambda count, m: f"across the {count}-book library"),
]


def apply_book_count(text: str, count: int) -> str:
    """Replace catalogue-size claims from one generated count, without touching unrelated numbers."""
    for pattern, repl in BOOK_COUNT_PATTERNS:
        text = re.sub(pattern, lambda m, fn=repl: fn(count, m), text, flags=re.I)
    return text


def sync_book_counts(count: int) -> None:
    targets = [ROOT / "index.html", ROOT / "bio" / "index.html", ROOT / "glossary" / "index.html", ROOT / "assets" / "partials" / "footer.html"]
    for path in targets:
        if path.exists():
            path.write_text(apply_book_count(path.read_text(encoding="utf-8"), count), encoding="utf-8")
    facts_path = DATA / "site-facts.json"
    try:
        facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else {}
    except json.JSONDecodeError:
        facts = {}
    if not isinstance(facts, dict):
        facts = {}
    facts.pop("newsletter_cadence", None)
    facts.update({
        "book_count": count,
        "newsletter_name": "AI Edge",
        "newsletter_descriptor": "practical AI briefing",
        "podcast_name": "Turing's Torch: AI Weekly",
        "book_count_source": "data/ebooks-master.json",
    })
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def homepage(count: int) -> None:
    """Render the homepage deterministically from governed book data."""
    books = load_master()
    if not books:
        raise RuntimeError("Cannot build homepage without governed ebook records")
    featured = books[0]
    cover = featured.get("cover", "")
    srcset = build_same_source_srcset(cover, None)
    sizes = cover_sizes("featured-cover-img")
    srcset_attrs = f' srcset="{html.escape(srcset, quote=True)}" sizes="{html.escape(sizes, quote=True)}"' if srcset else ""
    featured_url = f"/ebooks/{featured['slug']}/"
    featured_buy = featured.get("buy_route") or f"{featured_url}buy-now"
    topic_links = [
        ("AI for Beginners", "/topics/ai-for-beginners/"),
        ("Generative AI", "/topics/generative-ai/"),
        ("AI in Healthcare", "/topics/ai-in-healthcare/"),
        ("AI in Business", "/topics/ai-in-business/"),
        ("Robotics & Automation", "/topics/robotics-automation/"),
        ("AI Glossary", "/glossary/"),
        ("AI Comparisons", "/compare/"),
        ("All Topics", "/topics/"),
    ]
    topic_html = "".join(f'<a class="chip" href="{href}">{html.escape(label)}</a>' for label, href in topic_links)
    organisation_schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": f"{SITE_URL}/#organisation",
        "name": "Jonathan Harris",
        "url": f"{SITE_URL}/",
        "logo": "https://images.jonathan-harris.online/site-logo",
        "founder": {"@id": f"{SITE_URL}/#person"},
    }
    hero = f'''<!-- GROWTH:HERO START -->
<section aria-labelledby="hero-heading" class="hero hero--home hero--commercial" role="region" data-jh-header-reveal-anchor>
<div class="wrap">
<img alt="Jonathan Harris" class="logo-plain logo-plain--hero" fetchpriority="high" height="96" loading="eager" src="https://images.jonathan-harris.online/site-logo" width="96"/>
<h1 class="hero__title" id="hero-heading">Practical AI books and analysis, without the hype</h1>
<p class="hero__lead">Explore {count} plain-English AI books, Turing’s Torch analysis and AI Edge, the practical AI briefing.</p>
<div class="cta-row"><a class="button" href="/book-finder/">Find the right AI book</a><a class="button secondary" href="#home-newsletter-hero">Get the free AI glossary</a></div>
<p class="home-podcast-text-link"><a href="/podcast/">Listen to the latest Turing’s Torch →</a></p>
<div class="home-trust-strip" aria-label="Publishing scale"><span>{count} books</span><span>Weekly podcast</span><span>Practical AI briefing</span><span>Plain-English AI</span></div>
<div class="home-intent" aria-labelledby="home-intent-heading"><h2 id="home-intent-heading">Start with your problem</h2><nav aria-label="Choose an AI route"><a href="/bundles/ai-at-work/">Work &amp; careers</a><a href="/catalogue/business/">Business</a><a href="/bundles/ai-health-and-care/">Healthcare</a><a href="/bundles/ai-in-regulated-industries/">Law &amp; regulation</a><a href="/catalogue/finance/">Finance</a><a href="/topics/ai-for-beginners/">AI fundamentals</a><a href="/blog/">Current AI news</a></nav></div>
<div id="home-newsletter-hero">{render_inline_newsletter_form("homepage:hero")}</div>
</div>
</section>
<!-- GROWTH:HERO END -->'''
    router = '''<!-- GROWTH:ROUTER START -->
<section class="main home-commercial-router" aria-labelledby="home-commercial-heading"><div class="wrap">
<section class="card answer-first"><h2 id="home-commercial-heading">What is the quickest route to the useful bit?</h2><p>Use the <a href="/book-finder/">book finder</a> when you have a problem to solve, the <a href="/evidence/">evidence guides</a> when you need sources, or a reading path when one book will not cover the whole decision. The podcast and AI Edge handle the moving story.</p></section>
<section class="card home-latest-podcast" aria-labelledby="home-latest-podcast-heading"><h2 id="home-latest-podcast-heading">Latest Turing’s Torch</h2><div data-podcast-latest-server><p>Current episode details come from the governed podcast RSS feed. <a href="/podcast/">Open the podcast</a> or <a href="/transcripts/">browse transcripts</a>.</p></div></section>
<section class="card" aria-labelledby="home-reading-paths-heading"><h2 id="home-reading-paths-heading">Reading paths</h2><p>Curated routes through books that belong together. The books are bought separately on Amazon.</p><div class="jh-journey-actions"><a href="/bundles/ai-at-work/">AI at Work</a><a href="/bundles/ai-health-and-care/">AI Health &amp; Care</a><a href="/bundles/ai-mobility-and-logistics/">AI Mobility &amp; Logistics</a><a href="/bundles/ai-in-regulated-industries/">AI in Regulated Industries</a></div></section>
<section class="card" aria-labelledby="home-evidence-heading"><h2 id="home-evidence-heading">Evidence, not vibes</h2><p>Source-backed guides on workplace AI literacy, agents, small business, deepfakes, healthcare, finance and governance.</p><div class="jh-journey-actions"><a href="/evidence/eu-ai-act-article-50-transparency/">Current evidence: EU AI Act Article 50</a><a href="/resources/eu-ai-act-article-50-readiness-checklist/">Article 50 readiness checklist</a><a href="/evidence/">Browse all evidence guides</a><a href="/resources/">Use practical checklists</a></div></section>
</div></section>
<!-- GROWTH:ROUTER END -->'''
    featured_block = f'''<section class="section--featured"><div class="wrap"><h2 class="section-label--centered">Featured this week</h2><article class="card featured-ebook"><a aria-label="View featured book" href="{html.escape(featured_url)}" id="featuredEbookPage"><img alt="{html.escape(featured['title'], quote=True)} cover" class="featured-cover-img" decoding="async" height="3508" id="featuredEbookCover" loading="lazy" src="{html.escape(cover, quote=True)}" width="2480"{srcset_attrs}/></a><div class="featured-copy"><span class="featured-meta" id="featuredEbookMeta">{html.escape(featured.get('topic',''))} · {featured.get('pages') or ''} pages</span><h3 class="featured-title" id="featuredEbookTitle">{html.escape(featured['title'])}</h3><p class="featured-desc" id="featuredEbookDesc">{html.escape(featured.get('short',''))}</p><p class="book-market-signal muted" id="featuredEbookMarketSignal">Current Kindle price and ratings are checked on Amazon at the buy step.</p><div class="featured-actions"><a class="button" href="{html.escape(featured_url)}" id="featuredEbookLink">View book</a><a class="button secondary" href="{html.escape(featured_buy)}" id="featuredEbookBuy">Buy on Amazon</a></div></div></article><p class="featured-footer-note">Updated weekly · <a href="/ebooks/">See all {count} books →</a></p></div></section>'''
    explore = f'''<section class="section--explore"><div class="wrap"><h2 class="section-label--centered">Explore</h2><div class="grid grid--explore"><article class="card card--explore"><span class="card__emoji" aria-hidden="true">📚</span><h3 class="card__title">{count} AI eBooks</h3><p class="card__desc">Plain-English guides covering AI in healthcare, law, banking, manufacturing, education and more.</p><a class="button" href="/ebooks/">Browse catalogue</a></article><article class="card card--explore"><span class="card__emoji" aria-hidden="true">🎙️</span><h3 class="card__title">Turing’s Torch Podcast</h3><p class="card__desc">Weekly AI analysis with practical context and zero patience for buzzwords.</p><a class="button" href="/podcast/">Listen free</a></article><article class="card card--explore"><span class="card__emoji" aria-hidden="true">📬</span><h3 class="card__title">AI Edge</h3><p class="card__desc">A practical AI briefing plus the free plain-English AI glossary.</p><a class="button" href="/newsletter/">Get the glossary</a></article></div></div></section>'''
    about = f'''<section class="section--about"><div class="wrap wrap--narrow"><h2 class="about__title">About Jonathan Harris</h2><p class="about__copy">Jonathan Harris is a UK artificial intelligence author and host of Turing’s Torch AI Weekly. His {count} books explain how AI works across industries without dressing the answer in conference-stage fog.</p><a class="button button--bio" href="/bio/">Read the full bio</a></div></section>'''
    topics = f'''<section class="section--topics"><div class="wrap"><h2 class="section-label--centered">Learn about AI</h2><nav class="chips chips--topics" aria-label="AI topics">{topic_html}</nav></div></section>'''
    description = "Plain-English AI books, Turing’s Torch podcast, AI Edge, evidence guides and practical resources from UK author Jonathan Harris."
    page = f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/><title>Jonathan Harris — AI Author &amp; Podcast Host</title><meta name="description" content="{html.escape(description, quote=True)}"/><link rel="canonical" href="{SITE_URL}/"/><meta name="robots" content="index,follow"/>{FONT_HEAD}<link rel="stylesheet" href="/assets/css/site.css"/><script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script><script data-jh-ai-pack="organisation" type="application/ld+json">{json.dumps(organisation_schema, ensure_ascii=False)}</script><script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script></head><body class="home page-home" data-page-type="home">{render_header()}<main id="main" role="main">{hero}{router}{featured_block}{explore}{about}{topics}</main>{render_footer()}<script defer src="/assets/js/featured-book.min.js"></script><script defer src="/assets/js/funnel-events.min.js"></script><script defer src="/assets/js/site-ui.min.js"></script></body></html>'''
    (ROOT / "index.html").write_text(page, encoding="utf-8")

def benefit_newsletter_copy() -> None:
    # The primary newsletter page uses the owner-managed hosted Jotform. Lightweight
    # inline forms elsewhere keep the one-field low-friction path and share the
    # same glossary destination after a successful submission.
    p = ROOT / "newsletter" / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    title = "AI Edge | Jonathan Harris"
    description = "Join AI Edge, Jonathan Harris's practical AI briefing, and download the free plain-English AI glossary cheat sheet."
    jotform_url = "https://form.jotform.com/260277027608054"
    glossary_pdf = "/downloads/ai-glossary-cheat-sheet/ai-glossary-cheat-sheet.pdf"
    body = f'''<header class="hero hero--newsletter hero--has-fixed-nav" role="region" aria-label="AI Edge newsletter header">
<div class="wrap"><img src="https://images.jonathan-harris.online/site-logo" alt="Jonathan Harris" class="logo-morph" loading="eager" fetchpriority="high" width="120" height="120"/>
<h1>AI Edge</h1><p>Practical AI analysis: what changed, what matters, and what is mostly theatre.</p></div></header>
<main class="main" id="main" role="main" aria-label="AI Edge newsletter sign-up content"><div class="wrap newsletter-page-shell">
<section class="card newsletter-signup-card newsletter-signup-card--primary" role="region" aria-labelledby="ai-edge-signup-heading" data-newsletter-shell data-newsletter-source="newsletter:primary">
<h2 id="ai-edge-signup-heading">Join AI Edge and get the free AI glossary</h2>
<p>The hosted form now collects your name and email address. Subscribe here, then keep the glossary as a quick-reference PDF.</p>
<div class="newsletter-jotform-wrap"><iframe id="JotFormIFrame-260277027608054" title="AI Edge newsletter sign-up" allowtransparency="true" allow="geolocation; microphone; camera; fullscreen; payment" src="{jotform_url}" data-jotform-base-src="{jotform_url}" frameborder="0" class="newsletter-jotform-frame" scrolling="no"></iframe></div>
<p class="newsletter-form-fallback">Form blocked by your browser? <a href="{jotform_url}" target="_blank" rel="noopener">Open the AI Edge sign-up form directly</a>.</p>
<div class="newsletter-glossary-cta"><p><strong>Already subscribed?</strong> The glossary is available as a direct download too.</p><a class="button secondary" href="{glossary_pdf}" download>Download the AI glossary PDF</a></div>
</section>
<section class="card newsletter-card-spaced" aria-labelledby="ai-edge-value-heading"><h2 id="ai-edge-value-heading">What lands in your inbox?</h2>
<p><strong>AI Edge</strong> is a practical briefing for readers who want the signal without the launch-day confetti. It focuses on developments that can affect work, business, policy, security and ordinary users.</p>
<ul class="checklist"><li>The development worth knowing.</li><li>A plain-English explanation of why it matters, or why it does not.</li><li>A practical verdict on what deserves attention next.</li></ul></section>
<section class="card newsletter-card-spaced" aria-labelledby="ai-edge-preview-heading"><h2 id="ai-edge-preview-heading">Preview the AI Edge format</h2>
<p class="muted">This is a format preview, not a fabricated past issue.</p>
<div class="newsletter-issue-preview"><p><strong>1. What changed</strong><br/>The important announcement in two or three sentences, stripped of launch copy.</p><p><strong>2. Why it matters</strong><br/>The practical consequences for work, business, policy, security or everyday use.</p><p><strong>3. The raised-eyebrow test</strong><br/>What still needs evidence, what is being oversold, and what to watch next.</p></div>
<p><a class="button secondary" href="/blog/">Read the current editorial analysis</a></p></section>
<section class="faq card" aria-label="AI Edge questions"><h2>Quick answers</h2><div class="ebook-faq-list">
<details class="ebook-faq-item" open><summary>What is AI Edge?</summary><div><p>A practical AI briefing focused on useful developments, consequences and evidence rather than launch copy.</p></div></details>
<details class="ebook-faq-item"><summary>Who is it for?</summary><div><p>Business readers, AI-curious professionals, creators and anyone who wants practical commentary rather than recycled launch copy.</p></div></details>
<details class="ebook-faq-item"><summary>What do subscribers get?</summary><div><p>AI Edge plus immediate access to the plain-English AI glossary cheat sheet.</p></div></details></div></section>
<section class="card newsletter-card-spaced" aria-labelledby="ai-edge-current-evidence"><h2 id="ai-edge-current-evidence">Current evidence worth keeping</h2><p>For source-backed detail, start with the <a href="/evidence/eu-ai-act-article-50-transparency/">EU AI Act Article 50 transparency guide</a> and its <a href="/resources/eu-ai-act-article-50-readiness-checklist/">readiness checklist</a>.</p></section>
<section class="card newsletter-book-bridge"><h2>Want the longer version?</h2><p>The <a href="/ebooks/">40-book catalogue</a> goes deeper by topic, with practical guides across healthcare, law, finance, education, manufacturing and more.</p><div class="jh-journey-actions"><a href="/book-finder/">Find the right book</a><a href="/podcast/">Listen to Turing's Torch</a></div></section>
</div></main>'''
    schema = {
        "@context": "https://schema.org", "@type": "WebPage", "name": "AI Edge",
        "url": f"{SITE_URL}/newsletter/", "description": description,
        "author": {"@id": f"{SITE_URL}/#person"}, "inLanguage": "en-GB",
    }
    page = f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/><title>{title}</title><meta name="description" content="{html.escape(description, quote=True)}"/><meta name="robots" content="index,follow"/><link rel="canonical" href="{SITE_URL}/newsletter/"/>{FONT_HEAD}<link rel="stylesheet" href="/assets/css/site.css"/><meta property="og:type" content="website"/><meta property="og:title" content="AI Edge | Jonathan Harris"/><meta property="og:description" content="{html.escape(description, quote=True)}"/><meta property="og:url" content="{SITE_URL}/newsletter/"/><meta property="og:image" content="https://images.jonathan-harris.online/site-newsletter"/><meta name="twitter:card" content="summary_large_image"/><meta name="twitter:title" content="AI Edge | Jonathan Harris"/><meta name="twitter:description" content="{html.escape(description, quote=True)}"/><meta name="twitter:image" content="https://images.jonathan-harris.online/site-newsletter"/><script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script><script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script><script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script></head><body class="page-form-shell page-newsletter" data-page-type="newsletter">{render_header()}{body}{render_footer()}<script src="https://cdn.jotfor.ms/s/umd/latest/for-form-embed-handler.js"></script><script defer src="/assets/js/newsletter-jotform.min.js"></script><script defer src="/assets/js/funnel-events.min.js"></script><script defer src="/assets/js/site-ui.min.js"></script></body></html>'''
    p.write_text(page, encoding="utf-8")




def load_podcast_fallback(limit: int = 3) -> list[dict[str, str]]:
    path = DATA / "podcast-episodes.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError, json.JSONDecodeError):
        payload = []
    records: list[dict[str, str]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        slug = str(item.get("slug") or "").strip()
        if not title or not slug:
            continue
        records.append({k: str(item.get(k) or "").strip() for k in ("title", "slug", "summary", "date", "episode_url", "transcript_url")})
    return records[:limit]


def render_static_podcast_cards(records: list[dict[str, str]]) -> str:
    if not records:
        return '<p>Browse the platform links above or <a href="/transcripts/">the transcript archive</a> while the current RSS snapshot refreshes.</p>'
    cards: list[str] = []
    for item in records:
        title = html.escape(item["title"])
        slug = html.escape(item["slug"], quote=True)
        episode_url = html.escape(item.get("episode_url") or f'/podcast/episodes/{slug}/', quote=True)
        summary = html.escape(item.get("summary") or "Practical AI analysis from Turing’s Torch.")
        date = html.escape(item.get("date") or "")
        transcript = item.get("transcript_url") or ""
        transcript_link = f'<a class="button secondary" href="{html.escape(transcript, quote=True)}" data-placement="podcast_latest">Read transcript</a>' if transcript else ""
        eyebrow = f'<p class="eyebrow">{date}</p>' if date else ""
        cards.append(f'<article class="card podcast-latest-card" data-episode-slug="{slug}">{eyebrow}<h3>{title}</h3><p>{summary}</p><div class="actions"><a class="button" href="{episode_url}" data-placement="podcast_latest">Listen</a>{transcript_link}</div></article>')
    return '<div class="grid podcast-latest-grid">' + ''.join(cards) + '</div>'


def remove_legacy_newsletter_collection() -> None:
    """Collapse all public newsletter collection to the governed Jotform page."""
    pattern = re.compile(r'<div class="inline-newsletter" data-newsletter-shell data-newsletter-source="([^"]+)">[\s\S]*?</div>', re.I)
    script_patterns = [
        re.compile(r'\s*<script[^>]+src="/assets/js/newsletter-signup\.min\.js"[^>]*></script>', re.I),
        re.compile(r'\s*<script[^>]+src="/assets/js/newsletter-exit\.min\.js"[^>]*></script>', re.I),
    ]
    for path in ROOT.rglob("*.html"):
        if "node_modules" in path.parts:
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        changed = pattern.sub(lambda m: render_inline_newsletter_form(html.unescape(m.group(1))), body)
        for script_pattern in script_patterns:
            changed = script_pattern.sub("", changed)
        if changed != body:
            path.write_text(changed, encoding="utf-8")

def podcast_page() -> None:
    """Keep the landing useful to no-JS requesters while RSS remains the episode authority."""
    p = ROOT / "podcast" / "index.html"
    if not p.exists():
        return
    t = p.read_text(encoding="utf-8")
    topic_filters = '''<!-- GROWTH:PODCAST-TOPICS START -->
<section class="card podcast-card u-s21" aria-labelledby="podcast-topic-filter-heading">
<h2 id="podcast-topic-filter-heading">Browse episodes by topic</h2>
<p class="muted">Use the same podcast feed, filtered around the subject you are already interested in.</p>
<div class="jh-journey-actions"><a href="/evidence/eu-ai-act-article-50-transparency/">EU AI Act Article 50</a><a href="/podcast/?topic=finance">Finance</a><a href="/podcast/?topic=work">Work</a><a href="/podcast/?topic=governance">Governance</a><a href="/podcast/?topic=healthcare">Healthcare</a><a href="/podcast/?topic=agents">AI agents</a><a href="/podcast/?topic=deepfake">Deepfakes &amp; trust</a></div>
</section>
<!-- GROWTH:PODCAST-TOPICS END -->'''
    if "<!-- GROWTH:PODCAST-TOPICS START -->" in t:
        t = replace_between(t, "<!-- GROWTH:PODCAST-TOPICS START -->", "<!-- GROWTH:PODCAST-TOPICS END -->", topic_filters)
    elif '<section class="card podcast-card u-s21" aria-label="Podcast player">' in t:
        t = t.replace('<section class="card podcast-card u-s21" aria-label="Podcast player">', topic_filters + "\n\n" + '<section class="card podcast-card u-s21" aria-label="Podcast player">', 1)

    static_records = load_podcast_fallback(3)
    latest_cards = render_static_podcast_cards(static_records)
    latest = f'''<!-- GROWTH:PODCAST-LATEST START -->
<section class="card podcast-card u-s21" aria-labelledby="latest-three-episodes-heading">
<h2 id="latest-three-episodes-heading">Latest three episodes</h2>
<p class="muted">Current episode links come from the governed podcast RSS feed and remain available in the page HTML when enhanced players are unavailable.</p>
<div data-podcast-latest-server>{latest_cards}</div>
</section>
<!-- GROWTH:PODCAST-LATEST END -->'''
    if "<!-- GROWTH:PODCAST-LATEST START -->" in t:
        t = replace_between(t, "<!-- GROWTH:PODCAST-LATEST START -->", "<!-- GROWTH:PODCAST-LATEST END -->", latest)
    else:
        anchor = '<section class="card podcast-card u-s21" aria-label="Podcast player">'
        if anchor in t:
            t = t.replace(anchor, latest + "\n\n" + anchor, 1)
    t = re.sub(
        r'(<span data-latest-episode-title>).*?(</span>)',
        r"\1current episode\2",
        t, flags=re.S|re.I,
    )
    t = re.sub(
        r'(<strong data-latest-episode-title>).*?(</strong>)',
        r"\1Current Turing's Torch episode\2",
        t, flags=re.S|re.I,
    )
    t = re.sub(
        r'(<p class="muted" data-latest-episode-teaser>).*?(</p>)',
        r'\1The server-rendered episode list above provides the current titles and links even when the enhanced player is unavailable.\2',
        t, flags=re.S|re.I,
    )
    t = re.sub(
        r'<div class="responsive-media podcast-spotify-fallback">\s*<iframe[^>]+></iframe>\s*</div>',
        '<div class="responsive-media podcast-spotify-fallback" data-spotify-facade><button class="button secondary" type="button" data-spotify-load>Load Spotify player</button><p class="muted">Spotify loads only after you ask for it.</p></div>',
        t, flags=re.S|re.I,
    )
    # Elfsight is the intended primary on-page player because its configured widget
    # exposes the latest six episodes. Keep the exact embed in generated builds.
    elfsight_script = '<script src="https://elfsightcdn.com/platform.js" async></script>'
    elfsight_widget = '<div class="elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d" data-elfsight-app-lazy></div>'
    # Make regeneration idempotent: remove any prior loader before normalising the widget.
    t = re.sub(r'<script\s+src="https://elfsightcdn\.com/platform\.js"\s+async(?:="")?\s*></script>\s*', '', t, flags=re.I)
    t = re.sub(
        r'<div class="elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d"[^>]*>.*?</div>',
        elfsight_widget,
        t,
        flags=re.S | re.I,
    )
    if 'elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d' not in t:
        player_anchor = '<section class="card podcast-card u-s21" aria-label="Podcast player">'
        if player_anchor in t:
            t = t.replace(player_anchor, player_anchor + '\n<h2>Podcast Player</h2><p class="muted">Listen to the latest six episodes here.</p>\n' + elfsight_widget, 1)
    # The loader sits immediately before the widget and appears exactly once.
    t = t.replace(elfsight_widget, elfsight_script + '\n' + elfsight_widget, 1)
    # Elfsight is the visible six-episode player, not a disclosure/facade.
    t = re.sub(
        r'<details class="podcast-archive-widget">\s*<summary>.*?</summary>\s*(<!-- Elfsight Podcast Player \| Podcast Player -->\s*<script src="https://elfsightcdn\.com/platform\.js" async></script>\s*<div class="elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d" data-elfsight-app-lazy></div>)\s*</details>',
        r'\1',
        t, flags=re.S | re.I,
    )
    t = t.replace('<h2>Latest episode</h2>', '<h2>Podcast Player</h2>', 1)
    t = t.replace('The RSS-driven player is backed by the Spotify show embed below, so the page still has playable audio if the extended archive widget is blocked.', 'Use the six-episode player below, or choose Spotify, Apple Podcasts or RSS above.', 1)
    platform_hosts = {
        'open.spotify.com': 'spotify',
        'podcasts.apple.com': 'apple',
        'podcast-rss-feeds.jonathan-harris.online': 'rss',
    }
    for host, platform in platform_hosts.items():
        t = re.sub(
            rf'<a(?![^>]*data-podcast-platform)([^>]*href="https://{re.escape(host)}[^"]*"[^>]*)>',
            rf'<a\1 data-podcast-platform="{platform}" data-placement="podcast_header">',
            t,
            flags=re.I,
        )
    t = re.sub(r'"author":\{"@type":"Person","name":"Jonathan Harris","url":"https://jonathan-harris.online/bio/"\}', '"author":{"@id":"https://jonathan-harris.online/#person"}', t)
    if '/assets/js/podcast-facade.min.js' not in t:
        t = t.replace('</body>', '<script defer src="/assets/js/podcast-facade.min.js"></script>\n</body>')
    p.write_text(t, encoding="utf-8")

def add_static_newsletter_placements() -> None:
    targets = [(ROOT / "compare" / "index.html", "compare:index"), (ROOT / "podcast" / "index.html", "podcast:index")]
    for guide in sorted((ROOT / "topics").glob("*/index.html")):
        if guide.parent.name != "topics":
            targets.append((guide, f"topic-guide:{guide.parent.name}"))
    for p, source in targets:
        if not p.exists(): continue
        t = p.read_text(encoding="utf-8")
        marker = f'<!-- GROWTH:NEWSLETTER {source} -->'
        block = f'''{marker}<section class="card growth-newsletter-placement" aria-label="Newsletter sign-up">{render_inline_newsletter_form(source)}</section>'''
        if marker in t:
            t = re.sub(re.escape(marker) + r'<section class="card growth-newsletter-placement".*?</section>', block, t, flags=re.S)
        elif '</main>' in t:
            t = t.replace('</main>', block + '\n</main>', 1)
        p.write_text(t, encoding="utf-8")


def comparison_reading_paths() -> None:
    """Expose curated multi-book routes from the comparison hub without renaming stable /bundles/ URLs."""
    p = ROOT / "compare" / "index.html"
    if not p.exists():
        return
    t = p.read_text(encoding="utf-8")
    marker_start = '<!-- GROWTH:COMPARE-READING-PATHS START -->'
    marker_end = '<!-- GROWTH:COMPARE-READING-PATHS END -->'
    block = f'''{marker_start}
<section class="card" aria-labelledby="compare-reading-paths-heading">
<h2 id="compare-reading-paths-heading">Reading paths</h2>
<p>When a comparison opens up a wider decision, continue through a curated multi-book route. Each book is still purchased separately on Amazon.</p>
<div class="jh-journey-actions"><a href="/bundles/ai-at-work/">AI at Work</a><a href="/bundles/ai-health-and-care/">AI Health &amp; Care</a><a href="/bundles/ai-mobility-and-logistics/">AI Mobility &amp; Logistics</a><a href="/bundles/ai-in-regulated-industries/">AI in Regulated Industries</a></div>
</section>
{marker_end}'''
    if marker_start in t and marker_end in t:
        t = replace_between(t, marker_start, marker_end, block)
    elif '</main>' in t:
        t = t.replace('</main>', block + '\n</main>', 1)
    p.write_text(t, encoding="utf-8")


def topic_reading_paths() -> None:
    """Add only semantically defensible reading-path links to topic hubs."""
    mappings = {
        "ai-in-business": ("AI at Work", "/bundles/ai-at-work/"),
        "ai-in-healthcare": ("AI Health & Care", "/bundles/ai-health-and-care/"),
        "ai-in-finance": ("AI in Regulated Industries", "/bundles/ai-in-regulated-industries/"),
        "ai-ethics": ("AI in Regulated Industries", "/bundles/ai-in-regulated-industries/"),
        "robotics-automation": ("AI Mobility & Logistics", "/bundles/ai-mobility-and-logistics/"),
    }
    for slug, (label, href) in mappings.items():
        p = ROOT / "topics" / slug / "index.html"
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        marker_start = '<!-- GROWTH:TOPIC-READING-PATH START -->'
        marker_end = '<!-- GROWTH:TOPIC-READING-PATH END -->'
        evidence_href, episode_href, episode_label = TOPIC_CONTEXT_LINKS.get(
            slug, ("/evidence/", f"/podcast/?topic={slug}", "Turing’s Torch episodes for this topic")
        )
        block = f'''{marker_start}<section class="card topic-reading-path"><h2>Continue this topic</h2><p>This topic overlaps a curated route through several books. <a href="{href}">Continue with {html.escape(label)}</a>.</p><div class="jh-journey-actions"><a href="{html.escape(evidence_href, quote=True)}">Read the evidence guide</a><a href="{html.escape(episode_href, quote=True)}">Listen: {html.escape(episode_label)}</a><a href="/transcripts/">Browse transcripts</a><a href="/newsletter/">Join AI Edge</a></div></section>{marker_end}'''
        if marker_start in t and marker_end in t:
            t = replace_between(t, marker_start, marker_end, block)
        elif '</main>' in t:
            t = t.replace('</main>', block + '\n</main>', 1)
        p.write_text(t, encoding="utf-8")

    index = ROOT / "topics" / "index.html"
    if index.exists():
        t = index.read_text(encoding="utf-8")
        marker_start = '<!-- GROWTH:TOPICS-READING-PATHS START -->'
        marker_end = '<!-- GROWTH:TOPICS-READING-PATHS END -->'
        block = f'''{marker_start}<section class="card"><h2>Reading paths</h2><p>For decisions that span more than one topic, use a curated multi-book route.</p><div class="jh-journey-actions"><a href="/bundles/ai-at-work/">AI at Work</a><a href="/bundles/ai-health-and-care/">AI Health &amp; Care</a><a href="/bundles/ai-mobility-and-logistics/">AI Mobility &amp; Logistics</a><a href="/bundles/ai-in-regulated-industries/">AI in Regulated Industries</a></div></section>{marker_end}'''
        if marker_start in t and marker_end in t:
            t = replace_between(t, marker_start, marker_end, block)
        elif '</main>' in t:
            t = t.replace('</main>', block + '\n</main>', 1)
        index.write_text(t, encoding="utf-8")



PAGE_HERO_BRAND = '<a class="jh-page-hero__brand" href="/" aria-label="Jonathan Harris home"><img class="jh-page-hero__logo" src="https://images.jonathan-harris.online/site-logo" alt="Jonathan Harris" width="96" height="96" loading="eager" fetchpriority="high" decoding="async"/></a>'


def split_growth_hero(body: str) -> tuple[str, str]:
    """Lift the first generated hero out of the content wrap and give it the full shared brand treatment."""
    match = re.search(r'<header class="(?P<classes>[^"]*\bhero\b[^"]*)"(?P<attrs>[^>]*)>(?P<inner>[\s\S]*?)</header>', body, re.I)
    if not match:
        return "", body
    classes = match.group("classes").split()
    if "jh-page-hero" not in classes:
        classes.append("jh-page-hero")
    attrs = match.group("attrs")
    if "data-jh-header-reveal-anchor" not in attrs:
        attrs += " data-jh-header-reveal-anchor"
    inner = match.group("inner").strip()
    if 'class="wrap"' in inner[:120]:
        inner = re.sub(r'(<div class="wrap"[^>]*>)', r'\1' + PAGE_HERO_BRAND, inner, count=1, flags=re.I)
    else:
        inner = f'<div class="wrap">{PAGE_HERO_BRAND}{inner}</div>'
    hero = f'<header class="{" ".join(classes)}"{attrs}>{inner}</header>'
    rest = body[:match.start()] + body[match.end():]
    return hero, rest

def base_page(title: str, description: str, canonical: str, body: str, page_type: str) -> str:
    hero, content = split_growth_hero(body)
    safe_type = re.sub(r"[^a-z0-9_-]+", "-", page_type.lower()).strip("-")
    return f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/><title>{html.escape(title)} | Jonathan Harris</title><meta name="description" content="{html.escape(description, quote=True)}"/><link rel="canonical" href="{canonical}"/><meta name="robots" content="index,follow"/>{FONT_HEAD}<link rel="stylesheet" href="/assets/css/site.css"/><script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script><script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script></head><body class="jh-growth-page page-{safe_type}" data-page-type="{page_type}">{render_header()}{hero}<main class="main" id="main"><div class="wrap">{content}</div></main>{render_footer()}<script defer src="/assets/js/site-ui.min.js"></script></body></html>'''


def render_book_finder_module(source: str, *, heading: str = "Not sure which book fits?") -> str:
    safe_source = html.escape(source, quote=True)
    return f'''<section class="card book-finder-bridge"><h2>{html.escape(heading)}</h2><p>Use the rule-based book finder to narrow the 40-book catalogue by the problem you are actually trying to solve.</p><a class="button secondary" href="/book-finder/?source={safe_source}" data-book-finder-bridge data-placement="{safe_source}">Find the right AI book</a></section>'''


def generate_glossary_download_page() -> None:
    body = '''<header class="hero"><h1>Your AI glossary cheat sheet</h1><p>12 useful AI terms in plain English, with the full site glossary one click away when you need more.</p></header>
<section class="card lead-magnet-sheet"><h2>Download the PDF</h2><p>The PDF is a one-page reference you can save locally, print or share with colleagues.</p><p><a class="button" href="/downloads/ai-glossary-cheat-sheet/ai-glossary-cheat-sheet.pdf" download>Download the AI glossary PDF</a> <a class="button secondary" href="/glossary/">Open the full glossary</a></p><p class="muted">Subscribed via AI Edge? This is the same glossary resource promised on the sign-up page. No email scavenger hunt required.</p></section>
<section class="card"><h2>What is inside?</h2><dl class="lead-magnet-definitions"><dt>Artificial intelligence</dt><dd>Software designed to perform tasks that normally require human judgement, pattern recognition or decision-making.</dd><dt>Machine learning</dt><dd>AI systems that learn patterns from data rather than relying only on hand-written rules.</dd><dt>Large language model</dt><dd>A model trained on large amounts of text to predict and generate language.</dd><dt>Generative AI</dt><dd>AI that creates new text, images, audio, video or code from learned patterns.</dd><dt>AI agent</dt><dd>A system that can plan and take a sequence of actions towards a goal, often using tools.</dd><dt>Human in the loop</dt><dd>A workflow where a person reviews, approves or corrects important AI decisions.</dd></dl><p><a href="/glossary/">See the full A-Z glossary</a></p></section>'''
    out = ROOT / "downloads" / "ai-glossary-cheat-sheet"; out.mkdir(parents=True, exist_ok=True)
    page = base_page("AI glossary cheat sheet download", "Download the free AI Edge plain-English AI glossary cheat sheet.", f"{SITE_URL}/downloads/ai-glossary-cheat-sheet/", body, "lead_magnet")
    (out / "index.html").write_text(page, encoding="utf-8")


def generate_methodology() -> None:
    body = '''<header class="hero"><h1>Editorial and evidence methodology</h1><p>How sources are selected, claims are checked, updates are dated and corrections are handled across Jonathan Harris’s AI books, evidence guides, podcast support pages and practical resources.</p></header>
<section class="card"><h2>Source hierarchy</h2><p>Primary and official sources come first where they exist: legislation, regulators, government research, standards bodies, original research and first-party technical documentation. Secondary reporting is useful for context, but it should not silently replace the underlying source when the original is available.</p></section>
<section class="card"><h2>Claims, dates and scope</h2><p>Time-sensitive evidence pages carry a last-reviewed date. Factual claims should be tied to a named source and publication date. Commentary, interpretation and practical judgement are kept distinct from claims presented as sourced fact.</p></section>
<section class="card"><h2>AI-assisted workflow</h2><p>Where software or AI assists drafting, extraction or transformation, the published factual claim should still be checked against source material. AI output is not treated as a source merely because it sounds confident.</p></section>
<section class="card"><h2>Limitations and counterpoints</h2><p>Evidence pages include meaningful limitations and a counterpoint where the underlying issue has material uncertainty, jurisdictional differences or credible competing interpretations. The goal is useful judgement, not certainty theatre.</p></section>
<section class="card"><h2>Corrections</h2><p>If a factual error, broken citation or materially outdated claim is identified, use the <a href="/contact/">contact page</a> with the page URL and supporting source. Corrections should be made at the source page rather than hidden in a separate changelog nobody reads.</p></section>
<section class="jh-journey-panel"><h2>Use the evidence</h2><div class="jh-journey-actions"><a href="/evidence/">Evidence guides</a><a href="/resources/">Practical checklists</a><a href="/book-finder/">Book finder</a></div></section>'''
    out = ROOT / "methodology"; out.mkdir(exist_ok=True)
    (out / "index.html").write_text(base_page("Editorial and evidence methodology", "How Jonathan Harris selects sources, separates evidence from commentary, dates reviews and handles corrections.", f"{SITE_URL}/methodology/", body, "methodology"), encoding="utf-8")


def generate_high_value_pages() -> None:
    pages = {
        "for-teams": (
            "AI for teams",
            "Practical AI literacy and reading paths for managers and teams without a giant consultancy engagement.",
            '''<header class="hero"><h1>Practical AI for teams</h1><p>For organisations that need colleagues to use AI with better judgement, clearer data boundaries and less hype.</p></header><section class="card"><h2>Useful starting points</h2><ul><li>Role-appropriate AI literacy and verification habits.</li><li>Reading paths for managers, regulated teams and practical adopters.</li><li>Evidence-backed checklists that can support internal discussion and training.</li></ul></section><section class="card"><h2>For a team or organisation</h2><p>Use the contact route to discuss bulk reading, internal briefings or a focused session around the AI questions your team is actually dealing with. Scope and format can be agreed before anything commercial is committed.</p><a class="button" href="/contact/?subject=teams">Discuss a team requirement</a></section><section class="jh-journey-panel"><h2>Start with the public material</h2><div class="jh-journey-actions"><a href="/evidence/workplace-ai-literacy/">Workplace AI literacy</a><a href="/resources/uk-workplace-ai-literacy-checklist/">Manager checklist</a><a href="/bundles/ai-at-work/">AI at Work reading path</a></div></section>'''
        ),
        "media": (
            "Media and speaking",
            "Jonathan Harris media, podcast guest and speaking enquiries on practical artificial intelligence.",
            '''<header class="hero"><img src="https://images.jonathan-harris.online/headshot" alt="Jonathan Harris, AI author and podcast host" class="bio-headshot" loading="eager" fetchpriority="high" width="180" height="180"/><h1>Media and speaking</h1><p>Jonathan Harris is an AI author and host of Turing’s Torch: AI Weekly, focused on practical artificial intelligence without the hype layer.</p><p><a href="https://images.jonathan-harris.online/headshot" target="_blank" rel="noopener">Open the press headshot</a></p></header><section class="card"><h2>Useful discussion areas</h2><ul><li>AI literacy and the future of work.</li><li>AI governance, regulation and accountability.</li><li>Agentic AI, automation and ordinary business workflows.</li><li>Deepfakes, synthetic media and trust.</li><li>AI adoption across healthcare, finance, law and industry.</li></ul></section><section class="card"><h2>Short biography</h2><p>Jonathan Harris is an artificial intelligence author and host of Turing’s Torch: AI Weekly. His work focuses on explaining practical AI, its trade-offs and its effect on ordinary work and regulated industries in plain English.</p></section><section class="card"><h2>Background material</h2><p>For current work and supporting material, use the <a href="/bio/">author page</a>, <a href="/ebooks/">book catalogue</a>, <a href="/podcast/">podcast</a>, <a href="/transcripts/">transcript archive</a> and <a href="/evidence/">evidence guides</a>.</p><a class="button" href="/contact/?subject=media">Media or speaking enquiry</a></section>'''
        ),
        "contribute": (
            "Contribute a case study",
            "Submit a sourced AI case-study idea for possible consideration in Jonathan Harris’s podcast and editorial work.",
            '''<header class="hero"><h1>Contribute an AI case study</h1><p>Have a real deployment, result or failure worth examining? Start with evidence rather than a sales deck.</p></header><section class="card"><h2>What makes a useful submission</h2><ul><li>A concise description of what was deployed and for whom.</li><li>Source URLs that can be checked independently.</li><li>Measured outcomes, including the awkward numbers rather than only the flattering ones.</li><li>Known limitations, trade-offs or failures.</li><li>Confirmation that you have permission to share the material you submit.</li></ul></section><section class="card"><h2>Initial review route</h2><p>Use the contact page for the first pass and include the relevant public URLs. Files or additional evidence can be requested after that initial review, which avoids creating an ungoverned public upload bucket.</p><a class="button" href="/contact/?subject=case-study">Submit a case-study idea</a></section><section class="card"><h2>What happens next</h2><p>Submissions are reviewed for relevance, evidence quality and whether they add something useful to the audience. Submission does not guarantee podcast or editorial inclusion.</p></section>'''
        ),
    }
    for slug, (title, description, body) in pages.items():
        out = ROOT / slug; out.mkdir(exist_ok=True)
        (out / "index.html").write_text(base_page(title, description, f"{SITE_URL}/{slug}/", body + render_book_finder_module(slug), slug.replace('-', '_')), encoding="utf-8")


def generate_evidence() -> None:
    payload = json.loads((DATA / "evidence-content.json").read_text(encoding="utf-8"))
    out = ROOT / "evidence"; out.mkdir(exist_ok=True)
    cards=[]
    for item in payload["items"]:
        slug=item["slug"]; canonical=f"{SITE_URL}/evidence/{slug}/"
        questions=''.join(f'<section class="card evidence-answer"><h2>{html.escape(q["q"])}</h2><p>{html.escape(q["a"])}</p></section>' for q in item["questions"])
        rows=''.join(
            '<tr><td>{claim}</td><td>{org}</td><td>{date}</td><td><a href="{url}" rel="noopener">Primary source</a></td></tr>'.format(
                claim=html.escape(st["claim"]), org=html.escape(st["source"]["organisation"]),
                date=html.escape(st["source"]["publication_date"]), url=html.escape(st["source"]["url"], quote=True),
            ) for st in item["stats"]
        )
        sources=''.join(f'<li><strong>{html.escape(src["organisation"])}</strong> · {html.escape(src["title"])} · {html.escape(src["publication_date"])} · <a href="{html.escape(src["url"], quote=True)}" rel="noopener">Primary source</a></li>' for src in item["sources"])
        related=''.join(f'<a href="{html.escape(url, quote=True)}">{html.escape(url.strip("/").replace("-"," ").replace("/"," · ").title() or "Home")}</a>' for url in item["related"])
        body=f'''<header class="hero"><h1>{html.escape(item['title'])}</h1><p>{html.escape(item['summary'])}</p><p class="muted">Last reviewed {html.escape(item['last_reviewed'])} · <a href="/methodology/">Editorial methodology</a></p></header>{questions}<section class="card"><h2>What does the current evidence say?</h2><div class="table-scroll"><table class="evidence-claim-table"><thead><tr><th scope="col">Claim</th><th scope="col">Source organisation</th><th scope="col">Date</th><th scope="col">Evidence</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class="card"><h2>Limitations</h2><p>{html.escape(item['limitations'])}</p><h2>A counterpoint worth keeping</h2><p>{html.escape(item['counterpoint'])}</p></section><section class="card"><h2>Sources and provenance</h2><ul class="evidence-sources">{sources}</ul><p><a href="/methodology/">How evidence is selected and checked</a></p></section><section class="jh-journey-panel"><h2>Continue the evidence trail</h2><div class="jh-journey-actions">{related}{render_contextual_podcast_link(slug)}</div></section>{render_book_finder_module(f"evidence-{slug}")}{render_inline_newsletter_form(f"evidence:{slug}")}'''
        d=out/slug; d.mkdir(parents=True,exist_ok=True); (d/'index.html').write_text(base_page(item['title'],item['summary'],canonical,body,'evidence'),encoding='utf-8')
        cards.append(f'<article class="card"><h2><a href="/evidence/{html.escape(slug)}/">{html.escape(item["title"])}</a></h2><p>{html.escape(item["summary"])}</p></article>')
    body='<header class="hero"><h1>AI evidence guides</h1><p>Answer-first guides built around primary sources, limitations and practical decisions rather than another layer of search-engine porridge.</p><p><a href="/methodology/">Read the editorial and evidence methodology</a></p></header><section class="grid">'+''.join(cards)+'</section>'+render_book_finder_module('evidence-index')
    (out/'index.html').write_text(base_page('AI evidence guides','Source-backed AI evidence guides on workplace literacy, agents, small business, deepfakes, healthcare, finance and governance.',f'{SITE_URL}/evidence/',body,'evidence_index'),encoding='utf-8')


def generate_resources() -> None:
    payload=json.loads((DATA/'resource-content.json').read_text(encoding='utf-8')); out=ROOT/'resources'; out.mkdir(exist_ok=True); cards=[]
    for item in payload['items']:
        slug=item['slug']; sections=''
        for heading, bullets in item['sections']:
            sections += f'<section class="card"><h2>{html.escape(heading)}</h2><ul class="checklist">'+''.join(f'<li>{html.escape(x)}</li>' for x in bullets)+'</ul></section>'
        sources=''.join(f'<li><strong>{html.escape(src["organisation"])}</strong> · {html.escape(src["title"])} · {html.escape(src["publication_date"])} · <a href="{html.escape(src["url"])}" rel="noopener">Primary source</a></li>' for src in item['sources'])
        related=''.join(f'<a href="{html.escape(url)}">{html.escape(url.strip("/").replace("-"," ").replace("/"," · ").title())}</a>' for url in item['related'])
        body=f'<header class="hero"><h1>{html.escape(item["title"])}</h1><p>{html.escape(item["summary"])}</p><p class="muted">Last reviewed {html.escape(item.get("last_reviewed", ""))} · <a href="/methodology/">Editorial methodology</a></p></header>{sections}<section class="card"><h2>Evidence behind this checklist</h2><ul>{sources}</ul><p><a href="/methodology/">How evidence is selected and checked</a></p></section><section class="jh-journey-panel"><h2>Related reading</h2><div class="jh-journey-actions">{related}</div></section>{render_book_finder_module(f"resource-{slug}")}{render_inline_newsletter_form(f"resource:{slug}")}'
        d=out/slug; d.mkdir(parents=True,exist_ok=True); (d/'index.html').write_text(base_page(item['title'],item['summary'],f'{SITE_URL}/resources/{slug}/',body,'resource'),encoding='utf-8')
        cards.append(f'<article class="card"><h2><a href="/resources/{html.escape(slug)}/">{html.escape(item["title"])}</a></h2><p>{html.escape(item["summary"])}</p></article>')
    body='<header class="hero"><h1>Practical AI checklists</h1><p>Useful HTML first: checklists for workplace literacy, deepfake verification, procurement, responsible management, agent risk and regulated-industry evidence.</p><p><a href="/methodology/">Read the editorial and evidence methodology</a></p></header><section class="grid">'+''.join(cards)+'</section>'+render_book_finder_module('resources-index')
    (out/'index.html').write_text(base_page('Practical AI checklists','Indexable AI checklists for managers, small businesses and regulated teams.',f'{SITE_URL}/resources/',body,'resource_index'),encoding='utf-8')


def generate_book_finder() -> None:
    body='''<header class="hero"><h1>Find the right AI book</h1><p>A deterministic, rule-based finder. No pretend mind-reading, no model recommendation theatre.</p></header><section class="card"><form id="book-finder-form"><label for="book-finder-goal"><strong>What are you trying to solve?</strong></label><select id="book-finder-goal" name="goal" required><option value="">Choose a starting point</option><option value="work">Work, careers or AI literacy</option><option value="agents">Automating ordinary work with agents</option><option value="business">Small business and practical adoption</option><option value="healthcare">Healthcare and care services</option><option value="regulated">Law, finance or regulated decisions</option><option value="trust">Deepfakes, scams, security or trust</option><option value="fundamentals">AI fundamentals and history</option></select><button class="button" type="submit">Show me the best starting books</button></form></section><section class="card" id="book-finder-results" aria-live="polite"><h2>Your starting books</h2><p>Choose a problem above. Results are ranked by explicit topic and catalogue rules, not a personalisation model.</p></section><noscript><section class="card"><h2>JavaScript off?</h2><p>Use the <a href="/bundles/">reading paths</a> or <a href="/ebooks/">full catalogue</a>. Nothing essential is locked behind animation.</p></section></noscript>'''
    out=ROOT/'book-finder'; out.mkdir(exist_ok=True); page=base_page('Find the right AI book','A deterministic book finder based on reader problem, role and topic.',f'{SITE_URL}/book-finder/',body,'book_finder').replace('</body>','<script defer src="/assets/js/book-finder.min.js"></script></body>')
    (out/'index.html').write_text(page,encoding='utf-8')


def normalise_ai_edge_naming() -> None:
    """Enforce AI Edge naming without cadence or read-time promises."""
    replacements = {
        "AI Edge - a daily weekday newsletter": "AI Edge, the practical AI briefing",
        "AI Edge — a daily weekday newsletter": "AI Edge, the practical AI briefing",
        "AI Edge – a daily weekday newsletter": "AI Edge, the practical AI briefing",
        "AI Edge - a daily AI newsletter": "AI Edge, the practical AI briefing",
        "AI Edge — a daily AI newsletter": "AI Edge, the practical AI briefing",
        "AI Edge, the three-minute weekday briefing": "AI Edge, the practical AI briefing",
        "AI Edge, the three-minute weekday AI briefing": "AI Edge, the practical AI briefing",
        "three-minute weekday AI briefing": "practical AI briefing",
        "three-minute weekday briefing": "practical AI briefing",
        "3-minute AI briefing": "practical AI briefing",
        "3-minute briefing": "practical AI briefing",
        "tomorrow’s 3-minute AI briefing": "AI Edge briefing",
        "One useful weekday briefing": "One useful AI briefing",
        "A useful weekday AI briefing": "A useful AI briefing",
        "weekday AI briefing": "practical AI briefing",
        "weekday briefing": "practical AI briefing",
        "Weekday briefing": "Practical AI briefing",
        "daily AI newsletter": "AI Edge briefing",
        "daily weekday newsletter": "AI Edge briefing",
        "Publisher of AI Edge, a daily weekday artificial intelligence newsletter": "Publisher of AI Edge, a practical artificial intelligence briefing",
        "daily weekday AI newsletter for business leaders and professionals": "AI Edge briefing for business leaders and professionals",
        'aria-label="Daily newsletter"': 'aria-label="AI Edge"',
        "This is a <strong>daily weekday</strong> newsletter.": "AI Edge is a practical briefing.",
        "Subscribe to the Daily Newsletter": "Join AI Edge",
        '"The newsletter is daily weekday — one sharp briefing, no waffle. It is the quickest way I have found to keep up with AI without losing an afternoon."': '"AI Edge is one sharp briefing, no waffle. It is a useful way to keep up with AI without losing an afternoon."',
        "AI Edge daily newsletter": "AI Edge practical briefing",
        "AI Edge when you want the tighter weekday line": "AI Edge when you want the tighter briefing",
        "Get daily AI updates": "Explore AI Edge",
    }
    text_suffixes = {".html", ".json", ".txt", ".md", ".js"}
    for page in ROOT.rglob("*"):
        if not page.is_file() or page.suffix.lower() not in text_suffixes:
            continue
        if any(part.startswith(".") for part in page.relative_to(ROOT).parts):
            continue
        text = page.read_text(encoding="utf-8", errors="ignore")
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            page.write_text(updated, encoding="utf-8")


def footer_navigation() -> None:
    p=ROOT/'assets/partials/footer.html'; t=p.read_text(encoding='utf-8')
    additions = [
        ('<li><a href="/compare/">Comparisons</a></li>', [
            '<li><a href="/bundles/">Reading paths</a></li>',
            '<li><a href="/evidence/">Evidence guides</a></li>',
            '<li><a href="/resources/">Checklists</a></li>',
        ]),
        ('<li><a href="/contact/">Contact</a></li>', [
            '<li><a href="/for-teams/">AI for teams</a></li>',
            '<li><a href="/media/">Media &amp; speaking</a></li>',
            '<li><a href="/contribute/">Contribute a case study</a></li>',
        ]),
        ('<li><a href="/api/docs/">API docs</a></li>', [
            '<li><a href="/methodology/">Editorial methodology</a></li>',
        ]),
    ]
    for anchor, lines in additions:
        missing = [line for line in lines if line not in t]
        if missing and anchor in t:
            t=t.replace(anchor, anchor + '\n' + '\n'.join(missing), 1)
    p.write_text(t,encoding='utf-8')


def main() -> int:
    books=load_master(); count=len(books)
    sync_book_counts(count)
    footer_navigation()
    homepage(count)
    benefit_newsletter_copy()
    podcast_page()
    generate_glossary_download_page(); generate_methodology(); generate_high_value_pages()
    generate_evidence(); generate_resources(); generate_book_finder()
    add_static_newsletter_placements()
    remove_legacy_newsletter_collection()
    comparison_reading_paths()
    topic_reading_paths()
    normalise_ai_edge_naming()
    evidence_count = len(json.loads((DATA / "evidence-content.json").read_text(encoding="utf-8"))["items"])
    resource_count = len(json.loads((DATA / "resource-content.json").read_text(encoding="utf-8"))["items"])
    print(f"Growth assets generated from {count} governed books: {evidence_count} evidence guides, {resource_count} resources, book finder and commercial router.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
