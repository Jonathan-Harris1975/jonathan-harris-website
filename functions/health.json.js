const BUCKETS = [
  { binding: "TRANSCRIPTS_BUCKET", required: true },
  { binding: "BLOG_BUCKET", required: true },
  { binding: "BLOG_IMAGES_BUCKET" },
];

async function inspectBucket(env, { binding, required = false }) {
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

async function inspectCogniPalRateLimiter(env, expectedRevision) {
  const worker = env?.COGNIPAL_RATE_LIMIT_HEALTH;
  if (!worker || typeof worker.fetch !== "function") {
    return { configured: false, runtime_access: "not-tested", source_commit_sha: null, required: true };
  }
  try {
    const response = await worker.fetch(new Request("https://cognipal-rate-limit.internal/health"));
    if (!response.ok) {
      return { configured: true, runtime_access: "unavailable", source_commit_sha: null, required: true };
    }
    const payload = await response.json();
    const sourceCommitSha = typeof payload?.source_commit_sha === "string"
      ? payload.source_commit_sha.toLowerCase()
      : "";
    const valid = payload?.ok === true
      && payload?.service === "cognipal-rate-limit"
      && /^[0-9a-f]{40}$/.test(sourceCommitSha)
      && (!expectedRevision || sourceCommitSha === expectedRevision);
    return {
      configured: true,
      runtime_access: valid ? "available" : "unavailable",
      source_commit_sha: valid ? sourceCommitSha : null,
      required: true,
    };
  } catch {
    return { configured: true, runtime_access: "unavailable", source_commit_sha: null, required: true };
  }
}

export async function onRequest({ env }) {
  const revision = /^[0-9a-f]{40}$/.test(env?.CF_PAGES_COMMIT_SHA || "") ? env.CF_PAGES_COMMIT_SHA : null;
  const [bucketEntries, cognipalRateLimiter] = await Promise.all([
    Promise.all(BUCKETS.map(async (item) => [item.binding, await inspectBucket(env, item)])),
    inspectCogniPalRateLimiter(env, revision),
  ]);
  const bindings = Object.fromEntries([
    ...bucketEntries,
    ["COGNIPAL_RATE_LIMITER", cognipalRateLimiter],
  ]);
  const healthy = Object.values(bindings).every((result) => !result.required || (result.configured && result.runtime_access === "available"));
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
