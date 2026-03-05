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

  
  function is404Page(){
    try{
      const b = document.body;
      if (b && b.classList && b.classList.contains("jh-page-404")) return true;
      const p = (location && location.pathname ? location.pathname : "").toLowerCase();
      if (p.endsWith("/404") || p.endsWith("/404/") || p.endsWith("404.html")) return true;
      const t = (document.title || "").toLowerCase();
      if (t.startsWith("404") || t.includes("page not found") || t.includes("not here")) return true;
    }catch(_){}
    return false;
  }

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

          /* Header (clean, uncluttered, no “nav circle”) */
          .jh-header{position:sticky;top:0;z-index:2500;width:100%;background:rgba(13,20,32,0.92);backdrop-filter:saturate(1.2) blur(10px);border-bottom:1px solid rgba(255,255,255,0.10);opacity:0;pointer-events:none;transition:opacity 0.25s ease,transform 0.25s ease;transform:translateY(-4px);} .jh-header.jh-header--visible{opacity:1;pointer-events:auto;transform:translateY(0);}
          .jh-header__inner{max-width:1120px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:14px;}
          .jh-brand{color:#E5E7EB;text-decoration:none;font-weight:800;letter-spacing:-0.2px;white-space:nowrap;}
          .jh-topnav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end;}
          .jh-topnav a,.jh-navmore>summary{color:#E5E7EB;text-decoration:none;font-weight:650;font-size:13px;line-height:1.1;padding:8px 10px;border-radius:10px;}
          .jh-topnav a:hover,.jh-topnav a:focus,.jh-navmore>summary:hover,.jh-navmore>summary:focus{background:rgba(255,255,255,0.08);outline:none;}
          .jh-topnav a[aria-current="page"]{background:rgba(79,70,229,0.20);border:1px solid rgba(79,70,229,0.35);}
          .jh-navmore{position:relative;}
          .jh-navmore>summary{list-style:none;cursor:pointer;}
          .jh-navmore>summary::-webkit-details-marker{display:none;}
          .jh-navmore__panel{position:absolute;right:0;top:calc(100% + 10px);min-width:200px;background:rgba(13,20,32,0.98);border:1px solid rgba(255,255,255,0.14);border-radius:14px;box-shadow:0 18px 40px rgba(0,0,0,0.35);padding:8px;}
          .jh-navmore__panel a{display:block;padding:10px 10px;border-radius:10px;color:#E5E7EB;text-decoration:none;font-weight:600;}
          .jh-navmore__panel a:hover,.jh-navmore__panel a:focus{background:rgba(255,255,255,0.08);outline:none;}
          @media (max-width: 640px){.jh-header__inner{flex-wrap:wrap;justify-content:center;}.jh-topnav{justify-content:center;}.jh-navmore__panel{left:0;right:auto;}}.jh-header{bottom:10px;}.jh-header__inner{padding:10px 12px;}.jh-topnav{gap:10px;}.jh-topnav a{font-size:12.5px;}}
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
        hero.parentNode.insertBefore(header, hero); // keep navigation at the top
      }else{
        document.body.insertBefore(header, document.body.firstChild);
      }

      markActiveNav(header);

      // Scroll-reveal: header hidden until hero scrolls out of view
      try {
        const hero = findHeroHost() || document.querySelector('.hero') || document.querySelector('header[role="banner"]');
        if (hero && 'IntersectionObserver' in window) {
          const io = new IntersectionObserver(
            (entries) => {
              const heroVisible = entries[0].isIntersecting;
              if (heroVisible) {
                header.classList.remove('jh-header--visible');
              } else {
                header.classList.add('jh-header--visible');
              }
            },
            { threshold: 0.05 }
          );
          io.observe(hero);
        } else {
          // Fallback: always show if no IntersectionObserver
          header.classList.add('jh-header--visible');
        }
      } catch(_) {
        if (header) header.classList.add('jh-header--visible');
      }

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
    injectHeader();
    injectFooter();

    if (!is404Page()){
      injectBreadcrumbs();
      injectInlineNewsletterCta();
    } else {
      // Clean up anything injected before (safety)
      document.querySelectorAll(".jh-breadcrumbs, .jh-inline-cta").forEach(el=>el.remove());
    }

    hideLoader();
  }

if (document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  }else{
    init();
  }
})();
