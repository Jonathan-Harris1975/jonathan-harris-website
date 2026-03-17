#!/usr/bin/env node
/**
 * generate-blog-from-rss.mjs
 * - Fetches RSS (default: podcast RSS already referenced by the site)
 * - Creates /blog/posts/<yyyy-mm-dd>-<slug>/index.html
 * - Creates /blog/posts.json for publishing to R2_PUBLIC_BASE_URL_BLOG
 *
 * Usage:
 *   RSS_URL="https://example.com/feed.xml" node scripts/generate-blog-from-rss.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const repoRoot = path.resolve(__dirname, "..");
const cfgPath = path.join(repoRoot, "assets", "js", "blog-config.js");
const cfgText = fs.readFileSync(cfgPath, "utf8");

// Extract defaults from blog-config.js without eval
function extract(key){
  const re = new RegExp(key + ":\\s*\"([^\"]+)\"");
  const m = cfgText.match(re);
  return m ? m[1] : "";
}

const DEFAULT_RSS = extract("RSS_URL");
const R2_BLOG = extract("R2_PUBLIC_BASE_URL_BLOG");
const R2_IMG = extract("R2_PUBLIC_BASE_URL_BLOG_IMAGES");

const RSS_URL = process.env.RSS_URL || DEFAULT_RSS;
if (!RSS_URL){
  console.error("RSS_URL missing. Set RSS_URL env var or blog-config.js RSS_URL.");
  process.exit(1);
}

const MAX_ITEMS = Number(process.env.MAX_ITEMS || 20);

function slugify(s){
  return (s||"")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function stripHtml(s){
  return (s||"").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

function escapeHtml(s){
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function parseRss(xml){
  // Minimal RSS parsing via regex for portability (no deps)
  const items = [];
  const parts = xml.split(/<item>/i).slice(1);
  for (const part of parts){
    const chunk = part.split(/<\/item>/i)[0] || "";
    const get = (tag) => {
      const m = chunk.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
      return m ? m[1].trim() : "";
    };
    const title = stripHtml(get("title"));
    const link = stripHtml(get("link"));
    const pubDate = stripHtml(get("pubDate"));
    const descriptionRaw = get("description");
    const description = stripHtml(descriptionRaw);
    const enclosure = (chunk.match(/<enclosure[^>]*url="([^"]+)"/i)||[])[1] || "";
    const itImg = (chunk.match(/itunes:image[^>]*href="([^"]+)"/i)||[])[1] || "";
    items.push({ title, link, pubDate, description, image: enclosure || itImg });
    if (items.length >= MAX_ITEMS) break;
  }
  return items;
}

function loadTemplate(){
  const p = path.join(repoRoot, "blog", "_templates", "post.html");
  return fs.readFileSync(p, "utf8");
}

function applyTemplate(tpl, vars){
  return tpl.replace(/\{\{([A-Z0-9_]+)\}\}/g, (_, k) => (vars[k] ?? ""));
}

function isoDate(d){
  const dt = d instanceof Date ? d : new Date(d);
  if (Number.isNaN(dt.getTime())) return new Date().toISOString().slice(0,10);
  return dt.toISOString().slice(0,10);
}

function humanDate(d){
  const dt = d instanceof Date ? d : new Date(d);
  if (Number.isNaN(dt.getTime())) return isoDate(new Date());
  return dt.toLocaleDateString("en-GB", { year:"numeric", month:"long", day:"numeric" });
}

async function main(){
  const res = await fetch(RSS_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`RSS fetch failed: HTTP ${res.status}`);
  const xml = await res.text();
  const items = parseRss(xml);

  const tpl = loadTemplate();
  const postsDir = path.join(repoRoot, "blog", "posts");
  fs.mkdirSync(postsDir, { recursive: true });

  const manifest = { generated_utc: new Date().toISOString(), source_rss: RSS_URL, items: [] };

  for (const it of items){
    const published = isoDate(it.pubDate);
    const slug = `${published}-${slugify(it.title) || "post"}`;
    const outDir = path.join(postsDir, slug);
    fs.mkdirSync(outDir, { recursive: true });

    const canonical = `https://jonathan-harris.online/blog/posts/${slug}/`;
    const desc = (it.description || "").slice(0, 160) || "Weekly AI insight from Jonathan Harris — clear thinking, real-world context, no hype.";

    const image = it.image || "https://images.jonathan-harris.online/newsletter-img";

    const content = `
      <p><strong>Source:</strong> <a href="${escapeHtml(it.link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(it.link || "RSS item")}</a></p>
      <p>${escapeHtml(it.description || desc)}</p>
      <p class="muted">If you’re seeing this early: this post was generated from RSS. The editorial rewrite stage plugs in next.</p>
    `.trim();

    const html = applyTemplate(tpl, {
      TITLE: it.title || "Untitled",
      DESCRIPTION: desc,
      CANONICAL: canonical,
      IMAGE: image,
      PUBLISHED: published,
      MODIFIED: published,
      PUBLISHED_HUMAN: humanDate(it.pubDate),
      CONTENT: content
    });

    fs.writeFileSync(path.join(outDir, "index.html"), html, "utf8");

    manifest.items.push({
      title: it.title,
      link: canonical,
      pubDate: it.pubDate,
      desc: desc,
      image: it.image ? it.image : `${R2_IMG}/placeholder.webp`,
      source: it.link
    });
  }

  fs.writeFileSync(path.join(repoRoot, "blog", "posts.json"), JSON.stringify(manifest, null, 2), "utf8");

  console.log(`Generated ${manifest.items.length} posts.`);
  console.log(`Publish blog/posts/ and blog/posts.json to ${R2_BLOG} (and images to ${R2_IMG}).`);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
