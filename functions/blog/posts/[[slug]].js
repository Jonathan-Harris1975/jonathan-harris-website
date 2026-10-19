import { ensureSharedChrome } from "../../_shared/chrome.js";
import { sanitizeStoredHtml } from "../../_shared/security.js";
import {
  extensionContentType,
  getIfNoneMatchResponse,
  getR2Object,
  rewriteHtml,
  rewriteManifestItem,
  withCacheHeaders,
} from "../_utils/blog-r2.js";

function unavailable(reason) {
  return new Response(JSON.stringify({ error: "blog content unavailable", reason }), {
    status: 503,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Retry-After": "60",
      "X-Blog-Content": reason,
    },
  });
}

export async function onRequest(context) {
  const { params, env, request } = context;
  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug];
  const rawPath = slugParts.filter(Boolean).join("/");

  if (!rawPath) {
    return context.next();
  }

  const bucket = env?.BLOG_BUCKET;
  if (!bucket || typeof bucket.get !== "function") return unavailable("binding-missing");

  let match;
  try {
    match = await getR2Object(bucket, `posts/${rawPath}`);
  } catch {
    return unavailable("read-failed");
  }
  if (!match) {
    return context.next();
  }

  const { key, object } = match;
  const headers = withCacheHeaders(new Headers(), object, extensionContentType(key));
  const notModified = getIfNoneMatchResponse(request, headers, object);
  if (notModified) {
    return notModified;
  }

  if (key.endsWith(".json")) {
    const payload = await object.json().catch(async () => JSON.parse(await object.text()));
    const rewritten = rewriteManifestItem(payload, request);

    return new Response(JSON.stringify(rewritten, null, 2), {
      status: 200,
      headers,
    });
  }

  const body = await object.text();
  let html = body;
  if (key.endsWith(".html")) {
    html = rewriteHtml(await sanitizeStoredHtml(body), request);
    html = await ensureSharedChrome(context, html);
  }

  return new Response(html, { status: 200, headers });
}
