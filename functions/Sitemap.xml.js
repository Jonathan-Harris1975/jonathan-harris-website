import { redirectToCanonicalSitemap } from "./_shared/canonical-sitemap-redirect.js";

// Legacy case-sensitive sitemap alias retained for public URL compatibility.
export async function onRequest({ request }) {
  return redirectToCanonicalSitemap(request);
}
