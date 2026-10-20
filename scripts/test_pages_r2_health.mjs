import assert from 'node:assert/strict';
import test from 'node:test';
import { onRequest } from '../functions/health.json.js';
import { onRequest as transcriptRequest } from '../functions/transcripts/[[slug]].js';
import { onRequest as blogManifestRequest } from '../functions/blog/posts.json.js';
import { onRequest as blogPostRequest } from '../functions/blog/posts/[[slug]].js';

const revision = 'a'.repeat(40);
function bucket({ fail = false } = {}) {
  let listed = 0;
  return {
    async list(options) {
      listed += 1;
      assert.deepEqual(options, { limit: 1 });
      if (fail) throw new Error('provider error must not be returned');
      return { objects: [] };
    },
    listed: () => listed,
  };
}

function allBuckets(overrides = {}) {
  return {
    CF_PAGES_COMMIT_SHA: revision,
    TRANSCRIPTS_BUCKET: bucket(),
    BLOG_BUCKET: bucket(),
    BLOG_IMAGES_BUCKET: bucket(),
    COGNIPAL_RATE_LIMIT_HEALTH: {
      async fetch() {
        return Response.json({
          ok: true,
          service: "cognipal-rate-limit",
          source_commit_sha: revision,
        });
      },
    },
    ...overrides,
  };
}

test('health reports configured and reachable R2 bindings and exact Pages revision', async () => {
  const env = allBuckets();
  const response = await onRequest({ env });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(body.ok, true);
  assert.equal(body.status, 'healthy');
  assert.equal(body.revision, revision);
  for (const name of ['TRANSCRIPTS_BUCKET', 'BLOG_BUCKET', 'BLOG_IMAGES_BUCKET']) {
    assert.deepEqual(body.bindings[name], { configured: true, runtime_access: 'available', required: name !== 'BLOG_IMAGES_BUCKET' });
    assert.equal(env[name].listed(), 1);
  }
  assert.deepEqual(body.bindings.COGNIPAL_RATE_LIMITER, {
    configured: true,
    runtime_access: 'available',
    source_commit_sha: revision,
    required: true,
  });
});

test('health fails closed and redacts provider errors', async () => {
  const response = await onRequest({ env: allBuckets({ BLOG_BUCKET: bucket({ fail: true }) }) });
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.ok, false);
  assert.equal(body.status, 'degraded');
  assert.deepEqual(body.bindings.BLOG_BUCKET, { configured: true, runtime_access: 'unavailable', required: true });
  assert.doesNotMatch(JSON.stringify(body), /provider error/);
});

test('health reports a missing required transcript binding as degraded', async () => {
  const response = await onRequest({ env: allBuckets({ TRANSCRIPTS_BUCKET: undefined }) });
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.deepEqual(body.bindings.TRANSCRIPTS_BUCKET, { configured: false, runtime_access: 'not-tested', required: true });
});

test('health reports a missing required blog binding as degraded', async () => {
  const response = await onRequest({ env: allBuckets({ BLOG_BUCKET: undefined }) });
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.deepEqual(body.bindings.BLOG_BUCKET, { configured: false, runtime_access: 'not-tested', required: true });
});

test('health distinguishes a missing optional image binding from a healthy runtime', async () => {
  const response = await onRequest({ env: allBuckets({ BLOG_IMAGES_BUCKET: undefined }) });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.ok, true);
  assert.equal(body.status, 'healthy');
  assert.deepEqual(body.bindings.BLOG_IMAGES_BUCKET, { configured: false, runtime_access: 'not-tested', required: false });
  assert.equal(body.bindings.TRANSCRIPTS_BUCKET.required, true);
  assert.equal(body.bindings.BLOG_BUCKET.required, true);
});

test('transcript route returns a clear retryable response when its required binding is absent', async () => {
  const response = await transcriptRequest({
    params: { slug: 'episode-one' },
    env: {},
    request: new Request('https://jonathan-harris.online/transcripts/episode-one'),
    next: async () => new Response('must not be treated as a successful transcript response'),
  });
  assert.equal(response.status, 503);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.get('x-transcript-storage'), 'binding-missing');
  assert.deepEqual(await response.json(), { error: 'transcript storage unavailable', reason: 'binding-missing' });
});

test('transcript route redacts R2 read failures', async () => {
  const response = await transcriptRequest({
    params: { slug: 'episode-one' },
    env: { TRANSCRIPTS_BUCKET: { async get() { throw new Error('private provider details'); } } },
    request: new Request('https://jonathan-harris.online/transcripts/episode-one'),
    next: async () => new Response('not found', { status: 404 }),
  });
  assert.equal(response.status, 503);
  assert.equal(response.headers.get('x-transcript-storage'), 'read-failed');
  assert.doesNotMatch(await response.text(), /private provider details/);
});


test('blog manifest reports a missing required bucket explicitly', async () => {
  const response = await blogManifestRequest({ env: {}, request: new Request('https://jonathan-harris.online/blog/posts.json') });
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { error: 'blog manifest unavailable', reason: 'binding-missing' });
});

test('blog post route reports binding and read failures instead of a false not-found', async () => {
  const base = {
    params: { slug: 'weekly-briefing' },
    request: new Request('https://jonathan-harris.online/blog/posts/weekly-briefing'),
    next: async () => new Response('not found', { status: 404 }),
  };
  const missing = await blogPostRequest({ ...base, env: {} });
  assert.equal(missing.status, 503);
  assert.deepEqual(await missing.json(), { error: 'blog content unavailable', reason: 'binding-missing' });
  const failed = await blogPostRequest({ ...base, env: { BLOG_BUCKET: { async get() { throw new Error('private R2 error'); } } } });
  assert.equal(failed.status, 503);
  const failedBody = await failed.text();
  assert.deepEqual(JSON.parse(failedBody), { error: 'blog content unavailable', reason: 'read-failed' });
  assert.doesNotMatch(failedBody, /private R2 error/);
});

test('health fails closed when the private CogniPal Worker health binding is absent', async () => {
  const env = allBuckets({ COGNIPAL_RATE_LIMIT_HEALTH: undefined });
  const response = await onRequest({ env });
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.ok, false);
  assert.deepEqual(body.bindings.COGNIPAL_RATE_LIMITER, {
    configured: false,
    runtime_access: 'not-tested',
    source_commit_sha: null,
    required: true,
  });
});

test('health fails closed when the private CogniPal Worker has no valid source SHA', async () => {
  const env = allBuckets({
    COGNIPAL_RATE_LIMIT_HEALTH: {
      async fetch() {
        return Response.json({ ok: false, service: 'cognipal-rate-limit', source_commit_sha: null }, { status: 503 });
      },
    },
  });
  const response = await onRequest({ env });
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.ok, false);
  assert.equal(body.bindings.COGNIPAL_RATE_LIMITER.runtime_access, 'unavailable');
  assert.equal(body.bindings.COGNIPAL_RATE_LIMITER.source_commit_sha, null);
});
