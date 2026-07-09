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
  const escaped = tagName.replace(/[.*+?^${}()|[\]\\/-:]/g, "\\$&");
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
  const summary = clampWords(episode.description || title, 38);
  return [
    `What changed: ${summary}`,
    "Why it matters: the episode separates useful deployment signals from vendor fireworks and vague future talk.",
    "What to watch: cost, governance, data quality, security, labour impact and whether the claim survives real-world use.",
    "Where to go next: use the transcript, topic guides and related books to follow the practical thread.",
  ].slice(0, 4);
}

async function fetchFeed(context) {
  const configured = context.env?.PODCAST_RSS_FEED_URL || context.env?.R2_PUBLIC_BASE_URL_PODCAST_RSS || DEFAULT_PODCAST_FEED_URL;
  const feedUrl = String(configured || "").endsWith(".xml") ? configured : `${String(configured || "").replace(/\/$/, "")}/turing-torch.xml`;
  const response = await fetch(feedUrl, { headers: { Accept: "application/rss+xml, application/xml, text/xml" } });
  if (!response.ok) throw new Error(`Podcast feed fetch failed: ${response.status}`);
  return { feedUrl, xml: await response.text() };
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

function fallbackEpisodeFromSlug(slug, request) {
  const title = slug
    .split("-")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ") || "Archived Turing's Torch episode";
  return {
    title,
    description: "This archived Turing's Torch podcast route is retained for crawl continuity. Use the podcast hub and transcript archive for the current canonical episode, audio and transcript paths.",
    link: new URL(`/podcast/episodes/${slug}/`, request.url).toString(),
    guid: slug,
    transcriptUrl: new URL("/transcripts/", request.url).toString(),
    audioUrl: "",
    imageUrl: "https://podcast-coverart.jonathan-harris.online/cover-art.png",
    noindex: true,
  };
}

function renderEpisodePage(episode, request, feedUrl) {
  const title = episode.title || "Turing's Torch AI Weekly";
  const summary = clampWords(episode.description || "Jonathan Harris cuts through the week's artificial intelligence stories with practical judgement, scepticism and a working-person tolerance for less nonsense.", 60);
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
    author: { "@type": "Person", name: "Jonathan Harris", url: new URL("/bio/", request.url).toString() },
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
<body class="page-podcast page-podcast-episode">
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
</div>
</section>
<section class="section"><div class="wrap card">
<h2>What changed this week?</h2>
<p>${escapeHtml(summary)}</p>
<h2>Key takeaways</h2>
<ul>${takeaways.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
<h2>Entities and topics discussed</h2>
<ul>${entities.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
<h2>Transcript preview and next steps</h2>
<nav class="actions" aria-label="Episode links">
<a class="button secondary" href="${escapeHtml(transcriptUrl)}">Transcript preview</a>
<a class="button secondary" href="/topics/">Related AI topic guides</a>
<a class="button secondary" href="/ebooks/">Related Jonathan Harris books</a>
<a class="button secondary" href="/newsletter/">Join the newsletter</a>
</nav>
</div></section>
</main>
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

  if (!episode) episode = fallbackEpisodeFromSlug(slug, context.request);

  return new Response(renderEpisodePage(episode, context.request, feedUrl), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": episode.noindex ? "public, max-age=900" : "public, max-age=1800, stale-while-revalidate=86400",
      "X-Podcast-Episode-Source": episode.noindex ? "fallback-canonical-continuity" : "aims-rss-feed",
    },
  });
}
