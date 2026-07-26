import { ensureSharedChrome } from "../_shared/chrome.js";
const MANIFEST_PATH = "/data/podcast-episodes.json";
const DEFAULT_PODCAST_FEED_URL = "https://podcast-rss-feeds.jonathan-harris.online/turing-torch.xml";

function slugPartsFromParams(params) { const v = Array.isArray(params.slug) ? params.slug : [params.slug]; return v.filter(Boolean); }
function escapeHtml(v="") { return String(v||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function cleanText(v="") { return String(v||"").replace(/<!\[CDATA\[|\]\]>/g,"").replace(/<script[\s\S]*?<\/script>/gi," ").replace(/<style[\s\S]*?<\/style>/gi," ").replace(/<[^>]+>/g," ").replace(/&quot;/gi,'"').replace(/&#39;|&#x27;/gi,"'").replace(/&amp;/gi,"&").replace(/\s+/g," ").trim(); }
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
  return items.map(item=>{const transcriptNode=(item.match(/<podcast:transcript\b[^>]*>/i)||[])[0]||"", enclosureNode=(item.match(/<enclosure\b[^>]*>/i)||[])[0]||"", link=tagValue(item,"link"), title=tagValue(item,"title"), transcriptUrl=normaliseManifestUrl(attrValue(transcriptNode,"url"),request), audioUrl=normaliseManifestUrl(attrValue(enclosureNode,"url"),request), description=tagValue(item,"itunes:summary")||tagValue(item,"description");return {title,summary:description,date:tagValue(item,"pubDate"),slug:slugify(link?link.split('/').filter(Boolean).pop():title),episode_url:normaliseManifestUrl(link,request),transcript_url:transcriptUrl,audio_url:audioUrl,session_id:transcriptUrl?transcriptUrl.split('/').pop().replace(/\.(html|htm|txt)$/i,""):"",topics:detectTopics(`${title} ${description}`),entities:detectEntities(`${title} ${description}`)}});
}
async function fetchFeedEpisodes(context) {
  const configured=context.env?.PODCAST_RSS_FEED_URL||context.env?.R2_PUBLIC_BASE_URL_PODCAST_RSS||DEFAULT_PODCAST_FEED_URL, url=String(configured).endsWith('.xml')?String(configured):`${String(configured).replace(/\/$/,"")}/turing-torch.xml`, attempts=Math.max(1,Number(context.env?.PODCAST_RSS_RETRY_ATTEMPTS||4)); let last;
  for(let i=0;i<attempts;i++){const c=new AbortController(),timer=setTimeout(()=>c.abort(),12000);try{const r=await fetch(url,{headers:{Accept:"application/rss+xml, application/xml, text/xml"},signal:c.signal});if(!r.ok)throw new Error(`HTTP ${r.status}`);const xml=await r.text();if(!/<item\b/i.test(xml))throw new Error('no podcast items');return parseFeedEpisodes(xml,context.request)}catch(e){last=e;if(i+1<attempts)await new Promise(resolve=>setTimeout(resolve,400*(2**i)))}finally{clearTimeout(timer)}}
  throw last||new Error('podcast feed unavailable');
}

async function relatedBookMarkup(context, episode) {
  if(!episode)return"";
  try{
    const url=new URL('/api/v1/books.json',context.request.url),req=new Request(url.toString(),{headers:{Accept:'application/json'}}),response=context.env?.ASSETS?.fetch?await context.env.ASSETS.fetch(req):await fetch(req);if(!response.ok)return"";
    const payload=await response.json(),books=Array.isArray(payload)?payload:(Array.isArray(payload?.books)?payload.books:[]),stop=new Set(['this','that','with','from','into','about','artificial','intelligence','weekly','episode','turing','torch','jonathan','harris','what','where','which','when','your','have','will','their']),tokens=new Set(cleanText(`${episode.title||''} ${episode.summary||''}`).toLowerCase().split(/[^a-z0-9]+/).filter(x=>x.length>3&&!stop.has(x)));
    const ranked=books.map(book=>{const hay=cleanText(`${book.title||''} ${book.topic||''} ${(book.tags||[]).join(' ')} ${book.short||''}`).toLowerCase();let score=0;for(const token of tokens)if(hay.includes(token))score++;return{book,score}}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score||String(a.book.title).localeCompare(String(b.book.title))).slice(0,3);
    if(!ranked.length)return"";
    return `<h2>Related books</h2><p>Chosen deterministically from the governed catalogue by overlap with this episode's title and summary.</p><ul>${ranked.map(({book})=>`<li><a href="/ebooks/${escapeHtml(book.slug)}/">${escapeHtml(book.title)}</a> - ${escapeHtml(book.short||book.topic||'Related reading')}</li>`).join('')}</ul>`;
  }catch{return""}
}

function buildAeoPrelude(episode, request, relatedBooks="") {
  if(!episode)return"";
  const title=firstNonEmpty(episode.title,"Turing's Torch AI Weekly transcript"), summary=clamp(firstNonEmpty(episode.summary,`Jonathan Harris examines ${title} in plain English, focusing on what changed, what is useful, and where the evidence or incentives deserve a closer look.`),72), takeaways=Array.isArray(episode.key_takeaways)&&episode.key_takeaways.length?episode.key_takeaways.map(cleanText).filter(Boolean).slice(0,5):defaultTakeaways(episode), topics=Array.from(new Set([...(Array.isArray(episode.topics)?episode.topics:[]),...detectTopics(`${title} ${summary}`)].map(cleanText).filter(Boolean))).slice(0,8), entities=Array.from(new Set([...(Array.isArray(episode.entities)?episode.entities:[]),...detectEntities(`${title} ${summary}`)].map(cleanText).filter(Boolean))).slice(0,12), episodePath=episode.slug?`/podcast/episodes/${episode.slug}/`:"/podcast/", canonicalEpisodeUrl=normaliseManifestUrl(episode.episode_url,request)||new URL(episodePath,request.url).toString(), transcriptUrl=normaliseManifestUrl(episode.transcript_url,request)||request.url, audioUrl=normaliseManifestUrl(episode.audio_url,request);
  const episodeSchema={"@context":"https://schema.org","@type":"PodcastEpisode","name":title,"url":canonicalEpisodeUrl,"datePublished":firstNonEmpty(episode.date)||undefined,"description":summary,"transcript":transcriptUrl,"partOfSeries":{"@type":"PodcastSeries","name":"Turing's Torch: AI Weekly","url":new URL('/podcast/',request.url).toString()},"author":{"@id":new URL('/#person',request.url).toString()},"about":[...topics,...entities].map(name=>({"@type":"Thing","name":name}))};
  const transcriptSchema={"@context":"https://schema.org","@type":["CreativeWork","Transcript"],"additionalType":"https://schema.org/Transcript","name":`Transcript: ${title}`,"url":transcriptUrl,"isPartOf":{"@type":"PodcastEpisode","url":canonicalEpisodeUrl,"name":title},"author":{"@id":new URL('/#person',request.url).toString()},"description":summary,"inLanguage":"en-GB"};
  const serialise=o=>JSON.stringify(o,(k,v)=>v===undefined?undefined:v).replace(/<\/script/gi,"<\\/script");
  return `
<section class="transcript-aeo-summary" aria-label="Transcript summary and answer-engine index">
  <p class="transcript-kicker">Turing's Torch transcript</p>
  <h1>${escapeHtml(title)}</h1>
  <p class="transcript-summary"><strong>Episode summary:</strong> ${escapeHtml(summary)}</p>
  <nav class="actions transcript-listen-actions" aria-label="Listen to this episode"><a class="button" href="${escapeHtml(episodePath)}">Listen to this episode</a><a class="button secondary" href="/podcast/">Podcast home</a><a class="button secondary" href="/newsletter/">Join AI Edge</a></nav>
  ${audioUrl?`<audio controls preload="none" data-podcast-audio data-episode-slug="${escapeHtml(episode.slug||'')}" data-placement="transcript_top" src="${escapeHtml(audioUrl)}"></audio>`:""}
  <nav class="transcript-topic-index" aria-label="Transcript topic index"><strong>On this page:</strong> <a href="#what-changed">What changed</a> <a href="#key-takeaways">Takeaways</a> <a href="#named-entities">Named entities</a> <a href="#topic-index">Topics</a> <a href="#transcript-body">Full transcript</a></nav>
  <h2 id="what-changed">What changed this week?</h2><p>${escapeHtml(summary)}</p>
  <h2 id="key-takeaways">Five key takeaways</h2><ul>${takeaways.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2 id="named-entities">Key named entities</h2><ul>${entities.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2 id="topic-index">Topic index</h2><ul>${topics.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>
  <h2>Related reading and listening</h2><nav class="actions" aria-label="Related transcript links"><a class="button secondary" href="${escapeHtml(episodePath)}">Listen to this episode</a><a class="button secondary" href="/evidence/">Evidence guides</a><a class="button secondary" href="/book-finder/">Book finder</a><a class="button secondary" href="/newsletter/">Join AI Edge</a></nav>${relatedBooks}
</section>
<script type="application/ld+json">${serialise(episodeSchema)}</script>
<script type="application/ld+json">${serialise(transcriptSchema)}</script>`;
}
function enhanceTranscriptHtml(html,prelude){if(!prelude)return html;let out=html;if(!out.includes('transcript-aeo-summary')){const insertion=`${prelude}\n<div id="transcript-body" tabindex="-1"></div>`;if(/<main\b[^>]*>/i.test(out))out=out.replace(/<main\b[^>]*>/i,m=>`${m}\n${insertion}`);else if(/<body\b[^>]*>/i.test(out))out=out.replace(/<body\b[^>]*>/i,m=>`${m}\n<main id="main">\n${insertion}`).replace(/<\/body>/i,'</main>\n</body>');else out=`${insertion}\n${out}`}if(!out.includes('/assets/js/funnel-events.min.js'))out=out.replace(/<\/body>/i,'<script defer src="/assets/js/funnel-events.min.js"></script></body>');return out}

export async function onRequest(context) {
  const {params,env,request}=context, rawKey=slugPartsFromParams(params).join('/'); if(!rawKey)return context.next();
  let object=await env.TRANSCRIPTS_BUCKET.get(rawKey); if(!object&&!rawKey.match(/\.(html|htm|txt|json|xml)$/i))object=await env.TRANSCRIPTS_BUCKET.get(`${rawKey}.html`); if(!object)return context.next();
  const headers=new Headers(), contentType=object.httpMetadata?.contentType??"text/html; charset=utf-8"; headers.set('Content-Type',contentType);headers.set('Cache-Control','public, max-age=3600, stale-while-revalidate=86400');headers.set('X-Transcript-AEO-Enhancement','enabled');if(object.etag)headers.set('ETag',object.etag);if(request.headers.get('If-None-Match')===object.etag)return new Response(null,{status:304,headers});if(!contentType.includes('text/html'))return new Response(object.body,{status:200,headers});
  let episodes=await fetchEpisodeManifest(context), episode=findEpisodeForTranscript(episodes,rawKey,request); if(!episode){try{episodes=await fetchFeedEpisodes(context);episode=findEpisodeForTranscript(episodes,rawKey,request)}catch{}}
  const relatedBooks=await relatedBookMarkup(context,episode),html=await object.text(), enhanced=enhanceTranscriptHtml(html,buildAeoPrelude(episode,request,relatedBooks)), withChrome=await ensureSharedChrome(context,enhanced); return new Response(withChrome,{status:200,headers});
}
