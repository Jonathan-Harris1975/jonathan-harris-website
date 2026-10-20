# Agent Readiness deployment runbook

## Architecture

`jonathan-harris.online` stays on Cloudflare Pages. Agent protocol URLs are forwarded by the root Pages middleware to the independently deployed `agent-readiness` Worker through the `AGENT_READINESS` Service Binding.

Do not attach `agent-readiness` to `jonathan-harris.online/*` as a Worker Route. If an old wildcard route remains in the dashboard, remove it.

## Deploy order

### 1. CogniPal rate limiter

Deploy from the repository root so the Worker receives the exact source commit being released:

```bash
SOURCE_SHA="$(git rev-parse HEAD)"
test "${#SOURCE_SHA}" -eq 40
npx wrangler deploy --config workers/cognipal-rate-limit/wrangler.toml --var "COGNIPAL_RATE_LIMIT_SOURCE_SHA:${SOURCE_SHA}"
```

The `/health` response returns this source SHA. A missing or malformed value makes health return 503. The Worker keeps its existing `COGNIPAL_RATE_LIMITER` Durable Object binding and `CogniPalRateLimiter` export.
