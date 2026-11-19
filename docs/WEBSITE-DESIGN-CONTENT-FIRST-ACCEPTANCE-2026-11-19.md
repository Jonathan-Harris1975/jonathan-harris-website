# Website Design Modernisation: Content-First Acceptance (19 November 2026)

## Scope and design direction

This report extends the 18–19 November editorial design work and PR #179 with **PR #180**, for `https://jonathan-harris.online`. The selected direction is **premium editorial minimalism with precise Swiss-inspired spacing and selective responsive content grids**, not a rebrand or generic bento dashboard. Preserve the original approved brand colours and logo, Inter typography, seasonal/event appearance automation, original eBook cover artwork, Cloudflare Pages infrastructure, RSS/R2 publishing, D1 format availability, JotForm integrations, analytics, SEO metadata and purchase routes.

### Baseline findings, severity and corrective work

| Route family | Initial live issue | Priority | Implemented correction |
|---|---|---|---|
| Contact | Two guidance cards before actual contact form | High | Form and intact hosted fallback first; guidance and FAQ retained below |
| Podcast transcripts | Archive search buried under multiple explanatory cards | High | Search and live/RSS-backed archive first; links, live region and help retained |
| Weekly AI Briefings | Introductory explanation before searchable articles | High | Live searchable archive first; status, `blogList`, RSS seed and load-more IDs preserved |
| AI topic directory | Two tall overview cards before actual topic links | High | Topic guides introduced once; optional how-to text in native keyboard-accessible `details` |
| eBook catalogue | Tall mobile book covers push title and description below fold | High | Original cover as compact adjacent thumbnail; readable title/subject alongside; descriptions and actions intact |
| Individual eBooks | Oversized quick-facts panel appears before book cover/purchase journey | High | **All 40 canonical pages** and Python generator now render the original cover, overview and buying actions before facts |
| Newsletter | Desktop reading/signup split visually flat | Medium | Selective two-column desktop form/value layout; native single-column mobile remains |
| Podcast | Large fixed-height third-party iframe leaves excessive empty space | Medium | Reduced iframe reserved height, retaining original provider widget and RSS fallback |
| Individual eBook breadcrumbs | Tight segments become hard to distinguish | Medium | Shared flexible wrapping breadcrumb spacing; no destination changes |
| CSS maintenance | Repetitive heavy shadow/padding treatment across public surfaces | Medium | Centralised `JH-PUBLICATION-SURFACES-2026` styles; CSS budget remains finite |

All changes are bounded to the existing site architecture, generators and CSS. No new dependency, literal brand colour, stock image or unrelated content, price, form or publishing logic changes were introduced. The revised eBook cards target the **actual JS-generated** `#booksGrid>article.card`, not only the committed static `.ebook-card` markup. Rebuilds of both topics and book detail pages now enforce the same intended layout.

### Browser screenshot evidence

Production baseline versus the exact-code preview (`73b94b267b070b5dc99b15c99351dc52a62432e2`), captured at identical viewport sizes. The consent overlay was suppressed in both screenshots **only by injected browser-test CSS** so it would not mask the page comparison. CookieYes implementation and site behaviour were not changed.

| Route | Production baseline | Preview candidate |
| --- | --- | --- |
| Contact, 390px | [Before](../.github/audits/2026-11-19/content-first-contact-form-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-contact-form-preview.svg) |
| Transcripts, 390px | [Before](../.github/audits/2026-11-19/content-first-transcript-search-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-transcript-search-preview.svg) |
| Weekly briefings, 390px | [Before](../.github/audits/2026-11-19/content-first-weekly-archive-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-weekly-archive-preview.svg) |
| AI topics, 390px | [Before](../.github/audits/2026-11-19/content-first-topic-guides-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-topic-guides-preview.svg) |
| eBook catalogue, 390px | [Before](../.github/audits/2026-11-19/content-first-ebook-catalogue-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-ebook-catalogue-preview.svg) |
| Individual eBook, 390px | [Before](../.github/audits/2026-11-19/content-first-ebook-details-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-ebook-details-preview.svg) |
| AI Edge, desktop 1440px | [Before](../.github/audits/2026-11-19/content-first-newsletter-baseline.svg) | [Preview](../.github/audits/2026-11-19/content-first-newsletter-preview.svg) |

The preview screenshots are from exact *code* commit prior to the addition of this audit-only evidence and documentation. They are not production-after screenshots. Verify production independently after merge.

### Brand, seasonal and CSS controls

The shared stylesheet retains the `--accent` / `--season-accent` / `--border` / `--bg-dark` sources and the `:root[data-season]` and `:root[data-event]` selectors; the site JS automatic date switching is unmodified. The new rules use existing tokens rather than introducing replacement brand values. `prefers-reduced-motion` removes the added card transition. Existing seasonal date-boundary test suite continues running as part of `bash build.sh`.

`assets/css/site.css` remains subject to `scripts/check_css_budget.py` and `config/css-budget.json`, with a finite source ceiling of **153,600 bytes**. The CSS addition is justified by reusable content-first page structure, but no field Core Web Vitals improvement is asserted without measurement.

### CI and regression acceptance

`scripts/test_content_first_surfaces.mjs` now runs inside `bash build.sh`, alongside the existing seasonal/consent and editorial layout checks. It asserts:

- Correct contact, transcript, weekly and topic source order, and the continued existence of real forms, RSS lists and accessibility labels.
- All **40** canonical book pages use original cover/action-first section order, and generator's ordered-marker contract agrees with them.
- Topic directory generation cannot silently restore duplicate intros.
- eBook catalogue CSS targets the JS live card shape, while filters and buy-now routes remain.
- Shared newsletter/podcast embeds remain and new design consumes existing seasonal CSS tokens without introducing hard-coded palette values.
- The finite CSS budget, dependency/security gates and exact-head Cloudflare Pages preview remain enforced.

Check all required exact-commit workflows, Kilo reviewer, Trusted Autonomy Admission and owner risk approval before merging. No bypass or manual deletion of owner-hold labels. After merge inspect production deployment SHA and real live routes.

### Honest final scoring and remaining limitations

The previous published score was a **provisional 8/10** based on sampled visual inspection. This change resolves verified high- and medium-priority UX defects and should be rescored only after post-deployment parity testing; do not award a categorical 10/10 from screenshots alone.

The following cannot yet be certified by these code changes: complete manual keyboard and screen-reader WCAG 2.2 AA review, independent field LCP/INP/CLS monitoring, every seasonal/event/browser combination, every external form submission and 40-format KDP fulfilment flow. Keep umbrella acceptance issue **#170 open** until independently verified, with explicit evidence per requirement.
