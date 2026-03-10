# jonathan-harris.online — Patch Release Notes
**Date:** March 2026  
**Source:** SEO & AI Discoverability Audit 2026 + Implementation Roadmap

---

## Phase 1 — Immediate Fixes

### [F1.1] `blog/_templates/post.html` — Noindex blog template
- Changed `robots` meta from `index,follow` → `noindex,nofollow`  
- Prevents Googlebot from indexing a page containing unfilled `{{TITLE}}` placeholder tokens, protecting crawl budget and quality signals.

### [F1.2] `catalogue/*/index.html` (7 files) — Fix ItemList schema URLs
- Updated all `ItemList` JSON-LD schema `url` fields from `/book/[slug]/` → `/ebooks/[slug]/`  
- The `/book/` path is an internal rewrite; `/ebooks/` is the public canonical URL. Fixes link equity fragmentation for all 7 catalogue index pages.

### [F2.4] `catalogue/*/index.html` (6 files) — Fix ai:keywords
- Replaced placeholder `ai:keywords` values (`x, without, podcast, newsletter, gen, hype, ebooks, ai, automation`) with real, category-specific topical phrases on: artificial-intelligence, creativity, education, ethics, law, transportation.

### [F6.1] `catalogue/*/index.html`, `topics/index.html`, `glossary/index.html` (9 files) — Standardise Person schema jobTitle
- Changed `"jobTitle": "AI Technology Author"` → `"jobTitle": ["AI Author", "Podcast Host"]` across all catalogue, topics, and glossary pages  
- Now consistent with bio and book pages. Removes conflicting entity attributes that prevent stable Knowledge Graph node creation.

### [F6.3] `book/*/index.html` (36 files) — Remove placeholder AggregateRating schema
- Removed the `AggregateRating` JSON-LD block added in the prior audit pass  
- The `ratingCount: 22–24` placeholder does not match live Amazon review data per book. Inaccurate schema risks a Google rich-result penalty. Schema to be re-added with accurate per-book data.

---

## Phase 2 — Sprint Fixes (actionable without external data)

### [F4.3] `book/*/index.html` (34 files) — Convert topic chips to navigational links
- Changed `<span class="topic-chip">` → `<a class="topic-chip" href="/catalogue/[category]/">` for all topic chips with a matching catalogue page  
- Topic→catalogue URL mapping applied:
  - Transportation → `/catalogue/transportation/`
  - Artificial Intelligence, AI Trends, AI Governance, General AI, Automation, Robotics, Energy, Retail, AI in Sports → `/catalogue/artificial-intelligence/`
  - Creativity, AI & Creativity → `/catalogue/creativity/`
  - Education → `/catalogue/education/`
  - Ethics → `/catalogue/ethics/`
  - Healthcare → `/catalogue/healthcare/`
  - Law → `/catalogue/law/`
- Improves internal navigation, pages-per-session, and topical cluster crawl graph.

### [Pg.7] `index.html` — Add WebSite + SearchAction schema
- Added `WebSite` JSON-LD block with `SearchAction` `potentialAction` pointing to `/ebooks/?q={search_term_string}`  
- Enables Google Sitelinks Search Box eligibility. OpenSearch XML was already in place; this schema was the missing piece.

---

## Files Modified (57 total)

| File | Change |
|------|--------|
| `blog/_templates/post.html` | F1.1 |
| `catalogue/artificial-intelligence/index.html` | F1.2, F6.1, F2.4 |
| `catalogue/creativity/index.html` | F1.2, F6.1, F2.4 |
| `catalogue/education/index.html` | F1.2, F6.1, F2.4 |
| `catalogue/ethics/index.html` | F1.2, F6.1, F2.4 |
| `catalogue/healthcare/index.html` | F1.2, F6.1 |
| `catalogue/law/index.html` | F1.2, F6.1, F2.4 |
| `catalogue/transportation/index.html` | F1.2, F6.1, F2.4 |
| `topics/index.html` | F6.1 |
| `glossary/index.html` | F6.1 |
| `index.html` | Pg.7 |
| `book/*/index.html` (36 files) | F6.3, F4.3 |

---

## Remaining Roadmap Items (Not In This Patch)

| Ref | Task | Reason deferred |
|-----|------|-----------------|
| F2.1 | Activate blog pipeline | Requires running `generate-blog-from-rss.mjs` in deployment env |
| F2.2 | Unique 'What you'll learn' for top 10 books | Requires editorial content per book |
| F4.1 | Podcast episode pages | Requires RSS episode data & template build |
| F6.2 | Add ISBNs to Book schema | Requires ISBN data per title |
| F4.2 | Newsletter preview content | Newsletter page already has sample, testimonials, and frequency; verified up to date |
| F5.2 | Extend llm-index.json with podcast episodes | Requires episode data pipeline |
| F6.4 | External backlinks | Off-site action |
| F6.5 | Amazon Author Central | Off-site action (marked done in roadmap) |
| F2.3 | Glossary cross-links from book pages | Requires editorial pass per book |
| F3.1 | Metricool deferred load | Low priority performance tweak |
