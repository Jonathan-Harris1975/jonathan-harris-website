# Jonathan Harris website update patch

Date: 31 July 2026

Extract this ZIP over the repository root and replace existing files. No files are deleted by this patch.

## What this patch fixes

- Repairs the corrupted AI Agents, Agriculture and Aviation eBook outputs through the canonical generator.
- Removes the dated April 2026 blog fallback wording.
- Adds and validates social-sharing metadata across public pages.
- Adds intrinsic dimensions to reading-path cover images.
- Aligns image validation with the governed remote-image policy.
- Shortens overlong metadata while keeping workbook governance in sync.
- Makes the AI glossary PDF deterministic.
- Adds a Git working-tree drift gate so stale generated output fails CI.
- Refreshes crawler manifests, generated pages and validation evidence.

## Validation completed

- Ebook route integrity: 40 of 40 governed books passed.
- Shared header/footer: 120 of 120 pages passed.
- Social metadata, image assets, CSS budget, colour contrast and third-party script governance passed.
- Schema gate: 122 checked, 0 critical, 0 advisory.
- Workbook title parity: 92 of 92 routes passed.
- Workbook content parity: 400 fields, 0 mismatches.
- Deterministic rebuild: second complete pass changed 0 files.

## Included files (92)

- **Modified** `VALIDATION_OUTPUT.txt`
- **Modified** `bio/index.html`
- **Modified** `blog/index.html`
- **Modified** `book-finder/index.html`
- **Modified** `bundles/ai-at-work/index.html`
- **Modified** `bundles/ai-health-and-care/index.html`
- **Modified** `bundles/ai-in-regulated-industries/index.html`
- **Modified** `bundles/ai-mobility-and-logistics/index.html`
- **Modified** `bundles/index.html`
- **Modified** `catalogue/agriculture/index.html`
- **Modified** `catalogue/artificial-intelligence/index.html`
- **Modified** `catalogue/business/index.html`
- **Modified** `catalogue/construction/index.html`
- **Modified** `catalogue/creativity/index.html`
- **Modified** `catalogue/cyber-security/index.html`
- **Modified** `catalogue/defence/index.html`
- **Modified** `catalogue/education/index.html`
- **Modified** `catalogue/energy/index.html`
- **Modified** `catalogue/environment/index.html`
- **Modified** `catalogue/ethics/index.html`
- **Modified** `catalogue/finance/index.html`
- **Modified** `catalogue/future-of-work/index.html`
- **Modified** `catalogue/gaming/index.html`
- **Modified** `catalogue/government/index.html`
- **Modified** `catalogue/healthcare/index.html`
- **Modified** `catalogue/history/index.html`
- **Modified** `catalogue/industry/index.html`
- **Modified** `catalogue/law/index.html`
- **Modified** `catalogue/manufacturing/index.html`
- **Modified** `catalogue/media/index.html`
- **Modified** `catalogue/retail/index.html`
- **Modified** `catalogue/science/index.html`
- **Modified** `catalogue/sports/index.html`
- **Modified** `catalogue/transportation/index.html`
- **Modified** `config/crawler-checksums.json`
- **Modified** `config/crawler-snapshots/llms.txt`
- **Modified** `contribute/index.html`
- **Modified** `data/dynamic-route-manifest.json`
- **Modified** `data/ebook-bundles.json`
- **Modified** `data/evidence-content.json`
- **Modified** `data/search-visibility-surfaces.json`
- **Modified** `downloads/ai-glossary-cheat-sheet/ai-glossary-cheat-sheet.pdf`
- **Modified** `downloads/ai-glossary-cheat-sheet/index.html`
- **Modified** `ebooks/ai-agents-for-everyday-work/index.html`
- **Modified** `ebooks/ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future/index.html`
- **Modified** `ebooks/ai-in-aviation-transforming-safety-and-sustainability/index.html`
- **Modified** `ebooks/ai-in-education-reimagining-learning-for-every-student/index.html`
- **Modified** `ebooks/ai-literacy-for-the-modern-workplace/index.html`
- **Modified** `ebooks/artificial-intelligence-and-the-law-case-studies-and-future-trends/index.html`
- **Modified** `ebooks/artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology/index.html`
- **Modified** `ebooks/artificial-intelligence-in-banking-revolutionizing-finance-and-data-security/index.html`
- **Modified** `ebooks/climate-intelligence-harnessing-ai-for-a-greener-future/index.html`
- **Modified** `ebooks/the-artificial-intelligence-job-shift-navigating-the-future-of-work/index.html`
- **Modified** `ebooks/the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information/index.html`
- **Modified** `ebooks/url-manifest.json`
- **Modified** `evidence/ai-agents-for-ordinary-work/index.html`
- **Modified** `evidence/ai-for-small-business/index.html`
- **Modified** `evidence/ai-governance-and-law/index.html`
- **Modified** `evidence/ai-in-finance/index.html`
- **Modified** `evidence/ai-in-healthcare/index.html`
- **Modified** `evidence/deepfake-detection-and-synthetic-media/index.html`
- **Modified** `evidence/eu-ai-act-article-50-transparency/index.html`
- **Modified** `evidence/index.html`
- **Modified** `evidence/workplace-ai-literacy/index.html`
- **Modified** `for-teams/index.html`
- **Modified** `glossary/index.html`
- **Modified** `index.html`
- **Modified** `jonathan-harris-site-url-inventory-remediated-release-ready.xlsx`
- **Modified** `llm-index.json`
- **Modified** `llms.txt`
- **Modified** `media/index.html`
- **Modified** `methodology/index.html`
- **Modified** `newsletter/index.html`
- **Modified** `podcast/index.html`
- **Modified** `resources/ai-agent-risk-checklist/index.html`
- **Modified** `resources/ai-procurement-questions-small-businesses/index.html`
- **Modified** `resources/ai-regulated-industries-evidence-map/index.html`
- **Modified** `resources/deepfake-verification-checklist/index.html`
- **Modified** `resources/eu-ai-act-article-50-readiness-checklist/index.html`
- **Modified** `resources/index.html`
- **Modified** `resources/responsible-ai-checklist-managers/index.html`
- **Modified** `resources/uk-workplace-ai-literacy-checklist/index.html`
- **Added** `scripts/apply_social_metadata.py`
- **Added** `scripts/check_generated_output_drift.py`
- **Modified** `scripts/check_image_assets.py`
- **Modified** `scripts/deployment_ci.py`
- **Modified** `scripts/ebook_pipeline.py`
- **Modified** `scripts/generate_ai_glossary_pdf.py`
- **Modified** `scripts/generate_ebook_bundles.py`
- **Modified** `scripts/generate_growth_assets.py`
- **Modified** `topics/ai-in-education/index.html`
- **Modified** `topics/index.html`
