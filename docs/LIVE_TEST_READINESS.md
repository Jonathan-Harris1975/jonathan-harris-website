# Controlled live-test readiness evidence

Repository: `Jonathan-Harris1975/jonathan-harris-website`  
Baseline HEAD: `4d566369265983056b63c030bab996be9b789cd3`  
Assessment date: 2026-10-10 (UTC)  
Verdict: **NOT READY** until all mandatory gates below have witnessed passing evidence.

A successful YAML parse, skipped workflow, or matching release marker alone is not proof of a live deployment.

| Area | Requirement | Status | Implementation/evidence | Validation | Remaining dependency / owner |
| --- | --- | --- | --- | --- | --- |
| Detection | CI, security and deployed failure routing | blocked | `.github/workflows/autonomous-repair.yml`, `deployed-integration.yml` | Inspect last 30 workflow runs, skipped/cancelled conclusions and incident routing | Actions run evidence / repo maintainer |
| Repair | Deduplication, lease fencing, bounded repair PR and escalation | blocked | `.github/scripts/repair_lease.py`, `.github/workflows/autonomous-repair.yml` | Failure/retry/concurrency/stale-SHA simulations and PR review | Reproducible tests and witnessed runs / maintainer |
| Safeguards | Exact deployed SHA, correct environment, freshness and rollback | blocked | `scripts/wait_for_live_release.py`, `.github/workflows/deployed-integration.yml` | Compare origin, SHA, cache headers, deployment identity and independent hosting evidence | Cloudflare deployment metadata, rollback rehearsal / operator |
| Ecosystem | OIDC trust and service contract | blocked | `.github/workflows/oidc-readiness.yml`, `deployed-integration.yml` | Verify provider trust, audiences, endpoint and independent cross-repo evidence | Cloudflare and ecosystem owners |
| Website | Build, assets, routes, TLS, headers, redirects, sitemap, accessibility, browser and outage behaviour | blocked | `build.sh` | Run production build, link/browser/a11y checks and staging outage injection | CI and staging evidence / website owner |

## Safe controlled rehearsal (not yet executed)

1. Confirm current `main` SHA and required successful CI/security checks. Capture workflow run URLs, job conclusions and artefact digests.
2. Confirm staging domain is isolated from production, and deployment credentials are environment-scoped. Record Cloudflare deployment ID, commit SHA, build timestamp and immutable artefact digest.
3. Set explicit abort criteria before testing: unexpected production mutation, credential exposure, missing alerts, runaway PR creation, unbounded retries, or inability to roll back. Stop immediately if any occur.
4. Inject a **staging-only** simulated health failure. Record the failing request and originating run.
5. Witness classification, incident deduplication, lease fencing, trusted repair initiation and a bounded repair PR. Do not auto-approve or bypass branch protection.
6. Run required CI and security checks on the repair PR, obtain authorised human approval, and verify deployment using the exact commit and provider deployment metadata, not solely `release.json`.
7. Re-inject the same incident to verify idempotency, then test stale SHA, forked PR, rate limit, timeout, unavailable provider and malicious input paths with mocks.
8. Revert the staging change and rehearse rollback to the previous immutable artefact. Confirm restored routes, alerts and evidence links.
9. Update each ledger row with command, observed result, immutable run URL, owner and verified/blocked/not-applicable status. Only declare ready when every mandatory gate is verified.

## Evidence recording template

For each test record: timestamp (UTC), environment, expected SHA, observed deployment SHA, provider deployment ID, artefact digest, command, observed exit code/result, workflow/job URL, PR URL if relevant, alert destination, rollback outcome and approving operator.

**No live autonomous recovery is claimed.** Live recovery requires a separate witnessed production incident and recovery record.
