# Website CI Fix Report v13

## Incident summary

The website build and strict live production checks completed successfully. The workflow failed only in the final notification step because `scripts/post_deploy_notify.py` contained a hard-coded legacy webhook URL that now returns HTTP 410 `DELETED`.

The deployment itself was healthy: crawler publication, governed page parity, the public books API and redirect-chain validation all passed before the notifier ran.

## Root cause

The notifier used a repository-embedded default webhook when `POST_DEPLOY_WEBHOOK_URL` was absent. That endpoint had been deleted, so the otherwise successful post-deployment job exited with code 1.

## Changes

### Notification configuration

- Removed the hard-coded legacy webhook URL.
- Made legacy webhook delivery opt-in through the `POST_DEPLOY_WEBHOOK_URL` GitHub Actions secret.
- Wired the optional Cloudflare purge endpoint, secret and host list into the workflow.
- Preserved fail-visible behaviour when an explicitly configured integration rejects delivery.

### CI maintenance

- Updated GitHub-hosted JavaScript actions to Node 24-compatible v6 major releases.
- Added four regression tests covering missing and explicit webhook configuration.
- Added a five-minute bound to the optional notification step.

### Documentation

- Updated the production operations guide with the integration and secret contract.
- Added the v13 change record.

## Verification

- Post-deploy notifier tests: 4 passed.
- Notifier with no integrations configured: exits successfully and performs no network request.
- Python compilation: passed.
- All four workflow YAML files: parsed successfully.
- Deleted webhook URL scan: no remaining reference in scripts, workflows or operations documentation.
- The uploaded CI evidence showed the governed build and strict live gate passing before the deleted webhook returned HTTP 410.

## Files

### Updated

- `.github/workflows/ebook-subsystem-ci.yml`
- `.github/workflows/mobile-ux-hard-gate.yml`
- `.github/workflows/production-readiness.yml`
- `.github/workflows/seo-aeo-geo-forensic.yml`
- `scripts/post_deploy_notify.py`
- `docs/OPERATIONS.md`
- `CHANGELOG.md`

### New

- `scripts/test_post_deploy_notify.py`

## GitHub configuration

No webhook secret is required when notifications are not used. To enable them, create or replace:

- `POST_DEPLOY_WEBHOOK_URL`
- `CLOUDFLARE_PURGE_ENDPOINT_URL` (optional)
- `CLOUDFLARE_PURGE_SHARED_SECRET` (optional)
- `CLOUDFLARE_PURGE_HOSTS` as a repository variable (optional)

A deleted endpoint must not remain in the corresponding secret.
