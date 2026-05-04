# Changelog

## SEO/AEO/GEO audit callback configuration fix

- Added a default AI Management Suite callback URL for manual `workflow_dispatch` runs.
- Added callback configuration preflight in the GitHub Actions workflow so missing callback secrets fail the run clearly instead of generating a failed-gate report saying analysis was not attempted.
- Added support for `AUDIT_CALLBACK_TOKEN` and `AI_SUITE_AUDIT_CALLBACK_TOKEN` in the website workflow.
- Added optional `analysis_url` workflow input and passed it to the audit script.
- Added runtime fallback in `seo_aeo_geo_forensic.py` so callback URL/token can be read from env when CLI args are blank.
- Added async analysis polling support for AI Management Suite `202 Accepted` responses.
- Improved missing callback diagnostics so the report can say exactly whether `callback_url`, `callback_token`, or both are missing.
