function esc(value = "") {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
function clamp(value = "", max = 190) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= max ? text : `${text.slice(0, max - 1).replace(/[\s,;:.-]+$/g, "")}…`;
}
function wrap(value, width = 42, maxLines = 5) {
  const words = String(value || "").split(/\s+/).filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > width && line) {
      lines.push(line);
      line = word;
      if (lines.length >= maxLines) break;
    } else line = next;
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (words.join(" ").length > lines.join(" ").length && lines.length) lines[lines.length - 1] = `${lines[lines.length - 1].replace(/[.…]+$/g, "")}…`;
  return lines;
}
export function onRequestGet({ request }) {
  const url = new URL(request.url);
  const title = clamp(url.searchParams.get("title") || "Turing's Torch AI Weekly", 120);
  const quote = clamp(url.searchParams.get("quote") || "AI analysis without the hype.", 220);
  const titleLines = wrap(title, 34, 3);
  const quoteLines = wrap(quote, 48, 5);
  const titleSvg = titleLines.map((line, i) => `<text x="86" y="${180 + i * 58}" font-family="Arial,Helvetica,sans-serif" font-size="46" font-weight="\
800" fill="#93C5FD">${esc(line)}</text>`).join("");
  const quoteStart = 390;
  const quoteSvg = quoteLines.map((line, i) => `<text x="86" y="${quoteStart + i * 48}" font-family="Arial,Helvetica,sans-serif" font-size="31" font-w\
eight="600" fill="#F8FAFC">${esc(line)}</text>`).join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#0D1420"\
/><rect x="64" y="64" width="1072" height="502" rx="34" fill="#111827" stroke="#334155" stroke-width="2"/><text x="86" y="118" font-family="Arial,Helv\
etica,sans-serif" font-size="23" font-weight="700" letter-spacing="2" fill="#CBD5E1">JONATHAN-HARRIS.ONLINE · AI BRIEFING</text>${titleSvg}<line x1="8\
6" x2="1114" y1="350" y2="350" stroke="#334155" stroke-width="2"/>${quoteSvg}<text x="86" y="535" font-family="Arial,Helvetica,sans-serif" font-size="\
22" fill="#94A3B8">Turing's Torch · plain-English AI analysis</text></svg>`;
  return new Response(svg, { headers: { "Content-Type": "image/svg+xml; charset=utf-8", "Cache-Control": "public, max-age=86400", "Content-Disposition\
": "inline; filename=ai-briefing-share-card.svg" } });
}
