# Audit Fix Deployment — jonathan-harris.online
**Date:** 10 March 2026  
**Source:** SEO & AI Discoverability Audit 2026  
**Files changed:** 42 HTML files

---

## Changes Applied

### [FIX-01] Duplicate Metricool script removed — 36 book pages
**Priority:** HIGH | **Effort:** ~30 min  
**Files:** `book/*/index.html` (all 36)

Each book page contained two `loadScript()` function calls injecting the Metricool tracker. The first (early in `<head>`, missing the `console.error` handler) was removed. The second instance — positioned after CookieYes and with a proper `onerror` handler — is retained.

---

### [FIX-02] Canonical URL corrected to /ebooks/ path — 36 book pages
**Priority:** HIGH | **Effort:** ~1 hr  
**Files:** `book/*/index.html` (all 36)

`<link rel="canonical">` was pointing to the internal `/book/[slug]/` URL instead of the public-facing `/ebooks/[slug]/` URL, splitting link equity. All canonical tags now point to the correct `/ebooks/` path.

---

### [FIX-03] og:url corrected to /ebooks/ path — 36 book pages
**Priority:** HIGH  
**Files:** `book/*/index.html` (all 36)

`og:url` Open Graph tags were also pointing to `/book/[slug]/`. Updated to match the canonical `/ebooks/[slug]/` path for consistency.

---

### [FIX-04] Broken ./detail.html button removed — 36 book pages
**Priority:** HIGH | **Effort:** ~1 hr  
**Files:** `book/*/index.html` (all 36)

Every book page contained a "Full Details" secondary CTA button linking to `./detail.html`. These files were absent from the repository, creating 36 dead links. The button has been removed. (Note: creating rich `detail.html` pages is a MEDIUM-priority content opportunity for a future sprint.)

---

### [FIX-05] Person schema @id standardised site-wide
**Priority:** HIGH | **Effort:** ~1 hr  
**Files:** `bio/index.html`, `blog/index.html`, `ebooks/index.html`, `podcast/index.html`, `privacy-policy/index.html`

Five pages used `https://jonathan-harris.online/#person-jonathan-harris` as the JSON-LD `@id` for the Person entity, while the homepage and book pages correctly used `https://jonathan-harris.online/#person`. All instances normalised to the shorter canonical form so Google's Knowledge Graph and LLM systems can merge signals into a single entity node.

---

### [FIX-06] Twitter/X added to Person sameAs array
**Priority:** MEDIUM | **Effort:** ~30 min  
**Files:** `bio/index.html`

`https://twitter.com/jonathan_harris_01` added to the `sameAs` array in the Person JSON-LD schema on the bio page. Twitter/X is a primary signal LLMs use for author authority verification.

---

### [FIX-07] Bio page ai:keywords replaced with meaningful phrases
**Priority:** HIGH | **Effort:** ~15 min  
**Files:** `bio/index.html`

Previous value: `"x, about, podcast, newsletter, gen, ebooks, harris, ai, jonathan, automation"` — contained meaningless tokens.  
New value: `"Jonathan Harris AI author, practical artificial intelligence, AI books non-technical, Turing's Torch podcast, AI plain English"`

---

### [FIX-08] ai:summary meta tag added to bio page
**Priority:** LOW | **Effort:** ~15 min  
**Files:** `bio/index.html`

The bio page lacked an `ai:summary` meta tag (present on other pages). Added a concise, citable description for AI crawlers and LLM ingestion pipelines.

---

### [FIX-09] Blog page ai:keywords replaced with meaningful phrases
**Priority:** HIGH | **Effort:** ~15 min  
**Files:** `blog/index.html`

Previous value: `"x, without, podcast, newsletter, gen, hype, ebooks, ai, automation"` — contained meaningless tokens including the literal character `x`.  
New value: `"AI analysis, weekly AI insights, artificial intelligence commentary, AI trends, practical AI notes"`

---

### [FIX-10] Topics page ai:keywords replaced with meaningful phrases
**Priority:** HIGH | **Effort:** ~15 min  
**Files:** `topics/index.html`

Previous value: `"topic, x, podcast, newsletter, gen, ebooks, ai, browse, automation"` — contained meaningless tokens.  
New value: `"AI topics index, AI by industry, artificial intelligence categories, AI ebook catalogue by subject"`

---

## Remaining High-Priority Items (Not in this deployment)

| Task | Why deferred |
|------|-------------|
| Activate blog publishing pipeline | Requires content creation, not a code-only fix |
| Create individual podcast episode pages | Ongoing content work |
| Write unique "What you'll learn" bullets for top-10 book pages | Requires per-book content research |
| Add Amazon Author Central / Goodreads to sameAs | External account setup required |
| Create 3 curated list blog posts | Content creation task |

---

*Fix script: `fix_site.py` | Source audit: `JonathanHarris_SEO_AI_Audit_2026.pdf`*
