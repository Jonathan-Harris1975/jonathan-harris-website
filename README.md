# Jonathan Harris Online - Static Site Repository

This repository contains the static HTML, CSS, JavaScript, JSON manifests, partials, and redirect/config files for Jonathan Harris Online.

## Public route families
- `/` home page
- `/404.html` not-found page
- Core routes: `/affiliate/`, `/api/docs/`, `/bio/`, `/compare/`, `/contact/`, `/glossary/`, `/newsletter/`, `/podcast/`, `/privacy-policy/`, `/terms-of-use/`
- Blog routes: `/blog/`, `/blog/weekly/`
- Topic routes: `/topics/` plus guide pages under `/topics/*/`
- Catalogue routes: `/catalogue/*/`
- eBook catalogue: `/ebooks/`
- Canonical eBook pages: `/ebooks/<slug>/`
- Legacy eBook detail pages: `/ebooks/<slug>/detail.html`

## Data and shared assets
- Canonical book manifest: `ebooks/books.json`
- Public/API derivatives: `assets/js/books.json`, `api/v1/books.json`, `feed.json`, `ai/entity-map.json`
- Shared partials: `assets/partials/header.html`, `assets/partials/footer.html`
- Shared styles/scripts: `assets/css/*`, `assets/js/*`

## Redirects
- `_redirects` is the primary redirect source for the deployed static site.
- `_redirects.txt` mirrors the current redirect rules and should be kept in sync if a deployment workflow still depends on it.
- `robots.txt`, `sitemap.xml`, and `llms.txt` are present locally and also redirected to their externally hosted canonical assets by `_redirects`.
