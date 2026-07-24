const DEFAULT_BLOG_RSS_URL = "https://blog-rss.jonathan-harris.online/feed.xml";
const FALLBACK_SITE_ORIGIN = "https://jonathan-harris.online";

function escapeRegex(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function decodeXmlEntities(value) {
  return String(value || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&amp;/gi, "&")
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCharCode(parseInt(code, 16)));
}

function stripHtml(value) {
  return decodeXmlEntities(String(value || ""))
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function trimToLength(value, maxLength = 220) {
  const text = String(value || "").trim();
  if (!text || text.length <= maxLength) {
    return text;
  }

  const clipped = text.slice(0, maxLength - 1).replace(/[\s,;:.-]+$/g, "");
  return `${clipped}…`;
}

function getSiteOrigin(request) {
  try {
    return request ? new URL(request.url).origin : FALLBACK_SITE_ORIGIN;
  } catch {
    return FALLBACK_SITE_ORIGIN;
  }
}

function getFirstMatch(source, patterns) {
  for (const pattern of patterns) {
    const match = pattern.exec(source);
    if (match && match[1]) {
      return decodeXmlEntities(match[1]).trim();
    }
  }
  return "";
}

function getTagValue(source, tagNames) {
  const names = Array.isArray(tagNames) ? tagNames : [tagNames];
  const patterns = names.map((tagName) => new RegExp(`<${escapeRegex(tagName)}[^>]*>([\\s\\S]*?)<\\/${escapeRegex(tagName)}>`, "i"));
  return getFirstMatch(source, patterns);
}

function getAttributeValue(source, tagNames, attributeName = "url") {
  const names = Array.isArray(tagNames) ? tagNames : [tagNames];
  const patterns = names.map((tagName) => new RegExp(`<${escapeRegex(tagName)}\\b[^>]*\\s${escapeRegex(attributeName)}=(?:"([^"]+)"|'([^']+)')[^>]*>`, "i"));
  for (const pattern of patterns) {
    const match = pattern.exec(source);
    if (match) {
      return decodeXmlEntities(match[1] || match[2] || "").trim();
    }
  }
  return "";
}

function firstImageFromMarkup(markup) {
  const match = /<img\b[^>]*\ssrc=(?:"([^"]+)"|'([^']+)')[^>]*>/i.exec(String(markup || ""));
  return decodeXmlEntities(match ? match[1] || match[2] || "" : "").trim();
}

function canonicalBlogUrl(rawLink, request, slug) {
  const origin = getSiteOrigin(request);

  try {
    const url = new URL(String(rawLink || "").trim(), origin);
    if (slug && !/\/blog\/posts\//i.test(url.pathname)) {
      return `${origin}/blog/posts/${encodeURIComponent(slug)}/`;
    }

    if (slug) {
      return `${origin}/blog/posts/${encodeURIComponent(slug)}/`;
    }

    return url.toString();
  } catch {
    return slug ? `${origin}/blog/posts/${encodeURIComponent(slug)}/` : `${origin}/blog/`;
  }
}

function slugFromLink(rawLink) {
  const value = String(rawLink || "").trim();
  if (!value) {
    return "";
  }

  try {
    const url = new URL(value, FALLBACK_SITE_ORIGIN);
    const match = url.pathname.match(/\/blog\/posts\/([^/]+)\/?$/i);
    if (match && match[1]) {
      return decodeURIComponent(match[1]);
    }
    const lastSegment = url.pathname.split("/").filter(Boolean).pop() || "";
    return decodeURIComponent(lastSegment);
  } catch {
    const match = value.match(/\/blog\/posts\/([^/]+)\/?$/i);
    if (match && match[1]) {
      return decodeURIComponent(match[1]);
    }
    return "";
  }
}

function deriveWeekFromSlug(slug) {
  const match = String(slug || "").match(/^(\d{4})-w(\d{2})/i);
  if (!match) {
    return "";
  }
  return `${match[1]}-W${match[2]}`;
}

function isoWeekDateRangeLabel(slug, fallbackDate) {
  const match = String(slug || "").match(/^(\d{4})-w(\d{2})/i);
  if (!match) {
    return formatPublishedDate(fallbackDate);
  }

  const year = Number(match[1]);
  const week = Number(match[2]);
  if (!Number.isFinite(year) || !Number.isFinite(week) || week < 1 || week > 53) {
    return formatPublishedDate(fallbackDate);
  }

  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1 + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);

  return `${formatDateLabel(monday)} to ${formatDateLabel(sunday)}`;
}

function formatDateLabel(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function parseDate(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatPublishedDate(value) {
  const parsed = value instanceof Date ? value : parseDate(value);
  if (!parsed) {
    return "";
  }
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function extractEntries(xmlText) {
  const source = String(xmlText || "");
  const rssItems = source.match(/<item\b[\s\S]*?<\/item>/gi) || [];
  if (rssItems.length) {
    return rssItems.map((item) => ({ kind: "rss", xml: item }));
  }
  const atomEntries = source.match(/<entry\b[\s\S]*?<\/entry>/gi) || [];
  return atomEntries.map((entry) => ({ kind: "atom", xml: entry }));
}

function parseFeedEntry(entry, request) {
  const xml = entry.xml;
  const title = stripHtml(getTagValue(xml, ["title"])) || "Untitled";
  const bodyHtml = getTagValue(xml, ["content:encoded", "content", "description", "summary"]);
  const summaryText = trimToLength(
    stripHtml(getTagValue(xml, ["description", "summary"])) || stripHtml(bodyHtml),
    220
  );
  const link = entry.kind === "atom"
    ? getAttributeValue(xml, ["link"], "href") || getTagValue(xml, ["id", "link"])
    : getTagValue(xml, ["link", "guid"]);
  const slug = slugFromLink(link);
  const canonicalUrl = canonicalBlogUrl(link, request, slug);
  const publishedAt = getTagValue(xml, ["pubDate", "published", "updated", "dc:date"]);
  const imageUrl = getAttributeValue(xml, ["media:content", "media:thumbnail", "enclosure"], "url") || firstImageFromMarkup(bodyHtml);
  const parsedDate = parseDate(publishedAt);
  const dateLabel = isoWeekDateRangeLabel(slug, parsedDate);

  return {
    id: slug || canonicalUrl,
    week: deriveWeekFromSlug(slug),
    slug,
    title,
    summary: summaryText,
    excerpt: summaryText,
    body_html: bodyHtml || "",
    url: canonicalUrl,
    canonical_url: canonicalUrl,
    path: slug ? `/blog/posts/${slug}/` : "/blog/",
    image: imageUrl,
    image_url: imageUrl,
    date_label: dateLabel,
    published_at: parsedDate ? parsedDate.toISOString() : String(publishedAt || "").trim(),
    source_count: 0,
    sources: [],
  };
}

function uniqueBySlugOrUrl(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.slug || item.url || item.title;
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function toBlogManifest(xmlText, request) {
  const items = uniqueBySlugOrUrl(
    extractEntries(xmlText)
      .map((entry) => parseFeedEntry(entry, request))
      .filter((item) => item.slug && item.url)
      .sort((left, right) => {
        const leftTime = parseDate(left.published_at)?.getTime() || 0;
        const rightTime = parseDate(right.published_at)?.getTime() || 0;
        return rightTime - leftTime;
      })
  );

  return {
    schema_version: 1,
    updated_at: new Date().toISOString(),
    source_feed: DEFAULT_BLOG_RSS_URL,
    items,
  };
}

async function fetchBlogFeedManifest(request, feedUrl = DEFAULT_BLOG_RSS_URL) {
  const sourceUrl = new URL(feedUrl);
  // The weekly publisher updates this R2-backed object immediately before it
  // requests a website rebuild. Use a minute-bucket cache buster so Pages never
  // hydrates the manifest from an older CDN edge object while still avoiding a
  // unique origin request for every visitor.
  sourceUrl.searchParams.set("_jh_feed_bust", String(Math.floor(Date.now() / 60000)));

  const response = await fetch(sourceUrl.toString(), {
    cache: "no-store",
    headers: {
      Accept: "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
      "Cache-Control": "no-cache, no-store, max-age=0",
      Pragma: "no-cache",
    },
    cf: {
      cacheTtl: 0,
      cacheEverything: false,
    },
  });

  if (!response.ok) {
    throw new Error(`Blog RSS fetch failed: HTTP ${response.status}`);
  }

  const xmlText = await response.text();
  return toBlogManifest(xmlText, request);
}

export {
  DEFAULT_BLOG_RSS_URL,
  FALLBACK_SITE_ORIGIN,
  fetchBlogFeedManifest,
  formatPublishedDate,
  isoWeekDateRangeLabel,
  parseDate,
  stripHtml,
  toBlogManifest,
  trimToLength,
};
