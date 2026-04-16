# Crawler Asset Governance

## Canonical files

| Asset | Canonical path | Purpose |
|-------|---------------|---------|
| Robots | `/robots.txt` | Canonical robots directives, AI crawler allowances, and sitemap pointer |
| Sitemap | `/sitemap.xml` | Canonical sitemap — referenced from robots.txt |

## Alias files (retained for compatibility)

| File | Status | Notes |
|------|--------|-------|
| `robot.txt` | Legacy alias | Some crawlers drop the trailing 's'. Identical content to robots.txt. |
| `Sitemap.xml` | Legacy alias | Capital-S variant retained for crawlers that case-match. |
| `site-map.xml` | Legacy alias | Hyphenated variant retained for backwards compatibility. |

## Authoritative source

All crawler files are generated from `scripts/check_crawlers.py` and validated in `config/crawler-checksums.json`.
The canonical publication target for robots is `https://jonathan-harris.online/robots.txt`.
The canonical sitemap target is `https://jonathan-harris.online/sitemap.xml`.

Do not edit alias files directly. Edit `robots.txt` or `sitemap.xml` and re-run the crawler sync script.
