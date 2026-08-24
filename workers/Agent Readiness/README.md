# Cloudflare Agent Readiness Worker

This is an independently deployed Cloudflare Worker named `jonathan-harris-agent-readiness` that lives inside the website repository. It runs in front of the existing Cloudflare Pages custom domain and passes ordinary site traffic through unchanged.

## What it implements

1. RFC 9727 API Catalog at `/.well-known/api-catalog`.
2. RFC 8288 discovery `Link` headers on the homepage.
3. `auth.md` agent registration instructions at `/auth.md`.
4. OAuth authorization-server/OIDC discovery metadata.
5. RFC 9728 OAuth Protected Resource Metadata.
6. A2A v1 Agent Card plus a minimal read-only HTTP+JSON `message:send` implementation.
7. Agent Skills Discovery v0.2.0 index plus a digest-verified `SKILL.md`.
8. MCP Server Card plus a minimal stateless read-only MCP Streamable HTTP server.
9. Web Bot Auth Ed25519 JWKS directory with HTTP Message Signature response signing.
10. WebMCP registration using the current `document.modelContext` API, injected by the Worker into HTML pages.
11. DNS-AID deployment records in `dns-aid-records.txt`.

The Durable Object stores one persistent Ed25519 signing key. That key signs OAuth JWTs and the Web Bot Auth directory response. No private signing key is committed to the repository.

## Deploy

From this directory:

```bash
npx wrangler deploy
```

The deploy output must name **`jonathan-harris-agent-readiness`** and must publish the Worker Route **`jonathan-harris.online/*`**. The Worker name must not be `jonathan-harris-website`; that is the Pages project.

The route runs in front of the existing Pages custom domain. Unmatched requests use `fetch(request)` to reach Pages. `workers_dev = true` is intentionally enabled so the deployment also has a direct diagnostic `workers.dev` URL.

### Mandatory production route check

Before running the Agent Readiness scanner, request:

```bash
curl -i https://jonathan-harris.online/.well-known/agent-readiness/status
```

Production is wired correctly only if the response is HTTP 200 and contains:

```text
X-Agent-Readiness-Worker: jonathan-harris-agent-readiness
```

If that header is absent, do not re-scan yet. In Cloudflare go to **Workers & Pages → jonathan-harris-agent-readiness → Settings → Domains & Routes** and confirm a **Worker Route** exists for `jonathan-harris.online/*`. Do not replace the Pages custom domain with a Worker Custom Domain.

## External Cloudflare steps still required

### DNS-AID

Create the records in `dns-aid-records.txt` in the `jonathan-harris.online` Cloudflare DNS zone. Enable DNSSEC for the zone. A Worker cannot publish authoritative DNS records by itself.

### Web Bot Auth verified-bot registration

After deployment, confirm this URL returns a signed key directory:

```text
https://jonathan-harris.online/.well-known/http-message-signatures-directory
```

Then submit that URL through Cloudflare's Bot Submission Form with **Request Signature** as the verification method. Publishing the key directory is implemented by this Worker; Cloudflare's external verified-bot registration is an account-level action.

## Validation

Run the local contract tests:

```bash
node --test test.mjs
```

Then run `node verify-production.mjs` and scan production:

```bash
curl -sS https://isitagentready.com/api/scan \
  -H 'Content-Type: application/json' \
  --data '{"url":"https://jonathan-harris.online"}'
```

Useful direct checks:

```bash
curl -i https://jonathan-harris.online/.well-known/api-catalog
curl -i https://jonathan-harris.online/.well-known/oauth-protected-resource
curl -i https://jonathan-harris.online/.well-known/oauth-authorization-server
curl -i https://jonathan-harris.online/.well-known/agent-card.json
curl -i https://jonathan-harris.online/.well-known/agent-skills/index.json
curl -i https://jonathan-harris.online/.well-known/mcp/server-card.json
curl -i https://jonathan-harris.online/.well-known/http-message-signatures-directory
```
