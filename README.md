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
- `_redirects` is the primary redirect source for the deployed static site refresh it with `python3 scripts/sync_redirects.py` rather than editing both files by hand.
- `robots.txt`, `sitemap.xml`, `site-map.xml`, and `llms.txt` are governed artefacts published from the repo root, while generated source snapshots stay under `config/crawler-snapshots/` for release verification.
- `sitemap.xml` is the canonical sitemap target and `site-map.xml` is the compatibility mirror.
- The sitemap snapshot is generated from the public HTML route registry after excluding pages that explicitly declare `noindex`.



## Source-of-truth boundaries
- The workbook is the human-editable source of truth for ebook routing fields and raw book content, with `config/workbook-normalisations.json` acting as the approved override registry for governed copy normalisations.
- `data/ebooks-master.json` is the generated in-repo master record produced from the workbook import path.
- `data/ebooks-master.json` is the only in-repo source used by generated pages and derivative outputs.
- Refresh the generated master record from the workbook with `python3 scripts/import_ebook_workbook.py <workbook.xlsx>` before rebuilding the ebook subsystem.
- Canonical `ebooks/<slug>/index.html` pages are generated and synchronised from the generated master record with `python3 scripts/fix_book_head_metadata.py`.
- Generated derivatives are rebuilt from the generated master record with `python3 scripts/build_book_derivatives.py`.
- Treat `ebooks/books.json`, `assets/js/books.json`, `api/v1/books.json`, `config/crawler-snapshots/*`, and per-book sidecars as generated outputs, not hand-edited source files.
- `blog/posts.json` is the committed weekly-archive manifest; the weekly blog page should enhance from that local artefact rather than from remote fallbacks.
- `docs/third-party-dependency-matrix.md` documents the governed third-party vendors, fallbacks, and failure modes for the live site.
- `docs/image-publishing-contract.md` documents the remote image publishing contract for logos, hero art, and ebook covers.
- Workbook routing fields are intentionally split: `Buy now URL` is the canonical internal route, `Redirect URL` is the final off-site retailer or shortlink destination, and `Legacy alias URL` is the legacy `/book/<slug>/buy-now` path.
- Legacy buy-now aliases must resolve to the canonical internal buy route first, then continue to the final off-site destination.
- `Summary` is the long-form structured explanation field. It is not the same source as `Short description`, which only feeds the shorter summary/card surfaces.

## Route policy
- `/ebooks/<slug>/` is the sole canonical indexable book route.
- `/ebooks/<slug>/detail`, `/ebooks/<slug>/detail.html`, and `/ebooks/<slug>/details.html` are retired legacy routes that now 301 to `/ebooks/<slug>/`.
- Public pages now carry the shared header/footer in initial HTML; `assets/js/site-ui.js` should enhance that shell, not create it from scratch.

## Validation commands
1. `python3 scripts/import_ebook_workbook.py <workbook.xlsx> --check`
2. `python3 scripts/sync_redirects.py --check`
3. `python3 scripts/fix_book_head_metadata.py --check`
4. `python3 scripts/build_book_derivatives.py --check`
5. `python3 scripts/maintenance/check_buy_now.py`
6. `python3 scripts/check_crawlers.py`
7. `python3 scripts/check_crawlers.py --live`
8. `python3 scripts/check_crawlers.py --live --strict-live`
9. `python3 scripts/check_live_pages.py --strict`
10. `python3 scripts/maintenance/check_identifiers.py`
11. `python3 scripts/check_image_assets.py`
12. `python3 scripts/check_image_assets.py --live`
13. `python3 scripts/validate_release.py --workbook <workbook.xlsx>`
14. `python3 scripts/validate_release.py --workbook <workbook.xlsm> --post-deploy-live`
15. `python3 scripts/validate_release.py --workbook <workbook.xlsm> --strict-post-deploy-live`
16. `python3 scripts/maintenance/check_redirect_chains.py`
17. `python3 scripts/maintenance/rebuild_ebook_subsystem.py <workbook.xlsx>`

## Live crawler validation modes
- `python3 scripts/check_crawlers.py` keeps the existing pre-deploy repo checks only.
- `python3 scripts/check_crawlers.py --live` adds live GET validation against the published crawler URLs but does not fail the command when the deployment is drifting.
- `python3 scripts/check_crawlers.py --live --strict-live` is the hard gate for post-deploy validation.
- `python3 scripts/validate_release.py --post-deploy-live` runs the normal release checks first, then runs the live crawler checks plus the curated live page/API contract smoke checks.
- Add `--skip-live-content` when you only want crawler reachability and do not want exact crawler content matching.
- Add `--skip-live-page-smoke` when you need to bypass the curated live page/API smoke checks for local diagnostics only.

## Deployment automation
- `build.sh` is the Cloudflare Pages-friendly build entrypoint for this repo.
- Set the Pages build command to `bash build.sh` and the output directory to `.`.
- `scripts/deployment_ci.py` runs the governed build-time CI chain: optional workbook import, page regeneration, derivative rebuild, redirect sync, crawler snapshot checks, and release validation.
- Workbook import is automatic when either `--workbook` is supplied, `EBOOK_WORKBOOK_PATH` is set, or exactly one workbook is present in the repo root. If multiple workbook candidates exist, the build now fails fast until one governed workbook is selected explicitly.
- `.github/workflows/ebook-subsystem-ci.yml` mirrors the build-time validation path on pull requests and adds a post-deploy live gate on `main` and `master` pushes.

## Post-deploy notification and Cloudflare purge
- `scripts/post_deploy_notify.py` still supports the legacy production success webhook at `https://hooks.jonathan-harris.online/b9gwu0nlgc751d`.
- The same script can now also call the AI Management Suite Cloudflare purge route directly, or a Hookdeck URL that forwards to it, by setting `CLOUDFLARE_PURGE_ENDPOINT_URL`.
- When `CLOUDFLARE_PURGE_ENDPOINT_URL` is present, the script sends a JSON purge request shaped for the suite route at `/cloudflare/purge`, with `{"hosts": ["jonathan-harris.online"]}` by default.
- If the suite requires auth, set `CLOUDFLARE_PURGE_SHARED_SECRET`; the script sends it as `x-cloudflare-purge-secret`.
- Override the default purge host with `CLOUDFLARE_PURGE_HOSTS` using a comma-separated hostname list.
- The notifier is wired in as the final step of the `post-deploy-live-gate` job in `.github/workflows/ebook-subsystem-ci.yml`.
- It fires once per successful deployment workflow run only after the push target is `main` or `master`, the build validation job has passed, live reachability has passed, strict post-deploy live validation has passed, and live redirect validation has passed.
- It does not fire on pull requests, on failed validation, on failed live checks, or when the workflow never reaches the final successful state of the post-deploy gate.
- The legacy webhook payload includes `event`, `repository`, `branch`, `commit_sha`, `commit_message`, `actor`, `workflow`, `run_id`, `run_number`, `run_url`, `deployed_url`, `environment`, `status`, and `timestamp_utc`.
- Delivery uses bounded retries with exponential backoff and a request timeout. If delivery still fails, the final workflow step fails visibly so the problem is not hidden.
