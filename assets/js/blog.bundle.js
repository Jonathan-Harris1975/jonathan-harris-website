window.__JH_BLOG__ = window.__JH_BLOG__ || {
  MAX_ITEMS: 20
};

(function () {
  const cfg = window.__JH_BLOG__ || {};
  const list = document.querySelector("#blogList");
  const status = document.querySelector("#blogStatus");

  if (!list) {
    return;
  }

  const surfaceKey =
    (document.body && document.body.dataset && document.body.dataset.blogSurface) ||
    (document.body && document.body.classList.contains("page-blog-weekly") ? "weekly" : "hub");

  const surface = {
    hub: {
      emptyTitle: "Published briefings appear here",
      emptyCopy:
        "This section carries the latest written briefings from Jonathan Harris. The archive fills as each weekly post is published, with the newsletter and podcast tracking the same editorial line.",
      emptyHref: "/blog/weekly/",
      emptyLabel: "Open weekly briefings",
      loading: "Loading published briefings…",
      emptyStatus: "The next published briefing will appear here.",
      loadedStatus: (count) => `Showing ${count} published ${count === 1 ? "briefing" : "briefings"}.`
    },
    weekly: {
      emptyTitle: "The weekly archive updates here",
      emptyCopy:
        "Each weekly briefing joins this archive as it is published. Use the blog hub, newsletter, and podcast for the same sharp editorial line while the archive is still sparse.",
      emptyHref: "/blog/",
      emptyLabel: "Open the blog hub",
      loading: "Loading weekly briefings…",
      emptyStatus: "The archive is ready for the next published briefing.",
      loadedStatus: (count) => `Showing ${count} published weekly ${count === 1 ? "briefing" : "briefings"}.`
    }
  }[surfaceKey] || {
    emptyTitle: "Published posts appear here",
    emptyCopy: "Published posts appear here as they are released.",
    emptyHref: "/blog/",
    emptyLabel: "Open the blog hub",
    loading: "Loading published posts…",
    emptyStatus: "",
    loadedStatus: () => ""
  };

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

  function normaliseItem(item) {
    const slug = pickFirst(item, ["slug"]);
    const href =
      pickFirst(item, ["url", "canonical_url", "canonicalUrl", "link", "permalink", "path"]) ||
      (slug ? `/blog/posts/${encodeURIComponent(slug)}/` : "");
    const publishedAt = pickFirst(item, ["published_at", "publishedAt", "datePublished", "date", "pubDate"]);
    const dateLabel = pickFirst(item, ["date_label", "dateLabel"]) || formatPublishedDate(publishedAt);

    return {
      slug,
      title: pickFirst(item, ["title", "headline"]) || "Untitled",
      summary: pickFirst(item, ["summary", "excerpt", "description", "desc"]),
      image: pickFirst(item, ["image", "image_url", "cover", "heroImage", "hero_image"]),
      href,
      dateLabel,
      publishedAt,
      parsedDate: parseDate(publishedAt)
    };
  }

  function normaliseManifest(payload) {
    const items = Array.isArray(payload)
      ? payload
      : payload && Array.isArray(payload.items)
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

  function renderEmptyState() {
    list.innerHTML = `
      <div class="card u-s04">
        <h2 class="u-s02">${escapeHtml(surface.emptyTitle)}</h2>
        <p>${escapeHtml(surface.emptyCopy)}</p>
        <p><a class="button primary" href="${escapeHtml(surface.emptyHref)}">${escapeHtml(surface.emptyLabel)}</a></p>
      </div>`;
  }

  function render(items) {
    if (!items.length) {
      renderEmptyState();
      return;
    }

    const maxItems = Number(list.dataset.maxItems || cfg.MAX_ITEMS || 20);
    const html = items.slice(0, maxItems).map(function (item) {
      const safeTitle = escapeHtml(item.title);
      const safeSummary = escapeHtml(item.summary);
      const safeHref = escapeHtml(item.href);
      const safeImage = escapeHtml(item.image);
      const safeDateLabel = escapeHtml(item.dateLabel);
      const imageMarkup = item.image
        ? `<img class="cover" src="${safeImage}" alt="${safeTitle}" loading="lazy" decoding="async">`
        : "";
      const actionMarkup = item.href
        ? `<a class="button secondary" href="${safeHref}">Read briefing</a>`
        : "";

      return `
        <article class="card u-s05">
          ${imageMarkup}
          <div class="u-s06">
            ${safeDateLabel ? `<div class="tag u-s07">${safeDateLabel}</div>` : ""}
            <h2 class="u-s08">${safeTitle}</h2>
            ${safeSummary ? `<p class="u-s09">${safeSummary}</p>` : ""}
            ${actionMarkup}
          </div>
        </article>`;
    }).join("");

    list.innerHTML = `<div class="grid">${html}</div>`;
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
        return [];
      }

      const payload = await response.json();
      return normaliseManifest(payload);
    } catch (_error) {
      return [];
    }
  }

  async function init() {
    setStatus(surface.loading);
    const items = await fetchManifest();

    if (items.length) {
      setStatus(surface.loadedStatus(items.length));
      render(items);
      return;
    }

    setStatus(surface.emptyStatus);
    render([]);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
