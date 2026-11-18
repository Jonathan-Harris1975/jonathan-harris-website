# Website design acceptance evidence: 18 November 2026 (additional sample)

## Scope and production baseline

- Production: `https://jonathan-harris.online/`, Cloudflare Pages project `jonathan-harris-website`, production branch `main`.
- At time of inspection, Cloudflare's latest successful production deployment was `a550d397-a281-4300-812a-d0ba654e49e4`, built from GitHub commit `04e961e93e901b40215f85c1f520055b56e58c4e`.
- The earlier broad editorial design change is merged PR #169, and default mobile-route coverage change is merged PR #171. The original design audit and representative baseline/candidate screenshots remain at `docs/WEBSITE-DESIGN-AUDIT-2026-11-18.md`.
- This document is supplementary **browser evidence**, not a claim that every public route, seasonal variation or WCAG criterion has passed.

## First production browser sample (Cloudflare Browser Rendering, Playwright)

Routes checked: `/`, `/blog/`, `/newsletter/`, `/podcast/`, `/ebooks/`, `/ebooks/artificial-intelligence-for-small-business/`, `/contact/`, `/bio/`, `/compare/` and `/__website-design-audit-not-found__/`.

Each route was rendered at **320, 390, 768 and 1440px** for **40 viewport checks**. Browser checks inspected HTTP response, main and H1 count, DOM width/overflow, image alt attributes, labels on standard form fields, navigation landmarks, seasonal runtime state and sampled compact links.

Observed:

- Nine expected routes returned HTTP 200; the deliberate unknown route returned HTTP 404.
- All 40 viewports had one `main`, one `h1`, no detected document horizontal overflow, and no image elements missing the `alt` attribute in the sampled render.
- The live runtime set `data-season="autumn"`, and computed body typography used Inter with the established fallbacks.
- The public book catalogue and detail content rendered. The audit did **not** validate all 40 individual book pages or assert print-format availability.
- The consent layer was present on sampled routes. Mobile consent obstruction, Reject/Customise semantics and all possible loaded/async states still require a separate acceptance test.
- This first pass is not an axe assessment, keyboard or screen-reader certification, full-page visual comparison, contrast matrix, or measured LCP/INP/CLS.

## Measured navigation defect and candidate correction

At 390px on `/ebooks/artificial-intelligence-for-small-business/`, two separate visible `nav[aria-label="Breadcrumb"]` landmarks were found. The second, legacy trail includes a useful Business category link. Baseline compact breadcrumb link boxes were approximately **17px** in that trail and **21px** in the generic trail. On `/blog/`, a breadcrumb Home link was approximately **22px** high, and the homepage featured-book footer link was approximately **17px** high.

The candidate CSS in this change:

1. Hides the redundant generic trail **only** on book-detail pages which contain the richer `.breadcrumbs` trail. It explicitly overrides an older `display:block!important` compatibility rule; the fallback generic trail is retained if the richer trail is missing.
2. Makes both breadcrumb link variants and the featured-book footer link at least 24px high without changing content, links, fonts, colours or seasonal tokens.

A live-document stylesheet-injection comparison on the eBook detail, blog and homepage, at 320, 390, 768 and 1440px, confirmed:

- Visible eBook-detail breadcrumb landmarks: **2 before, 1 with candidate**.
- Sampled compact breadcrumb/footer links: **17–22px before, 24px with candidate**.
- Horizontal document overflow: **none** at all 12 candidate viewport combinations.
- The new stylesheet remained within the existing CSS budget (**142,162 of 142,336 bytes**).
- These are candidate-injection findings, not yet post-deployment verification.

## Design position and remaining acceptance

Continue premium editorial minimalism, with precise Swiss-style alignment, restrained card systems and the existing brand palette. The seasonal engine, auto-switch dates, original covers, live D1/KDP formats, R2 publishing, consent and analytics were **not** altered by this patch.

Outstanding: full route-by-route visual evidence at desktop/tablet/mobile; measured Core Web Vitals and field data; axe plus manual WCAG 2.2 AA testing; complete seasonal/event contrast checks; consent journeys; dynamic content and print-format purchase links; new post-production screenshots and exact-SHA parity.

**No revised final 9/10 or 10/10 scores are asserted.** Tracked acceptance must remain open until the required checks are independently verified.
### Reproducible visual pair

The same live book-detail page was captured at 390px with an identical 440px document crop, before and after injecting the candidate CSS:

- [Production baseline](../.github/audits/2026-11-18/ebook-breadcrumb-baseline.svg)
- [Candidate stylesheet](../.github/audits/2026-11-18/ebook-breadcrumb-candidate.svg)

The screenshots are scoped first-viewport crops, not complete-page, all-breakpoint or **deployed** after-images. They are embedded JPEGs in SVG containers to retain browser captures as reviewable repository evidence. A fresh post-deployment comparison remains required.
