/**
 * functions/transcripts/[[slug]].js
 *
 * Pages Function — proxies /transcripts/<slug> requests to the R2 bucket
 * bound as TRANSCRIPTS_BUCKET.
 *
 * Route coverage (via [[slug]] catch-all):
 *   /transcripts/episode-title-slug        → R2 key: episode-title-slug
 *   /transcripts/episode-title-slug.html   → R2 key: episode-title-slug.html
 *
 * The bare /transcripts and /transcripts/ paths are handled upstream by
 * the _redirects 200-rewrite rules and never reach this function.
 *
 * R2 binding setup (Cloudflare Pages dashboard):
 *   Settings → Functions → R2 bucket bindings
 *   Variable name : TRANSCRIPTS_BUCKET
 *   R2 bucket     : <your bucket name>
 */

export async function onRequest(context) {
  const { params, env, request } = context;

  // params.slug is an array of path segments from the [[slug]] catch-all.
  // Join them back into a single key string.
  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug];
  const rawKey = slugParts.join('/');

  // Guard: empty slug means /transcripts/ — should have been caught by
  // _redirects already, but fall through cleanly just in case.
  if (!rawKey) {
    return context.next();
  }

  // Attempt 1: key exactly as provided (e.g. "episode-slug" or "episode-slug.html")
  let object = await env.TRANSCRIPTS_BUCKET.get(rawKey);

  // Attempt 2: append .html if the bare slug wasn't found and doesn't
  // already end with a recognised extension.
  if (!object && !rawKey.match(/\.(html|htm|txt|json|xml)$/i)) {
    object = await env.TRANSCRIPTS_BUCKET.get(rawKey + '.html');
  }

  // No matching object in R2 — fall through to the Pages 404 handler.
  if (!object) {
    return context.next();
  }

  // Build response headers.
  const headers = new Headers();

  // Content-Type: use the metadata stored on the R2 object if present,
  // otherwise default to HTML (all transcript pages are HTML documents).
  headers.set(
    'Content-Type',
    object.httpMetadata?.contentType ?? 'text/html; charset=utf-8'
  );

  // Cache for 1 hour at the edge; stale-while-revalidate keeps the CDN
  // serving while it refreshes in the background.
  headers.set('Cache-Control', 'public, max-age=3600, stale-while-revalidate=86400');

  // ETag from R2 for conditional request support.
  if (object.etag) {
    headers.set('ETag', object.etag);
  }

  // Honour conditional GET (If-None-Match) to avoid sending unchanged
  // transcript bodies to clients that already have them cached.
  const ifNoneMatch = request.headers.get('If-None-Match');
  if (ifNoneMatch && ifNoneMatch === object.etag) {
    return new Response(null, { status: 304, headers });
  }

  return new Response(object.body, { status: 200, headers });
}
