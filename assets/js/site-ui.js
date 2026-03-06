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
          .jh-header{position:fixed;top:0;left:0;right:0;z-index:2500;background:rgba(13,20,32,0.96);backdrop-filter:saturate(1.2) blur(12px);-webkit-backdrop-filter:saturate(1.2) blur(12px);border-bottom:1px solid rgba(255,255,255,0.10);opacity:0;pointer-events:none;transform:translateY(-6px);transition:opacity 0.28s ease,transform 0.28s ease;}.jh-header.is-visible{opacity:1;pointer-events:auto;transform:translateY(0);}
          .jh-header__inner{max-width:1120px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:14px;}
          .jh-brand{color:#E5E7EB;text-decoration:none;font-weight:800;letter-spacing:-0.2px;white-space:nowrap;display:flex;align-items:center;gap:8px;}
          .jh-topnav{display:flex;align-items:center;gap:10px;flex-wrap:nowrap;}
          .jh-topnav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:13px;padding:7px 9px;border-radius:10px;white-space:nowrap;}
          .jh-topnav a:hover,.jh-topnav a:focus{background:rgba(255,255,255,0.08);outline:none;}
          .jh-topnav a[aria-current="page"]{background:rgba(79,70,229,0.20);border:1px solid rgba(79,70,229,0.35);}
          .jh-hamburger{display:none;background:rgba(255,255,255,0.10);border:1px solid rgba(255,255,255,0.28);border-radius:9px;color:#fff;cursor:pointer;font-size:20px;line-height:1;padding:8px 12px;margin-left:auto;min-width:42px;}
          .jh-hamburger:focus{outline:2px solid rgba(147,197,253,0.75);outline-offset:2px;}
          .jh-mobile-nav{display:none;flex-direction:column;gap:3px;padding:8px 12px 12px;border-top:1px solid rgba(255,255,255,0.08);background:rgba(10,16,28,0.99);}
          .jh-mobile-nav.is-open{display:flex;}
          .jh-mobile-nav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:15px;padding:11px 12px;border-radius:10px;}
          .jh-mobile-nav a:hover,.jh-mobile-nav a:focus{background:rgba(255,255,255,0.09);outline:none;}
          .jh-mobile-nav a[aria-current="page"]{background:rgba(79,70,229,0.22);border:1px solid rgba(79,70,229,0.38);}
          .jh-header-spacer{display:block;height:54px;}
          @media (max-width:640px){
            .jh-topnav{display:none !important;}
            .jh-hamburger{display:block;}
            .jh-header__inner{padding:10px 14px;}
            .jh-header-spacer{height:52px;}
          }
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


      // Wire up hamburger button if present
      try {
        var btn = header.querySelector('.jh-hamburger');
        var mobileNav = header.querySelector('.jh-mobile-nav');
        if (btn && mobileNav) {
          btn.addEventListener('click', function(){
            var open = mobileNav.classList.toggle('is-open');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            btn.textContent = open ? '\u2715' : '\u2630';
          });
          // Mark active links in mobile nav too
          markActiveNav(mobileNav);
        }
      } catch(_) {}

      // ── Scroll-reveal: show nav only after hero leaves viewport ──
      // Falls back to always-visible if no hero or no IntersectionObserver support.
      try {
        var heroEl = (
          document.querySelector('section[aria-label="Page Header"]') ||
          document.querySelector('header.hero') ||
          document.querySelector('.hero') ||
          document.querySelector('header[role="banner"]') ||
          null
        );
        if (heroEl && 'IntersectionObserver' in window) {
          var revealIO = new IntersectionObserver(
            function(entries) {
              // Hero leaving view → show nav. Hero entering view → hide nav.
              if (entries[0].isIntersecting) {
                header.classList.remove('is-visible');
              } else {
                header.classList.add('is-visible');
              }
            },
            { threshold: 0.01, rootMargin: '-72px 0px 0px 0px' }
          );
          revealIO.observe(heroEl);
        } else {
          // No hero found or no IO support — always show
          header.classList.add('is-visible');
        }
      } catch(_) {
        // Safety fallback
        try { header.classList.add('is-visible'); } catch(__) {}
      }

    }catch(_){}
  }

  function ensureFooterTarget(){
    let target = document.getElementById(FOOTER_TARGET_ID);
    if (target) return target;

    target = document.createElement("div");
    target.id = FOOTER_TARGET_ID;
    document.body.appendChild(target);
    return target;
  }

  async function injectFooter(){
    try{
      const target = ensureFooterTarget();
      if (!target) return;

      const legacyFooters = Array.from(document.querySelectorAll("footer"));
      legacyFooters.forEach((footer) => {
        if (!footer.closest(`#${FOOTER_TARGET_ID}`)) footer.remove();
      });

      const res = await fetch(FOOTER_URL, { cache: "force-cache" });
      if (!res.ok) return;
      const html = await res.text();
      target.innerHTML = html;
    }catch(_){ }
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
