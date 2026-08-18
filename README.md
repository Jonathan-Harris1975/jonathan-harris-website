# Jonathan Harris Online

This repository is the governed static source for `https://jonathan-harris.online`. It contains the public site, eBook catalogue, shared assets, crawler contracts, redirects, Cloudflare Pages Functions and validation scripts.

## Source boundaries

- The governed workbook is the human-editable source for eBook routing/content.
- `data/ebooks-master.json` is the generated in-repository eBook data source used by pages and derivatives.
- Podcast episodes/transcripts are governed in Cloudflare R2 rather than treated as static patch targets here.
- AIMS publishes weekly blog artefacts to R2; this repository contains the public blog shell/runtime renderer rather than a committed article fallback.
- `sitemap.xml`, `robots.txt`, `llms.txt`, `_redirects` and `_headers` are governed public assets.

## CogniPal website chat

The current site uses the first-party CogniPal integration. Public pages load the governed CogniPal CSS/JavaScript; same-origin Pages Functions under `/api/cognipal/*` sign server-to-server requests into AIMS Comms Hub.

- BotSailor is intentionally absent from the public runtime and CSP.
- The launcher uses the CogniPal image asset.
- First-time visitors see the launcher after 30 seconds or after 35% page scroll, whichever comes first; returning engaged visitors can see it immediately.
- The widget never auto-opens.
- Public copy speaks directly about messages going to Jonathan rather than implying a separate team.

The validation script `scripts/check_webchat_contract.py` prevents BotSailor from being reintroduced into public runtime surfaces.

## Deployment and validation

Cloudflare Pages publishes the repository root. The deployment validation entry point is the existing `bash build.sh` script, which runs the governed static checks and generation steps required by Pages.

Local verification:

```bash
python -m pip install -r requirements.txt
bash build.sh
```

The default governed workbook is `jonathan-harris-site-url-inventory-remediated-release-ready.xlsx`; use `EBOOK_WORKBOOK_PATH` only when deliberately validating another approved workbook.

Validation covers health, eBook derivatives, route/redirect integrity, shared chrome, layout spacing/header visibility, crawler assets, images, first-party webchat and generated-output drift.

## Operational references

- `SECURITY.md`
- `docs/OPERATIONS.md`
- `docs/CRAWLER-GOVERNANCE.md`
- `docs/SHARED-CHROME-LAYOUT.md`
- `docs/cognipal-webchat-deployment.md`
- `docs/image-publishing-contract.md`
