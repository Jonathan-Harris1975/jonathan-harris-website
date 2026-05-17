import { getPublicationState, getWeeklyArchiveUrl } from "./blog/_utils/blog-publication.js";

const MANIFEST_PATH = "/blog/posts.json";
const DYNAMIC_ROUTE_MANIFEST_PATH = "/data/dynamic-route-manifest.json";

function escapeRegex(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasUrl(xml, loc) {
  return new RegExp(`<loc>${escapeRegex(loc)}<\\/loc>`, "i").test(xml);
}

function appendUrlEntry(xml, route) {
  const loc = String(route?.loc || "").trim();
  if (!loc || hasUrl(xml, loc)) return xml;
  const lastmod = String(route?.lastmod || "").trim();
  const block = [
    "  <url>",
    `    <loc>${loc}</loc>`,
    lastmod ? `    <lastmod>${lastmod}</lastmod>` : "",
    "  </url>",
  ].filter(Boolean).join("\n");
  return xml.replace(/<\/urlset>\s*$/i, `${block}\n</urlset>`);
}

function updateWeeklyArchiveEntry(xml, hasItems) {
  const weeklyUrl = getWeeklyArchiveUrl();
  const escapedWeeklyUrl = weeklyUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const weeklyBlockPattern = new RegExp(`\\s*<url>\\s*<loc>${escapedWeeklyUrl}<\\/loc>(?:\\s*<lastmod>[^<]+<\\/lastmod>)?\\s*<\\/url>`, "i");
  const weeklyBlock = `\n  <url>\n    <loc>${weeklyUrl}</loc>\n  </url>`;

  if (hasItems) {
    if (weeklyBlockPattern.test(xml)) {
      return xml;
    }
    return xml.replace(/<\/urlset>\s*$/i, `${weeklyBlock}\n</urlset>`);
  }

  return xml.replace(weeklyBlockPattern, "");
}

async function fetchJsonAsset(context, path) {
  const url = new URL(path, context.request.url);
  const request = new Request(url.toString(), { headers: { Accept: "application/json" } });
  const response = context.env?.ASSETS?.fetch
    ? await context.env.ASSETS.fetch(request)
    : await fetch(request);
  if (!response.ok) return null;
  return response.json();
}

async function updateDynamicRouteEntries(xml, context) {
  const manifest = await fetchJsonAsset(context, DYNAMIC_ROUTE_MANIFEST_PATH);
  const routes = Array.isArray(manifest?.routes) ? manifest.routes : [];
  return routes.reduce((currentXml, route) => appendUrlEntry(currentXml, route), xml);
}

export async function onRequest(context) {
  const response = await context.next();
  const contentType = response.headers.get("content-type") || "";

  if (!response.ok || !contentType.includes("xml")) {
    return response;
  }

  let xml = await response.text();
  const publication = await getPublicationState(context.request, MANIFEST_PATH);
  xml = updateWeeklyArchiveEntry(xml, publication.hasItems);
  xml = await updateDynamicRouteEntries(xml, context);

  const headers = new Headers(response.headers);
  headers.set("cache-control", "public, max-age=300, s-maxage=300");
  headers.set("x-blog-archive-state", publication.hasItems ? "populated" : "empty");
  headers.set("x-dynamic-route-manifest", "enabled");

  return new Response(xml, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
