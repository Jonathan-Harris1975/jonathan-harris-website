import { getPublicationState, getWeeklyArchiveUrl } from "./blog/_utils/blog-publication.js";

const MANIFEST_PATH = "/blog/posts.json";

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

export async function onRequest(context) {
  const response = await context.next();
  const contentType = response.headers.get("content-type") || "";

  if (!response.ok || !contentType.includes("xml")) {
    return response;
  }

  const xml = await response.text();
  const publication = await getPublicationState(context.request, MANIFEST_PATH);
  const headers = new Headers(response.headers);
  headers.set("cache-control", "public, max-age=300, s-maxage=300");
  headers.set("x-blog-archive-state", publication.hasItems ? "populated" : "empty");

  return new Response(updateWeeklyArchiveEntry(xml, publication.hasItems), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
