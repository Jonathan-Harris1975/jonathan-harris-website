/**
 * featured-book.js
 * Rotates the featured book on the homepage week-by-week using the canonical book manifest.
 */
(function(){
  "use strict";

  var BOOKS_URL = "/ebooks/books.json";

  function isoWeekNumber(d) {
    var date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    var dayNum = date.getUTCDay() || 7;
    date.setUTCDate(date.getUTCDate() + 4 - dayNum);
    var yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    return Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  }

  function extractPages(shortText) {
    var short = String(shortText || "");
    var match = short.match(/(\d+)-page\b/i) || short.match(/Pages:\s*(\d+)/i);
    return match ? Number(match[1]) : null;
  }

  function normaliseBook(book) {
    if (!book || !book.slug) return null;

    var slug = String(book.slug);
    var url = "/ebooks/" + slug + "/";
    var topic = book.filter || (Array.isArray(book.tags) && book.tags[0]) || "";

    return {
      slug: slug,
      title: book.title || "",
      desc: book.short || "",
      cover: book.cover || book.main_image || "",
      buy: url + "buy-now",
      topic: topic,
      pages: extractPages(book.short),
      url: url
    };
  }

  async function loadBooks() {
    try {
      var response = await fetch(BOOKS_URL, { cache: "no-store" });
      if (!response.ok) return [];
      var data = await response.json();
      if (!Array.isArray(data)) return [];
      return data.map(normaliseBook).filter(Boolean);
    } catch (_) {
      return [];
    }
  }

  function pickBook(books) {
    if (!books || !books.length) return null;
    var now = new Date();
    var week = isoWeekNumber(now);
    var idx = week % books.length;
    return books[idx];
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = value || "";
  }

  function setAttr(id, attr, value) {
    var el = document.getElementById(id);
    if (!el || !value) return;
    el.setAttribute(attr, value);
  }

  function buildResponsiveImageUrl(src, width) {
    if (!src || !width) return src || "";
    if (/\/cdn-cgi\/image\//.test(src) || /\.svg(?:$|\?)/i.test(src)) return src;
    return "/cdn-cgi/image/width=" + width + ",quality=85,fit=scale-down,format=auto/" + src;
  }

  function buildSameSourceSrcset(src, widths) {
    if (!src || !Array.isArray(widths)) return "";
    var unique = Array.from(new Set(widths.filter(Boolean))).sort(function(a, b){ return a - b; });
    if (!unique.length) return "";
    return unique.map(function(width){ return buildResponsiveImageUrl(src, width) + " " + width + "w"; }).join(", ");
  }

  async function render() {
    var books = await loadBooks();
    var b = pickBook(books);
    if (!b) return;

    setText("featuredEbookTitle", b.title);
    setText("featuredEbookDesc", b.desc);
    setText("featuredEbookMeta", (b.topic ? (b.topic + " · ") : "") + (b.pages ? (b.pages + " pages") : ""));

    setAttr("featuredEbookCover", "src", b.cover);
    setAttr("featuredEbookCover", "alt", b.title + " cover");
    setAttr("featuredEbookCover", "srcset", buildSameSourceSrcset(b.cover, [400, 800, 1200]));
    setAttr("featuredEbookCover", "sizes", "(min-width: 1100px) 180px, (min-width: 768px) 28vw, 50vw");
    setAttr("featuredEbookCover", "width", "2480");
    setAttr("featuredEbookCover", "height", "3508");
    setAttr("featuredEbookCover", "decoding", "async");

    setAttr("featuredEbookLink", "href", b.url);
    setAttr("featuredEbookPage", "href", b.url);
    setAttr("featuredEbookBuy", "href", b.buy);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
