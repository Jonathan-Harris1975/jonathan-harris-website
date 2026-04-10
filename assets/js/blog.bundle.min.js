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
      emptyTitle: "No local blog posts published yet",
      emptyCopy:
        "This archive populates from the AI Management Suite blog manifest. Until the next local post is published, use the written archive, newsletter, or podcast for the freshest analysis.",
      emptyHref: "/blog/weekly/",
      emptyLabel: "Open written archive",
      loading: "Loading blog posts…",
      emptyStatus: "No local weekly posts are published yet.",
      loadedStatus: "Showing the latest published local blog posts."
    },
    weekly: {
      emptyTitle: "No local blog posts published yet",
      emptyCopy:
        "This written archive stays useful between published posts, with direct paths back into the blog hub, newsletter, and podcast.",
      emptyHref: "/blog/",
      emptyLabel: "Open the blog hub",
      loading: "Loading blog posts…",
      emptyStatus: "Showing the guided written archive while the local archive is between releases.",
      loadedStatus: "Showing the latest published local blog posts."
    }
  }[surfaceKey] || {
    emptyTitle: "No local blog posts published yet",
    emptyCopy: "Check back for the next published local blog post.",
    emptyHref: "/blog/",
    emptyLabel: "Open the blog hub",
    loading: "Loading posts…",
    emptyStatus: "",
    loadedStatus: ""
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
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }

    return null;
  }

  function formatDate(value) {
    const parsed = parseDate(value);
    if (parsed) {
      return parsed.toLocaleDateString("en-GB", {
        year: "numeric",
        month: "short",
        day: "2-digit"
      });
    }

    const raw = String(value || "").trim();
    return raw ? raw.slice(0, 10) : "";
  }

  function normaliseItem(item) {
    const slug = pickFirst(item, ["slug"]);
    const href =
      pickFirst(item, ["url", "link", "canonicalUrl", "canonical_url", "permalink"]) ||
      (slug ? `/blog/posts/${encodeURIComponent(slug)}/` : "");

    return {
      slug,
      title: pickFirst(item, ["title", "headline"]) || "Untitled",
      summary: pickFirst(item, ["desc", "summary", "description", "excerpt", "dek"]),
      image: pickFirst(item, ["image", "cover", "heroImage", "hero_image"]),
      href,
      rawDate: pickFirst(item, ["pubDate", "datePublished", "date", "published", "published_at"]),
      parsedDate: parseDate(
        pickFirst(item, ["pubDate", "datePublished", "date", "published", "published_at"])
      )
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
        return item.title || item.summary || item.href || item.slug;
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
      const publishedLabel = formatDate(item.rawDate);
      const imageMarkup = item.image
        ? `<img class="cover" src="${safeImage}" alt="${safeTitle}" loading="lazy" decoding="async">`
        : "";
      const actionMarkup = item.href
        ? `<a class="button secondary" href="${safeHref}">Read post</a>`
        : "";

      return `
        <article class="card u-s05">
          ${imageMarkup}
          <div class="u-s06">
            ${publishedLabel ? `<div class="tag u-s07">${escapeHtml(publishedLabel)}</div>` : ""}
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
      setStatus(surface.loadedStatus);
      render(items);
      return;
    }

    setStatus(surface.emptyStatus);
    render([]);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
