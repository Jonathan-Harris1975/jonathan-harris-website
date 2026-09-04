const CANONICAL_PATH = "/sitemap.xml";

export function redirectToCanonicalSitemap(request) {
  const url = new URL(request.url);
  url.pathname = CANONICAL_PATH;
  url.search = "";
  return Response.redirect(url.toString(), 301);
}
