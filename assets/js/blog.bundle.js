window.__JH_BLOG__ = window.__JH_BLOG__ || {
  MAX_ITEMS: 20,
  WEEKLY_PAGE_SIZE: 4
};

(function () {
  const cfg = window.__JH_BLOG__ || {};
  const list = document.querySelector("#blogList");
  const status = document.querySelector("#blogStatus");
  const search = document.querySelector("#blogSearch");
  const loadMore = document.querySelector("#blogLoadMore");

  if (!list) {
    return;
  }

  const surfaceKey =
    (document.body && document.body.dataset && document.body.dataset.blogSurface) ||
    (document.body && document.body.classList.contains("page-blog-weekly") ? "weekly" : "hub");

  const surface = {
    hub: {
      pageSize: 1,
      emptyTitle: "Published briefings",
      emptyCopy:
        "The weekly briefings land here with the same plain-English editorial line that runs through the archive, newsletter, podcast, and topic pages.",
      emptyHref: "/blog/weekly/",
      emptyLabel: "Open weekly briefings",
      loading: "Checking the latest briefing…",
      emptyStatus: "The latest weekly briefing appears here when the live feed updates.",
      loadedStatus: (count) => count > 0 ? `Latest briefing drawn from ${count} published ${count === 1 ? "post" : "posts"}.` : "",
    },
    weekly: {
      pageSize: Number(cfg.WEEKLY_PAGE_SIZE || 4),
      emptyTitle: "Weekly archive",
      emptyCopy:
        "The archive collects each published weekly briefing, with the blog hub, newsletter, and podcast carrying the same editorial line alongside it.",
      emptyHref: "/blog/",
      emptyLabel: "Open the blog",
      loading: "Loading weekly briefings…",
      emptyStatus: "The archive updates as weekly briefings are published.",
      loadedStatus: (visible, total, query) => {
        if (query) {
          return visible === total
            ? `${visible} ${visible === 1 ? "briefing" : "briefings"} found.`
            : `Showing ${visible} of ${total} matching briefings.`;
        }
        return visible === total
          ? `Showing ${visible} published weekly ${visible === 1 ? "briefing" : "briefings"}.`
          : `Showing ${visible} of ${total} published weekly briefings.`;
      },
    }
  }[surfaceKey] || {
    pageSize: Number(cfg.MAX_ITEMS || 20),
    emptyTitle: "Published briefings",
    emptyCopy: "Published briefings appear here as they are released.",
    emptyHref: "/blog/",
    emptyLabel: "Open the blog",
    loading: "Loading published briefings…",
    emptyStatus: "",
    loadedStatus: () => "",
  };

  let allItems = [];
  let visibleCount = surface.pageSize;

  function setStatus(message) {
    if (status) {
      status.textContent = message || "";
    }
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, function (character) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[character];
    });
  }

  function pickFirst(item, keys) {
    for (const key of keys) {
      const value = item && item[key];
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
    return "";
  }

  function parseDate(value) {
    if (!value) {
      return null;
    }

    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function formatPublishedDate(value) {
    const parsed = parseDate(value);
    if (!parsed) {
      return "";
    }

    return parsed.toLocaleDateString("en-GB", {
      year: "numeric",
      month: "short",
      day: "2-digit"
    });
  }

  function normaliseQuery(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function normaliseItem(item) {
    const slug = pickFirst(item, ["slug"]);
    const href =
      pickFirst(item, ["url", "canonical_url", "canonicalUrl", "path"]) ||
      (slug ? `/blog/posts/${encodeURIComponent(slug)}/` : "");
    const publishedAt = pickFirst(item, ["published_at", "publishedAt", "datePublished", "date", "pubDate"]);
    const dateLabel = pickFirst(item, ["date_label", "dateLabel"]) || formatPublishedDate(publishedAt);
    const summary = pickFirst(item, ["summary", "excerpt", "description", "desc"]);

    return {
      slug,
      title: pickFirst(item, ["title", "headline"]) || "Untitled",
      summary,
      image: pickFirst(item, ["image", "image_url", "cover", "heroImage", "hero_image"]),
      href,
      dateLabel,
      publishedAt,
      parsedDate: parseDate(publishedAt),
      searchBlob: normaliseQuery([pickFirst(item, ["title", "headline"]), summary, dateLabel].join(" "))
    };
  }

  function normaliseManifest(payload) {
    const items = payload && typeof payload === "object" && Array.isArray(payload.items)
      ? payload.items
      : [];

    return items
      .map(normaliseItem)
      .filter(function (item) {
        return item.slug || item.href || item.title || item.summary;
      })
      .sort(function (left, right) {
        const leftTime = left.parsedDate ? left.parsedDate.getTime() : 0;
        const rightTime = right.parsedDate ? right.parsedDate.getTime() : 0;
        return rightTime - leftTime;
      });
  }

  function countSeededItems() {
    const anchors = Array.from(list.querySelectorAll('a[href^="/blog/posts/"], a[href^="https://jonathan-harris.online/blog/posts/"]'));
    return new Set(anchors.map(function (anchor) {
      return anchor.getAttribute("href");
    }).filter(Boolean)).size;
  }

  function renderEmptyState() {
    list.innerHTML = `
      <div class="card u-s04">
        <h2 class="u-s02">${escapeHtml(surface.emptyTitle)}</h2>
        <p>${escapeHtml(surface.emptyCopy)}</p>
        <p><a class="button primary" href="${escapeHtml(surface.emptyHref)}">${escapeHtml(surface.emptyLabel)}</a></p>
      </div>`;
    if (loadMore) {
      loadMore.hidden = true;
    }
  }

  function renderHub(item) {
    const safeTitle = escapeHtml(item.title);
    const safeSummary = escapeHtml(item.summary);
    const safeHref = escapeHtml(item.href);
    const safeDateLabel = escapeHtml(item.dateLabel);

    list.innerHTML = `
      <article class="card jh-blog-card">
        ${safeDateLabel ? `<p class="jh-blog-card__meta">${safeDateLabel}</p>` : ""}
        <h3 class="jh-blog-card__title"><a href="${safeHref}">${safeTitle}</a></h3>
        ${safeSummary ? `<p class="jh-blog-card__excerpt">${safeSummary}</p>` : ""}
        <p><a class="button secondary" href="${safeHref}">Read article</a></p>
      </article>`;
  }

  function renderArchive(items) {
    const html = items.map(function (item) {
      const safeTitle = escapeHtml(item.title);
      const safeSummary = escapeHtml(item.summary);
      const safeHref = escapeHtml(item.href);
      const safeImage = escapeHtml(item.image);
      const safeDateLabel = escapeHtml(item.dateLabel);
      const imageMarkup = item.image
        ? `<img class="cover" src="${safeImage}" alt="${safeTitle}" loading="lazy" decoding="async">`
        : "";

      return `
        <article class="card u-s05">
          ${imageMarkup}
          <div class="u-s06">
            ${safeDateLabel ? `<div class="tag u-s07">${safeDateLabel}</div>` : ""}
            <h2 class="u-s08">${safeTitle}</h2>
            ${safeSummary ? `<p class="u-s09">${safeSummary}</p>` : ""}
            <a class="button secondary" href="${safeHref}">Read article</a>
          </div>
        </article>`;
    }).join("");

    list.innerHTML = `<div class="grid">${html}</div>`;
  }

  function getFilteredItems() {
    const query = normaliseQuery(search ? search.value : "");
    if (!query) {
      return allItems.slice();
    }
    return allItems.filter(function (item) {
      return item.searchBlob.indexOf(query) !== -1;
    });
  }

  function updateArchiveView() {
    const filteredItems = getFilteredItems();
    const visibleItems = filteredItems.slice(0, visibleCount);
    const query = normaliseQuery(search ? search.value : "");

    if (!filteredItems.length) {
      renderEmptyState();
      setStatus(query ? "No briefings match that search." : surface.emptyStatus);
      return;
    }

    renderArchive(visibleItems);
    setStatus(surface.loadedStatus(visibleItems.length, filteredItems.length, query));

    if (loadMore) {
      loadMore.hidden = visibleItems.length >= filteredItems.length;
    }
  }

  async function fetchManifest() {
    try {
      const response = await fetch("/blog/posts.json", {
        cache: "no-store",
        headers: {
          Accept: "application/json"
        }
      });

      if (!response.ok) {
        return { ok: false, items: [] };
      }

      const payload = await response.json();
      return { ok: true, items: normaliseManifest(payload) };
    } catch (_error) {
      return { ok: false, items: [] };
    }
  }

  async function init() {
    setStatus(surface.loading);
    const result = await fetchManifest();

    if (result.items.length) {
      allItems = result.items;
      if (surfaceKey === "hub") {
        renderHub(result.items[0]);
        setStatus(surface.loadedStatus(result.items.length));
        return;
      }

      visibleCount = surface.pageSize;
      updateArchiveView();
      return;
    }

    if (result.ok) {
      setStatus(surface.emptyStatus);
      renderEmptyState();
      return;
    }

    const seededItems = countSeededItems();
    if (seededItems > 0) {
      if (surfaceKey === "hub") {
        setStatus(surface.loadedStatus(seededItems));
      } else {
        setStatus(surface.loadedStatus(Math.min(surface.pageSize, seededItems), seededItems, ""));
      }
      return;
    }

    setStatus(surface.emptyStatus);
    renderEmptyState();
  }

  if (search) {
    search.addEventListener("input", function () {
      visibleCount = surface.pageSize;
      updateArchiveView();
    });
  }

  if (loadMore) {
    loadMore.addEventListener("click", function () {
      visibleCount += surface.pageSize;
      updateArchiveView();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
