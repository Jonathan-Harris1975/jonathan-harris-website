const MANIFEST_PATH = "/data/podcast-episodes.json";
const DEFAULT_PODCAST_FEED_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

function slugPartsFromParams(params) { const v = Array.isArray(params.slug) ? params.slug : [params.slug]; return v.filter(Boolean); }
function escapeHtml(v="") { return String(v||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function cleanText(v="") { return String(v||"").replace(/<!\[CDATA\[|\]\]>/g,"").replace(/<script[\s\S]*?<\/script>/gi," ").replace(/<style[\s\S]*?<\/style>/gi," ").replace(/<[^>]+>/g," ").replace(/&amp;/gi,"&").replace(/&quot;/gi,'"').replace(/&#39;|&#x27;/gi,"'").replace(/\s+/g," ").trim(); }
function firstNonEmpty(...values) { for (const value of values) { const text=cleanText(value); if(text) return text; } return ""; }
function slugify(v="") { return cleanText(v).toLowerCase().replace(/[’']/g,"").replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,100); }
function tagValue(xml,name){const escaped=name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"),m=String(xml).match(new RegExp(`<${escaped}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escaped}>`,`i`));return cleanText(m?.[1]||"")}
function attrValue(node,name){return cleanText(String(node||"").match(new RegExp(`${name}=["']([^"']+)["']`,`i`))?.[1]||"")}
function clamp(v,words=70){const p=cleanText(v).split(/\s+/).filter(Boolean);return p.length<=words?cleanText(v):`${p.slice(0,words).join(" ").replace(/[\s,;:.]+$/g,"")}.`}
function normaliseManifestUrl(value, request) { const text=firstNonEmpty(value); if(!text) return ""; try{return new URL(text,request.url).toString()}catch{return ""} }

function defaultTakeaways(episode) {
  const title=firstNonEmpty(episode?.title,"this episode");
  return [
    `Why ${title} matters beyond the usual artificial intelligence headline noise.`,
    "What changed for work, policy, business, creators or ordinary users this week.",
    "Where the technology looks useful, where the claims need testing, and what evidence matters next.",
    "Which power, money, data, labour, security and control questions sit underneath the announcement.",
    "How the episode connects back to Jonathan Harris's wider artificial intelligence books, glossary and topic guides.",
  ];
}

function detectTopics(text="") {
  const hay=cleanText(text).toLowerCase(), out=[];
  const rules=[["AI governance",/governance|regulation|policy|accountability|ethics|safety/],["AI models",/model|llm|gpt|claude|gemini|openai|anthropic/],["AI agents",/agentic|agents?|autonomous/],["work and automation",/work|job|automation|productivity/],["data and security",/data|privacy|security|cyber|risk/],["AI costs and infrastructure",/cost|compute|chip|energy|infrastructure|investment/],["AI in healthcare",/health|medical|clinical|care/],["robotics",/robot|robotics/]];
  for(const [name,re] of rules) if(re.test(hay)) out.push(name);
  return [...new Set(out)].slice(0,8);
}
function detectEntities(text="") { const matches=cleanText(text).match(/\b(?:OpenAI|Anthropic|Google|Microsoft|NVIDIA|Meta|Apple|Amazon|Gemini|Claude|GPT|LLM|DeepMind)\b/gi)||[]; return [...new Set(["Jonathan Harris","Turing's Torch AI Weekly","artificial intelligence",...matches].map(cleanText).filter(Boolean))].slice(0,12); }

async function fetchEpisodeManifest(context) {
  try { const url=new URL(MANIFEST_PATH,context.request.url), req=new Request(url.toString(),{headers:{Accept:"application/json"}}), response=context.env?.ASSETS?.fetch?await context.env.ASSETS.fetch(req):await fetch(req); if(!response.ok)return[]; const data=await response.json(); return Array.isArray(data)?data:[]; } catch { return []; }
}
function findEpisodeForTranscript(episodes, rawKey, request) {
  const key=String(rawKey||"").replace(/^\/+/,""), absolute=new URL(`/transcripts/${key}`,request.url).toString(), bare=key.replace(/\.(html|htm|txt)$/i,"");
  return episodes.find((episode)=>{const u=normaliseManifestUrl(episode?.transcript_url,request);return u===absolute||u.endsWith(`/${key}`)||firstNonEmpty(episode?.session_id)===bare})||null;
}

function parseFeedEpisodes(xml, request) {
  const items=String(xml||"").match(/<item\b[\s\S]*?<\/item>/gi)||[];
  return items.map(item=>{const transcriptNode=(item.match(/<podcast:transcript\b[^>]*>/i)||[])[0]||"", link=tagValue(item,"link"), title=tagValue(item,"title"), transcriptUrl=normaliseManifestUrl(attrValue(transcriptNode,"url"),request), description=tagValue(item,"itunes:summary")||tagValue(item,"description");return {title,summary:description,date:tagValue(item,"pubDate"),slug:slugify(link?link.split('/').filter(Boolean).pop():title),transcript_url:transcriptUrl,session_id:transcriptUrl?transcriptUrl.split('/').pop().replace(/\.(html|htm|txt)$/i,""):"",topics:detectTopics(`${title} ${description}`),entities:detectEntities(`${title} ${description}`)}});
}
async function fetchFeedEpisodes(context) {
  const configured=context.env?.PODCAST_RSS_FEED_URL||context.env?.R2_PUBLIC_BASE_URL_PODCAST_RSS||DEFAULT_PODCAST_FEED_URL, url=String(configured).endsWith('.xml')?String(configured):`${String(configured).replace(/\/$/,"")}/turing-torch.xml`, attempts=Math.max(1,Number(context.env?.PODCAST_RSS_RETRY_ATTEMPTS||4)); let last;
  for(let i=0;i<attempts;i++){const c=new AbortController(),timer=setTimeout(()=>c.abort(),12000);try{const r=await fetch(url,{headers:{Accept:"application/rss+xml, application/xml, text/xml"},signal:c.signal});if(!r.ok)throw new Error(`HTTP ${r.status}`);const xml=await r.text();if(!/<item\b/i.test(xml))throw new Error('no podcast items');return parseFeedEpisodes(xml,context.request)}catch(e){last=e;if(i+1<attempts)await new Promise(resolve=>setTimeout(resolve,400*(2**i)))}finally{clearTimeout(timer)}}
  throw last||new Error('podcast feed unavailable');
}

function buildAeoPrelude(episode, request) {
  if(!episode)return"";
  const title=firstNonEmpty(episode.title,"Turing's Torch AI Weekly transcript"), summary=clamp(firstNonEmpty(episode.summary,`Jonathan Harris examines ${title} in plain English, focusing on what changed, what is useful, and where the evidence or incentives deserve a closer look.`),72), takeaways=Array.isArray(episode.key_takeaways)&&episode.key_takeaways.length?episode.key_takeaways.map(cleanText).filter(Boolean).slice(0,5):defaultTakeaways(episode), topics=Array.from(new Set([...(Array.isArray(episode.topics)?episode.topics:[]),...detectTopics(`${title} ${summary}`)].map(cleanText).filter(Boolean))).slice(0,8), entities=Array.from(new Set([...(Array.isArray(episode.entities)?episode.entities:[]),...detectEntities(`${title} ${summary}`)].map(cleanText).filter(Boolean))).slice(0,12), episodePath=episode.slug?`/podcast/episodes/${episode.slug}/`:"/podcast/", canonicalEpisodeUrl=new URL(episodePath,request.url).toString(), transcriptUrl=normaliseManifestUrl(episode.transcript_url,request)||request.url;
  const episodeSchema={"@context":"https://schema.org","@type":"PodcastEpisode","name":title,"url":canonicalEpisodeUrl,"datePublished":firstNonEmpty(episode.date)||undefined,"description":summary,"transcript":transcriptUrl,"partOfSeries":{"@type":"PodcastSeries","name":"Turing's Torch: AI Weekly","url":new URL('/podcast/',request.url).toString()},"author":{"@type":"Person","name":"Jonathan Harris","url":new URL('/bio/',request.url).toString()},"about":[...topics,...entities].map(name=>({"@type":"Thing","name":name}))};
  const transcriptSchema={"@context":"https://schema.org","@type":["CreativeWork","Transcript"],"additionalType":"https://schema.org/Transcript","name":`Transcript: ${title}`,"url":transcriptUrl,"isPartOf":{"@type":"PodcastEpisode","url":canonicalEpisodeUrl,"name":title},"author":{"@type":"Person","name":"Jonathan Harris","url":new URL('/bio/',request.url).toString()},"description":summary,"inLanguage":"en-GB"};
  const serialise=o=>JSON.stringify(o,(k,v)=>v===undefined?undefined:v).replace(/<\/script/gi,"<\\/script");
  return `
<section class="transcript-aeo-summary" aria-label="Transcript summary and answer-engine index">
  <p class="transcript-kicker">Turing's Torch transcript</p>
  <h1>${escapeHtml(title)}</h1>
  <p class="transcript-summary"><strong>Episode summary:</strong> ${escapeHtml(summary)}</p>
  <nav class="transcript-topic-index" aria-label="Transcript topic index"><strong>On this page:</strong> <a href="#what-changed">What changed</a> <a href="#key-takeaways">Takeaways</a> <a href="#named-entities">Named entities</a> <a href="#topic-index">Topics</a> <a href="#transcript-body">Full transcript</a></nav>
  <h2 id="what-changed">What changed this week?</h2><p>${escapeHtml(summary)}</p>
  <h2 id="key-takeaways">Five key takeaways</h2><ul>${takeaways.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2 id="named-entities">Key named entities</h2><ul>${entities.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2 id="topic-index">Topic index</h2><ul>${topics.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2>Related reading and listening</h2><nav class="actions" aria-label="Related transcript links"><a class="button secondary" href="${escapeHtml(episodePath)}">Episode page</a><a class="button secondary" href="/topics/">AI topic guides</a><a class="button secondary" href="/ebooks/">Related books</a><a class="button secondary" href="/glossary/">AI glossary</a></nav>
</section>
<script type="application/ld+json">${serialise(episodeSchema)}</script>
<script type="application/ld+json">${serialise(transcriptSchema)}</script>`;
}
function enhanceTranscriptHtml(html,prelude){if(!prelude||html.includes('transcript-aeo-summary'))return html;const insertion=`${prelude}\n<div id="transcript-body" tabindex="-1"></div>`;if(/<main\b[^>]*>/i.test(html))return html.replace(/<main\b[^>]*>/i,m=>`${m}\n${insertion}`);if(/<body\b[^>]*>/i.test(html))return html.replace(/<body\b[^>]*>/i,m=>`${m}\n<main id="main">\n${insertion}`).replace(/<\/body>/i,'</main>\n</body>');return `${insertion}\n${html}`}

export async function onRequest(context) {
  const {params,env,request}=context, rawKey=slugPartsFromParams(params).join('/'); if(!rawKey)return context.next();
  let object=await env.TRANSCRIPTS_BUCKET.get(rawKey); if(!object&&!rawKey.match(/\.(html|htm|txt|json|xml)$/i))object=await env.TRANSCRIPTS_BUCKET.get(`${rawKey}.html`); if(!object)return context.next();
  const headers=new Headers(), contentType=object.httpMetadata?.contentType??"text/html; charset=utf-8"; headers.set('Content-Type',contentType);headers.set('Cache-Control','public, max-age=3600, stale-while-revalidate=86400');headers.set('X-Transcript-AEO-Enhancement','enabled');if(object.etag)headers.set('ETag',object.etag);if(request.headers.get('If-None-Match')===object.etag)return new Response(null,{status:304,headers});if(!contentType.includes('text/html'))return new Response(object.body,{status:200,headers});
  let episodes=await fetchEpisodeManifest(context), episode=findEpisodeForTranscript(episodes,rawKey,request); if(!episode){try{episodes=await fetchFeedEpisodes(context);episode=findEpisodeForTranscript(episodes,rawKey,request)}catch{}}
  const html=await object.text(), enhanced=enhanceTranscriptHtml(html,buildAeoPrelude(episode,request)); return new Response(enhanced,{status:200,headers});
}
