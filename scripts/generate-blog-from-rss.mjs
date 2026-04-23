#!/usr/bin/env node
/**
 * Historical name aside, this script no longer fabricates blog posts from RSS.
 *
 * It snapshots the live weekly blog publication manifest into blog/posts.json so
 * the repo keeps a sane local fallback while the site itself reads the same-
 * origin live manifest via Pages Functions.
 *
 * Usage:
 *   BLOG_MANIFEST_URL="https://blog.jonathan-harris.online/blog/posts.json" node scripts/generate-blog-from-rss.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");

const DEFAULT_MANIFEST_URL = "https://blog.jonathan-harris.online/blog/posts.json";
const SITE_ORIGIN = "https://jonathan-harris.online";
const BLOG_MANIFEST_URL = String(process.env.BLOG_MANIFEST_URL || DEFAULT_MANIFEST_URL).trim();

function trimSlashes(value) {
  return String(value || "").replace(/^\/+|\/+$/g, "");
}

function mapImageToMainDomain(value) {
  const raw = String(value || "").trim();
  if (!raw) return raw;

  if (raw.startsWith(`${SITE_ORIGIN}/blog/images/`)) {
    return raw;
  }

  if (raw.startsWith("/blog/images/")) {
    return `${SITE_ORIGIN}${raw}`;
  }

  try {
    const url = new URL(raw);
    if (url.origin === SITE_ORIGIN && url.pathname.startsWith("/blog/images/")) {
      return url.toString();
    }
    if (url.hostname.includes("blog-images") || url.hostname.endsWith(".r2.dev")) {
      const key = trimSlashes(url.pathname);
      return key ? `${SITE_ORIGIN}/blog/images/${key}` : raw;
    }
    return raw;
  } catch {
    const key = trimSlashes(raw);
    return key ? `${SITE_ORIGIN}/blog/images/${key}` : raw;
  }
}

function normaliseEntry(item) {
  const slug = trimSlashes(item?.slug || "");
  const pathName = slug ? `/blog/posts/${slug}/` : String(item?.path || "/blog/");
  const postUrl = `${SITE_ORIGIN}${pathName}`;
  const imageUrl = mapImageToMainDomain(item?.image_url || item?.image || "");

  return {
    ...item,
    path: pathName,
    url: postUrl,
    canonical_url: postUrl,
    image: imageUrl || item?.image || "",
    image_url: imageUrl || item?.image_url || "",
  };
}

async function main() {
  if (!BLOG_MANIFEST_URL) {
    throw new Error("BLOG_MANIFEST_URL is missing.");
  }

  const response = await fetch(BLOG_MANIFEST_URL, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Manifest fetch failed: HTTP ${response.status}`);
  }

  const payload = await response.json();
  const items = Array.isArray(payload?.items) ? payload.items.map(normaliseEntry) : [];
  const snapshot = {
    ...payload,
    schema_version: Number(payload?.schema_version || 1),
    synced_at: new Date().toISOString(),
    source_manifest: BLOG_MANIFEST_URL,
    items,
  };

  const outPath = path.join(repoRoot, "blog", "posts.json");
  fs.writeFileSync(outPath, JSON.stringify(snapshot, null, 2) + "\n", "utf8");

  console.log(`Synced ${items.length} published blog entr${items.length === 1 ? "y" : "ies"} from ${BLOG_MANIFEST_URL}`);
  console.log(`Updated ${outPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
