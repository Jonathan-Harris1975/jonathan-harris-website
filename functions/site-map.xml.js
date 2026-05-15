const CANONICAL_PATH = "/sitemap.xml";

export async function onRequest(context) {
  const url = new URL(context.request.url);
  url.pathname = CANONICAL_PATH;
  url.search = "";
  return Response.redirect(url.toString(), 301);
}
