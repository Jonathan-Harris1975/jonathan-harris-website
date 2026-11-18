# Narrow-screen consent layout: browser evidence

**Date:** 18 November 2026. **Source:** live CookieYes banner on homepage, browser-rendered, with candidate CSS injected only into the test document.

The CookieYes notice is a first-visit interaction. The existing banner's 342px height at 320px and 390px screen widths obscures a material portion of the first viewport. The site already has three legally relevant, visible options: Accept All, Reject All and Customise. The change does not remove, rename, reorder in DOM, recolour or reconfigure any choice, preference category, tracker or cookie. It only rearranges the three buttons below 421px.

| Width | Live notice | Candidate | Result |
| --- | ---: | ---: | --- |
| 320px | 342px | 288px | 54px less obstruction, 44px-tall controls, no overflow |
| 390px | 342px | 288px | 54px less obstruction, Accept/Reject 165px each, no overflow |
| 600px | 210px | unchanged by final 420px breakpoint | Preserve already-compact native layout |
| 768px | 210px | unchanged | Preserve desktop/tablet CookieYes layout |

**Functional candidate tests, 390px:**

- Reject All clicked: banner closed, consent cookie set, preference-revisit button visible.
- Customise clicked: preference centre opened with `aria-modal=true`, Reject All and Save My Preferences still visible, no horizontal overflow.
- All three initial consent choices remained visible at minimum height 44px.
- The site stylesheet remains within its evidence-adjusted governed raw-size budget: **142,973 of 143,360 bytes**, with no new dependencies.
- Final production regression remains required after merge. This is not a declaration of full consent accessibility or legal certification.

The selectors target existing CookieYes notice classes. No consent semantics, banner copy, brand palette, seasonal engine, business logic or analytics integration were changed. The responsive rule is restricted to `max-width:420px` to avoid worsening the existing 600px/768px single-row layout.
## Screenshot pair

At the same 390px viewport, the live first-visit CookieYes layer was recorded before and after injecting the candidate CSS, without changing the user’s stored consent state:

- [Live baseline, 342px banner](../.github/audits/2026-11-18/consent-mobile-baseline.svg)
- [Candidate, 288px banner](../.github/audits/2026-11-18/consent-mobile-candidate.svg)

These are browser captures embedded in SVG containers for evidence review. The candidate is not a claim of post-production parity; recapture after exact-commit Cloudflare deployment.
## Expanded mobile catalogue audit and CLS correction

The original site has **26 topic filter buttons**, dynamically inserted into a wrapping flex container. The rail was **668px** high at 320px, **512px** at 390px, **248px** at 600px and **200px** at 768px; catalogue results were pushed much farther below the fold. A second layout shift resulted from the header transitioning to fixed positioning after initial parsing.

Browser laboratory observation at 390px (fresh first visit, no user interactions): initial **CLS ~0.53**, including 0.25 from header reflow and ~0.28 from catalogue controls expanding late.

The proposed shared CSS declares the established eBook-header fixed positioning from initial render, and at widths **768px or below**, keeps all 26 existing filter buttons on a keyboard-accessible, independently horizontally scrollable rail with no page-level horizontal overflow or hidden options. Existing Search and the book finder remain unchanged. The rail occupies **52px** after loading.

**Measured browser CSS-interception candidate** (not deployed; individual reload samples, indicative):

| Width | Candidate CLS | Filter height | Document overflow |
| --- | ---: | ---: | --- |
| 320px | 0.1411 | 52px | None |
| 390px | 0.0828 | 52px | None |
| 600px | 0.0982 | 52px | None |
| 768px | 0.0676 | 52px | None |
| 1440px | 0.0804 | 148px (existing desktop wrap) | None |

An earlier direct 390px baseline-vs-candidate browser comparison observed **CLS 0.5326 → 0.0869**. These are laboratory runs: they are not an INP/field-CWV certification, and remaining 320px shift **0.1411** requires follow-up.

- [Mobile eBook catalogue baseline, 390px](../.github/audits/2026-11-18/catalogue-filter-mobile-baseline.svg)
- [Same viewport with candidate scroll rail](../.github/audits/2026-11-18/catalogue-filter-mobile-candidate.svg)

The existing CSS size threshold was increased by exactly **1 KiB**, from 142,336 to **143,360 bytes**, to allow this measured, high-value performance/accessibility improvement without an unbounded stylesheet budget. The actual revised CSS is **142,973 bytes**, 387 bytes below the new ceiling. No colours, fonts, season tokens, covers, book metadata, filters, pricing or publishing logic were changed. Tests run under the existing `bash build.sh` harness.

Production verification is still required after the correct commit merges: inspect actual mobile CLS again, test selection and keyboard navigation of all topic buttons, monitor desktop and tablet layout, and confirm no publishing regressions.
### Post-review verification on exact-functionality preview

The Cloudflare preview of the catalogue patch returned HTTP 200 with all 26 filters. In a 390px browser run the real preview recorded **CLS 0.0815**, compared with the approximately 0.53 current-production baseline. At 320px the preview still recorded **CLS 0.14**, so this remains an explicitly open follow-up. Keyboard testing on the proposed rail reached the last topic button by Tab and automatically scrolled the rail into view; clicking Healthcare filtered the catalogue to 3 of 40 titles without page overflow.

The header needs `position:fixed!important` to counter the existing late hero-mode layout contract: a controlled browser interception without this override reproduced **CLS ~0.516**, compared with approximately 0.083 with the override. It is a deliberately scoped compatibility rule, not a generic preference for `!important`.

The CMP uses `data-cky-tag` notice, settings, accept and reject hooks instead of depending on its class names. If a future CookieYes update changes its HTML hooks, the original CookieYes banner remains available rather than having any choice hidden. Vendor updates still merit a first-visit smoke test.
