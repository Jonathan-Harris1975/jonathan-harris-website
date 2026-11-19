import assert from 'node:assert/strict';
import test from 'node:test';
import { onRequest } from '../functions/health.json.js';
import { onRequest as transcriptRequest, buildAeoPrelude, hasExistingTranscriptH1 } from '../functions/transcripts/[[slug]].js';
import { onRequest as blogManifestRequest } from '../functions/blog/posts.json.js';
import { onRequest as blogPostRequest } from '../functions/blog/posts/[[slug]].js';
import { onRequest as sitemapRequest, loadPublishedBlogRoutes } from '../functions/sitemap.xml.js';

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

test('health fails closed when the private CogniPal Worker SHA differs from the Pages revision', async () => {
  const env = allBuckets({
    COGNIPAL_RATE_LIMIT_HEALTH: {
      async fetch() {
        return Response.json({ ok: true, service: 'cognipal-rate-limit', source_commit_sha: 'b'.repeat(40) });
      },
    },
  });
  const response = await onRequest({ env });
  const body = await response.json();
  assert.equal(response.status, 503);
  assert.equal(body.ok, false);
  assert.deepEqual(body.bindings.COGNIPAL_RATE_LIMITER, {
    configured: true,
    runtime_access: 'unavailable',
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
test('transcript SEO introduction does not duplicate the existing R2 page H1', () => {
  const episode = {
    title: 'Episode with a title',
    summary: 'Practical and independent analysis of this episode, with sufficient detail for its summary.',
    slug: 'episode-with-a-title',
  };
  const request = new Request('https://jonathan-harris.online/transcripts/TT-example.html');
  const storedHtml = '<!doctype html><html><body><header><h1 class="episode-title">Episode with a title</h1></header><main><h2>Full transcript</h2></main></body></html>';
  const prelude = buildAeoPrelude(episode, request, storedHtml);
  assert.match(prelude, /transcript-aeo-summary/);
  assert.match(prelude, /"PodcastEpisode"/);
  assert.match(prelude, /All transcripts/);
  assert.equal((storedHtml + prelude).match(/<h1\b/gi).length, 1);
  assert.doesNotMatch(prelude, /<h1\b/);
});

test('transcript SEO introduction still supplies a single accessible H1 when R2 lacks one', () => {
  const episode = { title: 'Title & accessibility', summary: 'This is an episode summary.' };
  const request = new Request('https://jonathan-harris.online/transcripts/TT-example.html');
  const storedHtml = '<html><body><main><h2>Transcript</h2></main></body></html>';
  const prelude = buildAeoPrelude(episode, request, storedHtml);
  assert.match(prelude, /<h1>Title &amp; accessibility<\/h1>/);
  assert.equal((storedHtml + prelude).match(/<h1\b/gi).length, 1);
});

test('transcript introductions do not change stored headings with capitalisation or attributes', () => {
  const episode = { title: 'Episode title', summary: 'This is an episode summary.' };
  const storedHtml = '<html><body><H1 id="title">Existing heading</H1></body></html>';
  const prelude = buildAeoPrelude(episode, new Request('https://jonathan-harris.online/transcripts/sample'), storedHtml);
  assert.doesNotMatch(prelude, /<h1\b/i);
  assert.match(prelude, /<script type="application\/ld\+json">/);
});
test('transcript heading tokeniser ignores HTML comments, quoted attributes and inert content', () => {
  const comments = '<!-- <h1>not an actual heading</h1> --><main><h2>Transcript</h2></main>';
  const attributes = '<div data-example="<h1>not a heading</h1>">Episode details</div>';
  const inert = '<script>const example = "<h1>not a heading</h1>";</script><style>h1{display:block}</style><template><h1>Template heading</h1></template><textarea><h1>Input text</h1></textarea>';
  for (const html of [comments, attributes, inert]) {
    assert.equal(hasExistingTranscriptH1(html), false, html);
    const prelude = buildAeoPrelude({ title: 'Actual episode title', summary: 'Episode summary.' }, new Request('https://jonathan-harris.online/transcripts/example'), html);
    assert.match(prelude, /<h1>Actual episode title<\/h1>/);
  }
  assert.equal(hasExistingTranscriptH1('<h1 class="title">A real heading</h1>'), true);
  assert.equal(hasExistingTranscriptH1('<H1>A real heading</H1>'), true);
});

const baseSitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>https://jonathan-harris.online/</loc></url>\n  <url><loc>https://jonathan-harris.online/blog/weekly/</loc></url>\n</urlset>';

function sitemapContext(items, bucketOverride) {
  const get = async (key) => {
    assert.equal(key, 'blog/posts.json');
    return { json: async () => ({ items }) };
  };
  return {
    request: new Request('https://jonathan-harris.online/sitemap.xml'),
    env: {
      BLOG_BUCKET: bucketOverride || { get },
      PODCAST_RSS_RETRY_ATTEMPTS: 1,
      ASSETS: {
        async fetch() {
          return Response.json({ routes: [{ loc: 'https://jonathan-harris.online/other-dynamic/' }] });
        },
      },
    },
    next: async () => new Response(baseSitemap, { status: 200, headers: { 'content-type': 'application/xml; charset=utf-8' } }),
  };
}

test('R2 blog sitemap generates canonical article locations and accurate publication dates', async () => {
  const routes = await loadPublishedBlogRoutes(sitemapContext([
    { slug: '2026-w46-first-article', published_at: '2026-11-16T10:11:51.961Z' },
    { slug: '2026-w45-second', published_at: '2026-11-09T10:19:14.926Z', updated_at: '2026-11-17T09:00:00Z' },
    { slug: '2026-w46-first-article', published_at: '2026-11-16T10:11:51.961Z' },
  ]).env);
  assert.deepEqual(routes, { routes: [
    { loc: 'https://jonathan-harris.online/blog/posts/2026-w46-first-article/', lastmod: '2026-11-16' },
    { loc: 'https://jonathan-harris.online/blog/posts/2026-w45-second/', lastmod: '2026-11-17' },
  ] });
});

test('canonical sitemap combines static, dynamic and R2 blog entries without a redeploy', async () => {
  const items = [{ slug: '2026-w46-first', published_at: '2026-11-16T10:11:51.961Z' }];
  const context = sitemapContext(items);
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('RSS temporarily unavailable', { status: 503 });
  try {
    let response = await sitemapRequest(context);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('x-blog-sitemap-source'), 'r2');
    assert.equal(response.headers.get('x-blog-posts-in-sitemap'), '1');
    assert.equal(response.headers.get('cache-control'), 'public, max-age=300, s-maxage=300');
    let xml = await response.text();
    assert.match(xml, /<loc>https:\/\/jonathan-harris.online\/blog\/posts\/2026-w46-first\/<\/loc>/);
    assert.match(xml, /<lastmod>2026-11-16<\/lastmod>/);
    assert.match(xml, /<loc>https:\/\/jonathan-harris.online\/other-dynamic\/<\/loc>/);
    assert.match(xml, /<loc>https:\/\/jonathan-harris.online\/<\/loc>/);

    items.push({ slug: '2026-w47-new-weekly-post', published_at: '2026-11-23T09:00:00Z' });
    response = await sitemapRequest(context);
    xml = await response.text();
    assert.equal(response.headers.get('x-blog-posts-in-sitemap'), '2');
    assert.match(xml, /<loc>https:\/\/jonathan-harris.online\/blog\/posts\/2026-w47-new-weekly-post\/<\/loc>/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('empty published manifest removes empty weekly archive but preserves base sitemap', async () => {
  const result = await loadPublishedBlogRoutes(sitemapContext([]).env);
  assert.deepEqual(result, { routes: [] });
});

test('sitemap refuses a misleading success when R2 blog publishing is unavailable', async () => {
  for (const [reason, env] of [
    ['binding-missing', { BLOG_BUCKET: undefined }],
    ['read-failed', { BLOG_BUCKET: { async get() { throw Error('secret R2 failure'); } } }],
    ['object-missing', { BLOG_BUCKET: { async get() { return null; } } }],
    ['invalid-manifest', { BLOG_BUCKET: { async get() { return { async json() { return { items: [{ slug: '../bad' }] }; } }; } } }],
  ]) {
    const response = await sitemapRequest({ ...sitemapContext([]), env });
    assert.equal(response.status, 503);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.equal(response.headers.get('x-blog-sitemap-state'), 'unavailable');
    const text = await response.text();
    assert.deepEqual(JSON.parse(text), { error: 'sitemap unavailable', reason });
    assert.doesNotMatch(text, /secret R2 failure/);
  }
});
