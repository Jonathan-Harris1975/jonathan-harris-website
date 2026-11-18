# Website design audit and modernisation: evidence register

**Date:** 18 November 2026  
**Repository:** `Jonathan-Harris1975/jonathan-harris-website`  
**Production domain:** https://jonathan-harris.online/  
**Status:** First bounded implementation under review. **Not** a complete-site or WCAG certification.

## Verified architecture and sources of truth

- `assets/css/site.css`: global `--bg-dark`, `--accent`, `--accent-hover`, `--border`, `--radius`, colour and layout rules. Baseline stylesheet was 139,208 characters; the production CSS byte budget is 142,336.
- Inter typography from Google Fonts and fallbacks, used by existing pages.
- `assets/partials/header.html` and `footer.html`: canonical site chrome, checked by `scripts/check_shared_chrome_layout.py`.
- `assets/js/site-ui.min.js`: shared navigation behaviour, season / event calculation and automatic theme activation.
- `:root[data-season]` / `:root[data-event]` in the stylesheet: seasonal accent presentation; seasonal values and brand palette are unchanged in this change set.
- `wrangler.toml`: Cloudflare Pages, KDP D1, blog/transcript/image R2 bindings, CogniPal and Agent Readiness services. The build is `bash build.sh`.
- D1-backed eBook catalogue and live format availability; R2-backed blog and podcast content. Static duplicates must not replace their runtime sources.

## Evidence and initial assessment

Review included source inspection and live public-page inspection of the homepage, catalogue, representative eBook detail, blog, newsletter, podcast and contact pages. Cloudflare Browser Rendering was used for first-viewport sampling at mobile width 390px, with one broader desktop capture attempted. This is a **sample**, not a full page-by-page, breakpoint-by-breakpoint screenshot inventory. No before/after images are committed in this change set.

| Category | Provisional baseline | Evidence / constraint |
| --- | ---: | --- |
| Modern visual design | 7/10 | Large, centred hero treatments and strongly shadowed cards across sampled templates |
| Professional appearance | 7/10 | Brand is coherent; layout rhythm and card treatment are more prominent than editorial hierarchy |
| Brand consistency | 8/10 | Centralised tokens, Inter and shared chrome; seasonal event palette is present |
| Minimalism and clarity | 7/10 | Homepage has multiple competing routes and card groups |
| Navigation and usability | 7/10 | Shared desktop/mobile nav exists; resources duplicate some core routes |
| Mobile responsiveness | 7/10 | First viewport works at 390px; large hero and consent UI consume much of the screen |
| Content presentation | 7/10 | Blog, books and podcast use distinct templates; reading rhythm can be more consistent |
| Seasonal design integration | 8/10 | Calendar-based seasonal and event logic exists; new date-boundary regression needed |
| Accessibility | Not scored | Existing contrast/chrome checks are not a complete WCAG 2.2 AA audit |
| Performance | Not scored | Global CSS ~139 KB and Google font requests identified; no lab/field CWV baseline measured |
| Overall cohesion | 7/10 | Shared system exists but can better express a premium editorial hierarchy |

Scores are editorial judgements over the sampled evidence, **not** measured accessibility, performance, or whole-site compliance ratings. Perfect scores are not justified.

### Design approaches evaluated

- **Premium editorial minimalism:** Selected as the organising principle; improves reading measure, hierarchy, spacing and visual restraint without replacing original content.
- **Swiss-inspired modernism:** Used as a supporting grid/alignment discipline, not a new brand.
- **Bento modules:** Selective existing discovery-card use is sufficient; avoid making every content page a dashboard.
- **Asymmetry:** Suitable for future highlighted content only after screenshot testing.
- **Glass/animated treatments:** Not selected; they add complexity without a demonstrated UX gain.

## First implementation (in this branch)

- Added a small shared typography, reading-width, spacing, card-surface, focus-ring and touch-target refinement to `assets/css/site.css`.
- Applied selectors to actual homepage, catalogue, blog, newsletter, podcast and book-detail template classes rather than page-by-page inline edits.
- Preserved base brand values, seasonal CSS colours, calendar switching, original covers, purchasing links and data workflows.
- Added `scripts/test_seasonal_design_dates.mjs`: checks winter/spring/summer/autumn boundaries, representative event dates including the year rollover, CSS theme selectors and absence of new palette literals in the editorial block.
- Added that test to `build.sh` so governed CI runs it automatically.

## Remaining high-priority verification and improvement work

1. Capture **persisted** baseline and post-change screenshots for all public route families and representative dynamic R2 pages at desktop, tablet and mobile; store in the existing governed audit artefact location.
2. Run browser-computed accessibility checks: axe/WCAG 2.2 AA, keyboard menu/form journeys, screen-reader labels, focus ordering, text zoom, 320px and 400% reflow, contrast under **every** seasonal palette.
3. Run field and lab Core Web Vitals checks (LCP, INP, CLS) and inspect stylesheet/Google font duplication without breaking templates.
4. Audit third-party consent-management presentation on mobile: several sampled first views were obscured by its dialog. Preserve lawful choice, reject capability and analytics governance in any remediation.
5. Confirm API-driven Kindle, paperback and hardback badges appear **only** for formats verified live in D1 and follow through to the appropriate Amazon destination.
6. Verify content automation after deployment, including new R2-backed newsletter/blog/podcast publications, original book covers and schema metadata.
7. Repeat screenshots and measurements after production deployment and calculate final scores; do not award 9/10 or 10/10 without evidence.

## Deployment and governance acceptance

This file does **not** claim the branch is merged or deployed. Required: full `bash build.sh` and independent CI/security/admission checks; protected same-repository PR; successful Cloudflare Pages production deploy; strict post-deploy content/API/crawler checks; verified live screenshots and measured accessibility/performance. No security, publishing or consent controls may be bypassed to accelerate a cosmetic change.
