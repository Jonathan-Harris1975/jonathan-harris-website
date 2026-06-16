> **Document status:** Production reference  
> **Last reviewed:** 16 June 2026  
> **Operational authority:** Current repository README, SECURITY policy and operations guide.

# Search Console stale URL remediation plan

## Scope
This runbook covers the two stale URL families still surfacing in search even though live redirects are already governed in `_redirects`:

- Locale-prefixed aliases under `/en-gb/` and `/en-au/`.
- Legacy detail aliases under `/book/`.

The live redirect contract must remain:

- `/en-gb/* -> https://jonathan-harris.online/:splat` (301)
- `/en-au/* -> https://jonathan-harris.online/:splat` (301)
- `/book/* -> /ebooks/:splat` (301)

## Canonical destinations to verify before filing requests
Confirm that the destination pages already publish self-referential canonical links:

- Home: `https://jonathan-harris.online/`
- Topics hub: `https://jonathan-harris.online/topics/`
- Catalogue topic pages: `https://jonathan-harris.online/catalogue/<topic-slug>/`
- Canonical ebook pages: `https://jonathan-harris.online/ebooks/<slug>/`

Repository validation already checks canonical coverage for the governed HTML family and redirect-family completeness.

## Search Console actions
### 1. Removals
Use **Search Console > Indexing > Removals** to submit temporary Removals for the stale families that are still appearing in branded search:

- `https://jonathan-harris.online/en-gb/`
- `https://jonathan-harris.online/en-au/`
- `https://jonathan-harris.online/book/`

Apply the temporary Removals request to the URL prefix for each stale family.

### 2. Request indexing
Use **URL Inspection** on the canonical destinations and choose **Request indexing** after the live redirect and canonical checks pass.

Priority order:

1. `/`
2. `/topics/`
3. high-impression `/catalogue/*` pages
4. high-impression `/ebooks/*` pages

### 3. Sitemap resubmission
Resubmit the governed sitemap after deployment:

- `https://jonathan-harris.online/sitemap.xml`

## Evidence to capture
Keep screenshots or exported notes for:

- the Removals requests submitted for `/en-gb/`, `/en-au/`, and `/book/`
- the URL Inspection result for each canonical destination sampled
- the sitemap resubmission timestamp
- the follow-up branded search recheck window

## Follow-up recheck window
Recheck branded search results after the recrawl window and again after the temporary Removals request starts to age out.

Success looks like this:

- `/en-gb/` and `/en-au/` stop surfacing in branded search.
- `/book/` results collapse onto `/ebooks/` canonicals.
- live redirects and canonical destinations remain unchanged.
