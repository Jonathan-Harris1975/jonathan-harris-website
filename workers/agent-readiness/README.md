# Cloudflare Agent Readiness Worker

`agent-readiness` is an independently deployed Cloudflare Worker kept inside the website repository.

## Production architecture

The Worker does **not** own `jonathan-harris.online/*` and does not proxy the website.

```text
Internet
   |
   v
jonathan-harris.online
Cloudflare Pages + Functions
   |
   | AGENT_READINESS Service Binding
   v
agent-readiness Worker
   |
   +-- AGENT_READINESS_STATE Durable Object (persistent Ed25519 key)
```

Pages exposes the readiness URLs publicly through `functions/_middleware.js`. The Worker stays independently deployable and internally addressable through the service binding. This avoids Worker Route precedence problems on the Pages custom domain.

## Implemented readiness surfaces

1. API Catalog: `/.well-known/api-catalog`
2. Homepage RFC 8288 `Link` headers (added by Pages)
3. Auth.md: `/auth.md`
4. OAuth/OIDC metadata: `/.well-known/oauth-authorization-server` and `/.well-known/openid-configuration`
5. OAuth Protected Resource Metadata: `/.well-known/oauth-protected-resource`
6. A2A Agent Card and read-only A2A endpoint: `/.well-known/agent-card.json`, `/a2a`, `/a2a/message:send`
7. Agent Skills index + digest-verified SKILL.md
8. MCP Server Card + stateless read-only MCP endpoint. Compatibility aliases are also served.
9. Web Bot Auth signed Ed25519 key directory
10. WebMCP script. It prefers `document.modelContext` and retains `navigator.modelContext` compatibility for scanners/browser builds using the earlier API.
11. DNS-AID records are defined in `dns-aid-records.txt`; DNSSEC is an authoritative DNS setting and therefore remains outside the Worker.

## Environment, secrets and bindings

### Agent Readiness Worker

- Env var: `CANONICAL_ORIGIN=https://jonathan-harris.online` (committed in `wrangler.toml`)
- Secret: none
- Durable Object: `AGENT_READINESS_STATE` → `AgentReadinessState`

The Worker generates one Ed25519 key pair and persists it in the Durable Object. No private key is committed or configured as a secret.

### Pages project

- Service binding: `AGENT_READINESS` → `agent-readiness`
- Existing CogniPal Durable Object binding remains separate.

## Required first deployment order

The target of a Cloudflare Service Binding must already exist before the caller can be deployed.

1. Deploy `workers/cognipal-rate-limit` if its current version is not already live.
2. Deploy `workers/agent-readiness`:

   ```bash
   cd workers/agent-readiness
   npx wrangler deploy
   ```

3. Deploy/redeploy the root Cloudflare Pages project so the `AGENT_READINESS` service binding from the root `wrangler.toml` becomes active. If Pages is Git-connected, push this repository and let the production deployment complete.
4. Remove any old manually-created Worker Route `jonathan-harris.online/*` from `agent-readiness` if it still exists in the Cloudflare dashboard. This Worker intentionally has no production route.
5. Add the three SVCB records from `dns-aid-records.txt` and enable DNSSEC for the zone.

## Production verification

After both deployments:

```bash
cd workers/agent-readiness
node verify-production.mjs
```

A proxied readiness endpoint must contain **both**:

```text
X-Agent-Readiness-Gateway: cloudflare-pages-service-binding
X-Agent-Readiness-Worker: agent-readiness
```

The homepage must contain:

```text
X-Agent-Readiness-Homepage-Discovery: enabled
X-Agent-Readiness-WebMCP: injected
```

and RFC 8288 `Link` headers.

To call the Cloudflare scanner and print all matching readiness statuses:

```bash
node rescan.mjs
```

## Local/CI validation

From the repository root:

```bash
node --test workers/agent-readiness/test.mjs
node --test scripts/agent-readiness-pages.test.mjs
node --test scripts/cognipal-rate-limit.test.mjs
```

These tests are also run by `build.sh` so Pages cannot deploy a code revision that breaks the local readiness contracts.
