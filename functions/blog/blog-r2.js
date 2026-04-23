const BLOG_ROOT_PREFIX = "blog";

function trimSlashes(value) {
  return String(value || "").replace(/^\/+|\/+$/g, "");
}

function getOrigin(request) {
  return new URL(request.url).origin;
}

function decodeSlugPath(rawPath) {
  return trimSlashes(String(rawPath || "").split("?")[0]).split("/").filter(Boolean).map((segment) => {
    try {
      return decodeURIComponent(segment);
    } catch {
      return segment;
    }
  }).join("/");
}

function looksLikeImagePath(value) {
  return /\.(?:png|jpe?g|webp|avif|gif|svg)$/i.test(String(value || ""));
}

function extensionContentType(pathname) {
  const lower = String(pathname || "").toLowerCase();
  if (lower.endsWith(".json")) return "application/json; charset=utf-8";
  if (lower.endsWith(".xml")) return "application/xml; charset=utf-8";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".avif")) return "image/avif";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".svg")) return "image/svg+xml";
  if (lower.endsWith(".txt")) return "text/plain; charset=utf-8";
  return "text/html; charset=utf-8";
}

function withCacheHeaders(headers, object, fallbackType) {
  const nextHeaders = new Headers(headers || {});
  nextHeaders.set(
    "Content-Type",
    object?.httpMetadata?.contentType || fallbackType || "application/octet-stream"
  );
  nextHeaders.set("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400");
  if (object?.etag) {
    nextHeaders.set("ETag", object.etag);
  }
  return nextHeaders;
}

function getIfNoneMatchResponse(request, headers, object) {
  const ifNoneMatch = request.headers.get("If-None-Match");
  if (ifNoneMatch && object?.etag && ifNoneMatch === object.etag) {
    return new Response(null, { status: 304, headers });
  }
  return null;
}

function toSameOriginBlogPath(path, request) {
  const cleanPath = trimSlashes(path);
  if (!cleanPath) return `${getOrigin(request)}/blog/`;
  return `${getOrigin(request)}/blog/${cleanPath}`;
}

function mapBlogImagePath(value, request) {
  const raw = String(value || "").trim();
  if (!raw) return raw;

  if (raw.startsWith("/blog/images/")) {
    return `${getOrigin(request)}${raw}`;
  }

  if (/^https?:\/\//i.test(raw)) {
    try {
      const url = new URL(raw);
      if (url.origin === getOrigin(request) && url.pathname.startsWith("/blog/images/")) {
        return url.toString();
      }

      if (url.hostname.includes("blog-images") || url.hostname.endsWith(".r2.dev")) {
        const key = trimSlashes(url.pathname);
        if (key) {
          return `${getOrigin(request)}/blog/images/${key}`;
        }
      }

      return raw;
    } catch {
      return raw;
    }
  }

  const key = trimSlashes(raw);
  if (!key) return raw;
  return `${getOrigin(request)}/blog/images/${key}`;
}

function rewriteManifestItem(item, request) {
  if (!item || typeof item !== "object") return item;

  const slug = trimSlashes(item.slug || "");
  const postPath = slug ? `/blog/posts/${slug}/` : (item.path || "/blog/");
  const postUrl = `${getOrigin(request)}${postPath}`;
  const rewritten = { ...item, path: postPath, url: postUrl, canonical_url: postUrl };

  const imageUrl = item.image_url || item.image;
  if (imageUrl) {
    const sameOriginImage = mapBlogImagePath(imageUrl, request);
    rewritten.image = sameOriginImage;
    rewritten.image_url = sameOriginImage;
  }

  return rewritten;
}

function normaliseManifest(payload, request) {
  const source = payload && typeof payload === "object" ? payload : {};
  const items = Array.isArray(source.items) ? source.items : [];
  return {
    ...source,
    schema_version: Number(source.schema_version || 1),
    items: items.map((item) => rewriteManifestItem(item, request)).filter(Boolean),
  };
}

function rewriteHtml(html, request) {
  const origin = getOrigin(request);
  return String(html || "")
    .replace(/https:\/\/blog-images\.jonathan-harris\.online\/([^"'\s<]+)/gi, `${origin}/blog/images/$1`)
    .replace(/https:\/\/[^/]+\.r2\.dev\/([^"'\s<]+)/gi, (match, path) => {
      if (!looksLikeImagePath(path)) return match;
      return `${origin}/blog/images/${path}`;
    })
    .replace(/https:\/\/blog\.jonathan-harris\.online\/blog\//gi, `${origin}/blog/`);
}

async function getR2Object(bucket, requestPath) {
  const clean = decodeSlugPath(requestPath);
  if (!clean) return null;

  const candidates = [
    `${BLOG_ROOT_PREFIX}/${clean}`,
  ];

  if (!looksLikeImagePath(clean) && !clean.toLowerCase().endsWith(".json")) {
    candidates.push(`${BLOG_ROOT_PREFIX}/${clean}/index.html`);
    candidates.push(`${BLOG_ROOT_PREFIX}/${clean}.html`);
  }

  for (const key of candidates) {
    const object = await bucket.get(key);
    if (object) {
      return { key, object };
    }
  }

  return null;
}

export {
  BLOG_ROOT_PREFIX,
  decodeSlugPath,
  extensionContentType,
  getIfNoneMatchResponse,
  getOrigin,
  getR2Object,
  mapBlogImagePath,
  normaliseManifest,
  rewriteHtml,
  rewriteManifestItem,
  toSameOriginBlogPath,
  trimSlashes,
  withCacheHeaders,
};
