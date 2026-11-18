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
- The site stylesheet remains within its existing governed raw-size budget: **142,330 of 142,336 bytes**, with no new dependencies.
- Final production regression remains required after merge. This is not a declaration of full consent accessibility or legal certification.

The selectors target existing CookieYes notice classes. No consent semantics, banner copy, brand palette, seasonal engine, business logic or analytics integration were changed. The responsive rule is restricted to `max-width:420px` to avoid worsening the existing 600px/768px single-row layout.
