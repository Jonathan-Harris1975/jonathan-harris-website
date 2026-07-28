async function assetText(context, path) {
  try {
    const url = new URL(path, context.request.url);
    const request = new Request(url.toString(), { headers: { Accept: "text/html" } });
    const response = context.env?.ASSETS?.fetch ? await context.env.ASSETS.fetch(request) : await fetch(request);
    return response.ok ? await response.text() : "";
  } catch {
    return "";
  }
}

function replaceHeader(html, header) {
  if (!header) return html;
  const marker = /<!--\s*JH_SITE_SHELL_HEADER_START[\s\S]*?<!--\s*JH_SITE_SHELL_HEADER_END\s*-->/i;
  if (marker.test(html)) return html.replace(marker, header.trim());

  const withSkip = /<a\b[^>]*class=["'][^"']*skip-link[^"']*["'][^>]*>[\s\S]*?<\/a>\s*<header\b[^>]*(?:id=["']site-primary-nav["']|class=["'][^"']*jh-header[^"']*["'])[^>]*>[\s\S]*?<\/header>/i;
  if (withSkip.test(html)) return html.replace(withSkip, header.trim());

  const headerOnly = /<header\b[^>]*(?:id=["']site-primary-nav["']|class=["'][^"']*jh-header[^"']*["'])[^>]*>[\s\S]*?<\/header>/i;
  if (headerOnly.test(html)) return html.replace(headerOnly, header.trim());

  return html.replace(/<body\b[^>]*>/i, match => `${match}\n${header.trim()}`);
}

function replaceFooter(html, footer) {
  if (!footer) return html;
  const marker = /<!--\s*JH_SITE_SHELL_FOOTER_START[\s\S]*?<!--\s*JH_SITE_SHELL_FOOTER_END\s*-->/i;
  if (marker.test(html)) return html.replace(marker, footer.trim());

  const existing = /<footer\b[^>]*class=["'][^"']*site-footer[^"']*["'][^>]*>[\s\S]*?<\/footer>/i;
  if (existing.test(html)) return html.replace(existing, footer.trim());

  return html.replace(/<\/body>/i, `${footer.trim()}\n</body>`);
}

function ensureCurrentSharedAssets(html) {
  let out = html
    .replace(/\s*<link\b[^>]*href=["'](?:https:\/\/jonathan-harris\.online)?\/assets\/css\/site\.css[^"']*["'][^>]*>\s*/ig, "\n")
    .replace(/\s*<script\b[^>]*src=["'](?:https:\/\/jonathan-harris\.online)?\/assets\/js\/site-ui\.min\.js[^"']*["'][^>]*><\/script>\s*/ig, "\n");

  if (/<\/head>/i.test(out)) {
    out = out.replace(/<\/head>/i, '<link href="/assets/css/site.css" rel="stylesheet"/>\n</head>');
  }
  return out.replace(/<\/body>/i, '<script defer src="/assets/js/site-ui.min.js"></script>\n</body>');
}

export async function ensureSharedChrome(context, html) {
  let out = String(html || "");
  if (!/<body\b/i.test(out)) return out;

  const [header, footer] = await Promise.all([
    assetText(context, "/assets/partials/header.html"),
    assetText(context, "/assets/partials/footer.html"),
  ]);

  out = replaceHeader(out, header);
  out = replaceFooter(out, footer);
  out = ensureCurrentSharedAssets(out);
  return out;
}
