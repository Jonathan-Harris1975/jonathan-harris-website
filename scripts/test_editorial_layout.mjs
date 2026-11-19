import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../assets/css/site.css", import.meta.url), "utf8");
const home = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const blog = readFileSync(new URL("../blog/index.html", import.meta.url), "utf8");
const podcast = readFileSync(new URL("../podcast/index.html", import.meta.url), "utf8");

test("editorial desktop homepage retains both columns and existing publishing journeys", () => {
  assert.match(css, /@media\(min-width:1000px\)/);
  assert.match(css, /body\.page-home \.hero--home \.hero-logo-stage\{display:grid;grid-template-columns:/);
  assert.match(css, /body\.page-home \.hero--home \.home-intent\{grid-column:2;/);
  assert.match(css, /body\.page-home \.hero--home #home-newsletter-hero\{grid-column:2;/);
  for (const href of ["/book-finder/", "/newsletter/", "/podcast/", "/topics/ai-for-beginners/"]) {
    assert.ok(home.includes(href), `Existing visitor journey missing: ${href}`);
  }
});
test("latest live briefing remains before the evergreen explanation, without losing the RSS renderer", () => {
  const latest = blog.indexOf('aria-label="Latest weekly posts"');
  const explanation = blog.indexOf('aria-labelledby="blog-answer-first"');
  const status = blog.indexOf('id="blogStatus"');
  const renderer = blog.indexOf('id="blogList"');
  assert.ok(latest >= 0 && explanation > latest && status > latest && renderer > latest);
  assert.equal(blog.split('id="blogList"').length, 2, "One live RSS list only");
  assert.match(css, /body\.page-blog \.main>\.wrap>\.answer-first\{/);
});
test("podcast player and original transcripts remain while intro is visually de-emphasised", () => {
  assert.match(podcast, /referrerpolicy="no-referrer" src="https:\/\/podcast-coverart\.jonathan-harris\.online\//);
  assert.match(podcast, /aria-label="Podcast player"/);
  assert.match(podcast, /href="\/transcripts\/"/);
  assert.match(css, /body\.page-podcast \.podcast-main>\.answer-first\{/);
});
test("editorial composition cannot introduce new hard-coded colours or hidden controls", () => {
  const start = css.indexOf("JH-EDITORIAL-COMPOSITION-2026");
  assert.ok(start > 0);
  const block = css.slice(start);
  assert.doesNotMatch(block, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(block, /display:\s*none|visibility:\s*hidden/i);
  assert.match(block, /var\(--border\)/);
  assert.match(css, /\.home-intent a\{[^}]*min-height:44px/);
});
