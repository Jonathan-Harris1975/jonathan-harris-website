(function(){
  "use strict";

  const RSS_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

  const $ = (s, r=document) => r.querySelector(s);

  function escapeHtml(s){
    return (s||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  function stripHtml(s){
    return (s||"").replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
  }

  function formatDate(pubDate){
    if (!pubDate) return "";
    const d = new Date(pubDate);
    if (Number.isNaN(d.getTime())) return "";
    // YYYY-MM-DD (clean, non-dramatic)
    return d.toISOString().slice(0,10);
  }

  function buildStickyCta(){
    // Avoid duplicates
    if (document.querySelector(".jh-sticky-cta")) return;

    const bar = document.createElement("div");
    bar.className = "jh-sticky-cta";
    bar.setAttribute("role","region");
    bar.setAttribute("aria-label","Newsletter prompt");

    bar.innerHTML = `
      <div class="jh-sticky-cta__inner">
        <div class="jh-sticky-cta__copy">
          <strong>AI Edge</strong>
          <span class="jh-sticky-cta__muted">Weekly AI updates - minus the hype.</span>
        </div>
        <div class="jh-sticky-cta__actions">
          <a class="btn btn-primary" href="/newsletter/">Subscribe</a>
          <button class="jh-sticky-cta__close" type="button" aria-label="Dismiss">×</button>
        </div>
      </div>
    `;

    const close = bar.querySelector(".jh-sticky-cta__close");
    close?.addEventListener("click", () => {
      try { localStorage.setItem("jhStickyCtaDismissed","1"); } catch(_){}
      bar.remove();
    });

    // Respect dismissal (30 days is plenty)
    try{
      const dismissed = localStorage.getItem("jhStickyCtaDismissed");
      if (dismissed === "1") return;
    }catch(_){}

    document.body.appendChild(bar);
  }

  async function loadLatestEpisode(){
    const titleEl = $("#latestEpisodeTitle");
    const descEl = $("#latestEpisodeDesc");
    const dateEl = $("#latestEpisodeDate");
    const audioEl = $("#latestEpisodeAudio");

    if (!titleEl || !descEl || !dateEl) return;

    try{
      const res = await fetch(RSS_URL, { cache: "no-store" });
      if (!res.ok) throw new Error("RSS fetch failed");
      const xmlText = await res.text();
      const doc = new DOMParser().parseFromString(xmlText, "text/xml");
      const item = doc.querySelector("item");
      if (!item) throw new Error("No items");

      const title = item.querySelector("title")?.textContent?.trim() || "Latest episode";
      const pubDate = item.querySelector("pubDate")?.textContent?.trim() || "";
      const descRaw = item.querySelector("description")?.textContent || "";
      const desc = stripHtml(descRaw).slice(0, 240);

      const enclosureUrl = item.querySelector("enclosure[url]")?.getAttribute("url") || "";

      titleEl.textContent = title;
      descEl.textContent = desc ? desc + (desc.length >= 240 ? "…" : "") : "A fresh episode is up. Have a listen.";
      const d = formatDate(pubDate);
      dateEl.textContent = d ? d : "Latest";

      if (audioEl && enclosureUrl){
        audioEl.src = enclosureUrl;
        audioEl.style.display = "block";
      }
    }catch(_){
      // Quiet fallback: keep the embed + generic copy
      if (dateEl) dateEl.textContent = "Latest";
      if (titleEl) titleEl.textContent = "New episode available";
      if (descEl) descEl.textContent = "Hit play on Spotify (or use RSS) and you’ll get the latest one.";
    }
  }

  function init(){
    // Sticky CTA after initial paint (keeps the page feeling snappy)
    window.setTimeout(buildStickyCta, 1200);

    // Latest episode (best-effort)
    loadLatestEpisode();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();