# Website security policy

**Status:** Production-controlled  
**Last reviewed:** 16 June 2026

The site is static, but its build and publishing chain includes third-party scripts, forms, analytics, remote images, Cloudflare Pages Functions and deployment webhooks. Security controls therefore focus on content integrity, strict build validation, CSP and browser headers, dependency governance, secret isolation and post-deploy verification.

Do not commit API keys, webhook secrets or Cloudflare credentials. Keep deployment credentials in GitHub or Cloudflare encrypted settings. Any CSP expansion must be tied to a documented vendor in `docs/third-party-dependency-matrix.md`.

Report suspected content injection, redirect abuse, exposed credentials or compromised deployment behaviour privately to the repository owner.
