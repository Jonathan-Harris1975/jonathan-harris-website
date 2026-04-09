const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "public, max-age=3600, s-maxage=3600",
};

function featuredRotationSelection(now = new Date()) {
  const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const isoYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const isoWeek = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return {
    method: "iso_week_rotation",
    iso_week: isoWeek,
    year: isoYear,
  };
}

function selectFeaturedBookRecord(records, now = new Date()) {
  const selection = featuredRotationSelection(now);
  if (!Array.isArray(records) || records.length === 0) {
    return { book: null, selection };
  }
  return {
    book: records[selection.iso_week % records.length] || null,
    selection,
  };
}

function cleanText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function buildPodcastSponsor(book) {
  if (!book || typeof book !== "object") {
    return {
      label: "This week's sponsor",
      headline: "",
      cta: "",
      midroll_15: "",
      midroll_30: "",
    };
  }

  const title = cleanText(book.title);
  const short = cleanText(book.short);
  const topic = cleanText(book.filter);
  const canonicalUrl = cleanText(book.canonical_url);
  const buyRouteFull = cleanText(book.buy_route_full);
  const pages = Number.isFinite(book.pages) ? book.pages : null;
  const tags = Array.isArray(book.tags) ? book.tags.map(cleanText).filter(Boolean).slice(0, 3) : [];
  const shortSentence = short ? (/[.!?]$/.test(short) ? short : `${short}.`) : "";
  const topicSentence = topic ? ` It focuses on ${topic}.` : "";
  const pageSentence = pages && pages > 0 ? ` It runs ${pages} pages.` : "";
  const tagsSentence = tags.length ? ` Topics include ${tags.join(", ")}.` : "";

  return {
    label: "This week's sponsor",
    headline: `This week's sponsor is ${title}`,
    cta: `See the book at ${canonicalUrl} or buy on Amazon at ${buyRouteFull}`,
    midroll_15: `This week's sponsor is ${title}. ${shortSentence} Read more at ${canonicalUrl}`.replace(/\s+/g, " ").trim(),
    midroll_30: (
      `This week's sponsor is ${title}. ${shortSentence}${topicSentence}${pageSentence}${tagsSentence} ` +
      `See the full book page at ${canonicalUrl} or go straight to Amazon at ${buyRouteFull}.`
    ).replace(/\s+/g, " ").trim(),
  };
}

function buildFeaturedBookPayload(records, now = new Date()) {
  const { book, selection } = selectFeaturedBookRecord(records, now);
  return {
    version: "v1",
    selection,
    book: book || {},
    podcast_sponsor: buildPodcastSponsor(book),
  };
}

async function fetchBooksResponse(context) {
  const booksUrl = new URL("/api/v1/books.json", context.request.url);
  const request = new Request(booksUrl.toString(), {
    headers: { Accept: "application/json" },
  });

  if (context.env && context.env.ASSETS && typeof context.env.ASSETS.fetch === "function") {
    return context.env.ASSETS.fetch(request);
  }
  return fetch(request);
}

export async function onRequest(context) {
  try {
    const booksResponse = await fetchBooksResponse(context);
    if (!booksResponse.ok) {
      return new Response(
        JSON.stringify({ error: `Unable to load catalogue source: HTTP ${booksResponse.status}` }),
        { status: 502, headers: JSON_HEADERS },
      );
    }

    const books = await booksResponse.json();
    if (!Array.isArray(books) || books.length === 0) {
      return new Response(JSON.stringify({ error: "Catalogue source is empty or invalid" }), {
        status: 502,
        headers: JSON_HEADERS,
      });
    }

    return new Response(JSON.stringify(buildFeaturedBookPayload(books), null, 2) + "\n", {
      status: 200,
      headers: JSON_HEADERS,
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : "Unexpected featured-book failure" }),
      { status: 500, headers: JSON_HEADERS },
    );
  }
}
