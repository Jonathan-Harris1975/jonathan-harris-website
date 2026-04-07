# CSS Consolidation and Minification Execution Report

## Phase 3 executed merge

- Source files collapsed into one legal stylesheet:
  - `assets/css/privacy-policy-inline.css:1` (pre-merge source)
  - `assets/css/terms-of-use-inline.css:1` (pre-merge source)
  - Output: `assets/css/legal-inline.css:1`
- Updated page references:
  - `privacy-policy/index.html:44` now loads `/assets/css/legal-inline.css`
  - `terms-of-use/index.html:41` now loads `/assets/css/legal-inline.css`
- Deleted originals after relinking:
  - `assets/css/privacy-policy-inline.css`
  - `assets/css/terms-of-use-inline.css`

## Phase 4 minification results

| File | Evidence | Original bytes | Minified bytes | Reduction |
|---|---|---:|---:|---:|
| `assets/css/affiliate-inline.css` | `assets/css/affiliate-inline.css:1` | 2856 | 2856 | 0.00% |
| `assets/css/compare-inline.css` | `assets/css/compare-inline.css:1` | 928 | 928 | 0.00% |
| `assets/css/ebook-template.css` | `assets/css/ebook-template.css:1-50` | 3950 | 3907 | 1.09% |
| `assets/css/glossary-inline.css` | `assets/css/glossary-inline.css:1` | 828 | 828 | 0.00% |
| `assets/css/legal-inline.css` | `assets/css/legal-inline.css:1` | 2504 | 2504 | 0.00% |
| `assets/css/site.css` | `assets/css/site.css:1` | 81045 | 81045 | 0.00% |

Notes:
- `site.css` was audited separately and not merged into any other file. It remains a standalone global bundle at `assets/css/site.css:1`.
- No CSS source maps were present before execution. No `.map` files existed under the repo root, and no `sourceMappingURL` comment was present in `assets/css/site.css:1`, `assets/css/affiliate-inline.css:1`, `assets/css/compare-inline.css:1`, `assets/css/glossary-inline.css:1`, `assets/css/legal-inline.css:1`, or `assets/css/ebook-template.css:1-50`.

## Phase 5 verification

### CSS path validation
- Repository-wide HTML scan found 221 local stylesheet links and 0 broken local CSS references after the merge.
- Representative live references:
  - `index.html:15` loads `/assets/css/site.css`
  - `affiliate/index.html:12` loads `/assets/css/affiliate-inline.css`
  - `compare/index.html:43` loads `/assets/css/compare-inline.css`
  - `ebooks/index.html:18` loads `/assets/css/ebook-template.css`
  - `privacy-policy/index.html:44` loads `/assets/css/legal-inline.css`
  - `terms-of-use/index.html:41` loads `/assets/css/legal-inline.css`

### Existing validation/build script results
- `python3 scripts/deployment_ci.py --workbook jonathan-harris-site-url-inventory-remediated-release-ready.xlsm` failed at `scripts/deployment_ci.py:112`, where the pipeline runs `scripts/inject_partials.py --validate`.
- The failing validator reported existing header drift in many generated pages. Example affected heads:
  - `catalogue/agriculture/index.html:13-17`
  - `ebooks/index.html:14-18`
  These pages load CSS but do not contain the shared Inter font head block that appears on pages such as `privacy-policy/index.html:41-43` and `newsletter/index.html:12-14`.
- `python3 scripts/validate_release.py --workbook jonathan-harris-site-url-inventory-remediated-release-ready.xlsm` failed with 5 issues:
  1. Shared CSS missing `.sr-only` while HTML still references it. Validator logic is at `scripts/ebook_pipeline.py:3535-3537`. HTML references exist at `404.html:94` and `podcast/index.html:96,100,104,114,172,175`.
  2. Inline style attributes in `contact/index.html:287,295,307-355`.
  3. Inline style attributes in `newsletter/index.html:267,300,307,313,315,319,322,327,339-387`.
  4. Workbook title mismatch at `contact/index.html:10`.
  5. Workbook title mismatch at `newsletter/index.html:6`.
