# Jonathan Harris Online — Static Pages

This repository contains static HTML pages for deployment to Cloudflare Pages / GitHub Pages.

## Routes
- `/` → `index.html`
- `/bio/` → `bio/index.html`
- `/newsletter/` → `newsletter/index.html`
- `/contact/` → `contact/index.html`
- `/affiliate/` → `affiliate/index.html`
- `/privacy-policy/` → `privacy-policy/index.html`
- `/terms-of-use/` → `terms-of-use/index.html`
- `404` → `404.html`

Note: `sitemap.xml`, `robots.txt`, and `llms.txt` are managed externally per current setup.

## Audit fixes implemented (Feb 2026)
This repo has been updated to address the items in *Jonathan_Harris_Website_Audit.pdf*.
Key changes include: schema de-duplication, homepage H1 fix, complete hreflang coverage (+ x-default), affiliate rel=sponsored + disclosure, removal of hidden AI DOM content, Core Web Vitals image loading tweaks, and enriched structured data for the podcast + freshness fields.


## Redirects

This site uses a root `_redirects` file (Cloudflare Pages/Netlify-style) to 301 redirect:

- `/robots.txt` → canonical robots file on `assets.jonathan-harris.online`
- `/sitemap.xml` → canonical sitemap on `assets.jonathan-harris.online`
- `/llms.txt` → canonical `llms.txt` hosted on R2

If you are deploying somewhere that does not support `_redirects`, replicate these redirects in that platform’s redirect rules.
