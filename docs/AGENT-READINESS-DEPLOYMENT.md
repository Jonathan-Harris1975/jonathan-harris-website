# Agent Readiness deployment runbook

## Architecture

`jonathan-harris.online` stays on Cloudflare Pages. Agent protocol URLs are forwarded by the root Pages middleware to the independently deployed `agent-readiness` Worker through the `AGENT_READINESS` Service Binding.

Do not attach `agent-readiness` to `jonathan-harris.online/*` as a Worker Route. If an old wildcard route remains in the dashboard, remove it.

## Deploy order

### 1. CogniPal rate limiter

```bash
cd workers/cognipal-rate-limit
npx wrangler deploy
```

No env vars or secrets are required by this Worker. It exports `CogniPalRateLimiter` and its Durable Object storage.

### 2. Agent Readiness Worker

```bash
cd workers/agent-readiness
npx wrangler deploy
```

Expected service name: `agent-readiness`.

Bindings:

- `AGENT_READINESS_STATE` Durable Object
- `CANONICAL_ORIGIN=https://jonathan-harris.online`

No Worker secret is required.

### 3. Cloudflare Pages

Deploy/redeploy the root Pages project after the Agent Readiness Worker exists. The root `wrangler.toml` declares:

```toml
[[services]]
binding = "AGENT_READINESS"
service = "agent-readiness"
```

and the existing external Durable Object binding:

```toml
[[durable_objects.bindings]]
name = "COGNIPAL_RATE_LIMITER"
class_name = "CogniPalRateLimiter"
script_name = "cognipal-rate-limit"
```

If the project is Git-connected to Cloudflare Pages, commit/push the repo and allow the production Pages deployment to complete.

### 4. Remove obsolete Agent Readiness route

Cloudflare dashboard:

`Workers & Pages` → `agent-readiness` → `Settings` → `Domains & Routes`

There should be no Worker Route for `jonathan-harris.online/*`. `workers.dev` can remain enabled for direct diagnostics.

### 5. DNS-AID

Cloudflare DNS → Records. Create these DNS-only SVCB records (names are relative to the zone):

| Type | Name | Priority | Target | Params |
| --- | --- | ---: | --- | --- |
| SVCB | `_index._agents` | 1 | `jonathan-harris.online` | `mandatory=alpn,port alpn="h2,h3" port=443` |
| SVCB | `_a2a._agents` | 1 | `jonathan-harris.online` | `mandatory=alpn,port alpn="a2a,h2,h3" port=443` |
| SVCB | `_mcp._agents` | 1 | `jonathan-harris.online` | `mandatory=alpn,port alpn="mcp,h2,h3" port=443` |

Then enable DNSSEC for `jonathan-harris.online` in Cloudflare DNS. Complete the registrar-side DS step if Cloudflare requests it for your DNS setup.

## Validate

```bash
cd workers/agent-readiness
node verify-production.mjs
node rescan.mjs
```

The key diagnostic is the pair of headers on all readiness endpoints:

```text
X-Agent-Readiness-Gateway: cloudflare-pages-service-binding
X-Agent-Readiness-Worker: agent-readiness
```

If the first is missing, production Pages is not running the updated middleware. If it says `binding-missing`, the Pages service binding is absent. If the first exists but the Worker header is missing, the bound Worker deployment is wrong.
