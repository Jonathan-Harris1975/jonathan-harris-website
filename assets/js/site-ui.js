(function(){
  if (window.__JH_SITE_UI_INIT__) return;
  window.__JH_SITE_UI_INIT__ = true;

  const HEADER_URL = "/assets/partials/header.html";
  const FOOTER_TARGET_ID = "siteFooter";
  const FOOTER_URL = "/assets/partials/footer.html";
  const LOADER_ID = "pageLoader";
  const SITE_CSS_HREF = "/assets/css/site.css";

  // Optional web font (keeps the brand minimal, just cleaner)
  const FONT_PRECONNECT_1 = "https://fonts.googleapis.com";
  const FONT_PRECONNECT_2 = "https://fonts.gstatic.com";
  const FONT_STYLESHEET = "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap";

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

      // Web font (safe no-op if blocked)
      if (!document.querySelector(`link[rel="stylesheet"][href="${FONT_STYLESHEET}"]`)){
        const p1 = document.createElement("link");
        p1.rel = "preconnect";
        p1.href = FONT_PRECONNECT_1;
        head.appendChild(p1);

        const p2 = document.createElement("link");
        p2.rel = "preconnect";
        p2.href = FONT_PRECONNECT_2;
        p2.crossOrigin = "anonymous";
        head.appendChild(p2);

        const f = document.createElement("link");
        f.rel = "stylesheet";
        f.href = FONT_STYLESHEET;
        head.appendChild(f);
      }

      // Minimal critical styles so navigation + skip link don't look like 1998 if CSS fails to load.
      if (!document.getElementById("jh-ui-inline")){
        const style = document.createElement("style");
        style.id = "jh-ui-inline";
        style.textContent = `
          .skip-link{position:absolute;left:-999px;top:auto;width:1px;height:1px;overflow:hidden;z-index:3000;}
          .skip-link:focus{left:12px;top:12px;width:auto;height:auto;padding:10px 12px;background:#111827;color:#fff;border-radius:12px;outline:2px solid rgba(79,70,229,0.9);}

          /* Hero-host + nav pill fallback */
          .jh-hero-host{position:relative;padding-bottom:54px;}
          .jh-header{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);z-index:2500;background:rgba(13,20,32,0.78);backdrop-filter:saturate(1.2) blur(10px);border:1px solid rgba(255,255,255,0.14);border-radius:999px;box-shadow:0 18px 40px rgba(0,0,0,0.22);}
          .jh-header__inner{padding:10px 14px;display:flex;align-items:center;justify-content:center;}
          .jh-topnav{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:14px;}
          .jh-topnav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:13px;line-height:1.1;padding:6px 6px;border-radius:10px;}
          .jh-topnav a:hover,.jh-topnav a:focus{background:rgba(255,255,255,0.08);outline:none;}
          .jh-topnav a[aria-current="page"]{background:rgba(79,70,229,0.20);border:1px solid rgba(79,70,229,0.35);}
          @media (max-width: 520px){.jh-hero-host{padding-bottom:64px;}.jh-header{bottom:10px;}.jh-header__inner{padding:10px 12px;}.jh-topnav{gap:10px;}.jh-topnav a{font-size:12.5px;}}
        `;
        head.appendChild(style);
      }
    }catch(_){}
  }

  function hideLoader(){
    try{
      const loader = document.getElementById(LOADER_ID);
      if (loader) {
        loader.style.display = "none";
        loader.setAttribute("aria-hidden", "true");
        loader.setAttribute("aria-live", "off");
      }
    }catch(_){}
  }

  function ensureSkipLink(){
    try{
      if (document.querySelector(".skip-link")) return;
      const a = document.createElement("a");
      a.className = "skip-link";
      a.href = "#main";
      a.textContent = "Skip to main content";
      document.body.insertBefore(a, document.body.firstChild);
    }catch(_){}
  }

  function ensureMainId(){
    try{
      let main = document.getElementById("main");
      if (main) return;

      main = document.querySelector("main") || document.querySelector('[role="main"]');
      if (main && !main.id) main.id = "main";
    }catch(_){}
  }

  function findHeroHost(){
    // Prefer the existing hero/header section so nav feels native.
    return (
      document.querySelector('section[aria-label="Page Header"]') ||
      document.querySelector('header.hero') ||
      document.querySelector('.hero') ||
      document.querySelector('header[role="banner"]') ||
      null
    );
  }

  function markActiveNav(container){
    try{
      const path = (location.pathname || "/").replace(/\/+$/, "/");
      const links = container.querySelectorAll("a[href]");
      links.forEach(a=>{
        try{
          const href = a.getAttribute("href");
          if (!href || href.indexOf("http") === 0 || href.indexOf("mailto:") === 0) return;

          const target = href.replace(/\/+$/, "/");
          const isActive = (target === "/" && path === "/") || (target !== "/" && path.startsWith(target));
          if (isActive) a.setAttribute("aria-current","page");
          else a.removeAttribute("aria-current");
        }catch(_){}
      });
    }catch(_){}
  }

  async function injectHeader(){
    try{
      // Avoid duplicate headers
      if (document.querySelector(".jh-header")) return;

      const res = await fetch(HEADER_URL, { cache: "force-cache" });
      if (!res.ok) return;
      const html = await res.text();

      const wrap = document.createElement("div");
      wrap.innerHTML = html.trim();
      const header = wrap.firstElementChild;
      if (!header) return;

      const hero = findHeroHost();
      if (hero){
        hero.classList.add("jh-hero-host");
        hero.appendChild(header); // bottom-floating pill (CSS positions it)
      }else{
        document.body.insertBefore(header, document.body.firstChild);
      }

      markActiveNav(header);
    }catch(_){}
  }

  function pageAlreadyHasFooter(){
    return !!document.querySelector("footer") && !document.getElementById(FOOTER_TARGET_ID);
  }

  async function injectFooter(){
    try{
      // If the page already includes a real footer, don't inject another.
      const hasRealFooter = !!document.querySelector("footer");
      const target = document.getElementById(FOOTER_TARGET_ID);

      if (hasRealFooter){
        // Prevent double-footers and remove the mount point if it exists.
        if (target) target.remove();
        return;
      }

      if (!target) return;

      const res = await fetch(FOOTER_URL, { cache: "force-cache" });
      if (!res.ok) return;
      const html = await res.text();
      target.innerHTML = html;
    }catch(_){}
  }


  function prettyLabel(seg){
    if (!seg) return "";
    const map = {
      "ebooks":"eBooks",
      "book":"Book",
      "podcast":"Podcast",
      "newsletter":"Newsletter",
      "blog":"Blog",
      "topics":"Topics",
      "glossary":"Glossary",
      "compare":"Compare",
      "contact":"Contact",
      "privacy-policy":"Privacy Policy",
      "terms-of-use":"Terms of Use",
      "author":"Author",
      "bio":"About",
      "api":"API",
      "catalogue":"Catalogue",
      "affiliate":"Affiliate"
    };
    if (map[seg]) return map[seg];
    // Title case with hyphens
    return seg.replace(/-/g," ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function injectBreadcrumbs(){
    try{
      const path = (location.pathname || "/").replace(/\/+$/, "/");
      if (path === "/") return; // no breadcrumbs on home

      const main = document.getElementById("main") || document.querySelector("main") || document.querySelector('[role="main"]');
      if (!main) return;

      // Avoid duplicates
      if (document.querySelector(".jh-breadcrumbs")) return;

      const segs = path.split("/").filter(Boolean);
      if (!segs.length) return;

      const nav = document.createElement("nav");
      nav.className = "jh-breadcrumbs";
      nav.setAttribute("aria-label","Breadcrumb");
      nav.innerHTML = '<ol class="jh-breadcrumbs__list"></ol>';

      const ol = nav.querySelector("ol");
      const liHome = document.createElement("li");
      liHome.className = "jh-breadcrumbs__item";
      liHome.innerHTML = '<a href="/">Home</a>';
      ol.appendChild(liHome);

      let accum = "/";
      segs.forEach((seg, i) => {
        accum += seg + "/";
        const li = document.createElement("li");
        li.className = "jh-breadcrumbs__item";
        const label = prettyLabel(seg);

        const isLast = i === segs.length - 1;
        if (isLast){
          li.innerHTML = '<span aria-current="page">' + label + '</span>';
        }else{
          li.innerHTML = '<a href="' + accum + '">' + label + '</a>';
        }
        ol.appendChild(li);
      });

      // Insert breadcrumbs as the first element inside main
      if (main.firstElementChild){
        main.insertBefore(nav, main.firstElementChild);
      }else{
        main.appendChild(nav);
      }
    }catch(_){}  
  }

  function shouldSkipInlineCta(){
    const path = (location.pathname || "/");
    if (path === "/" || path.startsWith("/newsletter")) return true;
    if (document.querySelector("[data-no-inline-cta='true']")) return true;
    return false;
  }

  function injectInlineNewsletterCta(){
    try{
      if (shouldSkipInlineCta()) return;

      const main = document.getElementById("main") || document.querySelector("main") || document.querySelector('[role="main"]');
      if (!main) return;

      if (document.querySelector(".jh-inline-cta")) return;

      const cta = document.createElement("section");
      cta.className = "jh-inline-cta";
      cta.setAttribute("aria-label","Newsletter sign-up prompt");
      cta.innerHTML = `
        <div class="jh-inline-cta__inner">
          <div class="jh-inline-cta__copy">
            <h2>Get the AI Edge</h2>
            <p>Daily AI updates. Short. Useful. Zero breathless hype.</p>
          </div>
          <div class="jh-inline-cta__actions">
            <a class="btn btn-primary" href="/newsletter/">Join the newsletter</a>
            <a class="btn btn-ghost" href="/ebooks/">Browse eBooks</a>
          </div>
        </div>
      `;

      // Append near the end but before footer mount, so it feels intentional.
      main.appendChild(cta);
    }catch(_){}  
  }

  function init(){
    ensureStyles();
    ensureSkipLink();
    ensureMainId();
    injectBreadcrumbs();
    injectInlineNewsletterCta();
    hideLoader();
    injectHeader();
    injectFooter();
  }

  if (document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  }else{
    init();
  }
})();