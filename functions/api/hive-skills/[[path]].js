const DEFAULT_PUBLIC_BASE_URL = "https://pub-da50a6512f164566955a3076a1c795ef.r2.dev";
const DEFAULT_OBJECT_KEY = "manifests/website-skills-manifest.json";

const ALLOWED_ROOTS = new Set(["audits", "index", "manifests", "schemas", "skills"]);
const ALLOWED_ROOT_FILES = new Set(["README.md", "file-manifest.json"]);

const CONTENT_TYPES = {
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

function jsonResponse(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload, null, 2) + "\n", {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": status === 200
        ? "public, max-age=300, s-maxage=300, stale-while-revalidate=3600"
        : "no-store",
      "Access-Control-Allow-Origin": "*",
      "X-HIVE-Skills-Access-Mode": "read-only",
      ...extraHeaders,
    },
  });
}

function objectKeyFromParams(params = {}) {
  const raw = params.path;
  const parts = Array.isArray(raw) ? raw : raw ? [raw] : [];
  const key = parts
    .join("/")
    .replace(/^\/+/, "")
    .replace(/\/+/g, "/")
    .trim();
  return key || DEFAULT_OBJECT_KEY;
}

function isSafeObjectKey(key) {
  if (!key || key.includes("..") || key.includes("\\") || key.includes("://")) return false;
  if (ALLOWED_ROOT_FILES.has(key)) return true;
  const [root] = key.split("/");
  if (!ALLOWED_ROOTS.has(root)) return false;
  return /\.(json|md|txt)$/i.test(key);
}

function contentTypeForKey(key) {
  const lower = key.toLowerCase();
  for (const [extension, contentType] of Object.entries(CONTENT_TYPES)) {
    if (lower.endsWith(extension)) return contentType;
  }
  return "application/octet-stream";
}

function copySafeObjectHeaders(object, key) {
  const headers = new Headers();
  headers.set("Content-Type", object?.httpMetadata?.contentType || contentTypeForKey(key));
  headers.set("Cache-Control", "public, max-age=300, s-maxage=300, stale-while-revalidate=3600");
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("X-HIVE-Skills-Access-Mode", "read-only");
  headers.set("X-HIVE-Skills-Object-Key", key);
  headers.set("X-HIVE-Skills-Source", "r2-binding");
  if (object?.etag) headers.set("ETag", object.etag);
  return headers;
}

async function fetchViaPublicBase(env, key, request) {
  const base = String(env?.R2_PUBLIC_BASE_URL_HIVE_SKILLS || DEFAULT_PUBLIC_BASE_URL).replace(/\/+$/, "");
  const upstreamUrl = `${base}/${encodeURI(key).replace(/%2F/g, "/")}`;
  const upstreamRequest = new Request(upstreamUrl, {
    method: "GET",
    headers: { Accept: request.headers.get("Accept") || "application/json,text/plain,*/*" },
  });
  const response = await fetch(upstreamRequest);
  if (!response.ok) {
    return jsonResponse({
      error: "HIVE skill object not found",
      object_key: key,
      upstream_status: response.status,
    }, response.status === 404 ? 404 : 502, {
      "X-HIVE-Skills-Source": "r2-public-url",
    });
  }

  const headers = new Headers(response.headers);
  headers.set("Content-Type", response.headers.get("Content-Type") || contentTypeForKey(key));
  headers.set("Cache-Control", "public, max-age=300, s-maxage=300, stale-while-revalidate=3600");
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("X-HIVE-Skills-Access-Mode", "read-only");
  headers.set("X-HIVE-Skills-Object-Key", key);
  headers.set("X-HIVE-Skills-Source", "r2-public-url");
  return new Response(response.body, { status: 200, headers });
}

export async function onRequest(context) {
  const { env, params, request } = context;

  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Accept, Content-Type",
        "Access-Control-Max-Age": "86400",
      },
    });
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    return jsonResponse({
      error: "Method not allowed",
      allowed_methods: ["GET", "HEAD", "OPTIONS"],
    }, 405, { Allow: "GET, HEAD, OPTIONS" });
  }

  const key = objectKeyFromParams(params);
  if (!isSafeObjectKey(key)) {
    return jsonResponse({
      error: "Object key is not allowed for website read-only access",
      object_key: key,
      allowed_roots: [...ALLOWED_ROOTS].sort(),
    }, 400);
  }

  const ifNoneMatch = request.headers.get("If-None-Match");
  if (env?.HIVE_SKILLS_BUCKET && typeof env.HIVE_SKILLS_BUCKET.get === "function") {
    const object = await env.HIVE_SKILLS_BUCKET.get(key);
    if (object) {
      const headers = copySafeObjectHeaders(object, key);
      if (ifNoneMatch && object.etag && ifNoneMatch === object.etag) {
        return new Response(null, { status: 304, headers });
      }
      return new Response(request.method === "HEAD" ? null : object.body, { status: 200, headers });
    }
  }

  if (request.method === "HEAD") {
    const response = await fetchViaPublicBase(env, key, request);
    return new Response(null, { status: response.status, headers: response.headers });
  }

  return fetchViaPublicBase(env, key, request);
}
