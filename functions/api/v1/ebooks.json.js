const PUBLIC_COLUMNS = `
  ebook_id, slug, title, short_description, description, summary, topic,
  tags_json, keywords_json, audience, who_for, what_book_covers,
  what_youll_learn_json, why_it_matters, tone, author, identifier,
  asin, page_count, publication_date, book_url, buy_now_url, redirect_url,
  cover_art_url, legacy_alias_url
`;

// Reject unverified records and links that are not an exact Amazon UK print ASIN.
export function publicPrintFormat(row) {
  if (row?.state !== "live_verified" || !["paperback", "hardcover"].includes(row?.format)) return null;
  const asin = String(row.print_asin || "").trim().toUpperCase();
  const isbn = String(row.isbn || "").trim();
  const verifiedAt = String(row.verified_at || "").trim();
  if (!/^[A-Z0-9]{10}$/.test(asin) || !/^\d{13}$/.test(isbn) || !Number.isFinite(Date.parse(verifiedAt))) return null;
  try {
    const url = new URL(String(row.purchase_url || ""));
    if (url.protocol !== "https:" || !["amazon.co.uk", "www.amazon.co.uk"].includes(url.hostname)) return null;
    if (!new RegExp("^/(?:dp|gp/product)/" + asin + "(?:/|$)", "i").test(url.pathname)) return null;
    return { format: row.format, isbn, asin, purchase_url: url.toString(), verified_at: verifiedAt };
  } catch { return null; }
}

function parseList(value) {
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function slugify(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function toWebsiteRecord(row) {
  const topicSlug = slugify(row.topic);
  const buyRoute = `/ebooks/${row.slug}/buy-now`;
  return {
    id: row.ebook_id,
    key: `${row.ebook_id}-ebook`,
    slug: row.slug,
    title: row.title,
    short: row.short_description,
    short_description: row.short_description,
    description: row.description,
    summary: row.summary,
    topic: row.topic,
    topic_slug: topicSlug,
    topic_url: topicSlug ? `/catalogue/${topicSlug}/` : "",
    filter: row.topic,
    tags: parseList(row.tags_json),
    keywords: parseList(row.keywords_json),
    audience: row.audience,
    who_for: row.who_for,
    what_this_book_covers: row.what_book_covers,
    what_youll_learn: parseList(row.what_youll_learn_json),
    why_it_matters: row.why_it_matters,
    tone: row.tone,
    author: row.author,
    identifier: row.identifier,
    asin: row.asin,
    pages: row.page_count,
    datePublished: row.publication_date,
    book_url: row.book_url,
    canonical_url: row.book_url,
    buy_url: row.redirect_url,
    buy_route: buyRoute,
    buy_route_full: row.buy_now_url,
    cover: row.cover_art_url,
    main_image: row.cover_art_url,
    image: row.cover_art_url,
    legacy_alias_url: row.legacy_alias_url
  };
}

export async function onRequestGet({ env }) {
  try {
    const result = await env.KDP_DB
      .prepare(`SELECT ${PUBLIC_COLUMNS} FROM ebooks ORDER BY ebook_id`)
      .all();
    const books = (result.results || []).map(toWebsiteRecord);
    // The table is introduced by migration 0002; an unapplied migration must
    // not take down the original 40 Kindle book listings.
    let editions = [];
    try {
      const print = await env.KDP_DB.prepare(
        "SELECT ebook_id, format, state, isbn, print_asin, purchase_url, verified_at FROM kdp_print_editions WHERE state = 'live_verified'"
      ).all();
      editions = print.results || [];
    } catch (error) {
      console.warn("KDP print format catalogue unavailable; preserving Kindle listings.", error);
    }
    const byEbookId = new Map();
    for (const row of editions) {
      const verified = publicPrintFormat(row);
      if (!verified) continue;
      const formats = byEbookId.get(Number(row.ebook_id)) || {};
      formats[verified.format] = verified;
      byEbookId.set(Number(row.ebook_id), formats);
    }
    for (const book of books) book.print_formats = byEbookId.get(Number(book.id)) || {};

    return Response.json(
      { books },
      {
        headers: {
          "Cache-Control": "public, max-age=300, s-maxage=300",
          "X-Content-Type-Options": "nosniff"
        }
      }
    );
  } catch (err) {
    console.error("KDP D1 ebook catalogue query failed", err);
    return Response.json(
      { error: "Ebook catalogue is temporarily unavailable." },
      {
        status: 503,
        headers: {
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff"
        }
      }
    );
  }
}
