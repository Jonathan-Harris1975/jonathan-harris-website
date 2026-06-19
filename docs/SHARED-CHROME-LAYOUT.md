> **Document status:** Production reference  
> **Last reviewed:** 18 June 2026

# Shared header, footer and page-top spacing

The website uses one canonical header and footer across every governed static HTML page:

- `assets/partials/header.html`
- `assets/partials/footer.html`

`bash build.sh` regenerates governed pages, injects both partials, and then runs two independent gates:

```bash
python3 scripts/inject_partials.py --validate
python3 scripts/check_shared_chrome_layout.py
```

## Visual contract

- The primary header is sticky and visible from the initial page load.
- Header visibility must not depend on scrolling past a hero section.
- Desktop navigation keeps the `jh-nav-desktop` class.
- Mobile navigation remains collapsed behind the menu button when JavaScript is enabled.
- Hero sections use their own content padding only. They do not reserve space for a fixed or hidden header.
- Direct `main` and `main.wrap` elements use bounded content padding rather than the former 88-pixel fixed-header compensation.
- Every governed page contains exactly one canonical website footer.

The final override block in `assets/css/site.css` is marked:

```text
JH-SHARED-CHROME-VISIBILITY-CONTRACT
```

It intentionally appears after older compatibility rules so the header cannot become transparent or non-interactive at the top of a page.

## Editing rules

1. Edit the partial, never dozens of generated pages by hand.
2. Run `bash build.sh` after changing either partial, the layout CSS, or ebook source data.
3. Commit the generated page updates with the partial and CSS changes.
4. Do not deploy repository-root HTML that has not passed the two shared-chrome gates.

## Troubleshooting

If a page appears to have no header, inspect the computed `opacity`, `visibility`, `pointer-events`, and `transform` values on `.jh-header`. They must resolve to visible and interactive values at scroll position zero.

If a page shows an empty band above its first heading, inspect hero `padding-top` and direct-main padding. The shared contract deliberately removes the historical fixed-header compensation.
