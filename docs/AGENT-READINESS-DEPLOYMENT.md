# Agent Readiness deployment runbook

## Architecture

`jonathan-harris.online` stays on Cloudflare Pages. Agent protocol URLs are forwarded by the root Pages middleware to the independently deployed `agent-readiness` Worker through the `AGENT_READINESS` Service Binding.

Do not attach `agent-readiness` to `jonathan-harris.online/*` as a Worker Route. If an old wildcard route remains in the dashboard, remove it.

## Deploy order

### 1. CogniPal rate limiter

Deploy from the repository root. The command refuses dirty checkouts and verifies that the committed Worker file is the file Wrangler will upload:

```bash
if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  echo "Refusing to deploy from a dirty worktree." >&2
  exit 1
fi
SOURCE_SHA="$(git rev-parse HEAD)"
test "${#SOURCE_SHA}" -eq 40
test "$(git rev-parse "HEAD:workers/cognipal-rate-limit/index.js")" = "$(git hash-object workers/cognipal-rate-limit/index.js)"
npx wrangler deploy --config workers/cognipal-rate-limit/wrangler.toml --var "COGNIPAL_RATE_LIMIT_SOURCE_SHA:${SOURCE_SHA}"
```

The Worker keeps its existing `COGNIPAL_RATE_LIMITER` Durable Object binding and `CogniPalRateLimiter` export. Its private health response is queried through the Pages `COGNIPAL_RATE_LIMIT_HEALTH` service binding and reported at `https://jonathan-harris.online/health.json`. A missing or malformed SHA makes the website health endpoint return 503.

The Cloudflare Workers Builds production deploy command for this Worker must inject its actual GitHub commit:
```sh
test "${#WORKERS_CI_COMMIT_SHA}" -eq 40 && npx wrangler deploy --var "COGNIPAL_RATE_LIMIT_SOURCE_SHA:${WORKERS_CI_COMMIT_SHA}"
```
`WORKERS_CI_COMMIT_SHA` is provided by Workers Builds. Keep the Cloudflare project's deploy command aligned with this runbook; preview uploads are not production releases.

### 2. Agent Readiness Worker

```bash
cd workers/agent-readiness
node deploy-production.mjs
```

The helper resolves the exact commit that last changed the Worker entrypoint or Wrangler configuration and passes it to Wrangler as `AGENT_READINESS_SOURCE_SHA`. A plain `npx wrangler deploy` omits that attestation, so the deployed Worker cannot report the exact `source_sha` for its own source revision and the `Website deployed integration` workflow fails in `Verify Agent Readiness service binding and exact Worker source`. Never deploy this Worker with a plain Wrangler deploy.

The resolution is a `git log` over the repository history, so run it from a checkout that has the history covering the Worker source paths. In a shallow checkout the same command returns the shallow boundary commit instead of the last commit that changed the Worker, which attests the wrong revision. The helper also refuses to deploy while any file under `workers/agent-readiness` has uncommitted changes.

If the standalone Worker is connected directly to Git in Cloudflare, its build configuration must use:

```text
Root directory: workers/agent-readiness
```

The root is relative to the repository root. Do not use `agent-readiness`, `/workers/agent-readiness`, or the website repository root for the standalone Worker project. A wrong root fails immediately after repository cloning, before Wrangler or Worker code runs.

For a Git-connected project, set the deploy command to `node deploy-production.mjs` and give the build the repository history it needs to resolve the Worker source revision. The default deploy command (`npx wrangler deploy`) omits the attestation in the same way as a manual plain deploy.

Expected service name: `agent-readiness`.

Bindings:

- `AGENT_READINESS_STATE` Durable Object

Variables:

- `CANONICAL_ORIGIN=https://jonathan-harris.online` is already declared in `workers/agent-readiness/wrangler.toml`. Do not add it as a dashboard binding.
- `AGENT_READINESS_SOURCE_SHA` is written by `deploy-production.mjs` from the resolved Worker source revision. Never commit a value for it.

No Worker secret is required.

#### Attested source scope

The attested revision covers the Worker runtime source and configuration:

- `workers/agent-readiness/index.js`
- `workers/agent-readiness/wrangler.toml`

`deploy-production.mjs`, `verify-production.mjs` and the deployed-integration workflow resolve that same scope with `git log -1 --format=%H <commit> -- <paths>`, so each of them needs the repository history that covers those paths. A new Worker runtime file must be added to all three lists in the same commit, otherwise a deployment can be attested with a revision that does not contain it. Note that the dirty-tree refusal covers the whole `workers/agent-readiness` directory, while the attested revision covers only the two paths above: a change to any other file in that directory blocks the deployment without changing the attested revision.

### 3. Cloudflare Pages

Deploy/redeploy the root Pages project after the Agent Readiness Worker exists. The root `wrangler.toml` declares:

```toml
[[services]]
binding = "AGENT_READINESS"
service = "agent-readiness"

[[services]]
binding = "COGNIPAL_RATE_LIMIT_HEALTH"
service = "cognipal-rate-limit"
```

and the existing external Durable Object binding:

```toml
[[durable_objects.bindings]]
name = "COGNIPAL_RATE_LIMITER"
class_name = "CogniPalRateLimiter"
script_name = "cognipal-rate-limit"
```

If the project is Git-connected to Cloudflare Pages, commit/push the repo and allow the production Pages deployment to complete.

The deploy helper attests the commit that is checked out locally, while the deployed-integration workflow expects the Worker source revision resolved from the released Pages commit. They agree only when the Worker is deployed from the released Pages commit itself: deploy from the default branch at that commit, not from a branch ahead of it and not from a commit that never reached the default branch.

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

The `Readiness status` check compares the live `source_sha` with the Worker source revision resolved from the released Pages commit. `source=MISSING` or a SHA mismatch means the Worker was deployed without `deploy-production.mjs`, from a different revision, or from a checkout without the history that resolution needs. Redeploy it with the helper from the released Pages commit before expecting the `Website deployed integration` workflow to pass.
