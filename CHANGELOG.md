# Website Audit Workflow Fix v12

## Fixed
- Added `callback_token` as an optional workflow input for Koyeb-triggered audit runs.
- The workflow now prefers the Koyeb-supplied callback token, then falls back to GitHub environment secrets for manual runs.
- Direct website-side OpenRouter fallback remains disabled so provider resolution stays centralised in AI Management Suite.
