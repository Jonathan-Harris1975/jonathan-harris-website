import { fetchPodcastEpisodes } from "./_shared/podcast.js";

const SITE_ORIGIN = "https://jonathan-harris.online";

function cleanText(value = "") {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function publishedDate(value = "") {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString().slice(0, 10);
}

function transcriptKey(transcriptUrl = "") {
  if (!transcriptUrl) return "";
  try {
    return new URL(transcriptUrl).pathname.split("/").filter(Boolean).pop() || "";
  } catch {
    return "";
  }
}

function mergeByLocation(existing = [], additions = []) {
  const ordered = [];
  const positions = new Map();
  for (const item of [...existing, ...additions]) {
    if (!item || typeof item !== "object") continue;
    const key = cleanText(item.loc || item.url || item.path);
    if (!key) continue;
    if (positions.has(key)) {
      ordered[positions.get(key)] = { ...ordered[positions.get(key)], ...item };
    } else {
      positions.set(key, ordered.length);
      ordered.push(item);
    }
  }
  return ordered;
}

function episodeRecord(episode) {
  const path = `/podcast/episodes/${encodeURIComponent(episode.slug)}/`;
  return {
    family: "podcast-episode",
    title: cleanText(episode.title),
    path,
    loc: `${SITE_ORIGIN}${path}`,
    lastmod: publishedDate(episode.published_at),
    source: "live-podcast-rss",
    repo_path: "",
    summary: cleanText(episode.teaser || episode.description),
    entity: "Turing's Torch AI Weekly episode",
  };
}

function transcriptRecord(episode) {
  const key = transcriptKey(episode.transcript_url);
  if (!key) return null;
  const path = `/transcripts/${encodeURIComponent(decodeURIComponent(key))}`;
  return {
    family: "podcast-transcript",
    title: `Transcript: ${cleanText(episode.title)}`,
    path,
    loc: `${SITE_ORIGIN}${path}`,
    lastmod: publishedDate(episode.published_at),
    source: "live-podcast-rss",
    repo_path: "",
    summary: cleanText(episode.teaser || episode.description),
    entity: "Turing's Torch AI Weekly transcript",
    episode_url: `${SITE_ORIGIN}/podcast/episodes/${encodeURIComponent(episode.slug)}/`,
  };
}

export async function onRequest(context) {
  const response = await context.next();
  const contentType = response.headers.get("content-type") || "";
  if (!response.ok || !contentType.includes("json")) return response;

  let payload;
  try {
    payload = await response.json();
  } catch {
    return response;
  }

  try {
    const { episodes } = await fetchPodcastEpisodes(context.env, context.request, 100);
    const episodeRows = episodes.filter((episode) => episode?.slug).map(episodeRecord);
    const transcriptRows = episodes.map(transcriptRecord).filter(Boolean);
    payload.podcast_episodes = mergeByLocation(payload.podcast_episodes, episodeRows);
    payload.transcripts = mergeByLocation(payload.transcripts, transcriptRows);
    payload.generated_utc = new Date().toISOString();
  } catch {
    // Keep the checked-in index usable during a temporary podcast-feed outage.
  }

  const headers = new Headers(response.headers);
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "public, max-age=300, s-maxage=300");
  headers.set("x-llm-index-podcast-rss", "enabled");
  return new Response(JSON.stringify(payload, null, 2) + "\n", {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
