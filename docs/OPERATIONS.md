# Website production operations

**Status:** Production-controlled  
**Last reviewed:** 21 September 2026

## Release model

The website deploys from the repository root to Cloudflare Pages. The canonical build command is:

```bash
bash build.sh
```

The Pages output directory is `.`. CI uses Python 3.13 and Node.js 22. Direct production pins live in `requirements.in`; `requirements.txt` is the fully resolved production closure with repository-controlled SHA-256 hashes. The build validates the reviewed closure, verifies fail-closed hash enforcement, refuses mismatched installed versions and installs with `--require-hashes` when needed.

A release-ready build must run in a connected clean checkout because the governed manuscript-sample stage may download source PDFs. `--skip-manuscript-sync` is a local diagnostic option only and must not be treated as equivalent evidence for production release readiness.

The build covers the static health contract, repository hygiene, secret scanning, PDF compatibility, eBook source/derivative generation, redirects, crawler governance, shared chrome and assets, CogniPal/Pages/Agent Readiness contracts, CSP checks, release validation and generated-output drift.

## Dependency integrity

The production dependency contract is deliberately split:

- `requirements.in` is the human-reviewed list of direct exact pins;
- `requirements.txt` is the complete reviewed closure with exact versions and SHA-256 artefact hashes;
- `requirements-audit.txt` is a separate audit-tool environment and must not be used for the Pages production build.

Validate and install the production lock with:

```bash
python scripts/check_requirements_lock.py
python scripts/check_hash_fail_closed.py
python -m pip install --disable-pip-version-check --require-hashes -r requirements.txt
python -m pip check
```

A dependency update is incomplete until the direct input (when applicable), full transitive closure, hashes and reviewed closure in `scripts/check_requirements_lock.py` agree. Do not copy hashes from an untrusted package download produced during the same build that is being protected.

## Dependency and PDF upgrade gate

The PDF pipeline uses:

- `pypdf` for manuscript PDF reading/text extraction;
- `reportlab` for deterministic glossary PDF generation.

Before accepting a PDF dependency update, upgrade one package at a time and run:

```bash
python -m unittest scripts.test_pdf_pipeline scripts.test_sync_manuscript_samples
bash build.sh
python -m pip install --disable-pip-version-check pip-audit==2.10.1
python -m pip_audit -r requirements.txt
```

The focused PDF regression requires deterministic glossary bytes, successful pypdf reading of the generated glossary and successful extraction of a representative generated manuscript chapter. The full build remains the final compatibility gate.

## Cloudflare runtime requirements

`wrangler.toml` is the version-controlled binding contract for the Pages project. It defines the transcript/blog R2 buckets, the CogniPal rate-limit Durable Object binding and the Agent Readiness service binding.

Deploy the standalone Workers before a Pages deployment that depends on them:

1. `workers/cognipal-rate-limit`
2. `workers/agent-readiness`
3. root Cloudflare Pages project

Detailed Worker configuration is documented in `docs/cognipal-webchat-deployment.md`, `workers/agent-readiness/README.md` and `docs/AGENT-READINESS-DEPLOYMENT.md`.

CogniPal Pages secrets/variables must remain in Cloudflare configuration, never committed source. The required secret is `COMMS_HUB_COGINPAL_WEBHOOK_SECRET`; the AIMS origin is supplied through `AIMS_COMMS_HUB_BASE_URL`.

## Post-deploy checks

After deployment, verify at minimum:

- `/health.json`
- `/`
- `/ebooks/`
- one canonical `/ebooks/<slug>/` page
- `/api/v1/books.json`
- `/robots.txt`
- `/sitemap.xml`
- `/llms.txt`
- representative legacy redirects
- CogniPal request handling
- Agent Readiness discovery endpoints and gateway headers

The post-deploy CI workflow is the release authority: it waits for the expected live release, validates crawler and redirect contracts, and records deployment evidence. Do not treat a successful upload alone as proof that the intended release is live.

## Rollback and recovery

For a Pages regression, select a previous known-good Cloudflare Pages deployment or revert the offending commit, then rerun the live release gate. For a Worker regression, redeploy the previous known-good Worker revision and then revalidate the Pages integration contract.

Podcast episode pages and transcripts remain R2-governed and are not ordinary repository patch targets. The podcast landing page and homepage obtain current episode facts from the externally governed RSS feed through same-origin Pages Functions. Do not copy episode titles, dates, durations or transcript facts into hand-maintained repository data to make those surfaces look static.

Weekly blog publications are likewise R2/AIMS-governed. Do not create a parallel committed article store as a fallback.

## HIVE reconstruction contract

Canonical HIVE repository identity: **`Website`**. HIVE Repository Memory and Intelligence should reconstruct this service from `README.md`, `wrangler.toml`, `requirements.in`, `requirements.txt`, `requirements-audit.txt`, `build.sh`, the production/release workflows, and this operations document. Those sources together define architecture, dependencies, cryptographic build lock, build/release profile, Cloudflare deployment bindings, environment contracts, live verification and rollback.

## Commercial measurement and reconciliation

The repository-owned funnel contract is documented in [`docs/ANALYTICS-EVENT-CONTRACT.md`](ANALYTICS-EVENT-CONTRACT.md). GTM/GA4 may map those first-party `dataLayer` events downstream, but event payloads must remain free of email addresses, free-text form values and other PII.

Amazon outbound clicks can be reconciled with supplied KDP sales data using [`docs/KDP-RECONCILIATION.md`](KDP-RECONCILIATION.md) and `scripts/reconcile_kdp.py`. The repository does not infer or scrape KDP sales and must not manufacture an outbound-to-sale conversion rate when real sales data is absent.

## Search Console stale-URL remediation

Legacy `/book/*` routes remain compatibility redirects to canonical `/ebooks/*` routes. After a production release, follow [`docs/search-console-stale-url-removal-plan.md`](search-console-stale-url-removal-plan.md): verify direct permanent redirects, inspect affected legacy URLs, request indexing of canonical replacements, submit the authoritative `/sitemap.xml`, and monitor old impressions until the live index changes. Do not claim stale results have disappeared before Search Console or the public index confirms it.
