import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";

const read = (path) => readFileSync(new URL("../" + path, import.meta.url), "utf8");
const css = read("assets/css/site.css");
const contact = read("contact/index.html");
const transcripts = read("transcripts/index.html");
const weekly = read("blog/weekly/index.html");
const topics = read("topics/index.html");
const newsletter = read("newsletter/index.html");
const catalogue = read("ebooks/index.html");
const podcast = read("podcast/index.html");

const before = (html, earlier, later) => {
  const a = html.indexOf(earlier);
  const b = html.indexOf(later);
  assert.ok(a >= 0 && b >= 0 && a < b, "Expected content-first document order");
};

test("contact flow precedes guidance and retains both form routes", () => {
  before(contact, 'aria-label="Contact form"', 'aria-label="Contact overview"');
  before(contact, 'aria-label="Contact form"', 'aria-label="Contact questions"');
  assert.match(contact, /id="JotFormIFrame-260281179574362"/);
  assert.match(contact, /https:\/\/form\.jotform\.com\/260281179574362/);
});

test("transcript search and fallback archive precede supplementary advice", () => {
  before(transcripts, 'id="episode-transcripts"', 'id="transcripts-answer-first"');
  assert.match(transcripts, /id="transcriptSearch"/);
  assert.match(transcripts, /id="transcriptList"/);
  assert.match(transcripts, /aria-live="polite"/);
  assert.match(transcripts, /podcast-rss-feeds\.jonathan-harris\.online/);
});

test("topics show guides immediately, preserving accessible how-to copy", () => {
  before(topics, 'class="ebook-index-intro topic-guides-intro"', 'aria-label="Topic guides"');
  assert.equal(topics.split('class="topic-guides-help"').length, 2);
  assert.match(topics, /<summary>How to use these guides<\/summary>/);
  assert.match(topics, /href="\/topics\/ai-for-beginners\/"/);
  const generator = read("scripts/ebook_pipeline.py");
  assert.match(generator, /class="ebook-index-intro topic-guides-intro"/);
  assert.match(generator, /class="topic-guides-help"/);
  assert.doesNotMatch(generator.slice(generator.indexOf("def render_topics_index"), generator.indexOf("def path_to_public_url")), /<h2>How to use this page<\/h2>/);
  assert.match(topics, /aria-label="Catalogue pages"/);
});

test("weekly archive search appears before explanatory sections without changing feed IDs", () => {
  before(weekly, 'aria-label="Weekly briefings archive"', 'aria-label="Weekly briefings overview"');
  before(weekly, 'aria-label="Weekly briefings archive"', 'id="weekly-answer-first"');
  assert.match(weekly, /<h2>Search weekly briefings<\/h2>/);
  for (const id of ["blogList", "blogStatus", "blogSearch", "blogLoadMore"]) {
    assert.equal(weekly.split('id="' + id + '"').length, 2, "Feed control must be unique: " + id);
  }
  assert.match(weekly, /BLOG_ARCHIVE_SEED_START/);
});

test("ebook cards match both server seed and live JavaScript renderer", () => {
  assert.match(catalogue, /id="booksGrid"/);
  assert.match(css, /body\.ebooks-catalogue #booksGrid>article\.card\{/);
  assert.match(css, /grid-template-columns:minmax\(0,110px\) minmax\(0,1fr\)/);
  assert.match(css, /body\.ebooks-catalogue #booksGrid>article\.card>\.cover/);
  assert.match(css, /body\.ebooks-catalogue #booksGrid>article\.card>:is\(p,\.tags,\.book-avail,\.actions,details\)/);
  assert.match(catalogue, /data-ebook-amazon/);
});

test("newsletter and podcast embeds survive shared editorial polish", () => {
  assert.match(newsletter, /id="JotFormIFrame-262733359026055"/);
  assert.match(newsletter, /href="\/downloads\/ai-glossary-cheat-sheet/);
  assert.match(css, /body\.page-newsletter main \.newsletter-page-shell/);
  assert.match(podcast, /class="podcast-player-frame"/);
  assert.match(podcast, /data-podcast-latest-server/);
  assert.match(css, /body\.page-podcast \.podcast-player-frame\{height:840px\}/);
});

test("new design consumes existing theme tokens and honours reduced motion", () => {
  const marker = "JH-PUBLICATION-SURFACES-2026";
  const at = css.indexOf(marker);
  assert.ok(at >= 0, "Publication design section missing");
  const block = css.slice(at);
  assert.doesNotMatch(block, /#[0-9a-fA-F]{3,8}\b|display:\s*none|visibility:\s*hidden/);
  assert.match(block, /var\(--season-accent,var\(--accent\)\)/);
  assert.match(block, /@media\(prefers-reduced-motion:reduce\)/);
});

test("all 40 book detail pages lead with cover and buying actions, before quick facts", () => {
  const dirs = readdirSync(new URL("../ebooks/", import.meta.url), { withFileTypes: true });
  let count = 0;
  for (const dir of dirs) {
    if (!dir.isDirectory()) continue;
    const path = new URL("../ebooks/" + dir.name + "/index.html", import.meta.url);
    if (!existsSync(path)) continue;
    const page = readFileSync(path, "utf8");
    if (!page.includes('<body class="ebook-detail"')) continue;
    before(page, '<section class="ebook-showcase">', '<section class="card ebook-section quick-facts">');
    assert.match(page, /class="cover ebook-showcase__cover"/, "Original cover must remain");
    assert.match(page, /data-placement="ebook_primary"/, "Original purchase route must remain");
    assert.match(page, /<h2>Quick facts<\/h2>/, "Existing factual content must remain");
    count++;
  }
  assert.equal(count, 40, "Every canonical book page must use the same content-first order");
  const validator = read("scripts/ebook_pipeline.py").split("TEMPLATE_ORDERED_MARKERS = [")[1]?.split("]")[0];
  assert.ok(validator, "Generated canonical page order is governed by a validator");
  before(validator, "'<section class=\"ebook-showcase\">'", "'<section class=\"card ebook-section quick-facts\">'");
});

test("automated publishing retains discoverable metadata on every canonical book page", () => {
  const dirs = readdirSync(new URL("../ebooks/", import.meta.url), { withFileTypes: true });
  let checked = 0;
  for (const dir of dirs) {
    if (!dir.isDirectory()) continue;
    const url = new URL("../ebooks/" + dir.name + "/index.html", import.meta.url);
    if (!existsSync(url)) continue;
    const page = readFileSync(url, "utf8");
    if (!page.includes('<body class="ebook-detail"')) continue;
    assert.match(page, /<title>[^<]+<\/title>/i, `Missing title: ${dir.name}`);
    assert.match(page, /<meta\s+name="description"\s+content="[^"]+"/i,
      `Missing description: ${dir.name}`);
    assert.match(page, /<link\s+rel="canonical"\s+href="https:\/\/[^"]+"/i,
      `Missing canonical: ${dir.name}`);
    assert.match(page, /<h1\b[^>]*>[^<]+<\/h1>/i, `Missing H1: ${dir.name}`);
    checked++;
  }
  assert.equal(checked, 40);
});

test("mobile catalogue remains scrollable without hiding topic filters", () => {
  assert.match(css, /body\.ebooks-catalogue #chips\s*\{[^}]*overflow-x:\s*auto/);
  assert.match(css, /body\.ebooks-catalogue #chips>\.chip\s*\{\s*flex:\s*0 0 auto/);
  assert.match(catalogue, /id="booksGrid"/);
});
