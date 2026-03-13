(function(){
  const LIST_SEL = ".related-books ul";
  const INDEX_URL = "/llm-index.json";

  function norm(s){ return (s||"").toString().toLowerCase().trim(); }

  function slugFromPath(){
    const parts = location.pathname.split("/").filter(Boolean);
    // /ebooks/<slug>/ or /ebooks/<slug>/detail.html
    const i = parts.findIndex(p => p === "ebooks");
    if (i >= 0 && parts[i+1]) return parts[i+1];
    return "";
  }

  function shuffle(arr){
    for (let i = arr.length - 1; i > 0; i--){
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  function score(candidate, current){
    let s = 0;
    if (candidate.topic && current.topic && norm(candidate.topic) === norm(current.topic)) s += 50;
    const ct = new Set((current.tags||[]).map(norm));
    (candidate.tags||[]).forEach(t => { if (ct.has(norm(t))) s += 10; });
    // small bonus if keyword overlap
    const ck = new Set((current.keywords||[]).map(norm));
    (candidate.keywords||[]).forEach(k => { if (ck.has(norm(k))) s += 3; });
    return s;
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
      const books = (data && data.books) ? data.books : [];
      const current = books.find(b => b.slug === slug);
      if (!current) return;

      const ranked = books
        .filter(b => b.slug !== slug)
        .map(b => ({ b, s: score(b, current) }))
        .sort((a,b) => b.s - a.s);

      const top = ranked.filter(x => x.s > 0).slice(0, 12).map(x => x.b);
      shuffle(top);

      const picks = top.slice(0, 4);
      if (!picks.length){
        list.innerHTML = "<li>No related titles yet — check the catalogue.</li>";
        return;
      }

      list.innerHTML = "";
      picks.forEach(b => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = `/ebooks/${b.slug}/`;
        a.textContent = b.title;
        li.appendChild(a);
        list.appendChild(li);
      });
    }catch(_){
      // Keep the static list if anything goes wrong.
    }
  }

  document.addEventListener("DOMContentLoaded", run);
})();