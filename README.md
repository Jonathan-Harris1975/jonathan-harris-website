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
- Legacy detail routes: `/ebooks/<slug>/detail`, `/ebooks/<slug>/detail.html`, and `/ebooks/<slug>/details.html` (all permanently redirected to the canonical eBook page)

## Data and shared assets
- Master ebook data: `data/ebooks-master.json`
- Canonical book manifest: `ebooks/books.json`
- Public/API derivatives: `assets/js/books.json`, `api/v1/books.json`, `feed.json`, `ai/entity-map.json`
- Shared partials: `assets/partials/header.html`, `assets/partials/footer.html`
- Shared styles/scripts: `assets/css/*`, `assets/js/*`

## Redirects
- `_redirects` is the primary redirect source for the deployed static site.
- `_redirects.txt` is a generated mirror of `_redirects`; refresh it with `python3 scripts/sync_redirects.py` rather than editing both files by hand.
- `robots.txt`, `sitemap.xml`, and `llms.txt` remain externally hosted in production, but the repo keeps generated, versioned source snapshots for release verification.
- Those crawler snapshots are rebuilt by the derivative pipeline and verified before release; the main domain redirects point the live host at the externally published copies.



## Source-of-truth boundaries
- The workbook is the human-editable source of truth for ebook routing fields and book content.
- `data/ebooks-master.json` is the generated in-repo master record produced from the workbook import path.
- `data/ebooks-master.json` is the only in-repo source used by generated pages and derivative outputs.
- Refresh the generated master record from the workbook with `python3 scripts/import_ebook_workbook.py <workbook.xlsx>` before rebuilding the ebook subsystem.
- Canonical `ebooks/<slug>/index.html` pages are generated and synchronised from the generated master record with `python3 scripts/fix_book_head_metadata.py`.
- Generated derivatives are rebuilt from the generated master record with `python3 scripts/build_book_derivatives.py`.
- Treat `ebooks/books.json`, `assets/js/books.json`, `api/v1/books.json`, `robots.txt`, `sitemap.xml`, `llms.txt`, and per-book sidecars as generated outputs, not hand-edited source files.

## Route policy
- `/ebooks/<slug>/` is the sole canonical indexable book route.
- `/ebooks/<slug>/detail`, `/ebooks/<slug>/detail.html`, and `/ebooks/<slug>/details.html` are retired legacy routes that now 301 to `/ebooks/<slug>/`.
- Public pages now carry the shared header/footer in initial HTML; `assets/js/site-ui.js` should enhance that shell, not create it from scratch.

## Validation commands
1. `python3 scripts/import_ebook_workbook.py <workbook.xlsx> --check`
2. `python3 scripts/sync_redirects.py --check`
3. `python3 scripts/fix_book_head_metadata.py --check`
4. `python3 scripts/build_book_derivatives.py --check`
5. `python3 scripts/check_buy_now.py`
6. `python3 scripts/check_crawlers.py`
7. `python3 scripts/check_identifiers.py`
8. `python3 scripts/validate_release.py --workbook <workbook.xlsx>`
9. `python3 scripts/rebuild_ebook_subsystem.py <workbook.xlsx>`
