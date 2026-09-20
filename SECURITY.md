# Website security policy

**Status:** Production-controlled  
**Last reviewed:** 20 September 2026

The site is static, but its build and publishing chain includes third-party scripts, forms, analytics, remote images, Cloudflare Pages Functions and deployment webhooks. Security controls therefore focus on content integrity, strict build validation, CSP and browser headers, dependency governance, secret isolation and post-deploy verification.

Do not commit API keys, webhook secrets or Cloudflare credentials. Keep deployment credentials in GitHub or Cloudflare encrypted settings. Any CSP expansion must be tied to a documented vendor in `docs/third-party-dependency-matrix.md`.

Report suspected content injection, redirect abuse, exposed credentials or compromised deployment behaviour privately to the repository owner.

## Secret scanning

Run the same committed-source secret gate used by CI before pushing:

```bash
python3 scripts/scan_secrets.py
```

The scanner covers private-key blocks, GitHub-style tokens, cloud access keys, passwords and generic secrets, bearer/API tokens, webhook credentials, common vendor credentials, and high-entropy values in credential-bearing assignments. It excludes known generated/vendor locations and never prints detected secret values.

Synthetic regression fixtures may be exempted only through `.secret-scan-allowlist.json`. Every exception is bound to an exact repository path, scanner rule and SHA-256 of the exact fixture line, with a documented reason. Do not add directory-wide, wildcard or generic source-code exceptions.

