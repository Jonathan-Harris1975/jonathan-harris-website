import assert from "node:assert/strict";
import test from "node:test";
import worker from "./index.js";

const env = { CANONICAL_ORIGIN: "https://jonathan-harris.online" };
const call = (path, init = {}) => worker.fetch(new Request(`https://jonathan-harris.online${path}`, init), env);

test("API catalog is RFC 9727-shaped", async () => {
  const response = await call("/.well-known/api-catalog");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-agent-readiness-worker"), "jonathan-harris-agent-readiness");
  assert.match(response.headers.get("content-type"), /application\/linkset\+json/);
  const body = await response.json();
  assert.ok(Array.isArray(body.linkset));
  assert.ok(body.linkset[0]["service-desc"]);
});

test("OAuth discovery and PRM are published", async () => {
  const metadata = await (await call("/.well-known/oauth-authorization-server")).json();
  assert.equal(metadata.issuer, "https://jonathan-harris.online");
  assert.match(metadata.token_endpoint, /\/oauth2\/token$/);
  assert.ok(metadata.agent_auth.register_uri);

  const prm = await (await call("/.well-known/oauth-protected-resource")).json();
  assert.deepEqual(prm.scopes_supported, ["public.read"]);
  assert.deepEqual(prm.bearer_methods_supported, ["header"]);
});

test("anonymous identity assertion exchanges for a bearer token", async () => {
  const identityResponse = await call("/agent/identity", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ type: "anonymous" }),
  });
  assert.equal(identityResponse.status, 200);
  const identity = await identityResponse.json();
  assert.equal(identity.identity_assertion.split(".").length, 3);

  const form = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion: identity.identity_assertion,
    scope: "public.read",
  });
  const tokenResponse = await call("/oauth2/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: form,
  });
  assert.equal(tokenResponse.status, 200);
  const token = await tokenResponse.json();
  assert.equal(token.token_type, "Bearer");
  assert.equal(token.access_token.split(".").length, 3);
});

test("A2A card and message endpoint are functional", async () => {
  const card = await (await call("/.well-known/agent-card.json")).json();
  assert.equal(card.version, "1.0.0");
  assert.equal(card.supportedInterfaces[0].protocolVersion, "1.0");
  assert.ok(card.skills.length > 0);

  const response = await call("/a2a/message:send", {
    method: "POST",
    headers: { "content-type": "application/a2a+json" },
    body: JSON.stringify({ message: { role: "ROLE_USER", messageId: "test-message", parts: [{ text: "Where are the books?" }] } }),
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.match(body.message.parts[0].text, /books\.json/);
});

test("Agent Skills index digest matches served SKILL.md", async () => {
  const index = await (await call("/.well-known/agent-skills/index.json")).json();
  assert.equal(index.$schema, "https://schemas.agentskills.io/discovery/0.2.0/schema.json");
  assert.match(index.skills[0].digest, /^sha256:[0-9a-f]{64}$/);
  const skill = await (await call(index.skills[0].url)).text();
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(skill));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  assert.equal(index.skills[0].digest, `sha256:${hex}`);
});

test("MCP server supports initialize, tools/list and tools/call", async () => {
  const init = await call("/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2026-07-28", capabilities: {}, clientInfo: { name: "test", version: "1" } } }),
  });
  assert.equal(init.status, 200);
  assert.equal((await init.json()).result.serverInfo.name, "jonathan-harris-public-discovery");

  const list = await call("/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }),
  });
  assert.ok((await list.json()).result.tools.some((tool) => tool.name === "get_agent_readiness"));

  const toolCall = await call("/mcp", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "get_agent_readiness", arguments: {} } }),
  });
  assert.match((await toolCall.json()).result.content[0].text, /api_catalog/);
});

test("Web Bot Auth directory exposes signed Ed25519 JWKS", async () => {
  const response = await call("/.well-known/http-message-signatures-directory");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("content-type"), "application/http-message-signatures-directory+json");
  assert.match(response.headers.get("signature-input"), /http-message-signatures-directory/);
  assert.match(response.headers.get("signature"), /^sig1=:/);
  const body = await response.json();
  assert.equal(body.keys[0].crv, "Ed25519");
});


test("homepage pass-through adds RFC 8288 discovery Link headers", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response("<!doctype html><html><head></head><body>site</body></html>", { headers: { "content-type": "text/html; charset=utf-8" } });
  try {
    const response = await call("/");
    const link = response.headers.get("link") || "";
    assert.match(link, /rel="api-catalog"/);
    assert.match(link, /rel="service-desc"/);
    assert.match(link, /rel="service-doc"/);
    assert.match(link, /rel="describedby"/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("auth.md contains a complete anonymous registration path", async () => {
  const response = await call("/auth.md");
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /^# auth\.md/m);
  assert.match(body, /\/agent\/identity/);
  assert.match(body, /\/oauth2\/token/);
});

test("WebMCP uses current document.modelContext API", async () => {
  const script = await (await call("/.well-known/agent-readiness/webmcp.js")).text();
  assert.match(script, /document\.modelContext\.registerTool/);
  assert.doesNotMatch(script, /navigator\.modelContext/);
  assert.match(script, /AbortController/);
});
