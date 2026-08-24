import { withFunctionSecurityHeaders } from "./_shared/security.js";
import {
  addHomepageAgentDiscovery,
  isAgentReadinessPath,
  proxyAgentReadiness,
} from "./_shared/agent-readiness.js";

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
  const url = new URL(context.request.url);

  // Agent discovery/protocol requests are publicly exposed by Pages but
  // executed by the independently deployed Agent Readiness Worker.
  if (isAgentReadinessPath(url.pathname)) {
    return withFunctionSecurityHeaders(await proxyAgentReadiness(context));
  }

  const aliasResponse = supportAliasRedirect(context.request);
  if (aliasResponse) {
    return withFunctionSecurityHeaders(aliasResponse);
  }

  const response = await context.next();
  const discovered = await addHomepageAgentDiscovery(context.request, response);
  return withFunctionSecurityHeaders(discovered);
}
