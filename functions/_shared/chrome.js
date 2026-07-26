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

export async function ensureSharedChrome(context, html) {
  let out = String(html || "");
  if (!/<body\b/i.test(out)) return out;
  if (!out.includes('id="site-primary-nav"')) {
    const header = await assetText(context, "/assets/partials/header.html");
    if (header) out = out.replace(/<body\b[^>]*>/i, match => `${match}\n${header}`);
  }
  if (!out.includes('class="site-footer"')) {
    const footer = await assetText(context, "/assets/partials/footer.html");
    if (footer) out = out.replace(/<\/body>/i, `${footer}\n</body>`);
  }
  if (!out.includes('/assets/js/site-ui.min.js')) {
    out = out.replace(/<\/body>/i, '<script defer src="/assets/js/site-ui.min.js"></script>\n</body>');
  }
  return out;
}
