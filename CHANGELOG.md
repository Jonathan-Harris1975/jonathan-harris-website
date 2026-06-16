> **Document status:** Production reference  
> **Last reviewed:** 16 June 2026  
> **Operational authority:** Current repository README, SECURITY policy and operations guide.

# Website CI Notification Fix v13

## 2026.06.16

- Removed the deleted legacy webhook URL that was embedded as a notifier default.
- Made post-deploy webhook and Cloudflare purge delivery explicitly secret-driven and optional.
- Added regression tests for the no-webhook and explicit-webhook configurations.
- Updated GitHub Actions to Node 24-compatible major releases.

# Website Audit Workflow Fix v12

## 2026.06.16

- Added a static production health contract at `/health.json`.
- Added health validation to the governed build pipeline.
- Added production-readiness CI and refreshed operational documentation.

## Fixed
- Added `callback_token` as an optional workflow input for Koyeb-triggered audit runs.
- The workflow now prefers the Koyeb-supplied callback token, then falls back to GitHub environment secrets for manual runs.
- Direct website-side OpenRouter fallback remains disabled so provider resolution stays centralised in AI Management Suite.
