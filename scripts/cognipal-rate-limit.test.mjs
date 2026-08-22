import assert from 'node:assert/strict';
import test from 'node:test';

import { onRequestPost as messagePost } from '../functions/api/cognipal/message.js';
import { onRequestPost as syncPost } from '../functions/api/cognipal/sync.js';

class FakeRateLimiterNamespace {
  constructor() {
    this.counters = new Map();
  }

  idFromName(name) {
    return name;
  }

  get(id) {
    return {
      fetch: async (_url, options) => {
        const { limit } = JSON.parse(options.body);
        const count = this.counters.get(id) || 0;
        if (count >= limit) {
          return Response.json({ ok: true, success: false, retryAfterSeconds: 60, remaining: 0 });
        }
        this.counters.set(id, count + 1);
        return Response.json({ ok: true, success: true, retryAfterSeconds: 60, remaining: limit - count - 1 });
      },
    };
  }
}

function request(path, payload, { origin = 'https://jonathan-harris.online', ip = '203.0.113.8' } = {}) {
  const headers = { 'content-type': 'application/json', 'cf-connecting-ip': ip };
  if (origin) headers.origin = origin;
  return new Request(`https://jonathan-harris.online${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
}

function context(req, limiter) {
  return {
    request: req,
    env: {
      AIMS_COMMS_HUB_BASE_URL: 'https://app.jonathan-harris.online',
      COMMS_HUB_COGINPAL_WEBHOOK_SECRET: 'test-secret-that-is-not-production',
      ...(limiter ? { COGNIPAL_RATE_LIMITER: limiter } : {}),
    },
  };
}

async function responseBody(response) {
  return response.json();
}

test('message route blocks session rotation at the IP ceiling', async () => {
  const limiter = new FakeRateLimiterNamespace();
  const originalFetch = globalThis.fetch;
  let upstreamCalls = 0;
  globalThis.fetch = async () => {
    upstreamCalls += 1;
    return Response.json({ ok: true, accepted: true }, { status: 202 });
  };
  try {
    for (let i = 0; i < 20; i += 1) {
      const suffix = String(i).padStart(8, '0');
      const response = await messagePost(context(request('/api/cognipal/message', {
        sessionId: `session-${suffix}`,
        visitorId: `visitor-${suffix}`,
        text: 'production rate-limit test',
      }), limiter));
      assert.equal(response.status, 202);
    }
    const blocked = await messagePost(context(request('/api/cognipal/message', {
      sessionId: 'session-99999999',
      visitorId: 'visitor-99999999',
      text: 'production rate-limit test',
    }), limiter));
    assert.equal(blocked.status, 429);
    assert.equal((await responseBody(blocked)).error, 'rate_limited');
    assert.equal(upstreamCalls, 20, 'blocked message must not reach AIMS');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('sync route blocks session rotation at the IP ceiling', async () => {
  const limiter = new FakeRateLimiterNamespace();
  const originalFetch = globalThis.fetch;
  let upstreamCalls = 0;
  globalThis.fetch = async () => {
    upstreamCalls += 1;
    return Response.json({ ok: true, messages: [] });
  };
  try {
    for (let i = 0; i < 180; i += 1) {
      const suffix = String(i).padStart(8, '0');
      const response = await syncPost(context(request('/api/cognipal/sync', {
        sessionId: `session-${suffix}`,
        visitorId: `visitor-${suffix}`,
      }), limiter));
      assert.equal(response.status, 200);
    }
    const blocked = await syncPost(context(request('/api/cognipal/sync', {
      sessionId: 'session-99999999',
      visitorId: 'visitor-99999999',
    }), limiter));
    assert.equal(blocked.status, 429);
    assert.equal((await responseBody(blocked)).error, 'rate_limited');
    assert.equal(upstreamCalls, 180, 'blocked sync must not reach AIMS');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('public webchat rejects requests without Origin', async () => {
  const limiter = new FakeRateLimiterNamespace();
  const response = await messagePost(context(request('/api/cognipal/message', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
    text: 'origin test',
  }, { origin: '' }), limiter));
  assert.equal(response.status, 403);
  assert.equal((await responseBody(response)).error, 'origin_rejected');
});

test('production webchat fails closed if the Durable Object binding is absent', async () => {
  const response = await syncPost(context(request('/api/cognipal/sync', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
  }), null));
  assert.equal(response.status, 503);
  assert.equal((await responseBody(response)).error, 'rate_limiter_unavailable');
});
