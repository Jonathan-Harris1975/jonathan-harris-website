# Website design modernisation: 19 November 2026 follow-up

**Production domain:** https://jonathan-harris.online/  
**Governed source:** `Jonathan-Harris1975/jonathan-harris-website`  
**Evidence:** production screenshot baseline and CSS-injected candidate at 390px, plus reviewed responsive images at 320, 390, 768 and 1440px.  
**Scope of this change:** homepage narrow-screen discovery navigation only. This is **not** a whole-site acceptance or WCAG certification.

## Current architecture and non-negotiable sources

| Concern | Current source |
| --- | --- |
| Core brand colours and global styles | `assets/css/site.css` (`--bg-dark`, `--accent`, `--accent-hover`, editorial tokens) |
| Typography | Inter with existing fallbacks |
| Shared header/footer | `assets/partials/header.html`, `assets/partials/footer.html` |
| Automatic seasonal and event themes | `assets/js/site-ui.min.js` plus `:root[data-season]` and `:root[data-event]` CSS |
| Responsive layout | Shared CSS plus generated static page templates and R2-backed runtime pages |
| Governance | `bash build.sh`, protected same-repository PRs, exact-head trusted admission and Pages deployment |
| Dynamic publishing | D1 catalogue / format availability and R2 blog, podcast and transcripts |

Design direction: **premium editorial minimalism with Swiss-inspired alignment**, not an expanded bento dashboard or a new colour palette. The existing visual identity and original creative assets stay in place.

## Evidence and severity

**High: homepage mobile content discovery is unnecessarily tall.** The live 390px first-viewport screenshot shows seven route links stacked in seven full-width rows within `.home-intent` because a `max-width:440px` override replaces the already-supported two-column tablet grid with a single column. This pushes the AI Edge signup module below the first mobile screen.

The responsive browser candidate uses the existing two-column grid at all widths up to 760px, including 320 and 390px. It renders seven links in four rows rather than seven, with the existing 44px minimum link height. The first part of the newsletter module becomes visible in the same 390px crop, without changing route labels or destinations. A 320px candidate screenshot was also visually inspected, including wrapping links. At 768px, the existing layout is unchanged.

**Implementation:** remove only `.home-intent nav` from the `max-width:440px` single-column selector. Keep `.home-trust-strip` single-column at this width. No new dependency, colour, image, font, business logic, consent or publishing change. This reduces shared CSS length by 17 characters and stays below the governed 143,360-byte budget.

## Reproducible browser image pair

Browser rendering at **390×920**, same initial scroll position and live URL. A neutral test-only CSS rule suppresses the third-party consent overlay in *both screenshots* to compare page layout. The actual consent vendor, choices, cookies and preferences remain unchanged in source or deployment.

- [Current production before change](../.github/audits/2026-11-19/home-discovery-mobile-baseline.svg)
- [Live page with candidate CSS injected](../.github/audits/2026-11-19/home-discovery-mobile-candidate.svg)

These are real browser images stored in SVG image containers, **not** mock-ups. The candidate is not a deployed-after screenshot. If the change passes exact-head checks and deploys, production must be captured again and compared.

## Automated regression coverage

`scripts/test_seasonal_design_dates.mjs` retains the existing calendar boundary and seasonal token checks and adds a regression assertion that the 440px rule no longer collapses the home intent navigation. The existing `.home-intent a` 44px touch-target contract remains asserted.

## Current project-level assessment and remaining work

The 18 November evidence register gives provisional sampled baselines of: visual 7/10, professionalism 7/10, brand 8/10, clarity 7/10, navigation 7/10, mobile 7/10, content 7/10, seasons 8/10 and cohesion 7/10. Accessibility and performance were **not scored**, because a complete WCAG audit and real-user Core Web Vitals data were unavailable. This narrow correction does not justify revising those to 9 or 10.

Existing merged upgrades (#169, #171–#175 and #178) cover editorial reading width, mobile consent/filter stability, headings, touch targets, dynamic blog sitemap and blank space above heroes. Issue #170 remains the acceptance owner for: complete live route screenshot inventory, full WCAG 2.2 AA checks including manual keyboard/screen-reader review, field LCP/INP/CLS, all seasonal/event visual combinations, authorisation and conversion journeys, live format links, and production before/after parity. **Do not close issue #170 on the strength of this change.**

## Release controls

Before merge: full `bash build.sh`, all required exact-head CI/security/admission gates, and Cloudflare preview acceptance. After merge: inspect production Pages deployment SHA, 320/390/768/1440px home layout and seasonal/consent journeys. Report any unverified item as outstanding, not completed.


## Expanded editorial modernisation candidate (same PR, 19 November follow-up)

A second visual comparison exposed further serious design-quality gaps that the first tiny mobile-only patch could not address. The scoped preview now also changes:

- **Homepage, desktop:** primary copy, logo, book and glossary actions form a strong left editorial column; existing topic discovery and newsletter sign-up form a balanced right column. The former fully centred, single-column hero delayed the next content block and made every action compete at the same level. At 1440px the selected split surfaces the next section within the first viewport.
- **Homepage, mobile:** Inter, semantic heading, links and minimum touch targets are untouched. Existing two-column topic navigation and smaller 80px logo reduce hero height without hiding any links.
- **Blog archive:** actual latest weekly R2/RSS-backed story comes before the generic explanation. The `blogStatus` live region, `blogList` renderer, article URLs and all original copy remain. This is a **source HTML change**, not a JavaScript-only reordering.
- **Blog and podcast:** content-leading, restrained separators replace visually dominant introductory cards; the actual player and dynamic content remain unchanged. Source-backed articles are not replaced by stock art.
- **Bounded CSS trade-off:** the new shared editorial CSS is about 3 KiB of additional source; `config/css-budget.json` increases the finite ceiling from 143,360 to 146,432 bytes, and the current candidate is **146,296 bytes**. The new block contains no new literal palette colours or concealed interactive controls. Consolidation of older CSS remains a measured performance backlog item, not a claim this change improves field CWV.
- **Regression:** `scripts/test_editorial_layout.mjs` now participates in `bash build.sh`, and existing seasonal/consent tests are retained. One former consent test read **all future CSS**, erroneously treating unrelated `background:transparent` editorial styling as a change to CookieYes. Its scope has been corrected to the actual narrow-screen CookieYes media block; the checks themselves remain strict.

### Additional before/after evidence

The cloud-browser comparisons cover desktop 1440px and mobile 320/390px homepage, desktop/mobile blog and podcast. Real production baseline and exact-SHA Cloudflare **preview** images are stored alongside the first mobile pair. The comparisons suppress the third-party consent overlay in the test browser on both sides only for the editorial visual crop. Browser consent settings, accept/reject/customise semantics and analytics source are never changed.

The original provisional design scores (7/10 or 8/10 on sampled categories) are retained rather than inflated. A reviewable visual improvement is not equivalent to passing the full public-route WCAG, performance, seasonal and dynamic-content acceptance requirements of issue #170. New measured scores and post-deploy parity may only be published once the required checks actually complete.

**Governance:** this candidate remains behind exact-head CI, independent review and `autonomy:risk-approval-required`. Do not merge without the authorised exact-commit owner admission.
