(async function(){
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  const loader = $("#pageLoader");
  const searchInput = $("#search");
  const chipsWrap = $("#chips");
  const grid = $("#booksGrid");
  const countEl = $("#count");

  const pager = $("#pager");
  const prevBtn = $("#prevPage");
  const nextBtn = $("#nextPage");
  const pageInfo = $("#pageInfo");

  function hideLoader(){
    if (window.__JH_HIDE_LOADER__) { window.__JH_HIDE_LOADER__(); return; }
    if (!loader) return;
    loader.classList.add("hide");
    window.setTimeout(() => { try { loader.remove(); } catch(_){} }, 350);
  }

  function norm(s){ return (s||"").toString().toLowerCase(); }

  async function fetchBooks(){
    const candidates = [
      "/books.json",
      "/ebooks/books.json",
      "./books.json",
      "./ebooks/books.json",
      "/assets/js/books.json",
      "./assets/js/books.json"
    ];
    let lastErr = null;
    for (const url of candidates){
      try{
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) { lastErr = new Error(`HTTP ${resp.status} for ${url}`); continue; }
        const data = await resp.json();
        if (Array.isArray(data) && data.length) return data;
        lastErr = new Error(`Empty/invalid JSON at ${url}`);
      }catch(e){
        lastErr = e;
      }
    }
    throw lastErr || new Error("Unable to load books data");
  }

  let books = [];
  try{
    books = await fetchBooks();
  }catch(err){
    // Fail loudly (but not silently blank)
    if (countEl) countEl.textContent = "Unable to load the catalogue right now.";
    const msg = document.createElement("div");
    msg.className = "card";
    msg.innerHTML = `<h2>Catalogue unavailable</h2><p>Refresh the page. If it persists, the books data file isn’t being served from this path.</p>`;
    if (grid) grid.appendChild(msg);
    hideLoader();
    return;
  }

  // Build filter set (use 'filter' field first)
  const filters = new Set();
  books.forEach(b => { if (b && b.filter) filters.add(b.filter); });

  const params = new URLSearchParams(window.location.search);
  const legacyCat = (params.get("cat") || "").trim();
  const legacyCatMap = {
    "Artificial Intelligence": { filter: "Artificial Intelligence" },
    "Creativity": { filter: "Creativity" },
    "Education": { filter: "Education" },
    "Ethics": { filter: "Ethics" },
    "Healthcare": { filter: "Healthcare" },
    "Law": { filter: "Law" },
    "Transportation": { filter: "Transportation" },
    "Construction": { q: "Construction" },
    "Energy": { q: "Energy" },
    "Finance": { q: "Finance" },
    "Manufacturing": { q: "Manufacturing" },
    "Retail": { q: "Retail" },
    "Security": { q: "Security" },
    "Sports": { q: "Sports" }
  };
  const legacyState = legacyCatMap[legacyCat] || null;
  const state = {
    q: params.get("q") || (legacyState && legacyState.q) || "",
    filter: params.get("filter") || (legacyState && legacyState.filter) || "All",
    page: Math.max(1, parseInt(params.get("page") || "1", 10) || 1)
  };

  function syncUrl(){
    try {
      const next = new URL(window.location.href);
      if (state.q.trim()) next.searchParams.set("q", state.q.trim());
      else next.searchParams.delete("q");
      if (state.filter && state.filter !== "All") next.searchParams.set("filter", state.filter);
      else next.searchParams.delete("filter");
      if (state.page > 1) next.searchParams.set("page", String(state.page));
      else next.searchParams.delete("page");
      const nextUrl = `${next.pathname}${next.searchParams.toString() ? `?${next.searchParams.toString()}` : ""}${next.hash}`;
      window.history.replaceState({}, "", nextUrl);
    } catch(_) {}
  }

  function getPerPage(){
    const w = window.innerWidth || 0;
    if (w >= 1100) return 8;
    if (w >= 760) return 6;
    return 4;
  }

  function makeChip(label){
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.textContent = label;
    btn.setAttribute("aria-pressed", label === state.filter ? "true" : "false");
    btn.addEventListener("click", () => {
      state.filter = label;
      state.page = 1;
      $$(".chip", chipsWrap).forEach(c => c.setAttribute("aria-pressed", c.textContent === label ? "true":"false"));
      // FIX #9: Announce active filter to screen readers via aria-live region
      try {
        var countEl2 = document.getElementById("count");
        if (countEl2) {
          var filterMsg = label === "All"
            ? "Showing all books"
            : "Filtered by " + label + ". ";
          // Announcement is appended after count update in renderBooks()
          countEl2.dataset.pendingFilter = filterMsg;
        }
      } catch(_) {}
      syncUrl();
      render();
    });
    return btn;
  }

  // chips (clear any pre-rendered content)
  if (chipsWrap) chipsWrap.innerHTML = "";
  if (chipsWrap) chipsWrap.appendChild(makeChip("All"));
  Array.from(filters).sort((a,b)=>a.localeCompare(b)).forEach(f => chipsWrap && chipsWrap.appendChild(makeChip(f)));

  function matches(book){
    if (!book) return false;
    if (state.filter !== "All" && norm(book.filter) !== norm(state.filter)) return false;
    const hay = [
      book.title, book.short,
      (book.tags||[]).join(" "),
      book.keywords || "",
      book.slug || ""
    ].map(norm).join(" | ");
    const q = norm(state.q).trim();
    if (!q) return true;
    return q.split(/\s+/).every(term => hay.includes(term));
  }

  function card(book){
    const a = document.createElement("article");
    a.className = "card";
    a.setAttribute("aria-label", book.title);

    const img = document.createElement("img");
    img.className = "cover";
    img.loading = "lazy";
    img.alt = book.title;
    img.src = book.cover;

    const h = document.createElement("h2");
    h.textContent = book.title;


    const topicWrap = document.createElement("div");
    topicWrap.className = "topic-chip-wrap";
    const topicChip = document.createElement("span");
    topicChip.className = "topic-chip";
    topicChip.textContent = book.filter || "AI";
    topicWrap.appendChild(topicChip);

    const p = document.createElement("p");
    p.textContent = book.short;

    const tags = document.createElement("div");
    tags.className = "tags";
    (book.tags||[]).slice(0,4).forEach(t=>{
      const s = document.createElement("span");
      s.className = "tag";
      s.textContent = t;
      tags.appendChild(s);
    });

    // Availability badge
    const avail = document.createElement("div");
    avail.className = "book-avail";
    avail.innerHTML = '<span class="book-avail__badge">&#x1F6CD;&#xFE0F; Available on Amazon Kindle</span>';

    const more = document.createElement("details");
    more.className = "more";
    const sum = document.createElement("summary");
    sum.setAttribute("aria-expanded", "false");
    sum.textContent = "More details";
    const moreText = document.createElement("div");
    moreText.className = "meta";
    moreText.textContent = "Read the full description, then check the latest price on Amazon.";
    const actions = document.createElement("div");
    actions.className = "actions";
    const btnDetail = document.createElement("a");
    btnDetail.className = "button secondary";
    btnDetail.href = `/ebooks/${book.slug}/`;
    btnDetail.textContent = "Full description";
    const btnBuy = document.createElement("a");
    btnBuy.className = "button";
    btnBuy.href = book.buy_url || "#";
    btnBuy.target = "_blank";
    btnBuy.rel = "noopener noreferrer";
    btnBuy.textContent = "View on Amazon";

    actions.appendChild(btnDetail);
    actions.appendChild(btnBuy);

    more.appendChild(sum);
    more.appendChild(moreText);
    more.appendChild(actions);

    a.appendChild(img);
    a.appendChild(h);
    a.appendChild(topicWrap);
    a.appendChild(p);
    a.appendChild(tags);
    a.appendChild(avail);
    a.appendChild(more);

    return a;
  }

  function updatePager(totalPages){
    if (!pager || !prevBtn || !nextBtn || !pageInfo) return;
    if (totalPages <= 1){
      pager.style.display = "none";
      return;
    }
    pager.style.display = "flex";
    pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
    prevBtn.disabled = state.page <= 1;
    nextBtn.disabled = state.page >= totalPages;
  }

  function render(){
    if (!grid) return;
    grid.innerHTML = "";
    const filtered = books.filter(matches);
    const perPage = getPerPage();
    const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
    if (state.page > totalPages) state.page = totalPages;

    const start = (state.page - 1) * perPage;
    const pageItems = filtered.slice(start, start + perPage);

    pageItems.forEach(b => grid.appendChild(card(b)));
    if (countEl) {
      var pendingFilter = countEl.dataset.pendingFilter || "";
      delete countEl.dataset.pendingFilter;
      countEl.textContent = pendingFilter + filtered.length + " of " + books.length + " books";
    }
    updatePager(totalPages);

    hideLoader();
  }

  if (searchInput){
    searchInput.addEventListener("input", (e)=>{
      state.q = e.target.value;
      state.page = 1;
      syncUrl();
      render();
    });
  }

  if (prevBtn){
    prevBtn.addEventListener("click", ()=>{
      if (state.page > 1){ state.page -= 1; syncUrl(); render(); }
    });
  }
  if (nextBtn){
    nextBtn.addEventListener("click", ()=>{
      state.page += 1;
      syncUrl();
      render();
    });
  }

  window.addEventListener("resize", ()=>{
    // keep current page valid across breakpoints
    render();
  });

  if (searchInput) searchInput.value = state.q;

  if (state.filter !== "All" && !filters.has(state.filter)) {
    state.filter = "All";
  }

  syncUrl();
  render();
})();