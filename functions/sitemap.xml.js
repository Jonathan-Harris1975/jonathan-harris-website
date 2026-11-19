import { getWeeklyArchiveUrl } from "./blog/_utils/blog-publication.js";
import { fetchPodcastEpisodes } from "./_shared/podcast.js";

const BLOG_MANIFEST_KEY = "blog/posts.json";
const DYNAMIC_ROUTE_MANIFEST_PATH = "/data/dynamic-route-manifest.json";
const SITE_ORIGIN = "https://jonathan-harris.online";

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
    if (weeklyBlockPattern.test(xml)) return xml;
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

function publishedDate(value = "") {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString().slice(0, 10);
}

// The same R2 manifest is written by weekly publishing; never require a Pages rebuild.
export async function loadPublishedBlogRoutes(env) {
  const bucket = env?.BLOG_BUCKET;
  if (!bucket || typeof bucket.get !== "function") return { reason: "binding-missing" };

  let object;
  try {
    object = await bucket.get(BLOG_MANIFEST_KEY);
  } catch {
    return { reason: "read-failed" };
  }
  if (!object) return { reason: "object-missing" };

  try {
    const manifest = await object.json();
    if (!Array.isArray(manifest?.items)) return { reason: "invalid-manifest" };
    const seen = new Set();
    const routes = [];
    for (const item of manifest.items) {
      const slug = item?.slug;
      // Only publish canonical same-site article paths; never trust URLs from R2 metadata.
      if (typeof slug !== "string" || slug.length > 200 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
        return { reason: "invalid-manifest" };
      }
      if (seen.has(slug)) continue;
      seen.add(slug);
      routes.push({
        loc: `${SITE_ORIGIN}/blog/posts/${slug}/`,
        lastmod: publishedDate(item.updated_at || item.published_at),
      });
    }
    return { routes };
  } catch {
    return { reason: "invalid-manifest" };
  }
}

function transcriptSiteUrl(transcriptUrl = "") {
  if (!transcriptUrl) return "";
  try {
    const parsed = new URL(transcriptUrl);
    const key = parsed.pathname.split("/").filter(Boolean).pop();
    if (!key) return "";
    return `${SITE_ORIGIN}/transcripts/${encodeURIComponent(decodeURIComponent(key))}`;
  } catch {
    return "";
  }
}

async function updateCurrentPodcastEntries(xml, context) {
  try {
    const { episodes } = await fetchPodcastEpisodes(context.env, context.request, 100);
    let current = xml;
    for (const episode of episodes) {
      if (!episode?.slug) continue;
      const lastmod = publishedDate(episode.published_at);
      current = appendUrlEntry(current, {
        loc: `${SITE_ORIGIN}/podcast/episodes/${encodeURIComponent(episode.slug)}/`,
        lastmod,
      });
      const transcriptLoc = transcriptSiteUrl(episode.transcript_url);
      if (transcriptLoc) current = appendUrlEntry(current, { loc: transcriptLoc, lastmod });
    }
    return current;
  } catch {
    // The static sitemap and governed route manifest remain valid if the RSS feed is temporarily unavailable.
    return xml;
  }
}

export async function onRequest(context) {
  const response = await context.next();
  const contentType = response.headers.get("content-type") || "";
  if (!response.ok || !contentType.includes("xml")) return response;

  let xml = await response.text();
  const blog = await loadPublishedBlogRoutes(context.env);
  if (blog.reason) {
    // An incomplete 200 sitemap would mask a publishing/storage incident.
    return new Response(JSON.stringify({ error: "sitemap unavailable", reason: blog.reason }), {
      status: 503,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "Retry-After": "60",
        "X-Blog-Sitemap-State": "unavailable",
      },
    });
  }
  xml = updateWeeklyArchiveEntry(xml, blog.routes.length > 0);
  for (const route of blog.routes) xml = appendUrlEntry(xml, route);
  xml = await updateDynamicRouteEntries(xml, context);
  xml = await updateCurrentPodcastEntries(xml, context);

  const headers = new Headers(response.headers);
  headers.set("cache-control", "public, max-age=300, s-maxage=300");
  headers.set("x-blog-archive-state", blog.routes.length > 0 ? "populated" : "empty");
  headers.set("x-blog-sitemap-source", "r2");
  headers.set("x-blog-posts-in-sitemap", String(blog.routes.length));
  headers.set("x-dynamic-route-manifest", "enabled");
  headers.set("x-podcast-rss-enrichment", "enabled");

  return new Response(xml, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
