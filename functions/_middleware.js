import { withFunctionSecurityHeaders } from "./_shared/security.js";

const SUPPORT_ALIASES = new Map([
  ["/robot.txt", "/robots.txt"],
  ["/Sitemap.xml", "/sitemap.xml"],
  ["/site-map.xml", "/sitemap.xml"],
]);

function supportAliasRedirect(request) {
  const url = new URL(request.url);
  const targetPath = SUPPORT_ALIASES.get(url.pathname);
  if (!targetPath) {
    return null;
  }

  url.pathname = targetPath;
  url.search = "";
  url.hash = "";
  return Response.redirect(url.toString(), 301);
}

export async function onRequest(context) {
  const aliasResponse = supportAliasRedirect(context.request);
  if (aliasResponse) {
    return withFunctionSecurityHeaders(aliasResponse);
  }

  const response = await context.next();
  return withFunctionSecurityHeaders(response);
}
