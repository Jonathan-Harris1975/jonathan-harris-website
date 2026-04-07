# CSS Audit Execution Report

## Phase 1 — Inventory & analysis

| CSS file | Source lines audited | Original bytes | Referenced from | Notes |
|---|---:|---:|---|---|
| `assets/css/affiliate-inline.css` | `assets/css/affiliate-inline.css:1` | 2856 | `affiliate/index.html:12` | Page-scoped stylesheet. |
| `assets/css/compare-inline.css` | `assets/css/compare-inline.css:1` | 928 | `compare/index.html:43` | Page-scoped stylesheet. |
| `assets/css/ebook-template.css` | `assets/css/ebook-template.css:1-53` | 3950 | `ebooks/index.html:18`; `topics/index.html:17`; `scripts/ebook_pipeline.py:37` | Shared only by ebook, catalogue, and topics pages; pipeline-managed. |
| `assets/css/glossary-inline.css` | `assets/css/glossary-inline.css:1` | 828 | `glossary/index.html:13` | Page-scoped stylesheet. |
| `assets/css/legal-inline.css` | `assets/css/legal-inline.css:1` | 2504 | `privacy-policy/index.html:44`; `terms-of-use/index.html:41` | Shared only by privacy-policy and terms-of-use pages. |
| `assets/css/site.css` | `assets/css/site.css:1` | 81045 | `index.html:20`; `contact/index.html:54`; `compare/index.html:13`; `topics/index.html:14`; `scripts/inject_partials.py:71`; `scripts/inject_partials.py:108` | Global stylesheet; audited separately; contains the only @import chain. |

### Merge candidacy and separation decisions

- `assets/css/site.css:1` was audited separately and left standalone. It is referenced broadly across the site, and `scripts/inject_partials.py:71` plus `scripts/inject_partials.py:108-128` hard-code validation/injection around the shared `site.css` tag, making it the wrong place to absorb page-specific CSS.
- `assets/css/ebook-template.css:1-50` remains separate because it is loaded only on ebook/catalogue/topic pages such as `ebooks/index.html:18`, `topics/index.html:17`, and `catalogue/agriculture/index.html:17`, and the generator pipeline points to that file explicitly at `scripts/ebook_pipeline.py:37`.
- `assets/css/affiliate-inline.css:1`, `assets/css/compare-inline.css:1`, and `assets/css/glossary-inline.css:1` remain separate because each is loaded by exactly one page: `affiliate/index.html:12`, `compare/index.html:43`, and `glossary/index.html:13` respectively.
- `assets/css/legal-inline.css:1` is already the shared legal-pages bundle for `privacy-policy/index.html:44` and `terms-of-use/index.html:41`; no further same-context merge candidate exists in the current tree.

### Duplicate rules / dead blocks / import chains

- `assets/css/affiliate-inline.css:1` contained a second `.grid` block later in the same file that overrode the earlier `.grid` declaration entirely, plus later `.card` and `.more` blocks that partially overrode earlier declarations. Those blocks were collapsed into single final declarations before minification so the live cascade remains unchanged.
- `assets/css/site.css:1` contains the only stylesheet import chain in the repo via `@import url("https://fonts.googleapis.com/...Inter...")`; no other CSS file uses `@import`, and no barrel-style CSS include chain was present.
- No exact duplicate standalone CSS files remained in the current tree. The only already-consolidated shared page bundle is `assets/css/legal-inline.css:1` for the two legal pages.

## Phase 2 / 3 — Executed merge plan

| Source Files | Proposed Output File | Justification | Risk | Execution |
|---|---|---|---|---|
| `assets/css/site.css` + any page-scoped CSS | Not approved | Cross-page merge would force page-only CSS onto unrelated pages and violates the page-context constraint. Evidence: `index.html:20`, `contact/index.html:54`, `compare/index.html:13`, `topics/index.html:14`, `scripts/inject_partials.py:71` | High | Not executed |
| `assets/css/ebook-template.css` + `assets/css/site.css` | Not approved | `ebook-template.css` is pipeline-managed and only loaded on ebook/catalogue/topic pages. Evidence: `scripts/ebook_pipeline.py:37`, `ebooks/index.html:18`, `topics/index.html:17` | Medium | Not executed |
| `assets/css/affiliate-inline.css` internal duplicate/dead blocks | Same file | Safe intra-file consolidation only. The later `.grid`, `.card`, and `.more` blocks at `assets/css/affiliate-inline.css:1` already determined the live cascade. | Low | Executed before minification |

## Phase 4 — Minification

- No CSS source maps were present before execution. No `.map` files existed under the repo root, and no `sourceMappingURL` comment was present in any stylesheet under `assets/css/`.
- The repository does not use a `/dist` or `/build` CSS output directory for published assets. The live HTML files point directly at `/assets/css/*.css`, so minification was performed in place.
- Preferred CSS CLI compressors were not installed in the environment. Minification used the available `tinycss2` parser/serializer to preserve rule order, selector text, and custom-property values while removing whitespace and dead intra-file overrides where safe.

| File | Original bytes | Minified bytes | Reduction |
|---|---:|---:|---:|
| `assets/css/affiliate-inline.css` | 2856 | 2612 | 8.54% |
| `assets/css/compare-inline.css` | 928 | 928 | 0.00% |
| `assets/css/ebook-template.css` | 3950 | 3884 | 1.67% |
| `assets/css/glossary-inline.css` | 828 | 828 | 0.00% |
| `assets/css/legal-inline.css` | 2504 | 2503 | 0.04% |
| `assets/css/site.css` | 81045 | 80967 | 0.10% |

## Phase 5 — Verification

- All HTML stylesheet links resolved to existing files. Verified against `221` `<link ... href="*.css">` references across the repo; see `css-ref-check-post-validation.tsv` for the full path-by-path result.

- `/opt/pyvenv/bin/python scripts/inject_partials.py --validate` → **FAIL** (return code: `1`)
- `/opt/pyvenv/bin/python scripts/validate_release.py` → **FAIL** (return code: `1`)
- `/opt/pyvenv/bin/python scripts/deployment_ci.py` → **FAIL** (return code: `1`)

See also: `VALIDATION_OUTPUT.txt`, `css-ref-check-post-validation.tsv`, and `css-size-report.json`.