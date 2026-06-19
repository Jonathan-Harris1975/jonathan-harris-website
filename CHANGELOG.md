> **Document status:** Production reference  
> **Last reviewed:** 16 June 2026  
> **Operational authority:** Current repository README, SECURITY policy and operations guide.

# Shared Page Chrome Repair v14

## 2026.06.18

- Restored the canonical desktop-navigation class across generated eBook pages.
- Made the shared sticky header visible and interactive from initial page load.
- Removed obsolete fixed-header compensation that created large empty bands above hero and main content.
- Added a build gate for canonical header/footer presence, visibility precedence and bounded top spacing.
- Documented the shared page-chrome contract and troubleshooting procedure.

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
