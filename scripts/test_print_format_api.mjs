import test from "node:test";
import assert from "node:assert/strict";
import { onRequestGet, publicPrintFormat } from "../functions/api/v1/ebooks.json.js";

const books = Array.from({ length: 40 }, (_, index) => ({
  ebook_id: index + 1,
  slug: "book-" + (index + 1),
  title: "Book " + (index + 1),
  author: "Test Author",
  asin: "B0" + String(index + 1).padStart(8, "0"),
  tags_json: "[]",
  keywords_json: "[]",
  what_youll_learn_json: "[]",
  topic: "AI",
  page_count: 200,
}));

const paperback = {
  ebook_id: 1,
  format: "paperback",
  state: "live_verified",
  isbn: "9780306406157",
  print_asin: "B012345678",
  purchase_url: "https://www.amazon.co.uk/dp/B012345678",
  verified_at: "2026-11-17T00:00:00Z",
  internal_kdp_id: "must-never-leak",
  internal_r2_key: "must-never-leak",
};
const hardcover = {
  ...paperback,
  format: "hardcover",
  isbn: "9780306406164",
  print_asin: "B098765432",
  purchase_url: "https://www.amazon.co.uk/dp/B098765432",
};

function mockEnv({ editions = [], printTableMissing = false, catalogueError = false } = {}) {
  return {
    KDP_DB: {
      prepare(sql) {
        return {
          async all() {
            if (sql.includes("FROM ebooks")) {
              if (catalogueError) throw new Error("private database credentials");
              return { results: books };
            }
            if (sql.includes("FROM kdp_print_editions")) {
              if (printTableMissing) throw new Error("no such table: kdp_print_editions");
              return { results: editions };
            }
            throw new Error("Unexpected SQL query");
          },
        };
      },
    },
  };
}

test("40 Kindle records stay available with no verified print editions, never cache availability", async () => {
  const response = await onRequestGet({ env: mockEnv() });
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(payload.books.length, 40);
  assert.equal(payload.books[0].slug, "book-1");
  assert.equal(payload.books[39].slug, "book-40");
  assert.deepEqual(payload.books[0].print_formats, {});
});

test("only identity-matched live print options appear, without private KDP identifiers", async () => {
  const response = await onRequestGet({
    env: mockEnv({ editions: [
      paperback,
      hardcover,
      { ...paperback, format: "paperback", state: "submitted" },
    ] }),
  });
  const payload = await response.json();
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(Object.keys(payload.books[0].print_formats).sort(), ["hardcover", "paperback"]);
  assert.deepEqual(payload.books[1].print_formats, {});
  const publicRow = payload.books[0].print_formats.paperback;
  assert.equal(publicRow.purchase_url, paperback.purchase_url);
  assert.equal(publicRow.asin, paperback.print_asin);
  assert.doesNotMatch(JSON.stringify(payload), /must-never-leak/);
});

test("reject non-live, unverified, Kindle-reused and off-site print purchase data", () => {
  const kindleAsin = books[0].asin;
  assert.equal(publicPrintFormat({ ...paperback, state: "submitted" }, kindleAsin), null);
  assert.equal(publicPrintFormat({ ...paperback, verified_at: null }, kindleAsin), null);
  assert.equal(publicPrintFormat({ ...paperback, print_asin: kindleAsin }, kindleAsin), null);
  assert.equal(publicPrintFormat({ ...paperback, purchase_url: "https://example.com/dp/B012345678" }, kindleAsin), null);
  assert.equal(publicPrintFormat({ ...paperback, purchase_url: "https://amazon.co.uk/dp/B012345679" }, kindleAsin), null);
  assert.equal(publicPrintFormat({ ...paperback, purchase_url: "http://amazon.co.uk/dp/B012345678" }, kindleAsin), null);
});

test("format revocation immediately disappears on next request", async () => {
  const active = await (await onRequestGet({ env: mockEnv({ editions: [paperback] }) })).json();
  const revoked = await onRequestGet({ env: mockEnv({ editions: [{ ...paperback, state: "unavailable" }] }) });
  const after = await revoked.json();
  assert.ok(active.books[0].print_formats.paperback);
  assert.deepEqual(after.books[0].print_formats, {});
  assert.equal(revoked.headers.get("cache-control"), "no-store");
});

test("unapplied print migration does not break all 40 Kindle listings", async () => {
  const response = await onRequestGet({ env: mockEnv({ printTableMissing: true }) });
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(payload.books.length, 40);
  assert.deepEqual(payload.books[0].print_formats, {});
});

test("private catalogue failure returns no-store 503 without leaking provider details", async () => {
  const response = await onRequestGet({ env: mockEnv({ catalogueError: true }) });
  const payload = await response.json();
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.doesNotMatch(JSON.stringify(payload), /private database credentials/);
});
