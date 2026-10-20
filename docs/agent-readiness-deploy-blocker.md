# Agent Readiness Worker deployment blocker

The "Website deployed integration" workflow requires the live Agent Readiness Worker
(https://jonathan-harris.online/.well-known/agent-readiness/status) to return
`source_sha` equal to the last commit that changed
`workers/agent-readiness/index.js` or `workers/agent-readiness/wrangler.toml`
in the deployed Pages commit.

- Expected source SHA (from repo state): `3602b2dd5c6a8f345ea3b942b0bac2ead746df8e` (PR #115)
- Current live status: `source_sha` is missing (null/absent) at the time of inspection
- Root cause: The Worker has not been redeployed with `AGENT_READINESS_SOURCE_SHA` set via `workers/agent-readiness/deploy-production.mjs`. The Worker code is correct and supports the env var, but deployment requires Cloudflare credentials (`CLOUDFLARE_API_TOKEN`) which are not available in this environment.

Required external action:
1. From the repository with valid Cloudflare credentials, run:
   `cd workers/agent-readiness && node deploy-production.mjs`
   (or equivalent wrangler deploy passing `--var AGENT_READINESS_SOURCE_SHA:<expected_sha>`)
2. Verify: `curl -s https://jonathan-harris.online/.well-known/agent-readiness/status | jq .source_sha` returns the expected SHA
3. Re-run the failed workflow / merge carrier PR #120 after the Worker is deployed with the correct source attestation.
