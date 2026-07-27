#!/usr/bin/env python3
from __future__ import annotations
import csv, html, json, re, tempfile, sys
from pathlib import Path
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ebook_pipeline import ROOT, SITE_URL, load_master, slugify
from scripts.generate_growth_assets import apply_book_count
from scripts.reconcile_kdp import reconcile

ERRORS=[]
def check(condition:bool,message:str):
    if not condition: ERRORS.append(message)

def text(path:Path)->str: return path.read_text(encoding='utf-8',errors='ignore')

NEWSLETTER_TIME_RE=re.compile(r'(?:three[- ]minute|3[- ]minute|weekday|daily\s+(?:AI\s+)?(?:newsletter|briefing))',re.I)
NEWSLETTER_MARKER_RE=re.compile(r'(?:\bAI Edge\b|\bnewsletter\b)',re.I)
NEWSLETTER_CONTEXT_BOUNDARIES={'html','body','main','article','nav','header','footer'}

def newsletter_contexts(source:str)->list[str]:
    """Return bounded copy blocks that are actually about the newsletter.

    Shared navigation puts an AI Edge link on almost every page, including ebook
    samples.  Newsletter timing policy must therefore inspect the CTA/copy block
    around a newsletter marker, not unrelated manuscript prose elsewhere in the
    document.
    """
    soup=BeautifulSoup(source,'html.parser')
    contexts=[]; seen=set()
    for tag in soup.find_all(True):
        direct=' '.join(str(node).strip() for node in tag.find_all(string=True,recursive=False) if str(node).strip())
        href=str(tag.get('href') or '')
        attrs=' '.join([str(tag.get('id') or ''), ' '.join(tag.get('class') or [])])
        if not (NEWSLETTER_MARKER_RE.search(direct) or '/newsletter/' in href or 'newsletter' in attrs.lower()):
            continue
        best=' '.join(tag.get_text(' ',strip=True).split())
        parent=tag.parent
        while getattr(parent,'name',None) and parent.name not in NEWSLETTER_CONTEXT_BOUNDARIES:
            candidate=' '.join(parent.get_text(' ',strip=True).split())
            if len(candidate)>800:
                break
            best=candidate
            parent=parent.parent
        if best and best not in seen:
            seen.add(best); contexts.append(best)
    return contexts

def newsletter_timing_match(source:str):
    for context in newsletter_contexts(source):
        match=NEWSLETTER_TIME_RE.search(context)
        if match:
            return match
    return None

def main()->int:
    books=load_master(); count=len(books)
    check(count>0,'governed ebook master is empty')

    # Dynamic count architecture + fixture behaviour.
    fixture='Browse 36 AI Books. His 36 books sit across the 36-book library.'
    changed=apply_book_count(fixture,41)
    check('41' in changed and '36-book' not in changed and '36 books' not in changed,'BOOK_COUNT helper did not update a synthetic fixture')
    for rel in ['index.html','bio/index.html','glossary/index.html']:
        body=text(ROOT/rel)
        check(not re.search(r'\b36(?:-book|\s+(?:plain-English\s+)?(?:AI\s+)?(?:books|ebooks|eBooks))\b',body,re.I),f'{rel} contains stale 36-book catalogue residue')
    check(str(count) in text(ROOT/'index.html'),'homepage does not expose generated book count')
    home_source=text(ROOT/'index.html')
    check('/book-finder/' in home_source,'homepage does not expose the book finder')
    check('/evidence/eu-ai-act-article-50-transparency/' in home_source,'homepage does not surface the current Article 50 evidence guide')
    stale_newsletter_phrases=('AI Edge - a daily weekday newsletter','AI Edge — a daily weekday newsletter','AI Edge – a daily weekday newsletter','Get the AI Edge','AI Edge Newsletter','Weekly AI updates')
    # Regression: shared AI Edge navigation must not make ordinary manuscript prose
    # subject to the newsletter timing rule.  Actual newsletter copy must still fail.
    unrelated_fixture='<nav><a href="/newsletter/">AI Edge</a></nav><article><p>The control room is staffed every weekday.</p></article>'
    newsletter_fixture='<main><section><h2>AI Edge</h2><p>A weekday briefing for practical AI decisions.</p></section></main>'
    check(newsletter_timing_match(unrelated_fixture) is None,'newsletter timing contract leaks into unrelated page copy')
    check(newsletter_timing_match(newsletter_fixture) is not None,'newsletter timing contract no longer catches actual AI Edge timing copy')
    for page_path in ROOT.rglob('*.html'):
        page_text=text(page_path)
        for phrase in stale_newsletter_phrases:
            check(phrase not in page_text,f'{page_path.relative_to(ROOT)} contains stale AI Edge naming: {phrase}')
        match=newsletter_timing_match(page_text)
        check(match is None,f'{page_path.relative_to(ROOT)} contains newsletter time/cadence wording: {match.group(0) if match else ""}')
        check('/api/newsletter/subscribe' not in page_text and 'newsletter-native-form' not in page_text and 'data-newsletter-form' not in page_text,f'{page_path.relative_to(ROOT)} exposes a retired second newsletter collection path')

    # Retail/category route invariants.
    retail=text(ROOT/'catalogue'/'retail'/'index.html')
    check(f'{SITE_URL}/catalogue/retail/' in retail,'Retail canonical URL is wrong')
    check('<h1>Retail AI Books</h1>' in retail,'Retail H1 is wrong')
    check('/newsletter/?source=topic%3Aretail' in retail and 'data-newsletter-cta' in retail,'Retail newsletter routing/source is wrong')
    check('Sports AI Books' not in retail,'Retail page still contains Sports title/H1 clone')

    # One physical sitemap + all reading paths.
    physical=[n for n in ['sitemap.xml','Sitemap.xml','site-map.xml','sitemap (1).xml'] if (ROOT/n).exists()]
    check(physical==['sitemap.xml'],f'physical sitemap set is {physical}, expected only sitemap.xml')
    sitemap=text(ROOT/'sitemap.xml') if (ROOT/'sitemap.xml').exists() else ''
    bundles=json.loads(text(ROOT/'data'/'ebook-bundles.json')).get('bundles',[])
    for bundle in bundles:
        check(f'/bundles/{bundle["slug"]}/' in sitemap,f'reading path {bundle["slug"]} missing from sitemap')
    check('/bundles/ai-at-work/' in text(ROOT/'index.html'),'homepage does not route to reading paths')
    check('/bundles/ai-in-regulated-industries/' in text(ROOT/'compare'/'index.html'),'comparison hub does not expose reading paths')
    check('/bundles/ai-health-and-care/' in text(ROOT/'topics'/'ai-in-healthcare'/'index.html'),'healthcare topic hub does not expose its relevant reading path')
    # Sitemap dates describe significant page changes, not the build timestamp.
    home_url=f'{SITE_URL}/'
    home_match=re.search(rf'<url>\s*<loc>{re.escape(home_url)}</loc>(.*?)</url>',sitemap,re.S)
    check(bool(home_match) and '<lastmod>' not in home_match.group(1),'homepage sitemap entry carries a synthetic build lastmod')
    article50_url=f'{SITE_URL}/evidence/eu-ai-act-article-50-transparency/'
    article50_match=re.search(rf'<url>\s*<loc>{re.escape(article50_url)}</loc>(.*?)</url>',sitemap,re.S)
    check(bool(article50_match) and '<lastmod>2026-07-26</lastmod>' in article50_match.group(1),'Article 50 evidence sitemap entry is missing its governed review date')

    # A sample route may exist only when a genuine manuscript chapter was extracted.
    # Partial extraction is allowed so one legacy manuscript cannot block the whole site.
    sample_cache_path=ROOT/'data'/'book-sample-chapters.json'
    genuine_sample_slugs=set()
    if sample_cache_path.exists():
        try:
            sample_payload=json.loads(text(sample_cache_path))
            for item in sample_payload.get('books',[]) if isinstance(sample_payload,dict) else []:
                if not isinstance(item,dict):
                    continue
                slug=str(item.get('slug','')).strip()
                paragraphs=item.get('paragraphs')
                try: word_count=int(item.get('word_count') or 0)
                except (TypeError,ValueError): word_count=0
                if slug and paragraphs and word_count>=350:
                    genuine_sample_slugs.add(slug)
        except (OSError,json.JSONDecodeError) as exc:
            check(False,f'could not parse manuscript sample cache: {exc}')
    sample_dirs=list((ROOT/'ebooks').glob('*/sample'))
    routed_sample_slugs={path.parent.name for path in sample_dirs if (path/'index.html').exists()}
    check(routed_sample_slugs==genuine_sample_slugs, f'sample route/cache mismatch: routes={len(routed_sample_slugs)} genuine={len(genuine_sample_slugs)}')
    sitemap_sample_slugs=set(re.findall(r'/ebooks/([^/]+)/sample/',sitemap))
    check(sitemap_sample_slugs==genuine_sample_slugs, f'sitemap sample/cache mismatch: sitemap={len(sitemap_sample_slugs)} genuine={len(genuine_sample_slugs)}')

    # Legacy redirects are permanent, exact and chain-free in repository rules.
    redirects=text(ROOT/'_redirects')
    check(re.search(r'^/book/\*\s+/ebooks/:splat\s+301\s*$',redirects,re.M) is not None,'broad /book/* redirect missing')
    for alias in ['/Sitemap.xml','/site-map.xml']:
        check(re.search(rf'^{re.escape(alias)}\s+/sitemap\.xml\s+301\s*$',redirects,re.M) is not None,f'{alias} does not redirect directly to /sitemap.xml')
    for book in books[:3]+books[-3:]:
        slug=book['slug']
        check(re.search(rf'^/book/{re.escape(slug)}/buy-now\s+/ebooks/{re.escape(slug)}/buy-now\s+301\s*$',redirects,re.M) is not None,f'exact legacy buy-now redirect missing for {slug}')

    # Chronology at source + generated levels; canonical Person references.
    for book in books:
        pub=str(book.get('datePublished',''))[:10]; mod=str(book.get('dateModified',''))[:10]
        check(not(pub and mod and mod<pub),f'{book["slug"]} source chronology invalid')
        page_path=ROOT/'ebooks'/book['slug']/'index.html'; page=text(page_path)
        soup=BeautifulSoup(page,'html.parser')
        book_schema=None
        for script in soup.find_all('script',attrs={'type':'application/ld+json'}):
            try: obj=json.loads(script.string or script.get_text())
            except Exception: continue
            if isinstance(obj,dict) and obj.get('@type')=='Book': book_schema=obj; break
        check(isinstance(book_schema,dict),f'{book["slug"]} Book JSON-LD missing/unparseable')
        if isinstance(book_schema,dict):
            sp=str(book_schema.get('datePublished',''))[:10]; sm=str(book_schema.get('dateModified',''))[:10]
            check(not(sp and sm and sm<sp),f'{book["slug"]} generated Book chronology invalid')
            check(book_schema.get('author')=={'@id':f'{SITE_URL}/#person'},f'{book["slug"]} author does not reference canonical #person')
            check(book_schema.get('publisher')=={'@id':f'{SITE_URL}/#person'},f'{book["slug"]} publisher does not reference canonical #person')
        check('Before you buy' in page and 'See exactly what this book covers' in page,f'{book["slug"]} confidence strip missing')
        check(('/podcast/?topic=' in page or '/podcast/episodes/' in page) and 'Listen next' in page,f'{book["slug"]} contextual podcast route missing')
        img=soup.select_one('img.ebook-showcase__cover')
        check(bool(img and str(img.get('src') or '').startswith('https://images.jonathan-harris.online/')), f'{book["slug"]} governed direct cover URL missing')
        check('/cdn-cgi/image/' not in (img.get('srcset') or ''), f'{book["slug"]} remote cover is incorrectly wrapped in Cloudflare image resizing')

    # Catalogue commercial actions must remain outside details.
    catalogue=BeautifulSoup(text(ROOT/'ebooks'/'index.html'),'html.parser')
    cards=catalogue.select('.ebook-card[data-book-slug]')
    check(len(cards)==count,f'catalogue card count {len(cards)} does not match master {count}')
    for card in cards:
        slug=card.get('data-book-slug','?')
        view=card.find('a',string=lambda s:isinstance(s,str) and s.strip()=='View book')
        buy=card.find('a',string=lambda s:isinstance(s,str) and s.strip()=='Buy on Amazon')
        check(view is not None and buy is not None,f'{slug} visible commercial actions missing')
        check(view is not None and view.find_parent('details') is None,f'{slug} View book is hidden in details')
        check(buy is not None and buy.find_parent('details') is None,f'{slug} Buy on Amazon is hidden in details')

    # Homepage featured cover responsive contract.
    home=BeautifulSoup(text(ROOT/'index.html'),'html.parser')
    featured=home.select_one('img.featured-cover-img')
    check(bool(featured and str(featured.get('src') or '').startswith('https://images.jonathan-harris.online/')),'homepage featured cover is not using the governed direct image host')
    check('/cdn-cgi/image/' not in (featured.get('srcset') or ''),'homepage remote featured cover is incorrectly wrapped in Cloudflare image resizing')

    # Funnel event contract and PII boundary.
    funnel=text(ROOT/'assets/js/funnel-events.min.js')
    required=['ebook_impression','ebook_view','ebook_amazon_click','ebook_preview_open','ebook_preview_signup','newsletter_view','newsletter_cta_click','newsletter_submit','newsletter_success','podcast_episode_view','podcast_play','podcast_30_seconds','podcast_platform_click','bundle_view','bundle_book_click']
    for event in required: check(f"'{event}'" in funnel,f'funnel event {event} missing')
    check("'email'" not in funnel and 'formData' not in funnel,'funnel abstraction contains an obvious PII/form-value field')
    newsletter_legacy=text(ROOT/'assets/js/newsletter-signup.min.js')
    check('/api/newsletter/subscribe' not in newsletter_legacy and 'fetch(' not in newsletter_legacy,'legacy newsletter JS can still collect subscriptions')
    newsletter_jotform=text(ROOT/'assets/js/newsletter-jotform.min.js')
    check('newsletter_success' in newsletter_jotform and 'newsletter_submit' in newsletter_jotform and 'ebook_preview_signup' in newsletter_jotform and 'utm_campaign' in newsletter_jotform,'Jotform newsletter instrumentation/source forwarding is incomplete')
    retired_endpoint=text(ROOT/'functions'/'api'/'newsletter'/'subscribe.js')
    check('status: 410' in retired_endpoint and 'MAILCHIMP' not in retired_endpoint and 'NEWSLETTER_SUBSCRIBE_ENDPOINT' not in retired_endpoint,'retired newsletter API still exposes a competing provider path')
    newsletter_page=text(ROOT/'newsletter'/'index.html')
    check('<title>AI Edge | Jonathan Harris</title>' in newsletter_page and 'form.jotform.com/260277027608054' in newsletter_page,'AI Edge page is missing the governed name or visible Jotform signup')
    check('/api/newsletter/subscribe' not in newsletter_page and 'data-newsletter-form' not in newsletter_page,'AI Edge page exposes more than the governed Jotform collection path')
    check(newsletter_timing_match(newsletter_page) is None,'AI Edge page contains a timing/cadence promise')
    check('/downloads/ai-glossary-cheat-sheet/ai-glossary-cheat-sheet.pdf' in newsletter_page,'AI Edge page is missing the direct glossary download')
    media_page=text(ROOT/'media'/'index.html')
    check('https://images.jonathan-harris.online/headshot' in media_page and 'Open the press headshot' in media_page,'media page is missing the governed press headshot asset')

    # Podcast crawlable integration seam and deferred third parties.
    podcast=text(ROOT/'podcast'/'index.html')
    check('Latest three episodes' in podcast and 'data-podcast-latest-server' in podcast,'podcast landing lacks server/static latest-three seam')
    check('Latest episode details are temporarily unavailable' not in podcast and 'loading current episode' not in podcast.lower(),'podcast landing ships an unresolved episode placeholder')
    check('data-spotify-load' in podcast and '<iframe title="Turing\'s Torch on Spotify"' not in podcast,'Spotify embed is not click-to-load')
    check('src="https://elfsightcdn.com/platform.js"' in podcast and 'elfsight-app-76cc65a0-0bcf-4dc0-ad36-1046c5a20e3d' in podcast and 'data-elfsight-load' not in podcast,'Elfsight six-episode player embed is missing or still deferred')
    check('podcast-archive-widget' not in podcast,'Elfsight player is still hidden inside a disclosure')
    check((ROOT/'functions'/'podcast'/'index.js').exists(),'exact /podcast/ Pages Function route is missing')
    check('data-podcast-platform="spotify"' in podcast and 'data-podcast-platform="apple"' in podcast and 'data-podcast-platform="rss"' in podcast,'podcast platform click markers are missing')
    check('"author":{"@id":"https://jonathan-harris.online/#person"}' in podcast,'podcast schema does not reference canonical #person')

    # Evidence/resource estate and source provenance.
    evidence=json.loads(text(ROOT/'data'/'evidence-content.json')).get('items',[])
    resources=json.loads(text(ROOT/'data'/'resource-content.json')).get('items',[])
    check(len(evidence)>=8,'expected at least eight commercial evidence clusters')
    check(len(resources)>=7,'expected at least seven linkable HTML resources')
    check(any(item.get('slug')=='eu-ai-act-article-50-transparency' for item in evidence),'Article 50 evidence opportunity is missing')
    check(any(item.get('slug')=='eu-ai-act-article-50-readiness-checklist' for item in resources),'Article 50 readiness checklist is missing')
    llm_payload=json.loads(text(ROOT/'llm-index.json'))
    llm_evidence={row.get('path') for row in llm_payload.get('evidence_guides',[]) if isinstance(row,dict)}
    llm_resources={row.get('path') for row in llm_payload.get('practical_resources',[]) if isinstance(row,dict)}
    check('/evidence/eu-ai-act-article-50-transparency/' in llm_evidence,'llm-index is missing the Article 50 evidence guide')
    check('/resources/eu-ai-act-article-50-readiness-checklist/' in llm_resources,'llm-index is missing the Article 50 readiness checklist')
    for item in evidence:
        check((ROOT/'evidence'/item['slug']/'index.html').exists(),f'evidence page missing: {item["slug"]}')
        for qa in item.get('questions',[]):
            wc=len(re.findall(r"\b[\w’'-]+\b",qa.get('a','')))
            check(40<=wc<=90,f'evidence answer {item["slug"]}: {qa.get("q")} is {wc} words; expected citation-sized 40-90')
        check(all(s.get('organisation') and s.get('title') and s.get('publication_date') and str(s.get('url','')).startswith('https://') for s in item.get('sources',[])),f'evidence provenance incomplete: {item["slug"]}')
    for item in resources:
        check((ROOT/'resources'/item['slug']/'index.html').exists(),f'resource page missing: {item["slug"]}')

    # KDP reconciliation does actual arithmetic without invented sales.
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); f=td/'f.csv'; s=td/'s.csv'; o=td/'o.csv'
        f.write_text('date,book_slug,qualified_sessions,book_views,amazon_clicks\n2026-07-24,test-book,100,50,10\n',encoding='utf-8')
        s.write_text('date,book_slug,sales\n2026-07-24,test-book,2\n',encoding='utf-8')
        reconcile(f,s,o); rows=list(csv.DictReader(o.open(encoding='utf-8')))
        check(rows and rows[0]['book_reach']=='0.500000' and rows[0]['amazon_click_rate']=='0.200000' and rows[0]['outbound_to_sale_conversion']=='0.200000','KDP reconciliation maths is wrong')

    if ERRORS:
        print('Growth contract failures:')
        for error in ERRORS: print(f' - {error}')
        return 1
    print(f'Growth contracts passed: {count} books, {len(evidence)} evidence guides, {len(resources)} resources, funnel + conversion + crawler invariants.')
    return 0
if __name__=='__main__': raise SystemExit(main())
