# Changelog

## SEO + AEO + GEO audit workflow hardening

- Made callback-to-analysis endpoint derivation deterministic for `/audits/seo-aeo-geo/callback` -> `/audits/seo-aeo-geo/analysis`.
- Removed the duplicate direct OpenRouter fallback from the website audit workflow. AI provider resolution now stays in AI Management Suite via `/analysis` and its shared `services/shared/utils/ai-config.js` setup.
- Hardened `/analysis` response handling so the website workflow only accepts a real `analysis` object and rejects `ok:false`, missing analysis payloads, and unavailable AI states.
- Changed completion-state logic so broken or failed live URLs remain audit findings rather than causing a failed forensic gate. The gate now reflects whether validated AI forensic JSON was received.
- Expanded `summary.json` output to include AI attempts, final scores, verdict, priorities, quick wins, major risks, ranked issue ledger, and expected report paths when a valid analysis payload exists.
- Updated HTML report rendering to consume strict forensic JSON fields as well as compatibility aliases from AI Management Suite.
- Added report tables for AI priority-page and template/component/generator annex payloads.
- Added deterministic unit tests for analysis URL derivation.
