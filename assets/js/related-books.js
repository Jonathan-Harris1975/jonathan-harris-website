(function(){
  const LIST_SEL = ".related-books ul";
  const INDEX_URL = "/llm-index.json";

  function norm(s){ return (s||"").toString().toLowerCase().trim(); }

  function slugFromPath(){
    const parts = location.pathname.split("/").filter(Boolean);
    const i = parts.findIndex(p => p === "ebooks");
    if (i >= 0 && parts[i+1]) return parts[i+1];
    return "";
  }

  function score(candidate, current){
    let s = 0;
    if (candidate.topic && current.topic && norm(candidate.topic) === norm(current.topic)) s += 100;

    const currentTitle = new Set((current.title_tokens || []).map(norm));
    (candidate.title_tokens || []).forEach(token => { if (currentTitle.has(norm(token))) s += 35; });

    const currentTopic = new Set((current.topic_tokens || []).map(norm));
    (candidate.topic_tokens || []).forEach(token => { if (currentTopic.has(norm(token))) s += 30; });

    const currentTags = new Set((current.tags || []).map(norm));
    (candidate.tags || []).forEach(tag => { if (currentTags.has(norm(tag))) s += 18; });

    const currentKeywords = new Set((current.keywords || []).map(norm));
    (candidate.keywords || []).forEach(keyword => { if (currentKeywords.has(norm(keyword))) s += 8; });

    return s;
  }

  function bySlug(books){
    const map = new Map();
    books.forEach(book => map.set(book.slug, book));
    return map;
  }

  function pickGovernedRelated(current, books){
    if (!Array.isArray(current.related_slugs) || !current.related_slugs.length) return [];
    const indexed = bySlug(books);
    return current.related_slugs
      .map(slug => indexed.get(slug))
      .filter(Boolean)
      .slice(0, 4);
  }

  function rankFallback(current, books){
    return books
      .filter(book => book.slug !== current.slug)
      .map(book => ({ book, score: score(book, current) }))
      .filter(entry => entry.score > 0)
      .sort((left, right) => right.score - left.score || left.book.title.localeCompare(right.book.title))
      .slice(0, 4)
      .map(entry => entry.book);
  }

  async function run(){
    const list = document.querySelector(LIST_SEL);
    if (!list) return;

    const slug = slugFromPath();
    if (!slug) return;

    try{
      const res = await fetch(INDEX_URL, { cache: "no-store" });
      if (!res.ok) throw new Error("index fetch failed");
      const data = await res.json();
      const books = Array.isArray(data && data.books) ? data.books : [];
      const current = books.find(book => book.slug === slug);
      if (!current) return;

      const picks = pickGovernedRelated(current, books).length ? pickGovernedRelated(current, books) : rankFallback(current, books);
      if (!picks.length){
        list.innerHTML = "<li>No related titles yet — check the catalogue.</li>";
        return;
      }

      list.innerHTML = "";
      picks.forEach(book => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = `/ebooks/${book.slug}/`;
        a.textContent = book.title;
        li.appendChild(a);
        list.appendChild(li);
      });
    }catch(_){
      // Keep the static list if anything goes wrong.
    }
  }

  document.addEventListener("DOMContentLoaded", run);
})();
