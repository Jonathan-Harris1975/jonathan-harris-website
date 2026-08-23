import assert from 'node:assert/strict';
import test from 'node:test';

import { onRequestPost as messagePost } from '../functions/api/cognipal/message.js';
import { onRequestPost as syncPost } from '../functions/api/cognipal/sync.js';

class FakeR2Bucket {
  constructor() {
    this.objects = new Map();
    this.version = 0;
  }

  async get(key) {
    const stored = this.objects.get(key);
    if (!stored) return null;
    return {
      etag: stored.etag,
      json: async () => JSON.parse(stored.body),
    };
  }

  async put(key, body, options = {}) {
    const current = this.objects.get(key);
    const onlyIf = options.onlyIf;

    if (onlyIf instanceof Headers) {
      if (onlyIf.get('if-none-match') === '*' && current) return null;
    } else if (onlyIf?.etagMatches && current?.etag !== onlyIf.etagMatches) {
      return null;
    }

    this.version += 1;
    const stored = { body: String(body), etag: `etag-${this.version}` };
    this.objects.set(key, stored);
    return { key, etag: stored.etag };
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

function context(req, bucket) {
  return {
    request: req,
    env: {
      AIMS_COMMS_HUB_BASE_URL: 'https://app.jonathan-harris.online',
      COMMS_HUB_COGINPAL_WEBHOOK_SECRET: 'test-secret-that-is-not-production',
      ...(bucket ? { BLOG_BUCKET: bucket } : {}),
    },
  };
}

async function responseBody(response) {
  return response.json();
}

test('message route blocks session rotation at the IP ceiling', async () => {
  const limiter = new FakeR2Bucket();
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
  const limiter = new FakeR2Bucket();
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
  const limiter = new FakeR2Bucket();
  const response = await messagePost(context(request('/api/cognipal/message', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
    text: 'origin test',
  }, { origin: '' }), limiter));
  assert.equal(response.status, 403);
  assert.equal((await responseBody(response)).error, 'origin_rejected');
});

test('production webchat fails closed if the R2 rate-limit store is absent', async () => {
  const response = await syncPost(context(request('/api/cognipal/sync', {
    sessionId: 'session-00000001',
    visitorId: 'visitor-00000001',
  }), null));
  assert.equal(response.status, 503);
  assert.equal((await responseBody(response)).error, 'rate_limiter_unavailable');
});


test('oversized JSON without Content-Length is rejected before rate limiting', async () => {
  const limiter = new FakeR2Bucket();
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
  const limiter = new FakeR2Bucket();
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
  const limiter = new FakeR2Bucket();
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
