> **Document status:** Production reference  
> **Last reviewed:** 16 June 2026  
> **Operational authority:** Current repository README, SECURITY policy and operations guide.

# Jonathan Harris Online

This repository is the governed static source for `https://jonathan-harris.online`. It contains the public site, ebook catalogue, shared assets, crawler contracts, redirects and build-time validation used by Cloudflare Pages.

## Production boundaries

- The workbook is the human-editable source for ebook routing and book content.
- `data/ebooks-master.json` is the generated in-repository source used by pages and derivatives.
- Podcast episodes and transcript objects are governed in Cloudflare R2, not as repository-owned static patch targets.
- AIMS publishes weekly blog artefacts to the same-origin publication contract; the repository carries the shell and committed fallback.
- `sitemap.xml`, `robots.txt`, `llms.txt`, `_redirects` and `_headers` are release-governed assets.

## Health and deployment

- **Deployment:** Cloudflare Pages
- **Build command:** `bash build.sh`
- **Output directory:** `.`
- **Health:** `GET /health.json`

The build validates the static health contract, ebook generation, route integrity, redirect synchronisation, crawler assets, images and release rules.

## Local release verification

```bash
python -m pip install -r requirements.txt
bash build.sh
```

The governed workbook defaults to `jonathan-harris-site-url-inventory-remediated-release-ready.xlsm`. Set `EBOOK_WORKBOOK_PATH` when validating a different approved workbook.

## Release workflow

1. Make source changes in the governed workbook, templates or source files.
2. Run `bash build.sh` and resolve every failing gate.
3. Open a pull request and wait for production-readiness CI.
4. Merge to `main` or `master` for Cloudflare Pages deployment.
5. Allow the post-deploy workflow to verify live crawlers, pages, APIs and redirect chains.

See [`SECURITY.md`](SECURITY.md), [`docs/OPERATIONS.md`](docs/OPERATIONS.md), [`docs/CRAWLER-GOVERNANCE.md`](docs/CRAWLER-GOVERNANCE.md) and [`docs/image-publishing-contract.md`](docs/image-publishing-contract.md).

## Deterministic production build

The Cloudflare Pages build uses `bash build.sh`. The only Python dependency is pinned in `requirements.txt`; the build reuses the exact installed version when available and installs it otherwise. This keeps local, CI and Pages builds aligned without unnecessary network work.
