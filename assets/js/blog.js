(function(){
  const cfg = window.__JH_BLOG__ || {};
  const $ = (s, r=document) => r.querySelector(s);

  const list = $("#blogList");
  const status = $("#blogStatus");

  function setStatus(msg){
    if (status) status.textContent = msg || "";
  }

  function escapeHtml(s){
    return (s||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  function render(items){
    if (!list) return;

    if (!items || !items.length){
      list.innerHTML = `
        <div class="card u-s04">
          <h2 class="u-s02">No posts yet</h2>
          <p>The archive is ready. Once weekly posts are published in the local manifest, they will appear here automatically.</p>
          <p><a class="button primary" href="/newsletter/">Get the newsletter instead</a></p>
        </div>`;
      return;
    }

    const html = items.slice(0, cfg.MAX_ITEMS || 20).map(it => {
      const rawDate = (it.pubDate || it.datePublished || it.date || "").trim();
      const date = rawDate ? rawDate.slice(0, 10) : "";
      const safeTitle = escapeHtml(it.title || "Untitled");
      const safeDesc = escapeHtml((it.desc || it.summary || "").trim());
      const image = (it.image || it.cover || "").trim();
      const img = image ? `<img class="cover" src="${escapeHtml(image)}" alt="${safeTitle}" loading="lazy">` : "";
      const href = (it.url || it.link || "").trim() || "#";

      return `
        <article class="card u-s05">
          ${img}
          <div class="u-s06">
            ${date ? `<div class="tag u-s07">${escapeHtml(date)}</div>` : ""}
            <h2 class="u-s08">${safeTitle}</h2>
            <p class="u-s09">${safeDesc}</p>
            ${href !== "#" ? `<a class="button secondary" href="${escapeHtml(href)}">Read post</a>` : ""}
          </div>
        </article>`;
    }).join("");

    list.innerHTML = `<div class="grid">${html}</div>`;
  }

  async function fetchManifest(){
    try{
      const res = await fetch("/blog/posts.json", { cache: "no-store" });
      if (!res.ok) return [];
      const data = await res.json();
      if (data && Array.isArray(data.items)) return data.items;
      if (Array.isArray(data)) return data;
      return [];
    }catch(_){
      return [];
    }
  }

  async function init(){
    setStatus("Loading posts…");
    const manifest = await fetchManifest();
    if (manifest.length){
      setStatus("");
      render(manifest);
      return;
    }
    setStatus("No weekly posts published yet.");
    render([]);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
