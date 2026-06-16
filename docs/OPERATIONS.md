# Website production operations

**Status:** Production-controlled  
**Last reviewed:** 16 June 2026

The website deploys from the repository root to Cloudflare Pages. Run `bash build.sh`; the output directory is `.`. The build must pass the static health contract, ebook source/derivative checks, redirects, crawler governance, asset validation and release validation.

After deployment, verify `/health.json`, home, ebook catalogue, one canonical ebook page, `/api/v1/books.json`, `/robots.txt`, `/sitemap.xml`, `/llms.txt` and representative redirects. The post-deploy workflow performs strict live checks and should remain the release authority.

Podcast episode pages and transcripts remain R2-governed and are not ordinary website-repository patch targets. For rollback, select a prior Cloudflare Pages deployment or revert the commit, then rerun the live gate.
