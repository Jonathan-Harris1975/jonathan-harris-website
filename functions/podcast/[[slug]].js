const DEFAULT_PODCAST_FEED_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

function slugPartsFromParams(params) {
  const raw = Array.isArray(params?.slug) ? params.slug.join("/") : String(params?.slug || "");
  return raw.replace(/^\/+|\/+$/g, "");
}

function cleanText(value = "") {
  return String(value || "")
    .replace(/<!\[CDATA\[|\]\]>/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function tagValue(xml = "", tagName = "") {
  const escaped = tagName.replace(/[-/:]/g, "\\$&");
  const re = new RegExp(`<${escaped}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escaped}>`, "i");
  return cleanText(xml.match(re)?.[1] || "");
}

function attrValue(node = "", attr = "") {
  const re = new RegExp(`${attr}=["']([^"']+)["']`, "i");
  return cleanText(node.match(re)?.[1] || "");
}

function normaliseUrl(value = "", request) {
  const raw = cleanText(value);
  if (!raw) return "";
  try { return new URL(raw, request.url).toString(); } catch { return ""; }
}

function parseItems(xml = "", request) {
  return (String(xml || "").match(/<item>[\s\S]*?<\/item>/gi) || []).map((item) => {
    const enclosureNode = item.match(/<enclosure\b[^>]*>/i)?.[0] || "";
    const transcriptNode = item.match(/<podcast:transcript\b[^>]*>/i)?.[0] || "";
    return {
      link: normaliseUrl(tagValue(item, "link"), request),
      guid: tagValue(item, "guid"),
      audioUrl: normaliseUrl(attrValue(enclosureNode, "url"), request),
      transcriptUrl: normaliseUrl(attrValue(transcriptNode, "url"), request),
    };
  });
}

async function fetchFeed(context) {
  const configured = context.env?.PODCAST_RSS_FEED_URL || context.env?.R2_PUBLIC_BASE_URL_PODCAST_RSS || DEFAULT_PODCAST_FEED_URL;
  const feedUrl = String(configured || "").endsWith(".xml") ? configured : `${String(configured || "").replace(/\/$/, "")}/turing-torch.xml`;
  const response = await fetch(feedUrl, { headers: { Accept: "application/rss+xml, application/xml, text/xml" } });
  if (!response.ok) throw new Error(`Podcast feed fetch failed: ${response.status}`);
  return await response.text();
}

export async function onRequest(context) {
  const slug = slugPartsFromParams(context.params);
  if (!/^TT-\d{4}-\d{2}-\d{2}\/?$/i.test(slug)) {
    return context.next();
  }

  try {
    const xml = await fetchFeed(context);
    const match = parseItems(xml, context.request).find((item) => {
      const haystack = `${item.guid} ${item.audioUrl} ${item.transcriptUrl}`;
      return haystack.includes(slug.replace(/\/$/, ""));
    });
    if (match?.link) {
      return Response.redirect(match.link, 301);
    }
  } catch {}

  return Response.redirect(new URL("/podcast/", context.request.url).toString(), 301);
}
