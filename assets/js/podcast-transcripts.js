(function(){
  const FEED_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

  const listEl = document.getElementById("transcriptList");
  const statusEl = document.getElementById("transcriptStatus");
  const searchEl = document.getElementById("transcriptSearch");
  const fallbackMarkup = listEl ? listEl.innerHTML : "";

  if(!listEl || !statusEl || !searchEl) return;

  function setStatus(msg){ statusEl.textContent = msg || ""; }

  function normalise(s){ return (s || "").toLowerCase().trim(); }

  function parseDate(s){
    try{
      const d = new Date(s);
      if(!isNaN(d.getTime())) return d;
    }catch(e){}
    return null;
  }

  function pickTranscriptUrl(item){
    // 1) <podcast:transcript url="..."> (Podcasting 2.0)
    const t1 = item.querySelector("podcast\\:transcript, transcript");
    if(t1){
      const u = t1.getAttribute && (t1.getAttribute("url") || t1.getAttribute("href"));
      if(u) return u;
      const txt = t1.textContent && t1.textContent.trim();
      if(txt && /^https?:\/\//i.test(txt)) return txt;
    }

    // 2) <link> is often the canonical episode page (sometimes the transcript page)
    const linkEl = item.querySelector("link");
    if(linkEl && linkEl.textContent){
      const u = linkEl.textContent.trim();
      if(/^https?:\/\//i.test(u)) return u;
    }

    // 3) Fallback: <guid> that looks like a URL
    const guidEl = item.querySelector("guid");
    if(guidEl && guidEl.textContent){
      const u = guidEl.textContent.trim();
      if(/^https?:\/\//i.test(u)) return u;
    }

    return null;
  }

  function buildRow(entry){
    const li = document.createElement("li");

    const a = document.createElement("a");
    a.href = entry.url;
    a.rel = "noopener noreferrer";
    a.target = "_blank";
    a.textContent = entry.title || entry.url;

    li.appendChild(a);

    if(entry.date){
      const meta = document.createElement("span");
      meta.className = "transcript-meta";
      meta.textContent = entry.date.toLocaleDateString("en-GB", { year:"numeric", month:"short", day:"2-digit" });
      li.appendChild(meta);
    }

    li.dataset.title = normalise(entry.title);
    return li;
  }

  function applyFilter(){
    const q = normalise(searchEl.value);
    const items = Array.from(listEl.querySelectorAll("li"));
    let visible = 0;
    items.forEach(li => {
      const t = li.dataset.title || "";
      const show = !q || t.includes(q);
      if(show){ li.removeAttribute("hidden"); } else { li.setAttribute("hidden", ""); }
      if(show) visible++;
    });
    setStatus(visible ? "" : "No transcripts match that search.");
  }

  async function loadFeed(){
    setStatus("Loading transcripts…");
    listEl.innerHTML = fallbackMarkup;

    try{
      const res = await fetch(FEED_URL, { cache: "no-store" });
      if(!res.ok) throw new Error("Feed fetch failed: " + res.status);

      const xmlText = await res.text();
      const doc = new DOMParser().parseFromString(xmlText, "text/xml");

      const items = Array.from(doc.querySelectorAll("item"));
      const entries = items.map(item => {
        const title = (item.querySelector("title")?.textContent || "").trim();
        const pubDateRaw = (item.querySelector("pubDate")?.textContent || "").trim();
        const url = pickTranscriptUrl(item);
        return { title, date: parseDate(pubDateRaw), url };
      }).filter(e => e.url);

      if(!entries.length){
        setStatus("No transcript links were found in the feed. Showing the static fallback list instead.");
        applyFilter();
        return;
      }

      listEl.innerHTML = "";

      // newest first (best-effort)
      entries.sort((a,b) => (b.date?.getTime()||0) - (a.date?.getTime()||0));

      const frag = document.createDocumentFragment();
      entries.forEach(e => frag.appendChild(buildRow(e)));
      listEl.appendChild(frag);

      setStatus("");
      applyFilter();
    }catch(err){
      setStatus("Couldn’t load the RSS feed in-browser. Showing the static fallback list instead.");
      applyFilter();
    }
  }

  searchEl.addEventListener("input", applyFilter);

  // Load once page is ready
  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", loadFeed);
  }else{
    loadFeed();
  }
})();
