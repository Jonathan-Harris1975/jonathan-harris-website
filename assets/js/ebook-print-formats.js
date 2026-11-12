/*
 * Progressive enhancement for verified Amazon print editions. Existing
 * Kindle routes remain unchanged. Hidden/pending print formats stay hidden.
 */
(() => {
  "use strict";
  const names = { paperback: "Paperback", hardcover: "Hardback" };
  const availableFormats = (book) => {
    const formats = book?.print_formats || {};
    return ["paperback", "hardcover"].filter((format) => {
      const item = formats[format];
      if (!item || !item.verified_at || !item.isbn || !item.asin || !item.purchase_url) return false;
      try {
        const url = new URL(item.purchase_url);
        return url.protocol === "https:" && ["amazon.co.uk", "www.amazon.co.uk"].includes(url.hostname)
          && new RegExp("/(?:dp|gp/product)/" + item.asin + "(?:/|$)", "i").test(url.pathname);
      } catch { return false; }
    });
  };

  async function addAvailablePrintFormats() {
    const detail = document.body?.matches(".ebook-detail[data-book-slug]");
    const cards = document.querySelectorAll(".ebook-card[data-book-slug]");
    if (!detail && !cards.length) return;
    let books;
    try {
      const response = await fetch("/api/v1/ebooks.json", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const payload = await response.json();
      books = Array.isArray(payload.books) ? payload.books : [];
    } catch { return; }
    const catalogue = new Map(books.map((book) => [book.slug, book]));

    for (const card of cards) {
      const book = catalogue.get(card.dataset.bookSlug);
      const formats = availableFormats(book);
      if (!formats.length) continue;
      const badge = card.querySelector(".book-avail__badge");
      if (badge) badge.textContent = ["Available on Amazon: Kindle", ...formats.map((format) => names[format])].join(" · ");
    }
    if (!detail) return;
    const book = catalogue.get(document.body.dataset.bookSlug);
    const formats = availableFormats(book);
    if (!formats.length) return;
    const actions = document.querySelector(".ebook-showcase .ebook-actions");
    if (!actions) return;
    for (const format of formats) {
      const item = book.print_formats[format];
      if (actions.querySelector('[data-print-format="' + format + '"]')) continue;
      const link = document.createElement("a");
      link.className = "button secondary";
      link.href = item.purchase_url;
      link.textContent = "Buy " + names[format] + " on Amazon";
      link.setAttribute("aria-label", "Buy " + names[format] + " edition of " + book.title + " on Amazon UK");
      link.setAttribute("data-print-format", format);
      link.rel = "noopener noreferrer";
      link.target = "_blank";
      actions.append(link);
    }
    // Enhance existing Book structured data only for independently verified editions.
    // The static page continues to describe the original Kindle edition.
    for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const data = JSON.parse(node.textContent);
        if (data?.["@type"] !== "Book" || !data?.["@id"]?.endsWith("/#book")) continue;
        data.workExample = formats.map((format) => {
          const item = book.print_formats[format];
          return { "@type": "Book", bookFormat: names[format],
            isbn: item.isbn, url: item.purchase_url,
            identifier: [{ "@type": "PropertyValue", propertyID: "ASIN", value: item.asin }] };
        });
        node.textContent = JSON.stringify(data);
        break;
      } catch { /* Ignore unrelated or invalid JSON-LD. */ }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", addAvailablePrintFormats, { once: true });
  } else {
    addAvailablePrintFormats();
  }
})();
