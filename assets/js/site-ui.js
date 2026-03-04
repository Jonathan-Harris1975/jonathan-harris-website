(function(){
  if (window.__JH_SITE_UI_INIT__) return;
  window.__JH_SITE_UI_INIT__ = true;

  const HEADER_URL = "/assets/partials/header.html";
  const FOOTER_TARGET_ID = "siteFooter";
  const FOOTER_URL = "/assets/partials/footer.html";
  const LOADER_ID = "pageLoader";
  const SITE_CSS_HREF = "/assets/css/site.css";

  function ensureStyles(){
    try{
      const head = document.head || document.getElementsByTagName("head")[0];
      if (!head) return;

      // Ensure global stylesheet is present even on older standalone pages.
      const hasSiteCss = !!document.querySelector(`link[rel="stylesheet"][href="${SITE_CSS_HREF}"],link[rel="stylesheet"][href$="${SITE_CSS_HREF}"]`);
      if (!hasSiteCss){
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = SITE_CSS_HREF;
        head.appendChild(link);
      }

      // Minimal critical styles so navigation + skip link don't look like 1998 if CSS fails to load.
      if (!document.getElementById("jh-ui-inline")){
        const style = document.createElement("style");
        style.id = "jh-ui-inline";
        style.textContent = `
          
          .skip-link{position:absolute;left:-999px;top:auto;width:1px;height:1px;overflow:hidden;z-index:3000;}
          .skip-link:focus{left:12px;top:12px;width:auto;height:auto;padding:10px 12px;background:#111827;color:#fff;border-radius:10px;outline:2px solid rgba(79,70,229,0.9);}
          .jh-header{position:relative;z-index:2500;}
          .jh-header__inner{max-width:1200px;margin:0 auto;padding:10px 15px;display:flex;align-items:center;justify-content:center;}
          .jh-header.jh-header--overlay{position:absolute;left:0;right:0;bottom:-18px;z-index:2600;}
          .jh-header.jh-header--overlay .jh-header__inner{padding:0 12px;}
          .jh-header.jh-header--overlay .jh-topnav{background:rgba(13,20,32,0.92);backdrop-filter:saturate(1.2) blur(10px);border:1px solid rgba(255,255,255,0.12);border-radius:16px;box-shadow:0 10px 28px rgba(0,0,0,0.35);padding:10px 14px;}
          .jh-topnav{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:16px;}
          .jh-topnav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:14px;line-height:1.1;padding:6px 0;border-bottom:1px solid transparent;}
          .jh-topnav a:hover,.jh-topnav a:focus{border-bottom-color:rgba(199,210,254,0.75);outline:none;}
          @media (max-width: 520px){
            .jh-header__inner{padding:10px 12px;}
            .jh-topnav{gap:12px;}
            .jh-topnav a{font-size:13px;}
          }

        `;
        head.appendChild(style);
      }
    }catch(_){}
  }

  function hideLoader(){
    const el = document.getElementById(LOADER_ID);
    if (!el) return;
    el.classList.add("hide");
    window.setTimeout(() => { try { el.remove(); } catch(_){} }, 350);
  }

  async function injectHeader(){
    // Avoid duplicate headers if a page already includes one.
    if (document.querySelector("header.jh-header")) return;
    try{
      const res = await fetch(HEADER_URL, { cache: "no-store" });
      if (!res.ok) throw new Error("header fetch failed");
      const html = await res.text();
      const wrap = document.createElement("div");
      wrap.innerHTML = html;

      const headerEl = wrap.firstElementChild;
      if (!headerEl) return;

      // Prefer mounting navigation at the bottom of the page "hero" so it feels
      // like part of the header section rather than a separate strip.
      const heroMount = document.querySelector(
        'section[role="region"][aria-label="Page Header"], header.hero, header[role="banner"]'
      );

      if (heroMount && !heroMount.querySelector('header.jh-header')){
        // Make the hero a positioning context for the floating nav.
        try{
          const cs = window.getComputedStyle(heroMount);
          if (!cs || cs.position === 'static') heroMount.style.position = 'relative';

          // Ensure there's breathing room for the floating nav to sit at the bottom.
          const pb = cs && cs.paddingBottom ? parseFloat(cs.paddingBottom) : 0;
          if (!Number.isNaN(pb) && pb < 40) heroMount.style.paddingBottom = '54px';
        }catch(_){
          heroMount.style.position = 'relative';
          heroMount.style.paddingBottom = '54px';
        }

        headerEl.classList.add('jh-header--overlay');
        heroMount.appendChild(headerEl);
        return;
      }

      // Fallback: insert near the top of the body.
      // Ensure skip-link stays first if present
      const first = document.body.firstElementChild;
      if (first && first.classList && first.classList.contains("skip-link")){
        first.insertAdjacentElement("afterend", headerEl);
      }else{
        document.body.prepend(headerEl);
      }
    }catch(_){
      // Header is optional. Pages still work.
    }
  }

  function pageHasRealFooter(){
    // If a page already hard-codes a footer, don't inject another one.
    const footers = Array.from(document.querySelectorAll("footer"));
    if (!footers.length) return false;

    // Ignore footers that might be inside templates or hidden blocks
    // but treat any visible page footer as "real".
    for (const f of footers){
      if (f.closest(`#${FOOTER_TARGET_ID}`)) continue; // footer already inside mount
      return true;
    }
    return false;
  }

  async function injectFooter(){
    const mount = document.getElementById(FOOTER_TARGET_ID);
    if (!mount) return;

    if (pageHasRealFooter()){
      // Prevent the empty mount from creating spacing / duplicate footer perception.
      try { mount.remove(); } catch(_){}
      return;
    }

    try{
      const res = await fetch(FOOTER_URL, { cache: "no-store" });
      if (!res.ok) throw new Error("footer fetch failed");
      const html = await res.text();
      mount.innerHTML = html;
    }catch(_){
      mount.innerHTML = '<footer style="background-color:#0D1420; color:#D1D5DB; font-family:Arial, Helvetica, sans-serif; font-size:14px; padding:20px 15px; text-align:center;" role="contentinfo" aria-label="Website Footer"><div style="max-width:1200px; margin:0 auto;">© 2026 Jonathan Harris. All rights reserved.</div></footer>';
    }
  }

  function init(){
    ensureStyles();
    injectHeader();
    injectFooter();
    hideLoader();
  }

  if (document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  }else{
    init();
  }
})();