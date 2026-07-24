#!/usr/bin/env python3
from __future__ import annotations
import html, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
books=json.loads((ROOT/'data/ebooks-master.json').read_text(encoding='utf-8'))
config=json.loads((ROOT/'data/ebook-bundles.json').read_text(encoding='utf-8'))
by_slug={b['slug']:b for b in books}
out=ROOT/'bundles'; out.mkdir(exist_ok=True)
header=(ROOT/'assets/partials/header.html').read_text(encoding='utf-8').rstrip('\n')
footer=(ROOT/'assets/partials/footer.html').read_text(encoding='utf-8').rstrip('\n')
font_head='''<link href="https://fonts.googleapis.com" rel="preconnect"/>\n<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>\n<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,600;0,700;0,800&display=swap" rel="stylesheet"/>'''

def card(book):
    return f'''<article class="card ebook-card"><img class="cover" loading="lazy" decoding="async" src="{html.escape(book['cover'])}" alt="{html.escape(book['title'])} cover"><h2>{html.escape(book['title'])}</h2><p>{html.escape(book['short'])}</p><div class="actions"><a class="button secondary" href="/ebooks/{html.escape(book['slug'])}/">Read book page</a><a class="button" href="{html.escape(book['buy_route'])}">View on Amazon</a></div></article>'''

def page(bundle):
    selected=[by_slug[s] for s in bundle['books'] if s in by_slug]
    cards='\n'.join(card(b) for b in selected)
    canonical=f"https://jonathan-harris.online/bundles/{bundle['slug']}/"
    schema={
        "@context":"https://schema.org",
        "@type":"CollectionPage",
        "name":bundle['title'],
        "url":canonical,
        "description":bundle['summary'],
        "author":{"@type":"Person","name":"Jonathan Harris","url":"https://jonathan-harris.online/bio/"},
        "mainEntity":{"@type":"ItemList","itemListElement":[
            {"@type":"ListItem","position":i+1,"item":{"@type":"Book","name":b['title'],"url":b['canonical_url']}}
            for i,b in enumerate(selected)
        ]},
    }
    schema_json=json.dumps(schema,ensure_ascii=False)
    return f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/><title>{html.escape(bundle['title'])} | Jonathan Harris</title><meta name="description" content="{html.escape(bundle['summary'])}"><link rel="canonical" href="{canonical}"><meta name="robots" content="index,follow"><script type="application/ld+json">{schema_json}</script>{font_head}<link rel="stylesheet" href="/assets/css/site.css"><link rel="stylesheet" href="/assets/css/ebook-template.css"></head><body class="ebooks-catalogue">{header}<header class="hero" data-jh-header-reveal-anchor><div class="wrap"><p class="eyebrow">Curated three-book reading path</p><h1>{html.escape(bundle['title'])}</h1><p>{html.escape(bundle['summary'])}</p></div></header><main class="main" id="main"><div class="wrap"><section class="card answer-first"><h2>Why read these books together?</h2><p>Each title tackles a different part of the same decision landscape. Read them as a sequence or pick the one closest to the problem in front of you.</p></section><section class="grid" aria-label="Books in this reading path">{cards}</section><section class="jh-journey-panel"><h2>Where should you go next?</h2><div class="jh-journey-actions"><a href="/bundles/">All reading paths</a><a href="/ebooks/">Full eBook catalogue</a><a href="/topics/">Topic guides</a></div></section></div></main>{footer}<script defer src="/assets/js/site-ui.min.js"></script></body></html>'''
for bundle in config.get('bundles',[]):
    d=out/bundle['slug']; d.mkdir(parents=True,exist_ok=True); (d/'index.html').write_text(page(bundle),encoding='utf-8')
links=''.join(f'<li><a href="/bundles/{html.escape(b["slug"])}/">{html.escape(b["title"])}</a> — {html.escape(b["summary"])}</li>' for b in config.get('bundles',[]))
index_schema={
    "@context":"https://schema.org",
    "@type":"CollectionPage",
    "name":"Curated AI eBook reading paths",
    "url":"https://jonathan-harris.online/bundles/",
    "description":"Curated three-book AI reading paths from the Jonathan Harris eBook catalogue.",
    "mainEntity":{"@type":"ItemList","itemListElement":[
        {"@type":"ListItem","position":i+1,"name":b['title'],"url":f"https://jonathan-harris.online/bundles/{b['slug']}/"}
        for i,b in enumerate(config.get('bundles',[]))
    ]},
}
index_schema_json=json.dumps(index_schema,ensure_ascii=False)
(out/'index.html').write_text(f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/><title>AI eBook Reading Paths | Jonathan Harris</title><meta name="description" content="Curated three-book AI reading paths from the Jonathan Harris eBook catalogue."><link rel="canonical" href="https://jonathan-harris.online/bundles/"><meta name="robots" content="index,follow"><script type="application/ld+json">{index_schema_json}</script>{font_head}<link rel="stylesheet" href="/assets/css/site.css"></head><body>{header}<header class="hero" data-jh-header-reveal-anchor><div class="wrap"><h1>Curated AI reading paths</h1><p>Three-book routes for readers who want a coherent theme instead of random catalogue hopping.</p></div></header><main class="main" id="main"><div class="wrap"><section class="card answer-first"><h2>Which three-book AI reading path should you choose?</h2><p>Start with the problem closest to your work: workplace adoption, health and care, mobility and logistics, or regulated industries.</p><ul>{links}</ul></section></div></main>{footer}<script defer src="/assets/js/site-ui.min.js"></script></body></html>''',encoding='utf-8')
print(f"Generated {len(config.get('bundles',[]))} bundle pages.")
