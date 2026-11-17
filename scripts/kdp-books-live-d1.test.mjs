import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet } from "../functions/api/v1/books.json.js";

test("legacy books.json is sourced from current D1 data and cannot retain a static page count", async () => {
  const env = { KDP_DB: { prepare(sql) {
    return { async all() {
      if (sql.includes("FROM kdp_print_editions")) return { results: [] };
      return { results: [{ ebook_id: 7, slug: "the-artificial-intelligence-revolution-from-algorithms-to-consciousness", title: "The Artificial Intelligence Revolution: From Algorithms to Consciousness", page_count: 185, asin: "B012345678", topic: "AI" }] };
    } };
  } } };
  const response = await onRequestGet({ env });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  const books = await response.json();
  assert.ok(Array.isArray(books));
  assert.equal(books[0].pages, 185);
  assert.equal(books[0].id, 7);
});

test("legacy books.json fails closed when D1 cannot be read", async () => {
  const response = await onRequestGet({ env: { KDP_DB: { prepare() { throw new Error("D1 unavailable"); } } } });
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});
