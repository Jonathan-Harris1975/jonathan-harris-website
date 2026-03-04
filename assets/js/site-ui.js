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
          .jh-header{position:sticky;top:0;z-index:2500;background:rgba(13,20,32,0.92);backdrop-filter:saturate(1.2) blur(10px);border-bottom:1px solid rgba(255,255,255,0.10);}
          .jh-header__inner{max-width:1200px;margin:0 auto;padding:12px 15px;display:flex;align-items:center;gap:14px;}
          .jh-logo img{display:block;height:auto;}
          .jh-nav{margin-left:auto;display:flex;align-items:center;gap:14px;}
          .jh-nav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:14px;padding:8px 10px;border-radius:12px;}
          .jh-nav a:hover,.jh-nav a:focus{background:rgba(255,255,255,0.08);outline:none;}
          .jh-nav__toggle{margin-left:auto;display:none;align-items:center;justify-content:center;width:44px;height:44px;border-radius:999px;border:1px solid rgba(255,255,255,0.18);background:rgba(17,24,39,0.45);color:#E5E7EB;}
          .jh-nav__toggle-bars{width:18px;height:2px;background:currentColor;position:relative;display:block;border-radius:2px;}
          .jh-nav__toggle-bars:before,.jh-nav__toggle-bars:after{content:"";position:absolute;left:0;width:18px;height:2px;background:currentColor;border-radius:2px;}
          .jh-nav__toggle-bars:before{top:-6px;}
          .jh-nav__toggle-bars:after{top:6px;}
          @media (max-width: 860px){
            .jh-nav__toggle{display:flex;}
            .jh-nav{position:fixed;inset:64px 12px auto 12px;display:none;flex-direction:column;align-items:stretch;gap:6px;padding:10px;border-radius:18px;background:rgba(13,20,32,0.97);border:1px solid rgba(255,255,255,0.10);box-shadow:0 16px 40px rgba(0,0,0,0.35);}
            .jh-nav.is-open{display:flex;}
            .jh-nav a{padding:12px 12px;}
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

      // Ensure skip-link stays first if present
      const first = document.body.firstElementChild;
      if (first && first.classList && first.classList.contains("skip-link")){
        first.insertAdjacentElement("afterend", headerEl);
      }else{
        document.body.prepend(headerEl);
      }

      // Hamburger toggle
      const btn = document.querySelector(".jh-nav__toggle");
      const nav = document.getElementById("jhPrimaryNav");
      if (btn && nav){
        const setState = (open) => {
          btn.setAttribute("aria-expanded", open ? "true" : "false");
          btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
          nav.classList.toggle("is-open", !!open);
          document.documentElement.classList.toggle("jh-nav-open", !!open);
        };

        btn.addEventListener("click", () => {
          const open = btn.getAttribute("aria-expanded") === "true";
          setState(!open);
        });

        document.addEventListener("keydown", (e) => {
          if (e.key === "Escape") setState(false);
        });

        nav.addEventListener("click", (e) => {
          const t = e.target;
          if (t && t.tagName === "A") setState(false);
        });
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