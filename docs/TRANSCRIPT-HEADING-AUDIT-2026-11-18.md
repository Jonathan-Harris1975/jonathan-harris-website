# Transcript heading hierarchy: live audit and rendering fix

**Date:** 18 November 2026
**Source:** Live production sitemap + browser-rendered transcript samples
**Scope:** Shared R2-to-Cloudflare-Pages transcript renderer only

## Before-change evidence

The live sitemap contained **181 URLs**; a read-only HTTP and HTML audit returned 181 HTTP 200 responses, 181 single-main pages and 181 valid canonical and description fields, with no `img` lacking an alt attribute in the retrieved HTML. **35** URLs, all podcast transcript detail pages, carried two H1 headings. The other 146 had one H1. This audit is of sitemap entries, not an assertion that every R2 route was indexed or all rendered UI met WCAG.

Browser-rendered examples:

- `/transcripts/TT-2026-11-13.html`: H1 `AI Agents Need Fences, Not Better Press Releases` appeared twice.
- `/transcripts/TT-2026-07-31.html`: H1 `AI Agents: Authority Not Just Ability` appeared twice.

In each example, an H1 already existed in the original R2-sourced transcript document. The Pages runtime `functions/transcripts/[[slug]].js` then inserted a second, identical H1 inside `.transcript-aeo-summary`. This duplicated the visible title and the primary heading semantics.

## Code change

The shared SEO introduction detects an existing H1 **in the sanitised R2 HTML** and only inserts its own title H1 when none exists. It preserves the page's original heading, introductory summary, navigation actions, JSON-LD episode/transcript metadata, source content and storage format. There is no change to brand tokens, seasonal themes, analytics, consent, KDP or publishing logic.

Regression tests added to `scripts/test_pages_r2_health.mjs` cover an existing H1 with attributes, uppercase heading markup, safe H1 fallback for documents without headings, title escaping and preservation of podcast metadata. The governed `bash build.sh` already invokes this Node test file.

## Verification required before completion

Governed full build, security, exact-head GitHub admission, production Cloudflare Pages deployment of the exact commit and *post-deployment* re-audit of all sitemap transcript routes. Until then, this is a **candidate fix**, not a claim that live transcript HTML has changed. The wider website design and accessibility acceptance remains tracked in [issue #170](https://github.com/Jonathan-Harris1975/jonathan-harris-website/issues/170).
