import assert from 'node:assert/strict';
import test from 'node:test';
import { onRequest } from '../functions/_middleware.js';
import agentWorker from '../workers/agent-readiness/index.js';

function contextFor(path, { binding = true, next } = {}) {
  let calls = 0;
  const service = {
    async fetch(request) {
      calls += 1;
      return new Response(JSON.stringify({ ok: true, path: new URL(request.url).pathname }), {
        status: 200,
        headers: {
          'content-type': 'application/json; charset=utf-8',
          'x-agent-readiness-worker': 'jonathan-harris-agent-readiness',
        },
      });
    },
  };
  const context = {
    request: new Request(`https://jonathan-harris.online${path}`),
    env: binding ? { AGENT_READINESS: service } : {},
    next: next || (async () => new Response('<!doctype html><html><head><title>Site</title></head><body>site</body></html>', {
      headers: { 'content-type': 'text/html; charset=utf-8' },
    })),
  };
  return { context, calls: () => calls };
}

test('Pages proxies agent discovery paths through AGENT_READINESS service binding', async () => {
  const { context, calls } = contextFor('/.well-known/api-catalog');
  const response = await onRequest(context);
  assert.equal(response.status, 200);
  assert.equal(calls(), 1);
  assert.equal(response.headers.get('x-agent-readiness-worker'), 'jonathan-harris-agent-readiness');
  assert.equal(response.headers.get('x-agent-readiness-gateway'), 'cloudflare-pages-service-binding');
  assert.equal(response.headers.get('x-agent-readiness-gateway-mode'), 'service-binding');
});

test('Pages fails visibly if the Agent Readiness service binding is absent', async () => {
  const { context } = contextFor('/.well-known/agent-card.json', { binding: false });
  const response = await onRequest(context);
  assert.equal(response.status, 503);
  assert.equal(response.headers.get('x-agent-readiness-gateway-mode'), 'binding-missing');
  const body = await response.json();
  assert.equal(body.expected_binding, 'AGENT_READINESS');
});

test('homepage receives discovery Link headers and WebMCP loader', async () => {
  const { context, calls } = contextFor('/');
  const response = await onRequest(context);
  assert.equal(calls(), 0);
  assert.equal(response.status, 200);
  const link = response.headers.get('link') || '';
  assert.match(link, /rel="api-catalog"/);
  assert.match(link, /rel="service-desc"/);
  assert.match(link, /rel="service-doc"/);
  assert.match(link, /rel="describedby"/);
  assert.equal(response.headers.get('x-agent-readiness-homepage-discovery'), 'enabled');
  assert.equal(response.headers.get('x-agent-readiness-webmcp'), 'injected');
  const html = await response.text();
  assert.match(html, /\.well-known\/agent-readiness\/webmcp\.js/);
});

test('MCP aliases and protocol action paths are forwarded to the Worker', async () => {
  for (const path of ['/mcp', '/mcp/server-card', '/.well-known/mcp/catalog.json', '/a2a/message:send', '/oauth2/token', '/agent/identity']) {
    const { context, calls } = contextFor(path);
    const response = await onRequest(context);
    assert.equal(response.status, 200, path);
    assert.equal(calls(), 1, path);
  }
});

test('Pages service binding integrates with the real Agent Readiness Worker', async () => {
  const context = {
    request: new Request('https://jonathan-harris.online/.well-known/api-catalog'),
    env: {
      AGENT_READINESS: {
        fetch: (request) => agentWorker.fetch(request, { CANONICAL_ORIGIN: 'https://jonathan-harris.online' }),
      },
    },
    next: async () => new Response('unexpected', { status: 599 }),
  };
  const response = await onRequest(context);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-type'), 'application/linkset+json');
  assert.equal(response.headers.get('x-agent-readiness-gateway'), 'cloudflare-pages-service-binding');
  assert.equal(response.headers.get('x-agent-readiness-worker'), 'jonathan-harris-agent-readiness');
  const body = await response.json();
  assert.ok(Array.isArray(body.linkset));
});
