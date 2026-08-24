# Cloudflare Agent Readiness Worker

This is an independently deployed Cloudflare Worker that lives inside the website repository. It runs in front of the existing Cloudflare Pages custom domain and passes ordinary site traffic through unchanged.

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

The route in `wrangler.toml` is `jonathan-harris.online/*`, so deploy this only after confirming the Pages custom domain is live and proxied through Cloudflare. Unmatched requests use `fetch(request)` to reach the existing Pages origin.

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

Then scan production:

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
