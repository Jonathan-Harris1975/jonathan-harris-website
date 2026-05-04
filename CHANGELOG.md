# CHANGELOG

## v11 - Audit caller diagnostics and OpenRouter centralisation

- Kept AI provider resolution centralised in AI Management Suite.
- Disabled the website-side direct OpenRouter fallback in the active audit workflow.
- Improved `/analysis` failure detail propagation into the failed-gate report.
- Preserved callback URL/token env fallback behaviour for GitHub Actions runs.
