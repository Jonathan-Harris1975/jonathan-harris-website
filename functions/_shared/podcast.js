const DEFAULT_FEED_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

export function cleanText(value = "") {
  return String(value || "").replace(/<!\[CDATA\[|\]\]>/g, "").replace(/<[^>]+>/g, " ")
    .replace(/&amp;/gi, "&").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">").replace(/&quot;/gi, '"')
    .replace(/&#39;|&#x27;/gi, "'").replace(/\s+/g, " ").trim();
}
function tagValue(xml = "", tagName = "") { const n=tagName.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"); return cleanText(xml.match(new RegExp(`<${n}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${n}>`,`i`))?.[1]||""); }
function attrValue(node = "", attr = "") { return cleanText(node.match(new RegExp(`${attr}=["']([^"']+)["']`,`i`))?.[1]||""); }
function slugify(v="") { return cleanText(v).toLowerCase().replace(/[’']/g,"").replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,90); }
function normaliseUrl(value="", request) { const raw=cleanText(value); if(!raw)return""; try{return new URL(raw,request.url).toString()}catch{return""} }
function firstSentence(value="") { const text=cleanText(value); return text.split(/(?<=[.!?])\s+/)[0]||text; }
function youtubeId(raw="") { for(const p of [/(?:youtube\.com\/watch\?[^\s"'<>]*v=|youtu\.be\/|youtube\.com\/(?:shorts|embed)\/)([A-Za-z0-9_-]{6,})/i,/<yt:videoId[^>]*>([^<]+)<\/yt:videoId>/i]){const m=String(raw).match(p);if(m?.[1])return m[1].trim()}return"" }

export function parsePodcastItems(xml="", request) {
  return (String(xml||"").match(/<item\b[\s\S]*?<\/item>/gi)||[]).map(item=>{
    const enclosure=item.match(/<enclosure\b[^>]*>/i)?.[0]||"";
    const transcript=item.match(/<podcast:transcript\b[^>]*>/i)?.[0]||"";
    const title=tagValue(item,"title"), description=tagValue(item,"itunes:summary")||tagValue(item,"description"), link=normaliseUrl(tagValue(item,"link"),request);
    const slug=slugify((link.split('/').filter(Boolean).pop())||title);
    return {slug,title,description,teaser:firstSentence(description),episode_url:link||new URL(`/podcast/episodes/${slug}/`,request.url).toString(),transcript_url:normaliseUrl(attrValue(transcript,"url"),request),audio_url:normaliseUrl(attrValue(enclosure,"url"),request),published_at:tagValue(item,"pubDate"),duration:tagValue(item,"itunes:duration"),youtube_video_id:youtubeId(item),guid:tagValue(item,"guid")};
  }).filter(x=>x.title);
}

export async function fetchPodcastEpisodes(env, request, limit=3) {
  const configured=env?.PODCAST_RSS_FEED_URL||env?.R2_PUBLIC_BASE_URL_PODCAST_RSS||DEFAULT_FEED_URL;
  const feedUrl=String(configured).endsWith('.xml')?String(configured):`${String(configured).replace(/\/$/,"")}/turing-torch.xml`;
  const attempts=Math.max(1,Number(env?.PODCAST_RSS_RETRY_ATTEMPTS||4)); let lastError;
  for(let i=0;i<attempts;i++){
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
    try{const r=await fetch(feedUrl,{headers:{Accept:"application/rss+xml, application/xml, text/xml"},signal:controller.signal});if(!r.ok)throw new Error(`HTTP ${r.status}`);const xml=await r.text();const episodes=parsePodcastItems(xml,request);if(!episodes.length)throw new Error('no items');return{feedUrl,episodes:episodes.slice(0,limit)}}
    catch(e){lastError=e;if(i+1<attempts)await new Promise(resolve=>setTimeout(resolve,400*(2**i)))}finally{clearTimeout(timer)}
  }
  throw lastError||new Error('feed unavailable');
}
