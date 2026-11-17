import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { onRequestGet } from "../functions/api/v1/books.json.js";

const legacy = JSON.parse(readFileSync(new URL("../api/v1/books.json", import.meta.url)));
function fixtureRow(book) {
  return {
    ebook_id: book.id, slug: book.slug, title: book.title, short_description: book.short,
    topic: book.filter, tags_json: JSON.stringify(book.tags), keywords_json: JSON.stringify(book.keywords),
    asin: book.asin, page_count: book.pages, publication_date: book.datePublished,
    updated_at: book.dateModified, book_url: book.canonical_url,
    buy_now_url: book.buy_route_full, redirect_url: book.buy_url, cover_art_url: book.cover,
    manuscript_r2_key: "PRIVATE_R2_DO_NOT_LEAK",
  };
}
function envFor(rows, fail=false) {
  return { KDP_DB: { prepare(sql) { return { async all() {
    if (sql.includes("FROM ebooks")) {
      if (fail) throw new Error("Private database connection details");
      return { results: rows };
    }
    if (sql.includes("FROM kdp_print_editions")) return { results: [] };
    throw new Error("Unexpected query");
  } }; } } };
}
async function responseFor(rows = legacy.map(fixtureRow), fail=false) {
  const response = await onRequestGet({ env: envFor(rows, fail) });
  return { response, body: await response.json() };
}
test("full 40-book legacy field and ranking contract equals governed snapshot", async () => {
  const { response, body } = await responseFor();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(body, legacy);
  assert.doesNotMatch(JSON.stringify(body), /PRIVATE_R2_DO_NOT_LEAK|print_formats/);
});
test("D1 page-count updates show immediately without a stale static fallback", async () => {
  const rows = legacy.map(fixtureRow);
  rows[6].page_count = 185;
  assert.equal((await responseFor(rows)).body[6].pages, 185);
  rows[6].page_count = 201;
  assert.equal((await responseFor(rows)).body[6].pages, 201);
});
test("D1 redirect URL and update timestamp map to existing legacy fields", async () => {
  const rows = legacy.map(fixtureRow);
  rows[0].redirect_url = "https://mybook.to/new-d1-target";
  rows[0].updated_at = "2026-11-17 02:15:41";
  const { body } = await responseFor(rows);
  assert.equal(body[0].buy_url, rows[0].redirect_url);
  assert.equal(body[0].buy_target_url, rows[0].redirect_url);
  assert.equal(body[0].dateModified, "2026-11-17T02:15:41Z");
});
test("unavailable D1 and invalid required fields fail closed, without credential leaks", async () => {
  const unavailable = await responseFor(legacy.map(fixtureRow), true);
  assert.equal(unavailable.response.status, 503);
  assert.equal(unavailable.response.headers.get("Cache-Control"), "no-store");
  assert.doesNotMatch(JSON.stringify(unavailable.body), /Private database connection details/);
  for (const change of [{short_description: ""},{updated_at: null},{page_count: null}]) {
    const rows = legacy.map(fixtureRow);
    Object.assign(rows[0], change);
    const outcome = await responseFor(rows);
    assert.equal(outcome.response.status, 503);
    assert.equal(outcome.response.headers.get("Cache-Control"), "no-store");
  }
});
