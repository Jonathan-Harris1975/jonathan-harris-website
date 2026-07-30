import { normaliseManifest } from "./_utils/blog-r2.js";

const MANIFEST_KEY = "blog/posts.json";

export async function onRequest(context) {
  const { env, request } = context;
  const object = await env.BLOG_BUCKET?.get(MANIFEST_KEY);

  if (!object) {
    return new Response(JSON.stringify({ error: "blog manifest unavailable" }), {
      status: 503,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Blog-Manifest-Source": "r2-missing",
      },
    });
  }

  const payload = await object.json().catch(async () => JSON.parse(await object.text()));
  const manifest = normaliseManifest(payload, request);

  return new Response(JSON.stringify(manifest, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=60, s-maxage=60, stale-while-revalidate=300",
      "X-Blog-Manifest-Source": "r2",
    },
  });
}
