const MANIFEST_PATH = "/data/podcast-episodes.json";

function slugPartsFromParams(params) {
  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug];
  return slugParts.filter(Boolean);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function firstNonEmpty(...values) {
  for (const value of values) {
    const text = cleanText(value);
    if (text) return text;
  }
  return "";
}

function defaultTakeaways(episode) {
  const title = firstNonEmpty(episode?.title, "this episode");
  return [
    `Why ${title} matters beyond the usual artificial intelligence headline noise.`,
    "What the story changes for work, policy, business, creators, and ordinary users.",
    "Where the technology looks useful, where the claims need testing, and what to watch next.",
    "Which power, money, data, labour, and control questions sit underneath the announcement.",
    "How the episode connects back to Jonathan Harris's wider artificial intelligence books and topic guides.",
  ];
}

function normaliseManifestUrl(value, request) {
  const text = firstNonEmpty(value);
  if (!text) return "";
  try {
    return new URL(text, request.url).toString();
  } catch {
    return "";
  }
}

async function fetchEpisodeManifest(context) {
  try {
    const url = new URL(MANIFEST_PATH, context.request.url);
    const request = new Request(url.toString(), { headers: { Accept: "application/json" } });
    const response = context.env?.ASSETS?.fetch
      ? await context.env.ASSETS.fetch(request)
      : await fetch(request);
    if (!response.ok) return [];
    const data = await response.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function findEpisodeForTranscript(episodes, rawKey, request) {
  const normalisedKey = String(rawKey || "").replace(/^\/+/, "");
  const path = `/transcripts/${normalisedKey}`;
  const absolute = new URL(path, request.url).toString();
  const withoutExtension = normalisedKey.replace(/\.(html|htm|txt)$/i, "");
  return episodes.find((episode) => {
    const transcriptUrl = normaliseManifestUrl(episode?.transcript_url, request);
    return transcriptUrl === absolute
      || transcriptUrl.endsWith(`/${normalisedKey}`)
      || firstNonEmpty(episode?.session_id) === withoutExtension;
  }) || null;
}

function buildAeoPrelude(episode, request) {
  if (!episode) return "";
  const title = firstNonEmpty(episode.title, "Turing's Torch AI Weekly transcript");
  const summary = firstNonEmpty(
    episode.summary,
    `Jonathan Harris examines ${title} in plain English, cutting through artificial intelligence hype and focusing on what matters for work, policy, business, and everyday users.`
  );
  const takeaways = Array.isArray(episode.key_takeaways) && episode.key_takeaways.length
    ? episode.key_takeaways.map(cleanText).filter(Boolean).slice(0, 5)
    : defaultTakeaways(episode);
  const entities = Array.from(new Set([
    "Jonathan Harris",
    "Turing's Torch AI Weekly",
    "artificial intelligence",
    ...(Array.isArray(episode.entities) ? episode.entities : []),
    ...(Array.isArray(episode.topics) ? episode.topics : []),
  ].map(cleanText).filter(Boolean))).slice(0, 10);
  const episodePath = episode.slug ? `/podcast/episodes/${episode.slug}/` : "/podcast/";
  const canonicalEpisodeUrl = new URL(episodePath, request.url).toString();
  const transcriptUrl = normaliseManifestUrl(episode.transcript_url, request) || request.url;
  const schema = {
    "@context": "https://schema.org",
    "@type": "PodcastEpisode",
    "name": title,
    "url": canonicalEpisodeUrl,
    "datePublished": firstNonEmpty(episode.date),
    "description": summary,
    "transcript": transcriptUrl,
    "partOfSeries": {
      "@type": "PodcastSeries",
      "name": "Turing's Torch: AI Weekly",
      "url": new URL("/podcast/", request.url).toString(),
    },
    "author": { "@type": "Person", "name": "Jonathan Harris", "url": new URL("/bio/", request.url).toString() },
  };

  return `
<section class="transcript-aeo-summary" aria-label="Transcript summary and answer-engine index">
  <p class="transcript-kicker">Turing's Torch transcript</p>
  <h1>${escapeHtml(title)}</h1>
  <p class="transcript-summary"><strong>Short answer:</strong> ${escapeHtml(summary)}</p>
  <h2>What changed this week?</h2>
  <p>${escapeHtml(summary)}</p>
  <h2>Key takeaways</h2>
  <ul>${takeaways.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2>Entities and topics discussed</h2>
  <ul>${entities.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2>Transcript sections</h2>
  <nav aria-label="Transcript section links">
    <a href="#transcript-body">Jump to transcript body</a>
    <a href="${escapeHtml(episodePath)}">Open episode page</a>
    <a href="/podcast/">Podcast hub</a>
    <a href="/topics/">AI topic guides</a>
    <a href="/ebooks/">Related books</a>
  </nav>
</section>
<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function enhanceTranscriptHtml(html, prelude) {
  if (!prelude || html.includes("transcript-aeo-summary")) return html;
  const bodyAnchor = '<div id="transcript-body"></div>';
  const insertion = `${prelude}\n${bodyAnchor}`;
  if (/<main\b[^>]*>/i.test(html)) {
    return html.replace(/<main\b[^>]*>/i, (match) => `${match}\n${insertion}`);
  }
  if (/<body\b[^>]*>/i.test(html)) {
    return html.replace(/<body\b[^>]*>/i, (match) => `${match}\n<main id="main">\n${insertion}`)
      .replace(/<\/body>/i, "</main>\n</body>");
  }
  return `${insertion}\n${html}`;
}

export async function onRequest(context) {
  const { params, env, request } = context;
  const rawKey = slugPartsFromParams(params).join("/");

  if (!rawKey) {
    return context.next();
  }

  let object = await env.TRANSCRIPTS_BUCKET.get(rawKey);

  if (!object && !rawKey.match(/\.(html|htm|txt|json|xml)$/i)) {
    object = await env.TRANSCRIPTS_BUCKET.get(rawKey + ".html");
  }

  if (!object) {
    return context.next();
  }

  const headers = new Headers();
  const contentType = object.httpMetadata?.contentType ?? "text/html; charset=utf-8";
  headers.set("Content-Type", contentType);
  headers.set("Cache-Control", "public, max-age=3600, stale-while-revalidate=86400");
  headers.set("X-Transcript-AEO-Enhancement", "enabled");

  if (object.etag) {
    headers.set("ETag", object.etag);
  }

  const ifNoneMatch = request.headers.get("If-None-Match");
  if (ifNoneMatch && ifNoneMatch === object.etag) {
    return new Response(null, { status: 304, headers });
  }

  if (!contentType.includes("text/html")) {
    return new Response(object.body, { status: 200, headers });
  }

  const episodes = await fetchEpisodeManifest(context);
  const episode = findEpisodeForTranscript(episodes, rawKey, request);
  const html = await object.text();
  const enhanced = enhanceTranscriptHtml(html, buildAeoPrelude(episode, request));
  return new Response(enhanced, { status: 200, headers });
}
