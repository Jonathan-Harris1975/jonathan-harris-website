#!/usr/bin/env node
/**
 * Snapshot the live blog RSS feed into the local fallback manifest and seed the
 * static blog surfaces with the latest saved links.
 *
 * The live site reads /blog/posts.json through a Pages Function that derives
 * the manifest from the RSS feed. This script keeps the repo snapshot and the
 * no-JS fallback HTML honest enough for CI and static source validation.
 *
 * Usage:
 *   BLOG_RSS_FEED_URL="https://blog-rss.jonathan-harris.online/feed.xml" node scripts/generate-blog-from-rss.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const DEFAULT_FEED_URL = "https://blog-rss.jonathan-harris.online/feed.xml";
const SITE_ORIGIN = "https://jonathan-harris.online";
const BLOG_RSS_FEED_URL = String(process.env.BLOG_RSS_FEED_URL || DEFAULT_FEED_URL).trim();
const BLOG_RSS_RETRY_ATTEMPTS = Math.max(1, Number(process.env.BLOG_RSS_RETRY_ATTEMPTS || 4));
const BLOG_RSS_RETRY_BASE_MS = Math.max(100, Number(process.env.BLOG_RSS_RETRY_BASE_MS || 750));
const BLOG_RSS_TIMEOUT_MS = Math.max(1000, Number(process.env.BLOG_RSS_TIMEOUT_MS || 15000));

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchTextWithRetry(url) {
  let lastError = null;
  for (let attempt = 1; attempt <= BLOG_RSS_RETRY_ATTEMPTS; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), BLOG_RSS_TIMEOUT_MS);
    try {
      const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const text = await response.text();
      if (!/<(?:item|entry)\b/i.test(text)) throw new Error('feed contains no item or entry nodes');
      return text;
    } catch (error) {
      lastError = error;
      if (attempt >= BLOG_RSS_RETRY_ATTEMPTS) break;
      const delay = BLOG_RSS_RETRY_BASE_MS * (2 ** (attempt - 1));
      console.warn(`Blog RSS attempt ${attempt}/${BLOG_RSS_RETRY_ATTEMPTS} failed (${error?.message || error}); retrying in ${delay}ms.`);
      await sleep(delay);
    } finally {
      clearTimeout(timeout);
    }
  }
  throw new Error(`Blog RSS sync failed after ${BLOG_RSS_RETRY_ATTEMPTS} attempts: ${lastError?.message || lastError || 'unknown error'}`);
}

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

function getTagValue(source, tagNames) {
  const names = Array.isArray(tagNames) ? tagNames : [tagNames];
  for (const tagName of names) {
    const pattern = new RegExp(`<${escapeRegex(tagName)}[^>]*>([\\s\\S]*?)<\\/${escapeRegex(tagName)}>`, "i");
    const match = pattern.exec(source);
    if (match && match[1]) {
      return decodeXmlEntities(match[1]).trim();
    }
  }
  return "";
}

function getAttributeValue(source, tagNames, attributeName = "url") {
  const names = Array.isArray(tagNames) ? tagNames : [tagNames];
  for (const tagName of names) {
    const pattern = new RegExp(`<${escapeRegex(tagName)}\\b[^>]*\\s${escapeRegex(attributeName)}=(?:"([^"]+)"|'([^']+)')[^>]*>`, "i");
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

function slugFromLink(rawLink) {
  const value = String(rawLink || "").trim();
  if (!value) {
    return "";
  }
  try {
    const url = new URL(value, SITE_ORIGIN);
    const match = url.pathname.match(/\/blog\/posts\/([^/]+)\/?$/i);
    if (match && match[1]) {
      return decodeURIComponent(match[1]);
    }
    return decodeURIComponent(url.pathname.split("/").filter(Boolean).pop() || "");
  } catch {
    const match = value.match(/\/blog\/posts\/([^/]+)\/?$/i);
    return match ? decodeURIComponent(match[1]) : "";
  }
}

function deriveWeekFromSlug(slug) {
  const match = String(slug || "").match(/^(\d{4})-w(\d{2})/i);
  return match ? `${match[1]}-W${match[2]}` : "";
}

function parseDate(value) {
  const parsed = new Date(String(value || "").trim());
  return Number.isNaN(parsed.getTime()) ? null : parsed;
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

function isoWeekDateRangeLabel(slug, fallbackDate) {
  const match = String(slug || "").match(/^(\d{4})-w(\d{2})/i);
  if (!match) {
    return fallbackDate ? formatDateLabel(fallbackDate) : "";
  }
  const year = Number(match[1]);
  const week = Number(match[2]);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1 + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  return `${formatDateLabel(monday)} to ${formatDateLabel(sunday)}`;
}

function extractEntries(xmlText) {
  const rssItems = String(xmlText || "").match(/<item\b[\s\S]*?<\/item>/gi) || [];
  if (rssItems.length) {
    return rssItems.map((xml) => ({ kind: "rss", xml }));
  }
  const atomEntries = String(xmlText || "").match(/<entry\b[\s\S]*?<\/entry>/gi) || [];
  return atomEntries.map((xml) => ({ kind: "atom", xml }));
}

function parseFeedEntry(entry) {
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
  const canonicalUrl = slug ? `${SITE_ORIGIN}/blog/posts/${encodeURIComponent(slug)}/` : link;
  const publishedAtRaw = getTagValue(xml, ["pubDate", "published", "updated", "dc:date"]);
  const publishedAt = parseDate(publishedAtRaw);
  const imageUrl = getAttributeValue(xml, ["media:content", "media:thumbnail", "enclosure"], "url") || firstImageFromMarkup(bodyHtml);

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
    date_label: isoWeekDateRangeLabel(slug, publishedAt),
    published_at: publishedAt ? publishedAt.toISOString() : String(publishedAtRaw || "").trim(),
    source_count: 0,
    sources: [],
  };
}

function uniqueItems(items) {
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

function buildManifest(xmlText) {
  const items = uniqueItems(
    extractEntries(xmlText)
      .map(parseFeedEntry)
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
    source_feed: BLOG_RSS_FEED_URL,
    items,
  };
}

function renderLatestSeed(item) {
  if (!item) {
    return '<article class="card jh-blog-card"><h3 class="jh-blog-card__title">No saved briefing yet</h3><p class="jh-blog-card__excerpt">Run the blog RSS sync again once the feed has at least one published item.</p></article>';
  }
  return `<article class="card jh-blog-card">\n          <p class="jh-blog-card__meta">${item.date_label || ''}</p>\n          <h3 class="jh-blog-card__title"><a href="${item.path}">${item.title}</a></h3>\n          <p class="jh-blog-card__excerpt">${item.summary || ''}</p>\n          <p><a class="button secondary" href="${item.path}">Read article</a></p>\n        </article>`;
}

function renderArchiveSeed(items) {
  const cards = items.slice(0, 4).map((item) => {
    const imageMarkup = item.image ? `<img alt="${item.title}" class="cover" decoding="async" loading="lazy" src="${item.image}"/>` : "";
    return `          <article class="card u-s05">\n            ${imageMarkup}\n            <div class="u-s06">\n              <div class="tag u-s07">${item.date_label || ''}</div>\n              <h2 class="u-s08">${item.title}</h2>\n              <p class="u-s09">${trimToLength(item.summary || '', 120)}</p>\n              <a class="button secondary" href="${item.path}">Read article</a>\n            </div>\n          </article>`;
  }).join("\n");
  return `<div class="grid">\n${cards}\n        </div>`;
}

function replaceBetween(text, startMarker, endMarker, replacement) {
  const pattern = new RegExp(`(${escapeRegex(startMarker)})([\\s\\S]*?)(${escapeRegex(endMarker)})`);
  return text.replace(pattern, `$1\n${replacement}\n        $3`);
}

function syncStaticSeeds(manifest) {
  const latest = manifest.items[0] || null;
  const latestStatus = latest ? 'Showing the latest published briefing.' : 'The latest weekly briefing appears here when the live feed updates.';
  const archiveStatus = manifest.items.length
    ? `Showing ${Math.min(4, manifest.items.length)} published weekly ${Math.min(4, manifest.items.length) === 1 ? 'briefing' : 'briefings'}.`
    : 'The archive updates as weekly briefings are published.';

  const blogIndexPath = path.join(repoRoot, 'blog', 'index.html');
  let blogIndex = fs.readFileSync(blogIndexPath, 'utf8');
  blogIndex = blogIndex.replace(/(<p class="subtle" id="blogStatus"[^>]*>)([\s\S]*?)(<\/p>)/, `$1${latestStatus}$3`);
  blogIndex = replaceBetween(blogIndex, '<!-- BLOG_LATEST_SEED_START -->', '<!-- BLOG_LATEST_SEED_END -->', renderLatestSeed(latest));
  fs.writeFileSync(blogIndexPath, blogIndex, 'utf8');

  const blogWeeklyPath = path.join(repoRoot, 'blog', 'weekly', 'index.html');
  let blogWeekly = fs.readFileSync(blogWeeklyPath, 'utf8');
  blogWeekly = blogWeekly.replace(/(<p class="subtle" id="blogStatus"[^>]*>)([\s\S]*?)(<\/p>)/, `$1${archiveStatus}$3`);
  blogWeekly = replaceBetween(blogWeekly, '<!-- BLOG_ARCHIVE_SEED_START -->', '<!-- BLOG_ARCHIVE_SEED_END -->', renderArchiveSeed(manifest.items));
  fs.writeFileSync(blogWeeklyPath, blogWeekly, 'utf8');
}

async function main() {
  if (!BLOG_RSS_FEED_URL) {
    throw new Error('BLOG_RSS_FEED_URL is missing.');
  }

  const xmlText = await fetchTextWithRetry(BLOG_RSS_FEED_URL);
  const snapshot = buildManifest(xmlText);
  if (!snapshot.items.length) {
    throw new Error('Blog RSS parsed successfully but produced zero publishable posts.');
  }
  const outPath = path.join(repoRoot, 'blog', 'posts.json');
  fs.writeFileSync(outPath, JSON.stringify(snapshot, null, 2) + '\n', 'utf8');
  syncStaticSeeds(snapshot);

  console.log(`Synced ${snapshot.items.length} published blog ${snapshot.items.length === 1 ? 'entry' : 'entries'} from ${BLOG_RSS_FEED_URL}`);
  console.log(`Updated ${outPath}`);
  console.log('Updated static blog seeds in blog/index.html and blog/weekly/index.html');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
