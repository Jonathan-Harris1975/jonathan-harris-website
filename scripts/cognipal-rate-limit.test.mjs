import assert from 'node:assert/strict';
import test from 'node:test';

import { onRequestPost as messagePost } from '../functions/api/cognipal/message.js';
import { onRequestPost as syncPost } from '../functions/api/cognipal/sync.js';
import { CogniPalRateLimiter } from '../workers/cognipal-rate-limit/index.js';

class FakeStorage {
  constructor() {
    this.values = new Map();
  }

  async get(key) {
    return this.values.get(key);
  }

  async put(key, value) {
    this.values.set(key, structuredClone(value));
  }
}

class FakeDurableObjectNamespace {
  constructor() {
    this.objects = new Map();
  }

  idFromName(name) {
    return String(name);
  }

  get(id) {
    const key = String(id);
    if (!this.objects.has(key)) {
      this.objects.set(key, new CogniPalRateLimiter({ storage: new FakeStorage() }));
    }
    const object = this.objects.get(key);
    return {
      fetch: (input, init) => object.fetch(input instanceof Request ? input : new Request(input, init)),
    };
  }
}

function request(path, payload, { origin = 'https://jonathan-harris.online', ip = '203.0.113.8', extraHeaders = {} } = {}) {
  const headers = { 'content-type': 'application/json', 'cf-connecting-ip': ip, ...extraHeaders };
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
      AIMS_COMMS_HUB_BASE_URL: 'https://zeroth-kara-jonathanharris-3296ed37.koyeb.app',
      COMMS_HUB_COGINPAL_WEBHOOK_SECRET: 'test-secret-that-is-not-production',
      ...(limiter ? { COGNIPAL_RATE_LIMITER: limiter } : {}),
    },
  };
}

async function responseBody(response) {
  return response.json();
}

test('message route blocks session rotation at the IP ceiling', async () => {
  const limiter = new FakeDurableObjectNamespace();
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
  const limiter = new FakeDurableObjectNamespace();
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
  const limiter = new FakeDurableObjectNamespace();
  const response = await messagePost(context(request('/api/cognipal/message', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
    text: 'origin test',
  }, { origin: '' }), limiter));
  assert.equal(response.status, 403);
  assert.equal((await responseBody(response)).error, 'origin_rejected');
});

test('production webchat fails closed if the Durable Object rate-limit binding is absent', async () => {
  const response = await syncPost(context(request('/api/cognipal/sync', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
  }), null));
  assert.equal(response.status, 503);
  assert.equal((await responseBody(response)).error, 'rate_limiter_unavailable');
});


test('oversized JSON without Content-Length is rejected before rate limiting', async () => {
  const limiter = new FakeDurableObjectNamespace();
  const req = request('/api/cognipal/message', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
    text: 'body limit test',
    padding: 'x'.repeat(17_000),
  });
  assert.equal(req.headers.get('content-length'), null, 'test must exercise an unknown-length request');
  const response = await messagePost(context(req, limiter));
  assert.equal(response.status, 413);
  assert.equal((await responseBody(response)).error, 'payload_too_large');
  assert.equal(limiter.objects.size, 0, 'oversized bodies must be rejected before rate-limit state is touched');
});

test('incorrect small Content-Length cannot bypass the actual body limit', async () => {
  const limiter = new FakeDurableObjectNamespace();
  const response = await messagePost(context(request('/api/cognipal/message', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
    text: 'body limit test',
    padding: 'x'.repeat(17_000),
  }, { extraHeaders: { 'content-length': '1' } }), limiter));
  assert.equal(response.status, 413);
  assert.equal((await responseBody(response)).error, 'payload_too_large');
  assert.equal(limiter.objects.size, 0);
});

test('streamed unknown-length body is bounded while it is read', async () => {
  const limiter = new FakeDurableObjectNamespace();
  const encoder = new TextEncoder();
  const prefix = JSON.stringify({
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
    text: 'body limit test',
    padding: '',
  }).slice(0, -2);
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(`${prefix}${'x'.repeat(9_000)}`));
      controller.enqueue(encoder.encode(`${'y'.repeat(9_000)}"}`));
      controller.close();
    },
  });
  const req = new Request('https://jonathan-harris.online/api/cognipal/message', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      origin: 'https://jonathan-harris.online',
      'cf-connecting-ip': '203.0.113.8',
    },
    body,
    duplex: 'half',
  });
  assert.equal(req.headers.get('content-length'), null);
  const response = await messagePost(context(req, limiter));
  assert.equal(response.status, 413);
  assert.equal((await responseBody(response)).error, 'payload_too_large');
  assert.equal(limiter.objects.size, 0);
});
