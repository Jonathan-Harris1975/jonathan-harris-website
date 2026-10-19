const BUCKETS = [
  { binding: "TRANSCRIPTS_BUCKET", required: true },
  { binding: "BLOG_BUCKET", required: true },
  { binding: "BLOG_IMAGES_BUCKET", required: false },
];

async function inspectBucket(env, { binding, required }) {
  const bucket = env?.[binding];
  if (!bucket || typeof bucket.list !== "function") {
    return { configured: false, runtime_access: "not-tested", required };
  }
  try {
    // A one-item metadata listing verifies runtime access without reading content or changing data.
    await bucket.list({ limit: 1 });
    return { configured: true, runtime_access: "available", required };
  } catch {
    // Do not return provider errors, bucket contents, or credentials in a public health response.
    return { configured: true, runtime_access: "unavailable", required };
  }
}

export async function onRequest({ env }) {
  const entries = await Promise.all(BUCKETS.map(async (item) => [item.binding, await inspectBucket(env, item)]));
  const bindings = Object.fromEntries(entries);
  const healthy = Object.values(bindings).every((result) => !result.required || (result.configured && result.runtime_access === "available"));
  const revision = /^[0-9a-f]{40}$/.test(env?.CF_PAGES_COMMIT_SHA || "") ? env.CF_PAGES_COMMIT_SHA : null;
  const payload = {
    ok: healthy,
    status: healthy ? "healthy" : "degraded",
    service: "WEBSITE",
    deployment: "cloudflare-pages",
    revision,
    bindings,
  };
  return new Response(JSON.stringify(payload), {
    status: healthy ? 200 : 503,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
