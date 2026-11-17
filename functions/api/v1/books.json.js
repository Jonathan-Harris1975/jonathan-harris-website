// The v1 public books.json contract is generated from current KDP D1 on every request.
// Preserve exact legacy field shape, related links and search ranking tokens.
// Never return static snapshots or expose private D1/R2 fields.
import { onRequestGet as getD1Ebooks } from "./ebooks.json.js";

const STOPWORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "book", "by", "for", "from", "how", "in", "into", "is", "it", "its", "of", "on", "or", "our", "that", "the", "this",
  "through", "to", "what", "when", "where", "why", "with", "your", "you", "ai", "artificial", "intelligence",
]);
const STEM_SUFFIXES = [
  "ization", "isation", "ational", "ability", "ibility", "ation", "ition", "fulness", "ousness", "iveness", "ingly", "ments", "ement", "ment", "able",
  "ible", "ness", "ship", "ance", "ence", "ally", "fully", "less", "iest", "ies", "ied", "ing", "ers", "er", "ed", "ly", "ity", "s",
];
const LEGACY_KEYS = [
  "id", "key", "title", "short", "short_description", "cover", "main_image", "tags", "filter", "keywords", "buy_url", "buy_target_url", "slug", "asin",
  "pages", "datePublished", "dateModified", "canonical_url", "buy_route", "buy_route_full", "topic_url", "related_slugs", "title_tokens",
  "topic_tokens",
];

function stemToken(token) {
  for(const suffix of STEM_SUFFIXES)if(token.length>suffix.length+2&&token.endsWith(suffix))return token.slice(0,-suffix.length);
  return token;
}
function significantTokens(value) {
  const tokens=String(value||"").toLowerCase().match(/[a-z0-9]+/g)||[];
  return new Set(tokens.filter(t=>t.length>2&&!STOPWORDS.has(t)).map(stemToken));
}
function tokenGroups(book) {
  return {topic:significantTokens(book.filter),title:significantTokens(book.title),
    tags:new Set(book.tags.flatMap(tag=>[...significantTokens(tag)])),
    keywords:new Set(book.keywords.flatMap(kw=>[...significantTokens(kw)]))};
}
function intersectionCount(left,right) {let n=0;for(const v of left)if(right.has(v))n++;return n;}
function toLegacyBooks(books) {
  if (!Array.isArray(books)||books.length===0)throw new Error("Missing canonical D1 catalogue");
  const seenIds=new Set(),seenSlugs=new Set();
  const mapped=books.map((book,index)=>{
    if(!book||typeof book!=="object")throw new Error("Invalid canonical book "+index);
    for(const field of ["id","key","title","short","cover","main_image","filter","buy_url","slug","asin","datePublished","dateModified","canonical_url","buy_route","buy_route_full","topic_url"]) {
      if(book[field]===null||book[field]===undefined||String(book[field]).trim()==="")throw new Error("Invalid canonical book field "+field);
    }
    for(const field of ["tags","keywords"])if(!Array.isArray(book[field]))throw new Error("Invalid canonical book list "+field);
    if(!Number.isSafeInteger(Number(book.id))||Number(book.id)<1||!Number.isSafeInteger(Number(book.pages))||Number(book.pages)<1)throw new Error("Invalid canonical book identity or pages");
    if(seenIds.has(Number(book.id))||seenSlugs.has(book.slug))throw new Error("Duplicate canonical book identity");
    seenIds.add(Number(book.id));seenSlugs.add(book.slug);
    const published=Date.parse(book.datePublished),modified=Date.parse(book.dateModified);
    if(!Number.isFinite(published)||!Number.isFinite(modified)||modified<published)throw new Error("Invalid canonical book chronology");
    return {id:Number(book.id),key:String(book.key),title:book.title,short:book.short,short_description:book.short,
      cover:book.cover,main_image:book.main_image,tags:book.tags,filter:book.filter,keywords:book.keywords,
      buy_url:book.buy_url,buy_target_url:book.buy_url,slug:book.slug,asin:book.asin,pages:Number(book.pages),
      datePublished:book.datePublished,dateModified:book.dateModified,canonical_url:book.canonical_url,
      buy_route:book.buy_route,buy_route_full:book.buy_route_full,topic_url:book.topic_url,
      related_slugs:[],title_tokens:[],topic_tokens:[]};
  });
  const grouped=new Map(mapped.map(book=>[book.slug,tokenGroups(book)]));
  for(const current of mapped) {
    const base=grouped.get(current.slug);
    current.title_tokens=[...base.title].sort();
    current.topic_tokens=[...base.topic].sort();
    const ranked=mapped.filter(candidate=>candidate.slug!==current.slug).map(candidate=>{
      const other=grouped.get(candidate.slug),same=Number(candidate.filter===current.filter);
      const title=intersectionCount(base.title,other.title),topic=intersectionCount(base.topic,other.topic),
        tags=intersectionCount(base.tags,other.tags),keywords=intersectionCount(base.keywords,other.keywords);
      return {candidate,same,score:same*100+title*35+topic*30+tags*18+keywords*8,title,grouped:topic+tags,keywords};
    });
    ranked.sort((a,b) =>
      b.same-a.same || b.score-a.score || b.title-a.title ||
      b.grouped-a.grouped || b.keywords-a.keywords ||
      (a.candidate.title.toLowerCase() < b.candidate.title.toLowerCase() ? -1 :
        a.candidate.title.toLowerCase() > b.candidate.title.toLowerCase() ? 1 : 0)
    );
    current.related_slugs=ranked.slice(0,4).map(item=>item.candidate.slug);
    if(Object.keys(current).sort().join("|")!==LEGACY_KEYS.slice().sort().join("|"))throw new Error("Legacy contract key drift");
  }
  return mapped;
}

// The Pages asset owns curated editorial copy and its release timestamp.
// D1 owns current book facts, including pages, ASINs, title and purchase URLs.
async function overlayGovernedEditorial(context, books) {
  if (!context.env?.ASSETS || typeof context.env.ASSETS.fetch !== "function") {
    throw new Error("Cloudflare Pages ASSETS binding is required");
  }
  const response = await context.env.ASSETS.fetch(
    "https://assets.local/assets/js/books.json"
  );
  if (!response.ok) throw new Error("Governed editorial asset unavailable");
  const governed = await response.json();
  if (!Array.isArray(governed) || governed.length !== books.length) {
    throw new Error("Governed editorial count mismatch");
  }
  const byId = new Map();
  for (const record of governed) {
    if (!record || !Number.isSafeInteger(record.id) || byId.has(record.id)) {
      throw new Error("Invalid governed editorial book identity");
    }
    byId.set(record.id, record);
  }
  return books.map(book => {
    const editorial = byId.get(book.id);
    if (!editorial || editorial.slug !== book.slug) {
      throw new Error("Governed editorial slug or ID mismatch");
    }
    for (const field of ["short", "short_description", "dateModified"]) {
      if (typeof editorial[field] !== "string" || !editorial[field].trim()) {
        throw new Error("Invalid governed editorial field " + field);
      }
    }
    const buildTime = Date.parse(editorial.dateModified);
    const databaseTime = Date.parse(book.dateModified);
    if (!Number.isFinite(buildTime) || !Number.isFinite(databaseTime)) {
      throw new Error("Invalid catalogue modification time");
    }
    return {
      ...book,
      short: editorial.short,
      short_description: editorial.short_description,
      dateModified: databaseTime > buildTime
        ? book.dateModified : editorial.dateModified,
    };
  });
}

const HEADERS = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
export async function onRequestGet(context) {
  try {
    const response = await getD1Ebooks(context);
    if (!response.ok) return response;
    const payload = await response.json();
    const projected = toLegacyBooks(payload.books);
    const compatible = await overlayGovernedEditorial(context, projected);
    return Response.json(compatible, { headers: HEADERS });
  } catch (error) {
    console.error("KDP legacy books.json mapping failed", error);
    return Response.json({ error: "Ebook catalogue is temporarily unavailable." }, { status: 503, headers: HEADERS });
  }
}
