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

  function stripHtml(s){
    return (s||"").replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
  }

  function parseRss(xmlText){
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");
    const items = Array.from(doc.querySelectorAll("item")).slice(0, cfg.MAX_ITEMS || 20);
    return items.map(it => {
      const title = it.querySelector("title")?.textContent?.trim() || "Untitled";
      const link = it.querySelector("link")?.textContent?.trim() || "";
      const pubDate = it.querySelector("pubDate")?.textContent?.trim() || "";
      const descRaw = it.querySelector("description")?.textContent || "";
      const desc = stripHtml(descRaw).slice(0, 220);

      // Try common image locations (RSS enclosure, iTunes image)
      const enclosure = it.querySelector("enclosure[url]")?.getAttribute("url") || "";
      const itImg = it.querySelector("itunes\\:image")?.getAttribute("href") || "";
      const image = enclosure || itImg || "";

      return { title, link, pubDate, desc, image };
    });
  }

  function render(items){
    if (!list) return;

    if (!items || !items.length){
      list.innerHTML = `
        <div class="card" style="padding:18px;">
          <h2 style="margin-top:0;">No posts yet</h2>
          <p>The blog template is live, but publishing hasn't started. When it does, posts will appear here automatically.</p>
          <p><a class="button primary" href="/newsletter/">Get the newsletter instead</a></p>
        </div>`;
      return;
    }

    const html = items.map(it => {
      const date = it.pubDate ? new Date(it.pubDate).toISOString().slice(0,10) : "";
      const safeTitle = escapeHtml(it.title);
      const safeDesc = escapeHtml(it.desc || "");
      const img = it.image ? `<img class="cover" src="${escapeHtml(it.image)}" alt="${safeTitle}" loading="lazy">` : "";
      const href = it.link || "#";

      return `
        <article class="card" style="overflow:hidden;">
          ${img}
          <div style="padding:16px;">
            ${date ? `<div class="tag" style="display:inline-flex;margin-bottom:8px;">${date}</div>` : ""}
            <h2 style="margin:0 0 8px 0; font-size:18px;">${safeTitle}</h2>
            <p style="margin:0 0 12px 0;">${safeDesc}</p>
            ${href !== "#" ? `<a class="button secondary" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Read / Listen</a>` : ""}
          </div>
        </article>`;
    }).join("");

    list.innerHTML = `<div class="grid">${html}</div>`;
  }

  async function fetchManifest(url){
    try{
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return null;
      const data = await res.json();
      if (data && Array.isArray(data.items)) return data.items;
      if (Array.isArray(data)) return data;
      return null;
    }catch(_){
      return null;
    }
  }

  async function tryManifest(){
    const local = await fetchManifest("/blog/posts.json");
    if (local && local.length) return local;

    const base = (cfg.R2_PUBLIC_BASE_URL_BLOG || "").replace(/\/$/, "");
    if (!base) return null;
    const remote = await fetchManifest(`${base}/posts.json`);
    return remote && remote.length ? remote : null;
  }

  async function tryRss(){
    if (!cfg.RSS_URL) return null;
    try{
      const res = await fetch(cfg.RSS_URL, { cache: "no-store" });
      if (!res.ok) return null;
      const xml = await res.text();
      return parseRss(xml);
    }catch(_){
      return null;
    }
  }

  async function init(){
    setStatus("Loading posts…");
    const manifest = await tryManifest();
    if (manifest){
      setStatus("");
      render(manifest);
      return;
    }
    const rss = await tryRss();
    setStatus("");
    render(rss || []);
  }

  document.addEventListener("DOMContentLoaded", init);
})();