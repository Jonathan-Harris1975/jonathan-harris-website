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

function normaliseParagraphText(value = "") {
  return String(value || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&#x27;/gi, "'")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function dedupeOpeningParagraphs(source = "") {
  const mainStart = source.search(/<(?:main|article)\b/i);
  const prefixLength = mainStart >= 0 ? mainStart : 0;
  const head = source.slice(0, prefixLength);
  let body = source.slice(prefixLength);
  const paragraphRe = /<p\b[^>]*>[\s\S]*?<\/p>/gi;
  const matches = [...body.matchAll(paragraphRe)].slice(0, 8);
  const seen = new Set();
  const remove = [];
  for (const match of matches) {
    const text = normaliseParagraphText(match[0]);
    if (text.length < 45) continue;
    if (seen.has(text)) remove.push(match[0]);
    else seen.add(text);
  }
  for (const duplicate of remove) body = body.replace(duplicate, "");
  return head + body;
}

function youtubeEmbedMarkup(source = "") {
  const match = source.match(/(?:youtube\.com\/watch\?[^\s"'<>]*v=|youtu\.be\/|youtube\.com\/(?:shorts|embed)\/)([A-Za-z0-9_-]{6,})/i);
  if (!match?.[1] || source.includes('data-jh-blog-video="1"')) return "";
  return `<section class="card blog-video-embed" data-jh-blog-video="1"><h2>Watch the episode</h2><div class="responsive-media"><iframe src="https://www.youtube-nocookie.com/embed/${match[1]}" title="Video for this weekly AI briefing" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div></section>`;
}

function stripMarkup(value = "") {
  return String(value || "").replace(/<script\b[\s\S]*?<\/script\b[^>]*>/gi, " ").replace(/<style\b[\s\S]*?<\/style\b[^>]*>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/&quot;/gi, '"').replace(/&#39;|&#x27;/gi, "'").replace(/\s+/g, " ").trim();
}

function blogShareCardParams(source = "") {
  const h1 = source.match(/<h1\b[^>]*>([\s\S]*?)<\/h1>/i);
  const quote = source.match(/<blockquote\b[^>]*>([\s\S]*?)<\/blockquote>/i) || source.match(/<p\b[^>]*class=(?:"[^"]*(?:standfirst|lead|summary)[^"]*"|'[^']*(?:standfirst|lead|summary)[^']*')[^>]*>([\s\S]*?)<\/p>/i);
  return { title: stripMarkup(h1?.[1] || "Turing's Torch AI Weekly"), quote: stripMarkup(quote?.[1] || "AI analysis without the hype.") };
}

function blogGrowthMarkup(request, source = "") {
  const canonical = new URL(request.url).toString();
  const encodedUrl = encodeURIComponent(canonical);
  return `<section class="card blog-growth-panel" data-jh-blog-growth="1">
<h2>Keep the useful bits</h2>
<p>Get the weekday AI briefing and the free plain-English AI glossary cheat sheet without leaving this article.</p>
<form class="newsletter-native-form" action="/api/newsletter/subscribe" method="post" data-newsletter-form>
<label>Email address <input name="email" type="email" autocomplete="email" inputmode="email" required maxlength="254" placeholder="you@example.com"></label>
<input type="hidden" name="source" value="blog-post"><input type="hidden" name="next" value="/downloads/ai-glossary-cheat-sheet/"><span class="newsletter-honeypot" aria-hidden="true"><label>Company <input name="company" tabindex="-1" autocomplete="off"></label></span>
<button class="button" type="submit">Join and get the cheat sheet</button><p class="subtle" data-newsletter-status hidden aria-live="polite"></p>
</form>
<p><a data-newsletter-fallback href="https://form.jotform.com/260277027608054" target="_blank" rel="noopener">Hosted sign-up fallback</a></p>
<h2>Share this briefing</h2><nav class="share-links" aria-label="Share this briefing"><a href="https://twitter.com/intent/tweet?url=${encodedUrl}" target="_blank" rel="noopener noreferrer">Share on X</a><a href="https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}" target="_blank" rel="noopener noreferrer">LinkedIn</a><a href="https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}" target="_blank" rel="noopener noreferrer">Facebook</a><button type="button" data-copy-url="${canonical}">Copy link</button>${(() => { const card = blogShareCardParams(source); return `<a href="/api/blog/share-card?title=${encodeURIComponent(card.title)}&quote=${encodeURIComponent(card.quote)}" target="_blank" rel="noopener">Share graphic</a>`; })()}</nav>
<p class="jh-related-callout">Continue with the <a href="/topics/">AI topic guides</a>, <a href="/glossary/">plain-English glossary</a>, <a href="/ebooks/">eBook catalogue</a>, or <a href="/podcast/">podcast archive</a>.</p>
</section>`;
}

function injectBeforeContentEnd(source, markup) {
  if (!markup) return source;
  const articleClose = source.search(/<\/article>/i);
  if (articleClose >= 0) return source.slice(0, articleClose) + markup + source.slice(articleClose);
  const mainClose = source.search(/<\/main>/i);
  if (mainClose >= 0) return source.slice(0, mainClose) + markup + source.slice(mainClose);
  return source + markup;
}

function ensureGrowthScripts(source) {
  if (!source.includes('/assets/js/newsletter-signup.min.js')) source = source.replace(/<\/body>/i, '<script defer src="/assets/js/newsletter-signup.min.js"></script>\n</body>');
  if (!source.includes('/assets/js/share.min.js')) source = source.replace(/<\/body>/i, '<script defer src="/assets/js/share.min.js"></script>\n</body>');
  return source;
}

function rewriteHtml(html, request) {
  const origin = getOrigin(request);
  let source = String(html || "")
    .replace(/https:\/\/blog-images\.jonathan-harris\.online\/([^"'\s<]+)/gi, `${origin}/blog/images/$1`)
    .replace(/https:\/\/[^/]+\.r2\.dev\/([^"'\s<]+)/gi, (match, path) => {
      if (!looksLikeImagePath(path)) return match;
      return `${origin}/blog/images/${path}`;
    })
    .replace(/https:\/\/blog\.jonathan-harris\.online\/blog\//gi, `${origin}/blog/`);
  source = dedupeOpeningParagraphs(source);
  if (!source.includes('data-jh-blog-growth="1"')) {
    source = injectBeforeContentEnd(source, `${youtubeEmbedMarkup(source)}${blogGrowthMarkup(request, source)}`);
  }
  return ensureGrowthScripts(source);
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
