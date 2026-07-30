import { ensureSharedChrome } from "../../_shared/chrome.js";
const DEFAULT_PODCAST_FEED_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

function slugPartsFromParams(params) {
  const raw = Array.isArray(params?.slug) ? params.slug.join("/") : String(params?.slug || "");
  return raw.replace(/^\/+|\/+$/g, "").replace(/\.(html?|json|xml)$/i, "");
}

function cleanText(value = "") {
  return String(value || "")
    .replace(/<!\[CDATA\[|\]\]>/g, "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&#x27;/gi, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function stripPodcastTiming(value = "") {
  return cleanText(value)
    .replace(/\b\d+\s*(?:-|–|—)?\s*minutes?\b/gi, "")
    .replace(/\b\d+\s*mins?\b/gi, "")
    .replace(/\b\d{1,2}:\d{2}(?::\d{2})?\b/g, "")
    .replace(/\bthis\s+week(?:[’']s)?\b/gi, "")
    .replace(/\bweekly\s+(briefing|analysis|round-?up|update)\b/gi, "$1")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\s,;:–—-]+|[\s,;:–—-]+$/g, "");
}

function escapeHtml(value = "") {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeJsonForScript(value) {
  return JSON.stringify(value, null, 2).replace(/<\/script/gi, "<\\/script");
}

function stripTags(xml = "") {
  return cleanText(xml);
}

function tagValue(xml = "", tagName = "") {
  const escaped = tagName.replace(/[.*+?^${}()|[\]\\/\-:]/g, "\\$&");
  const re = new RegExp(`<${escaped}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escaped}>`, "i");
  return stripTags(xml.match(re)?.[1] || "");
}

function attrValue(node = "", attr = "") {
  const re = new RegExp(`${attr}=["']([^"']+)["']`, "i");
  return cleanText(node.match(re)?.[1] || "");
}

function slugify(value = "") {
  return cleanText(value)
    .toLowerCase()
    .replace(/[’']/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 90);
}

function words(value = "") {
  return cleanText(value).split(/\s+/).filter(Boolean);
}

function clampWords(value = "", limit = 60) {
  const list = words(value);
  if (list.length <= limit) return cleanText(value);
  return list.slice(0, limit).join(" ").replace(/[\s,;:.]+$/, ".");
}

function normaliseUrl(value = "", request) {
  const raw = cleanText(value);
  if (!raw) return "";
  try {
    return new URL(raw, request.url).toString();
  } catch {
    return "";
  }
}

function youtubeVideoId(value = "") {
  const text = String(value || "");
  const patterns = [
    /(?:youtube\.com\/watch\?[^\s"'<>]*v=|youtu\.be\/|youtube\.com\/shorts\/|youtube\.com\/embed\/)([A-Za-z0-9_-]{6,})/i,
    /<yt:videoId[^>]*>([^<]+)<\/yt:videoId>/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return "";
}

function parseEpisodesFromFeed(xml = "", request) {
  const itemMatches = String(xml || "").match(/<item>[\s\S]*?<\/item>/gi) || [];
  return itemMatches.map((item) => {
    const enclosureNode = item.match(/<enclosure\b[^>]*>/i)?.[0] || "";
    const transcriptNode = item.match(/<podcast:transcript\b[^>]*>/i)?.[0] || "";
    const title = tagValue(item, "title");
    const description = tagValue(item, "itunes:summary") || tagValue(item, "description");
    const link = normaliseUrl(tagValue(item, "link"), request);
    const guid = tagValue(item, "guid");
    const transcriptUrl = normaliseUrl(attrValue(transcriptNode, "url"), request);
    const audioUrl = normaliseUrl(attrValue(enclosureNode, "url"), request);
    const imageNode = item.match(/<itunes:image\b[^>]*>/i)?.[0] || "";
    const imageUrl = normaliseUrl(attrValue(imageNode, "href"), request);
    return {
      title,
      description,
      link,
      guid,
      pubDate: tagValue(item, "pubDate"),
      duration: tagValue(item, "itunes:duration"),
      transcriptUrl,
      audioUrl,
      imageUrl,
      youtubeVideoId: youtubeVideoId(item),
      slug: slugify(link ? new URL(link).pathname.split("/").filter(Boolean).pop() : title),
    };
  });
}

function detectTopics(text = "") {
  const haystack = cleanText(text).toLowerCase();
  const topics = [];
  const rules = [
    ["AI governance", /governance|regulation|accountability|policy|safety|ethics/],
    ["agentic AI", /agentic|agents?|autonomous/],
    ["AI models", /model|gpt|claude|gemini|llm|openai|anthropic/],
    ["workflow automation", /workflow|automation|productivity|work/],
    ["AI costs", /cost|infrastructure|compute|investment|energy/],
    ["data and security", /data|security|privacy|risk|control/],
    ["robotics", /robot|robotics/],
    ["AI in healthcare", /health|medical|care|clinical/],
  ];
  for (const [label, pattern] of rules) {
    if (pattern.test(haystack)) topics.push(label);
  }
  return [...new Set(topics)].slice(0, 8);
}

function detectEntities(text = "") {
  const matches = cleanText(text).match(/\b(?:OpenAI|Anthropic|Google|Microsoft|NVIDIA|Meta|Apple|Amazon|Gemini|Claude|GPT|LLM|AI governance|agentic AI|robotics|finance AI|healthcare AI)\b/gi) || [];
  return [...new Set(["Jonathan Harris", "Turing's Torch", "artificial intelligence", ...matches].map(cleanText).filter(Boolean))].slice(0, 12);
}

function deriveTakeaways(episode) {
  const title = episode.title || "this AI story";
  const summary = clampWords(stripPodcastTiming(episode.description || title), 38);
  return [
    `What changed: ${summary}`,
    "Why it matters: the episode separates useful deployment signals from vendor fireworks and vague future talk.",
    "What to watch: cost, governance, data quality, security, labour impact and whether the claim survives real-world use.",
    "Who should care: teams making adoption, purchasing, policy or workflow decisions can use the episode as a reality check.",
    "Where to go next: use the transcript, topic guides and related books to follow the practical thread.",
  ].slice(0, 5);
}

async function fetchFeed(context) {
  const configured = context.env?.PODCAST_RSS_FEED_URL || context.env?.R2_PUBLIC_BASE_URL_PODCAST_RSS || DEFAULT_PODCAST_FEED_URL;
  const feedUrl = String(configured || "").endsWith(".xml") ? configured : `${String(configured || "").replace(/\/$/, "")}/turing-torch.xml`;
  const attempts = Math.max(1, Number(context.env?.PODCAST_RSS_RETRY_ATTEMPTS || 4));
  let lastError = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(feedUrl, { headers: { Accept: "application/rss+xml, application/xml, text/xml" }, signal: controller.signal });
      if (!response.ok) throw new Error(`Podcast feed fetch failed: ${response.status}`);
      const xml = await response.text();
      if (!/<item\b/i.test(xml)) throw new Error("Podcast feed returned no items");
      return { feedUrl, xml };
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 400 * (2 ** (attempt - 1))));
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastError || new Error("Podcast feed fetch failed");
}

function matchEpisode(episodes, slug, request) {
  const cleanSlug = slugify(slug);
  return episodes.find((episode) => {
    if (episode.slug === cleanSlug) return true;
    if (slugify(episode.title) === cleanSlug) return true;
    try {
      const path = new URL(episode.link || "", request.url).pathname;
      return path.replace(/\/+$/g, "").endsWith(`/podcast/episodes/${cleanSlug}`);
    } catch {
      return false;
    }
  }) || null;
}

function notFoundResponse() {
  return new Response("Podcast episode not found", {
    status: 404,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=300",
      "X-Podcast-Episode-Source": "not-in-governed-rss",
    },
  });
}

async function relatedBooksMarkup(context, episode) {
  try {
    const url = new URL("/api/v1/books.json", context.request.url);
    const req = new Request(url.toString(), { headers: { Accept: "application/json" } });
    const response = context.env?.ASSETS?.fetch ? await context.env.ASSETS.fetch(req) : await fetch(req);
    if (!response.ok) return "";
    const payload = await response.json();
    const books = Array.isArray(payload) ? payload : (Array.isArray(payload?.books) ? payload.books : []);
    const stop = new Set(["this","that","with","from","into","about","artificial","intelligence","weekly","episode","turing","torch","jonathan","harris","what","where","which","when","your","have","will","their"]);
    const tokens = new Set(cleanText(`${episode.title || ""} ${episode.description || ""}`).toLowerCase().split(/[^a-z0-9]+/).filter(x => x.length > 3 && !stop.has(x)));
    const ranked = books.map(book => {
      const hay = cleanText(`${book.title || ""} ${book.topic || ""} ${(book.tags || []).join(" ")} ${book.short || ""}`).toLowerCase();
      let score = 0; for (const token of tokens) if (hay.includes(token)) score += 1;
      return { book, score };
    }).filter(x => x.score > 0).sort((a,b) => b.score - a.score || String(a.book.title).localeCompare(String(b.book.title))).slice(0,3);
    if (!ranked.length) return "";
    const cards = ranked.map(({book}) => `<li><a href="/ebooks/${escapeHtml(book.slug)}/">${escapeHtml(book.title)}</a><span>${escapeHtml(book.short || `A related book on ${book.topic || "this topic"}.`)}</span></li>`).join("");
    return `<section class="podcast-related-books" aria-labelledby="related-books-heading"><h2 id="related-books-heading">Related books</h2><p>Chosen deterministically from the governed catalogue by overlap with this episode's title and summary.</p><ul class="link-list">${cards}</ul></section>`;
  } catch { return ""; }
}

function renderEpisodePage(episode, request, feedUrl, relatedBooks = "") {
  const title = episode.title || "Turing's Torch AI Weekly";
  const summary = clampWords(stripPodcastTiming(episode.description || "Jonathan Harris cuts through artificial intelligence stories with practical judgement, scepticism and a working-person tolerance for less nonsense."), 60);
  const canonical = episode.link || new URL(request.url).toString();
  const topics = detectTopics(`${title} ${summary}`);
  const entities = detectEntities(`${title} ${summary}`);
  const takeaways = deriveTakeaways({ ...episode, description: summary });
  const imageUrl = episode.imageUrl || "https://podcast-coverart.jonathan-harris.online/cover-art.png";
  const transcriptUrl = episode.transcriptUrl || new URL("/transcripts/", request.url).toString();
  const description = clampWords(summary, 42);
  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      { "@type": "Question", name: `What does ${title} cover?`, acceptedAnswer: { "@type": "Answer", text: summary } },
      { "@type": "Question", name: "What is the main takeaway?", acceptedAnswer: { "@type": "Answer", text: takeaways[1] || summary } },
    ],
  };
  const podcastEpisode = {
    "@context": "https://schema.org",
    "@type": "PodcastEpisode",
    name: title,
    description: summary,
    url: canonical,
    datePublished: episode.pubDate ? new Date(episode.pubDate).toISOString() : undefined,
    transcript: transcriptUrl,
    image: imageUrl,
    associatedMedia: episode.audioUrl ? { "@type": "AudioObject", contentUrl: episode.audioUrl, encodingFormat: "audio/mpeg" } : undefined,
    partOfSeries: { "@type": "PodcastSeries", name: "Turing's Torch: AI Weekly", url: new URL("/podcast/", request.url).toString() },
    author: { "@id": new URL("/#person", request.url).toString() },
    about: entities.map((name) => ({ "@type": "Thing", name })),
  };
  const cleanJsonLd = (obj) => Object.fromEntries(Object.entries(obj).filter(([, value]) => value !== undefined && value !== ""));
  return `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>${escapeHtml(title)} | Turing's Torch Podcast</title>
<meta name="description" content="${escapeHtml(description)}">
${episode.noindex ? '<meta name="robots" content="noindex,follow">' : '<meta name="robots" content="index,follow">'}
<link rel="canonical" href="${escapeHtml(canonical)}">
<meta property="og:type" content="article">
<meta property="og:title" content="${escapeHtml(title)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:image" content="${escapeHtml(imageUrl)}">
<link rel="stylesheet" href="/assets/css/site.css">
<script>document.documentElement.classList.add('js-enabled');</script>
<script type="application/ld+json">${escapeJsonForScript(cleanJsonLd(podcastEpisode))}</script>
<script type="application/ld+json">${escapeJsonForScript(faq)}</script>
</head>
<body class="page-podcast page-podcast-episode" data-page-type="podcast_episode" data-episode-slug="${escapeHtml(episode.slug || slugify(title))}">
<main id="main" class="main" role="main">
<section class="hero hero--podcast-episode">
<div class="wrap">
<p class="eyebrow">Turing's Torch podcast episode</p>
<h1>${escapeHtml(title)}</h1>
<p class="section-lead"><strong>Short answer:</strong> ${escapeHtml(summary)}</p>
<div class="actions">
${episode.audioUrl ? `<a class="button" href="${escapeHtml(episode.audioUrl)}" rel="noopener noreferrer">Listen to the episode</a>` : `<a class="button" href="/podcast/">Open podcast hub</a>`}
<a class="button secondary" href="${escapeHtml(transcriptUrl)}">Read the transcript</a>
<a class="button secondary" href="${escapeHtml(feedUrl || DEFAULT_PODCAST_FEED_URL)}" rel="noopener noreferrer">Subscribe via RSS</a>
</div>
${episode.audioUrl ? `<audio controls preload="none" data-podcast-audio data-episode-slug="${escapeHtml(episode.slug || slugify(title))}" data-placement="podcast_episode" src="${escapeHtml(episode.audioUrl)}"></audio>` : ""}
</div>
</section>
<section class="section"><div class="wrap card">
<h2>What changed?</h2>
<p>${escapeHtml(summary)}</p>
<h2>Key takeaways</h2>
<ul>${takeaways.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
<h2>Entities and topics discussed</h2>
<ul>${entities.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
<h2>Transcript preview and next steps</h2>
<nav class="actions" aria-label="Episode links">
<a class="button secondary" href="${escapeHtml(transcriptUrl)}">Transcript preview</a>
<a class="button secondary" href="/topics/">Related AI topic guides</a>
<a class="button secondary" href="/book-finder/">Find a related Jonathan Harris book</a>
<a class="button secondary" href="/newsletter/">Join AI Edge</a>
</nav>
${relatedBooks}
${episode.youtubeVideoId ? `<h2>Watch this episode</h2><div class="responsive-media"><iframe src="https://www.youtube-nocookie.com/embed/${escapeHtml(episode.youtubeVideoId)}" title="${escapeHtml(title)} video" loading="lazy" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div>` : ""}
<h2>Share this episode</h2>
<nav class="share-links" aria-label="Share episode">
<a href="https://twitter.com/intent/tweet?url=${encodeURIComponent(canonical)}&text=${encodeURIComponent(title)}" target="_blank" rel="noopener noreferrer">Share on X</a>
<a href="https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(canonical)}" target="_blank" rel="noopener noreferrer">LinkedIn</a>
<a href="https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(canonical)}" target="_blank" rel="noopener noreferrer">Facebook</a>
<button type="button" data-copy-url="${escapeHtml(canonical)}">Copy link</button>
</nav>
</div></section>
</main>
<script defer src="/assets/js/funnel-events.min.js"></script>
<script defer src="/assets/js/share.min.js"></script>
<script defer src="/assets/js/site-ui.min.js"></script>
</body>
</html>`;
}

export async function onRequest(context) {
  const slug = slugPartsFromParams(context.params);
  if (!slug) return context.next();

  let feedUrl = DEFAULT_PODCAST_FEED_URL;
  let episode = null;
  try {
    const loaded = await fetchFeed(context);
    feedUrl = loaded.feedUrl;
    episode = matchEpisode(parseEpisodesFromFeed(loaded.xml, context.request), slug, context.request);
  } catch {}

  // Episode routes are governed exclusively by the live AIMS RSS feed.
  // Never manufacture a page for an arbitrary/future slug. If AIMS has not
  // published the episode into the feed, the episode does not exist publicly.
  if (!episode) return notFoundResponse();

  const relatedBooks = await relatedBooksMarkup(context, episode);

  const pageHtml = await ensureSharedChrome(
    context,
    renderEpisodePage(episode, context.request, feedUrl, relatedBooks),
  );
  return new Response(pageHtml, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=1800, stale-while-revalidate=86400",
      "X-Podcast-Episode-Source": "aims-rss-feed",
    },
  });
}
