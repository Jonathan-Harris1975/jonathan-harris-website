import { getPublicationState } from "../_utils/blog-publication.js";

const MANIFEST_PATH = "/blog/posts.json";

function applyRobotsDirective(html, hasItems) {
  const replacement = `<meta content="${hasItems ? "index" : "noindex"},follow" name="robots"/>`;

  if (/<meta[^>]+name="robots"[^>]*>/i.test(html)) {
    return html.replace(/<meta[^>]+name="robots"[^>]*>/i, replacement);
  }

  return html.replace(/<\/head>/i, `${replacement}\n</head>`);
}

export async function onRequest(context) {
  const response = await context.next();
  const contentType = response.headers.get("content-type") || "";

  if (!response.ok || !contentType.includes("text/html")) {
    return response;
  }

  const html = await response.text();
  const publication = await getPublicationState(context.request, MANIFEST_PATH);
  const headers = new Headers(response.headers);
  headers.set("cache-control", "public, max-age=300, s-maxage=300");
  headers.set("x-blog-archive-state", publication.hasItems ? "populated" : "empty");

  return new Response(applyRobotsDirective(html, publication.hasItems), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
