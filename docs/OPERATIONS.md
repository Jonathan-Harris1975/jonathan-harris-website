# Website production operations

**Status:** Production-controlled  
**Last reviewed:** 25 July 2026

The website deploys from the repository root to Cloudflare Pages. Run `bash build.sh`; the output directory is `.`. The build must pass the static health contract, ebook source/derivative checks, redirects, crawler governance, asset validation and release validation.

After deployment, verify `/health.json`, home, ebook catalogue, one canonical ebook page, `/api/v1/books.json`, `/robots.txt`, `/sitemap.xml`, `/llms.txt` and representative redirects. The post-deploy workflow performs strict live checks and should remain the release authority.

Podcast episode pages and transcripts remain R2-governed and are not ordinary website-repository patch targets. For rollback, select a prior Cloudflare Pages deployment or revert the commit, then rerun the live gate.

The podcast landing page and homepage obtain current episode facts from the externally governed RSS feed at request time through same-origin Pages Functions. Do not copy episode titles, dates, durations or transcript facts into hand-maintained repository data to make those surfaces look static.

## Commercial measurement and reconciliation

The repository-owned funnel contract is documented in [`docs/ANALYTICS-EVENT-CONTRACT.md`](ANALYTICS-EVENT-CONTRACT.md). GTM/GA4 may map those first-party `dataLayer` events downstream, but event payloads must remain free of email addresses, free-text form values and other PII.

Amazon outbound clicks can be reconciled with supplied KDP sales data using [`docs/KDP-RECONCILIATION.md`](KDP-RECONCILIATION.md) and `scripts/reconcile_kdp.py`. The repository does not infer or scrape KDP sales and must not manufacture an outbound-to-sale conversion rate when real sales data is absent.

## Search Console stale-URL remediation

Legacy `/book/*` routes remain compatibility redirects to canonical `/ebooks/*` routes. After a production release, follow [`docs/search-console-stale-url-removal-plan.md`](search-console-stale-url-removal-plan.md): verify direct permanent redirects, inspect affected legacy URLs, request indexing of canonical replacements, submit the authoritative `/sitemap.xml`, and monitor old impressions until the live index changes. Do not claim stale results have disappeared before Search Console or the public index proves it.

## Post-deployment integrations

The strict live validation gate is the release authority. Notification and cache-purge integrations run only after the live crawler, page, API and redirect checks have passed. The website workflow does not dispatch MAST or require a GitHub personal access token; MAST owns its ecosystem smoke independently.

No webhook endpoint is hard-coded in the repository. Configure only the integrations that are actively used:

- `POST_DEPLOY_WEBHOOK_URL` as a GitHub Actions secret for an optional downstream success webhook.
- `CLOUDFLARE_PURGE_ENDPOINT_URL` as a GitHub Actions secret for the optional AIMS or Hookdeck purge endpoint.
- `CLOUDFLARE_PURGE_SHARED_SECRET` as a GitHub Actions secret when the purge endpoint requires authentication.
- `CLOUDFLARE_PURGE_HOSTS` as a GitHub Actions variable when the default production hostname is insufficient.

When an integration is not configured, the notifier records a clear skip message and exits successfully. When an explicitly configured endpoint rejects delivery, the workflow fails so the broken integration is visible rather than silently discarded. Deleted or rotated webhook URLs must therefore be removed or replaced in GitHub Actions secrets.
