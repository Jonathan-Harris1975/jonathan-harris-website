import { redirectToCanonicalSitemap } from "./_shared/canonical-sitemap-redirect.js";

// Legacy hyphenated sitemap alias retained for public URL compatibility.
export async function onRequest(context) {
  return redirectToCanonicalSitemap(context.request);
}
