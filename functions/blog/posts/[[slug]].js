import { ensureSharedChrome } from "../../_shared/chrome.js";
import {
  extensionContentType,
  getIfNoneMatchResponse,
  getR2Object,
  rewriteHtml,
  rewriteManifestItem,
  withCacheHeaders,
} from "../_utils/blog-r2.js";

export async function onRequest(context) {
  const { params, env, request } = context;
  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug];
  const rawPath = slugParts.filter(Boolean).join("/");

  if (!rawPath) {
    return context.next();
  }

  const match = await getR2Object(env.BLOG_BUCKET, `posts/${rawPath}`);
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
  let html = key.endsWith(".html") ? rewriteHtml(body, request) : body;
  if (key.endsWith(".html")) {
    html = await ensureSharedChrome(context, html);
  }

  return new Response(html, { status: 200, headers });
}
