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
node deploy-production.mjs
```

The helper resolves the exact commit that last changed the Worker entrypoint or Wrangler configuration and passes it to Wrangler as `AGENT_READINESS_SOURCE_SHA`. A plain `npx wrangler deploy` omits that attestation, so the deployed Worker cannot report the exact `source_sha` for its own source revision and the `Website deployed integration` workflow fails in `Verify Agent Readiness service binding and exact Worker source`. Never deploy this Worker with a plain Wrangler deploy.

If the standalone Worker is connected directly to Git in Cloudflare, its build configuration must use:

```text
Root directory: workers/agent-readiness
```

The root is relative to the repository root. Do not use `agent-readiness`, `/workers/agent-readiness`, or the website repository root for the standalone Worker project. A wrong root fails immediately after repository cloning, before Wrangler or Worker code runs.

For a Git-connected project, set the deploy command to `node deploy-production.mjs`. The default deploy command (`npx wrangler deploy`) omits the attestation in the same way as a manual plain deploy.

Expected service name: `agent-readiness`.

Bindings:

- `AGENT_READINESS_STATE` Durable Object
- `CANONICAL_ORIGIN=https://jonathan-harris.online`

Variables:

- `AGENT_READINESS_SOURCE_SHA` is written by `deploy-production.mjs` from the resolved Worker source revision. Never commit a value for it.

No Worker secret is required.

#### Attested source scope

The attested revision covers the Worker runtime source and configuration:

- `workers/agent-readiness/index.js`
- `workers/agent-readiness/wrangler.toml`

`deploy-production.mjs`, `verify-production.mjs` and the deployed-integration workflow resolve that same scope. A new Worker runtime file must be added to all three lists in the same commit, otherwise a deployment can be attested with a revision that does not contain it.

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

The deployed-integration workflow resolves the expected Worker source revision from the released Pages commit, so the Worker must be deployed from that same repository revision before the live `source_sha` can match.

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

The `Readiness status` check compares the live `source_sha` with the Worker source revision resolved from the repository. `source=MISSING` or a SHA mismatch means the Worker was deployed without `deploy-production.mjs`, or from a different revision. Redeploy it with the helper before expecting the `Website deployed integration` workflow to pass.
