const FUNCTION_CSP = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "upgrade-insecure-requests",
  "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://cdn-cookieyes.com https://*.cookieyes.c\
om https://tracker.metricool.com https://*.metricool.com https://elfsightcdn.com https://*.elfsight.com https://cdn.jotfor.ms https://js.jotform.com h\
ttps://www.jotform.com https://form.jotform.com",
  "script-src-elem 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://cdn-cookieyes.com https://*.cookie\
yes.com https://tracker.metricool.com https://*.metricool.com https://elfsightcdn.com https://*.elfsight.com https://cdn.jotfor.ms https://js.jotform.\
com https://www.jotform.com https://form.jotform.com",
  "script-src-attr 'none'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn-cookieyes.com https://*.cookieyes.com https://c\
dn.jotfor.ms https://www.jotform.com",
  "style-src-attr 'unsafe-inline'",
  "font-src 'self' https://fonts.gstatic.com data:",
  "img-src 'self' data: blob: https://www.googletagmanager.com https://www.google-analytics.com https://ssl.google-analytics.com https://stats.g.doubl\
eclick.net https://images.jonathan-harris.online https://assets.jonathan-harris.online https://*.jonathan-harris.online https://*.r2.dev https://cdn-c\
ookieyes.com https://*.cookieyes.com https://tracker.metricool.com https://*.metricool.com https://elfsightcdn.com https://*.elfsight.com https://cdn.\
jotfor.ms https://www.jotform.com https://form.jotform.com https://submit.jotform.com https://ik.imagekit.io",
  "connect-src 'self' https://www.googletagmanager.com https://www.google-analytics.com https://region1.google-analytics.com https://analytics.google.\
com https://stats.g.doubleclick.net https://cdn-cookieyes.com https://*.cookieyes.com https://tracker.metricool.com https://*.metricool.com https://el\
fsightcdn.com https://*.elfsight.com https://podcast-rss-feeds.jonathan-harris.online https://images.jonathan-harris.online https://assets.jonathan-ha\
rris.online https://*.jonathan-harris.online https://*.r2.dev https://www.jotform.com https://form.jotform.com https://cdn.jotfor.ms https://submit.jo\
tform.com https://api.jotform.com https://ik.imagekit.io",
  "frame-src 'self' https://www.googletagmanager.com https://form.jotform.com https://www.jotform.com https://cdn.jotfor.ms https://submit.jotform.com\
 https://open.spotify.com https://www.youtube-nocookie.com https://elfsightcdn.com https://*.elfsight.com https://cdn-cookieyes.com https://*.cookieye\
s.com",
  "media-src 'self' https://*.jonathan-harris.online https://*.r2.dev https://*.cloudflarestorage.com",
  "frame-ancestors 'self'",
].join("; ");
const DROP_ELEMENTS = new Set([
  "applet",
  "base",
  "embed",
  "form",
  "input",
  "object",
  "script",
  "select",
  "style",
  "svg",
  "template",
  "textarea",
]);
const DROP_ATTRIBUTES = new Set([
  "action",
  "formaction",
  "formmethod",
  "formtarget",
  "integrity",
  "nonce",
  "ping",
  "srcdoc",
  "srcset",
  "style",
  "xlink:href",
]);
const URL_ATTRIBUTES = new Set(["cite", "href", "poster", "src"]);
const SAFE_URL_SCHEMES = new Set(["http:", "https:", "mailto:", "tel:"]);
function isSafeStoredUrl(value) {
  const raw = String(value || "").trim();
  if (!raw || raw.startsWith("#") || raw.startsWith("./") || raw.startsWith("../") || raw.startsWith("?")) {
    return true;
  }
  if (raw.startsWith("//")) return false;
  if (raw.startsWith("/")) return true;
  try {
    const parsed = new URL(raw);
    return SAFE_URL_SCHEMES.has(parsed.protocol.toLowerCase());
  } catch {
    return false;
  }
}
function hardenStoredElement(element) {
  const tag = String(element.tagName || "").toLowerCase();
  if (DROP_ELEMENTS.has(tag)) {
    element.remove();
    return;
  }
  if (tag === "meta" && element.hasAttribute("http-equiv")) {
    element.remove();
    return;
  }
  if (tag === "link") {
    const rel = String(element.getAttribute("rel") || "").toLowerCase().split(/\s+/).filter(Boolean);
    if (rel.some((value) => ["stylesheet", "import", "preload", "modulepreload"].includes(value))) {
      element.remove();
      return;
    }
  }
  if (tag === "iframe") {
    const rawSrc = element.getAttribute("src") || "";
    let allowed = false;
    try {
      const url = new URL(rawSrc);
      allowed = url.protocol === "https:" && url.hostname === "www.youtube-nocookie.com" && url.pathname.startsWith("/embed/");
    } catch {}
    if (!allowed) {
      element.remove();
      return;
    }
    element.setAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation");
    element.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
  }
  for (const [rawName, value] of [...element.attributes]) {
    const name = String(rawName || "").toLowerCase();
    if (name.startsWith("on") || DROP_ATTRIBUTES.has(name)) {
      element.removeAttribute(rawName);
      continue;
    }
    if (URL_ATTRIBUTES.has(name) && !isSafeStoredUrl(value)) {
      element.removeAttribute(rawName);
    }
  }
  if (tag === "a" && element.getAttribute("target") === "_blank") {
    const rel = new Set(String(element.getAttribute("rel") || "").split(/\s+/).filter(Boolean));
    rel.add("noopener");
    rel.add("noreferrer");
    element.setAttribute("rel", [...rel].join(" "));
  }
}
export async function sanitizeStoredHtml(html) {
  const source = String(html || "");
  const response = new Response(source, { headers: { "Content-Type": "text/html; charset=utf-8" } });
  const transformed = new HTMLRewriter()
    .on("*", { element: hardenStoredElement })
    .transform(response);
  return transformed.text();
}
export function withFunctionSecurityHeaders(response) {
  const headers = new Headers(response.headers);
  headers.set("Content-Security-Policy", FUNCTION_CSP);
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "SAMEORIGIN");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
