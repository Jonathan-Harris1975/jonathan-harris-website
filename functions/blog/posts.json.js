import { normaliseManifest } from "./_utils/blog-r2.js";
import { DEFAULT_BLOG_RSS_URL, fetchBlogFeedManifest } from "./_utils/blog-feed.js";

const MANIFEST_KEY = "blog/posts.json";

export async function onRequest(context) {
  const { env, request } = context;
  const feedUrl = String(env.BLOG_RSS_FEED_URL || DEFAULT_BLOG_RSS_URL || "").trim();

  if (feedUrl) {
    try {
      const manifest = await fetchBlogFeedManifest(request, feedUrl);
      return new Response(JSON.stringify(manifest, null, 2), {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=60, s-maxage=60, stale-while-revalidate=300",
          "X-Blog-Manifest-Source": "rss",
        },
      });
    } catch (_error) {
      // Fall through to the last committed / R2 snapshot.
    }
  }

  const object = await env.BLOG_BUCKET?.get(MANIFEST_KEY);
  if (!object) {
    return context.next();
  }

  const payload = await object.json().catch(async () => JSON.parse(await object.text()));
  const manifest = normaliseManifest(payload, request);

  return new Response(JSON.stringify(manifest, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=60, s-maxage=60, stale-while-revalidate=300",
      "X-Blog-Manifest-Source": "snapshot",
    },
  });
}
