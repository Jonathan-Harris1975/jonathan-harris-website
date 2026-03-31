# Third-party dependency matrix

This site depends on a small set of external services that sit outside the repository boundary. This document is the governed reference for what they do, which pages rely on them, and what happens when they wobble.

## Runtime vendors

| Vendor | Role | Pages / surfaces | Failure mode | Fallback / mitigation |
| --- | --- | --- | --- | --- |
| CookieYes | Consent management for optional scripts | Homepage, catalogue, ebook pages, newsletter, contact, podcast, bio, compare, glossary, utility pages | Optional analytics/chat scripts may not load or may remain blocked | Core content stays server-rendered and readable without consent-managed scripts |
| Metricool | Analytics script loaded behind consent | Core marketing pages | Measurement loss only | No content, routing, or form dependency |
| BotSailor | Chat widget loaded behind consent | Core marketing pages | Chat entry point disappears | Navigation, CTAs, and page content remain available without chat |
| Jotform | Hosted forms and embeds | Newsletter and contact pages | Embedded form may fail or be blocked | Hosted Jotform fallback links remain published on-page |
| ImageKit via images.jonathan-harris.online | Remote delivery for logo and ebook cover images | Header, homepage, catalogue pages, ebook pages, metadata image tags | Logo / covers may fail to render if remote assets drift or image host is unavailable | `scripts/check_image_assets.py` validates the governed contract and supports live URL checks |
| assets.jonathan-harris.online | Favicon and governed static assets | Site-wide head metadata | Favicon / asset preload drift | Repo keeps explicit asset URLs and release validation checks head markup |

## Governance rules

1. Do not add a new runtime vendor without documenting the surface area, failure mode, and fallback here.
2. Consent-managed vendors must not become a prerequisite for reading core content, navigating the site, or reaching book and newsletter CTAs.
3. Hosted forms must keep a visible fallback route when an embed is present.
4. Remote image delivery must remain governed by `docs/image-publishing-contract.md` and `scripts/check_image_assets.py`.
