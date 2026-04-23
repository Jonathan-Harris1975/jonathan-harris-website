import { normaliseManifest } from "./_utils/blog-r2.js";

const MANIFEST_KEY = "blog/posts.json";

export async function onRequest(context) {
  const { env } = context;
  const object = await env.BLOG_BUCKET?.get(MANIFEST_KEY);

  if (!object) {
    return context.next();
  }

  const payload = await object.json().catch(async () => JSON.parse(await object.text()));
  const manifest = normaliseManifest(payload, context.request);

  return new Response(JSON.stringify(manifest, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=300, s-maxage=300, stale-while-revalidate=86400",
    },
  });
}
