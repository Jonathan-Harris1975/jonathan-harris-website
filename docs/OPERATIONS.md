# Website production operations

**Status:** Production-controlled  
**Last reviewed:** 16 June 2026

The website deploys from the repository root to Cloudflare Pages. Run `bash build.sh`; the output directory is `.`. The build must pass the static health contract, ebook source/derivative checks, redirects, crawler governance, asset validation and release validation.

After deployment, verify `/health.json`, home, ebook catalogue, one canonical ebook page, `/api/v1/books.json`, `/robots.txt`, `/sitemap.xml`, `/llms.txt` and representative redirects. The post-deploy workflow performs strict live checks and should remain the release authority.

Podcast episode pages and transcripts remain R2-governed and are not ordinary website-repository patch targets. For rollback, select a prior Cloudflare Pages deployment or revert the commit, then rerun the live gate.

## Post-deployment integrations

The strict live validation gate is the release authority. Notification and cache-purge integrations run only after the live crawler, page, API and redirect checks have passed.

No webhook endpoint is hard-coded in the repository. Configure only the integrations that are actively used:

- `POST_DEPLOY_WEBHOOK_URL` as a GitHub Actions secret for an optional downstream success webhook.
- `CLOUDFLARE_PURGE_ENDPOINT_URL` as a GitHub Actions secret for the optional AIMS or Hookdeck purge endpoint.
- `CLOUDFLARE_PURGE_SHARED_SECRET` as a GitHub Actions secret when the purge endpoint requires authentication.
- `CLOUDFLARE_PURGE_HOSTS` as a GitHub Actions variable when the default production hostname is insufficient.

When an integration is not configured, the notifier records a clear skip message and exits successfully. When an explicitly configured endpoint rejects delivery, the workflow fails so the broken integration is visible rather than silently discarded. Deleted or rotated webhook URLs must therefore be removed or replaced in GitHub Actions secrets.
