# Changelog

## SEO + AEO + GEO audit workflow hardening

- Kept AI analysis delegated to AI Management Suite `/audits/seo-aeo-geo/analysis`; the website repo still has no duplicate direct OpenRouter stack.
- Increased the website workflow analysis-call timeout so the GitHub audit job can wait for a real forensic JSON response instead of failing around the client timeout boundary.
- Added per-attempt AI analysis diagnostics to `report.html`, `summary.json`, and callback payloads via the existing attempt ledger.
- Captured safe HTTP status/body snippets from `/analysis` failures, including validation and provider diagnostics returned by AI Management Suite.
- Masked bearer tokens and OpenRouter-looking keys in analysis diagnostics.
- Preserved failed-gate behaviour when AI analysis genuinely fails.

## Previous hardening retained

- Deterministic callback-to-analysis URL derivation for `/audits/seo-aeo-geo/callback` -> `/audits/seo-aeo-geo/analysis`.
- Strict acceptance of only a real `analysis` object from AI Management Suite.
- Broken live URLs remain audit findings, not failed-gate causes.
