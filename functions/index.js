import { fetchPodcastEpisodes } from "./_shared/podcast.js";
function esc(v=''){return String(v||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
export async function onRequest(context){const response=await context.next();if(!response.headers.get('content-type')?.includes('text/html'))return response;
let text=await response.text();try{const{episodes}=await fetchPodcastEpisodes(context.env,context.request,1),ep=episodes[0];if(ep){const block=`<artic\
le class="podcast-latest-card" data-episode-slug="${esc(ep.slug)}"><h3>${esc(ep.title)}</h3><p>${esc(ep.teaser)}</p><div class="actions"><a class="but\
ton" href="${esc(ep.episode_url)}">Listen</a>${ep.transcript_url?`<a class="button secondary" href="${esc(ep.transcript_url)}">Read transcript</a>`:''}\
</div></article>`;text=text.replace(/<div data-podcast-latest-server>[\s\S]*?<\/div>/i,`<div data-podcast-latest-server>${block}</div>`)}}catch{}return new Response(text,
{status:response.status,statusText:response.statusText,headers:response.headers})}
