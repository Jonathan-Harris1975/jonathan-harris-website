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

DATA = ROOT / "data"
FONT_HEAD = '''<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap" rel="stylesheet"/>'''


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


def homepage(count: int) -> None:
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8")
    hero = f'''<!-- GROWTH:HERO START -->
<section aria-labelledby="hero-heading" class="hero hero--home hero--commercial" role="region">
<div class="wrap">
<img alt="Jonathan Harris" class="logo-plain logo-plain--hero" fetchpriority="high" height="96" loading="eager" src="https://images.jonathan-harris.online/site-logo" width="96"/>
<h1 class="hero__title" id="hero-heading">Practical AI books and analysis, without the hype</h1>
<p class="hero__lead">Explore {count} plain-English AI books, Turing’s Torch weekly analysis and AI Edge, the three-minute weekday briefing.</p>
<div class="cta-row"><a class="button" href="/book-finder/">Find the right AI book</a><a class="button secondary" href="#home-newsletter-hero">Get the free AI glossary</a></div>
<p class="home-podcast-text-link"><a href="/podcast/">Listen to the latest Turing’s Torch →</a></p>
<div class="home-trust-strip" aria-label="Publishing scale"><span>{count} books</span><span>Weekly podcast</span><span>Weekday briefing</span><span>Plain-English AI</span></div>
<div class="home-intent" aria-labelledby="home-intent-heading"><h2 id="home-intent-heading">Start with your problem</h2><nav aria-label="Choose an AI route"><a href="/bundles/ai-at-work/">Work &amp; careers</a><a href="/catalogue/business/">Business</a><a href="/bundles/ai-health-and-care/">Healthcare</a><a href="/bundles/ai-in-regulated-industries/">Law &amp; regulation</a><a href="/catalogue/finance/">Finance</a><a href="/topics/ai-for-beginners/">AI fundamentals</a><a href="/blog/">Current AI news</a></nav></div>
<div id="home-newsletter-hero">{render_inline_newsletter_form("homepage:hero")}</div>
</div>
</section>
<!-- GROWTH:HERO END -->'''
    if "<!-- GROWTH:HERO START -->" in text:
        text = replace_between(text, "<!-- GROWTH:HERO START -->", "<!-- GROWTH:HERO END -->", hero)
    else:
        match = re.search(r'<section aria-labelledby="hero-heading" class="hero hero--home" role="region">.*?</section>', text, flags=re.S)
        if not match:
            raise RuntimeError("Homepage hero block not found")
        text = text[:match.start()] + hero + text[match.end():]

    growth = f'''<!-- GROWTH:ROUTER START -->
<section class="main home-commercial-router" aria-labelledby="home-commercial-heading">
<div class="wrap">
<section class="card answer-first"><h2 id="home-commercial-heading">What is the quickest route to the useful bit?</h2><p>Start with the <a href="/book-finder/">book finder</a> when you have a problem to solve, use the evidence guides when you need sources, or take a reading path when one book will not cover the whole decision. The podcast and newsletter handle the moving story.</p></section>
<section class="card" id="home-newsletter-inline"><h2>Get the useful update without another tab safari</h2>{render_inline_newsletter_form("homepage:inline")}</section>
<section class="card home-latest-podcast" aria-labelledby="home-latest-podcast-heading"><h2 id="home-latest-podcast-heading">Latest Turing’s Torch</h2><div data-podcast-latest-server><p>Current episode details are supplied from the governed podcast RSS feed at request time. <a href="/podcast/">Open the podcast</a> or <a href="/transcripts/">browse transcripts</a>.</p></div></section>
<section class="card" aria-labelledby="home-reading-paths-heading"><h2 id="home-reading-paths-heading">Reading paths</h2><p>Curated routes through books that belong together. The books are still bought separately on Amazon.</p><div class="jh-journey-actions"><a href="/bundles/ai-at-work/">AI at Work</a><a href="/bundles/ai-health-and-care/">AI Health &amp; Care</a><a href="/bundles/ai-mobility-and-logistics/">AI Mobility &amp; Logistics</a><a href="/bundles/ai-in-regulated-industries/">AI in Regulated Industries</a></div></section>
<section class="card" aria-labelledby="home-evidence-heading"><h2 id="home-evidence-heading">Evidence, not vibes</h2><p>Source-backed guides on workplace AI literacy, agents, small business, deepfakes, healthcare, finance and governance.</p><div class="jh-journey-actions"><a href="/evidence/">Browse evidence guides</a><a href="/resources/">Use practical checklists</a></div></section>
</div></section>
<!-- GROWTH:ROUTER END -->'''
    if "<!-- GROWTH:ROUTER START -->" in text:
        text = replace_between(text, "<!-- GROWTH:ROUTER START -->", "<!-- GROWTH:ROUTER END -->", growth)
    else:
        text = text.replace('<main id="main" role="main">', '<main id="main" role="main">\n' + growth, 1)
    # Canonical Person/WebSite identity on the static home page.
    text = text.replace('"@id": "https://jonathan-harris.online/#person",\n  "name": "Jonathan Harris",\n  "url": "https://jonathan-harris.online/",', '"@id": "https://jonathan-harris.online/#person",\n  "name": "Jonathan Harris",\n  "url": "https://jonathan-harris.online/bio/",', 1)
    text = text.replace('"publisher": {"@id": "https://jonathan-harris.online/#organisation"},', '"publisher": {"@id": "https://jonathan-harris.online/#person"},')
    path.write_text(text, encoding="utf-8")


def benefit_newsletter_copy() -> None:
    p = ROOT / "newsletter" / "index.html"
    if not p.exists(): return
    t = p.read_text(encoding="utf-8")
    t = re.sub(r'>Join the newsletter<', '>Get my free AI glossary<', t, flags=re.I)
    t = re.sub(r'>Subscribe Free<', '>Send me the briefing + glossary<', t, flags=re.I)
    t = re.sub(r'>Subscribe free<', '>Send me the briefing + glossary<', t, flags=re.I)
    p.write_text(t, encoding="utf-8")



def podcast_page() -> None:
    """Keep the landing useful to no-JS requesters while RSS remains the episode authority."""
    p = ROOT / "podcast" / "index.html"
    if not p.exists():
        return
    t = p.read_text(encoding="utf-8")
    latest = '''<!-- GROWTH:PODCAST-LATEST START -->
<section class="card podcast-card u-s21" aria-labelledby="latest-three-episodes-heading">
<h2 id="latest-three-episodes-heading">Latest three episodes</h2>
<p class="muted">Episode facts stay governed by the podcast RSS pipeline. This block is populated from that feed by the same-origin Pages Function before the HTML response is returned.</p>
<div data-podcast-latest-server><p>Latest episode details are temporarily unavailable. Use the platform links above or <a href="/transcripts/">browse the transcript archive</a>.</p></div>
</section>
<!-- GROWTH:PODCAST-LATEST END -->'''
    if "<!-- GROWTH:PODCAST-LATEST START -->" in t:
        t = replace_between(t, "<!-- GROWTH:PODCAST-LATEST START -->", "<!-- GROWTH:PODCAST-LATEST END -->", latest)
    else:
        anchor = '<section class="card podcast-card u-s21" aria-label="Podcast player">'
        if anchor in t:
            t = t.replace(anchor, latest + "\n\n" + anchor, 1)
    t = re.sub(
        r'<div class="responsive-media podcast-spotify-fallback">\s*<iframe[^>]+></iframe>\s*</div>',
        '<div class="responsive-media podcast-spotify-fallback" data-spotify-facade><button class="button secondary" type="button" data-spotify-load>Load Spotify player</button><p class="muted">Spotify loads only after you ask for it.</p></div>',
        t, flags=re.S|re.I,
    )
    t = t.replace('<script src="https://elfsightcdn.com/platform.js" async></script>\n<div class="elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d" data-elfsight-app-lazy></div>', '<div class="elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d" data-elfsight-app-lazy data-elfsight-deferred><button class="button secondary" type="button" data-elfsight-load>Load extended player</button></div>')
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
        block = f'''{marker_start}<section class="card topic-reading-path"><h2>Reading path</h2><p>This topic overlaps a curated route through several books. <a href="{href}">Continue with {html.escape(label)}</a>.</p></section>{marker_end}'''
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


def base_page(title: str, description: str, canonical: str, body: str, page_type: str) -> str:
    return f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/><title>{html.escape(title)} | Jonathan Harris</title><meta name="description" content="{html.escape(description, quote=True)}"/><link rel="canonical" href="{canonical}"/><meta name="robots" content="index,follow"/>{FONT_HEAD}<link rel="stylesheet" href="/assets/css/site.css"/><script data-jh-ai-pack="person" type="application/ld+json">{json_script(build_person_schema())}</script><script data-jh-ai-pack="website" type="application/ld+json">{json_script(build_website_schema())}</script></head><body data-page-type="{page_type}">{render_header()}<main class="main" id="main"><div class="wrap">{body}</div></main>{render_footer()}<script defer src="/assets/js/newsletter-signup.min.js"></script><script defer src="/assets/js/site-ui.min.js"></script></body></html>'''


def generate_evidence() -> None:
    payload = json.loads((DATA / "evidence-content.json").read_text(encoding="utf-8"))
    out = ROOT / "evidence"; out.mkdir(exist_ok=True)
    cards=[]
    for item in payload["items"]:
        slug=item["slug"]; canonical=f"{SITE_URL}/evidence/{slug}/"
        questions=''.join(f'<section class="card evidence-answer"><h2>{html.escape(q["q"])}</h2><p>{html.escape(q["a"])}</p></section>' for q in item["questions"])
        stats=''.join(f'<li>{html.escape(st["claim"])} <a href="{html.escape(st["source"]["url"])}" rel="noopener">Source</a></li>' for st in item["stats"])
        sources=''.join(f'<li><strong>{html.escape(src["organisation"])}</strong> · {html.escape(src["title"])} · {html.escape(src["publication_date"])} · <a href="{html.escape(src["url"])}" rel="noopener">Primary source</a></li>' for src in item["sources"])
        related=''.join(f'<a href="{html.escape(url)}">{html.escape(url.strip("/").replace("-"," ").replace("/"," · ").title() or "Home")}</a>' for url in item["related"])
        body=f'''<header class="hero"><h1>{html.escape(item['title'])}</h1><p>{html.escape(item['summary'])}</p><p class="muted">Last reviewed {html.escape(item['last_reviewed'])}</p></header>{questions}<section class="card"><h2>What does the current evidence say?</h2><ul>{stats}</ul></section><section class="card"><h2>Limitations</h2><p>{html.escape(item['limitations'])}</p><h2>A counterpoint worth keeping</h2><p>{html.escape(item['counterpoint'])}</p></section><section class="card"><h2>Sources and provenance</h2><ul class="evidence-sources">{sources}</ul></section><section class="jh-journey-panel"><h2>Continue the evidence trail</h2><div class="jh-journey-actions">{related}</div></section>{render_inline_newsletter_form(f"evidence:{slug}")}'''
        d=out/slug; d.mkdir(parents=True,exist_ok=True); (d/'index.html').write_text(base_page(item['title'],item['summary'],canonical,body,'evidence'),encoding='utf-8')
        cards.append(f'<article class="card"><h2><a href="/evidence/{html.escape(slug)}/">{html.escape(item["title"])}</a></h2><p>{html.escape(item["summary"])}</p></article>')
    body='<header class="hero"><h1>AI evidence guides</h1><p>Answer-first guides built around primary sources, limitations and practical decisions rather than another layer of search-engine porridge.</p></header><section class="grid">'+''.join(cards)+'</section>'
    (out/'index.html').write_text(base_page('AI evidence guides','Source-backed AI evidence guides on workplace literacy, agents, small business, deepfakes, healthcare, finance and governance.',f'{SITE_URL}/evidence/',body,'evidence_index'),encoding='utf-8')


def generate_resources() -> None:
    payload=json.loads((DATA/'resource-content.json').read_text(encoding='utf-8')); out=ROOT/'resources'; out.mkdir(exist_ok=True); cards=[]
    for item in payload['items']:
        slug=item['slug']; sections=''
        for heading, bullets in item['sections']:
            sections += f'<section class="card"><h2>{html.escape(heading)}</h2><ul class="checklist">'+''.join(f'<li>{html.escape(x)}</li>' for x in bullets)+'</ul></section>'
        sources=''.join(f'<li><strong>{html.escape(src["organisation"])}</strong> · {html.escape(src["title"])} · {html.escape(src["publication_date"])} · <a href="{html.escape(src["url"])}" rel="noopener">Primary source</a></li>' for src in item['sources'])
        related=''.join(f'<a href="{html.escape(url)}">{html.escape(url.strip("/").replace("-"," ").replace("/"," · ").title())}</a>' for url in item['related'])
        body=f'<header class="hero"><h1>{html.escape(item["title"])}</h1><p>{html.escape(item["summary"])}</p></header>{sections}<section class="card"><h2>Evidence behind this checklist</h2><ul>{sources}</ul></section><section class="jh-journey-panel"><h2>Related reading</h2><div class="jh-journey-actions">{related}</div></section>{render_inline_newsletter_form(f"resource:{slug}")}'
        d=out/slug; d.mkdir(parents=True,exist_ok=True); (d/'index.html').write_text(base_page(item['title'],item['summary'],f'{SITE_URL}/resources/{slug}/',body,'resource'),encoding='utf-8')
        cards.append(f'<article class="card"><h2><a href="/resources/{html.escape(slug)}/">{html.escape(item["title"])}</a></h2><p>{html.escape(item["summary"])}</p></article>')
    body='<header class="hero"><h1>Practical AI checklists</h1><p>Useful HTML first: checklists for workplace literacy, deepfake verification, procurement, responsible management, agent risk and regulated-industry evidence.</p></header><section class="grid">'+''.join(cards)+'</section>'
    (out/'index.html').write_text(base_page('Practical AI checklists','Indexable AI checklists for managers, small businesses and regulated teams.',f'{SITE_URL}/resources/',body,'resource_index'),encoding='utf-8')


def generate_book_finder() -> None:
    body='''<header class="hero"><h1>Find the right AI book</h1><p>A deterministic, rule-based finder. No pretend mind-reading, no model recommendation theatre.</p></header><section class="card"><form id="book-finder-form"><label for="book-finder-goal"><strong>What are you trying to solve?</strong></label><select id="book-finder-goal" name="goal" required><option value="">Choose a starting point</option><option value="work">Work, careers or AI literacy</option><option value="agents">Automating ordinary work with agents</option><option value="business">Small business and practical adoption</option><option value="healthcare">Healthcare and care services</option><option value="regulated">Law, finance or regulated decisions</option><option value="trust">Deepfakes, scams, security or trust</option><option value="fundamentals">AI fundamentals and history</option></select><button class="button" type="submit">Show me the best starting books</button></form></section><section class="card" id="book-finder-results" aria-live="polite"><h2>Your starting books</h2><p>Choose a problem above. Results are ranked by explicit topic and catalogue rules, not a personalisation model.</p></section><noscript><section class="card"><h2>JavaScript off?</h2><p>Use the <a href="/bundles/">reading paths</a> or <a href="/ebooks/">full catalogue</a>. Nothing essential is locked behind animation.</p></section></noscript>'''
    out=ROOT/'book-finder'; out.mkdir(exist_ok=True); page=base_page('Find the right AI book','A deterministic book finder based on reader problem, role and topic.',f'{SITE_URL}/book-finder/',body,'book_finder').replace('</body>','<script defer src="/assets/js/book-finder.min.js"></script></body>')
    (out/'index.html').write_text(page,encoding='utf-8')


def footer_navigation() -> None:
    p=ROOT/'assets/partials/footer.html'; t=p.read_text(encoding='utf-8')
    if '<li><a href="/bundles/">Reading paths</a></li>' not in t:
        t=t.replace('<li><a href="/compare/">Comparisons</a></li>','<li><a href="/compare/">Comparisons</a></li>\n<li><a href="/bundles/">Reading paths</a></li>\n<li><a href="/evidence/">Evidence guides</a></li>\n<li><a href="/resources/">Checklists</a></li>')
    p.write_text(t,encoding='utf-8')


def main() -> int:
    books=load_master(); count=len(books)
    sync_book_counts(count)
    footer_navigation()
    homepage(count)
    benefit_newsletter_copy()
    podcast_page()
    generate_evidence(); generate_resources(); generate_book_finder()
    add_static_newsletter_placements()
    comparison_reading_paths()
    topic_reading_paths()
    print(f"Growth assets generated from {count} governed books: 7 evidence guides, 6 resources, book finder and commercial router.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
