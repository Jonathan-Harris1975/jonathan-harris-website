import {
  decodeSlugPath,
  extensionContentType,
  getIfNoneMatchResponse,
  trimSlashes,
  withCacheHeaders,
} from "../_utils/blog-r2.js";

export async function onRequest(context) {
  const { params, env, request } = context;
  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug];
  const rawPath = decodeSlugPath(slugParts.filter(Boolean).join("/"));

  if (!rawPath) {
    return context.next();
  }

  const key = trimSlashes(rawPath);
  const object = await env.BLOG_IMAGES_BUCKET?.get(key);

  if (!object) {
    return context.next();
  }

  const headers = withCacheHeaders(new Headers(), object, extensionContentType(key));
  const notModified = getIfNoneMatchResponse(request, headers, object);
  if (notModified) {
    return notModified;
  }

  return new Response(object.body, { status: 200, headers });
}
