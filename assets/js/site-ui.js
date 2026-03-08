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
          .jh-header--injected{position:fixed;top:0;left:0;right:0;z-index:2500;background:rgba(13,20,32,0.96);backdrop-filter:saturate(1.2) blur(12px);-webkit-backdrop-filter:saturate(1.2) blur(12px);border-bottom:1px solid rgba(255,255,255,0.10);opacity:0;pointer-events:none;transform:translateY(-6px);transition:opacity 0.28s ease,transform 0.28s ease;}.jh-header--injected.is-visible{opacity:1;pointer-events:auto;transform:translateY(0);}.jh-header{z-index:2500;}
          .jh-header__inner{max-width:1120px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:14px;}
          .jh-brand{color:#E5E7EB;text-decoration:none;font-weight:800;letter-spacing:-0.2px;white-space:nowrap;display:flex;align-items:center;gap:8px;}
          .jh-topnav{display:flex;align-items:center;gap:10px;flex-wrap:nowrap;}
          .jh-topnav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:13px;padding:7px 9px;border-radius:10px;white-space:nowrap;}
          .jh-topnav a:hover,.jh-topnav a:focus{background:rgba(255,255,255,0.08);outline:2px solid rgba(147,197,253,0.55);outline-offset:2px;}
          .jh-topnav a[aria-current="page"]{background:rgba(79,70,229,0.20);border:1px solid rgba(79,70,229,0.35);border-bottom:2px solid #93C5FD;font-weight:700;}
          .jh-hamburger{display:none;background:rgba(79,70,229,0.85);border:1px solid rgba(79,70,229,0.6);border-radius:10px;color:#fff;cursor:pointer;font-size:20px;line-height:1;padding:7px 10px;margin-left:auto;min-width:42px;}
          .jh-hamburger:focus{outline:2px solid rgba(147,197,253,0.75);outline-offset:2px;}
          .jh-mobile-nav{display:none;flex-direction:column;gap:3px;padding:8px 12px 12px;border-top:1px solid rgba(255,255,255,0.08);background:rgba(10,16,28,0.99);}
          .jh-mobile-nav.is-open{display:flex;}
          .jh-mobile-nav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:15px;padding:11px 12px;border-radius:10px;}
          .jh-mobile-nav a:hover{background:rgba(255,255,255,0.09);}
          .jh-mobile-nav a:focus{background:rgba(255,255,255,0.09);outline:2px solid rgba(147,197,253,0.75);outline-offset:2px;}
          .jh-mobile-nav a[aria-current="page"]{background:rgba(79,70,229,0.22);border:1px solid rgba(79,70,229,0.38);}
          .jh-header-spacer{display:block;height:54px;}
          @media (max-width:768px){
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
      // If a baked-in header already exists, wire it up with scroll-based reveal.
      var existingHeader = document.querySelector(".jh-header");
      if (existingHeader) {
      // Wire hamburger on the baked-in header
        try {
          var eBtn = existingHeader.querySelector('.jh-hamburger');
          var eMobileNav = existingHeader.querySelector('.jh-mobile-nav');
          if (eBtn && eMobileNav) {
            // Remove stale listener by cloning the button
            var newBtn = eBtn.cloneNode(true);
            eBtn.parentNode.replaceChild(newBtn, eBtn);
            newBtn.addEventListener('click', function(){
              var open = eMobileNav.classList.toggle('is-open');
              if (open) {
                eMobileNav.removeAttribute('hidden');
                eMobileNav.style.display='';
                // Move focus to first link for keyboard users
                var firstLink = eMobileNav.querySelector('a');
                if (firstLink) setTimeout(function(){ firstLink.focus(); }, 50);
              } else {
                eMobileNav.style.display='none';
                newBtn.focus();
              }
              newBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
              newBtn.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
              var lbl = newBtn.querySelector('.jh-hamburger__label');
              if (lbl) lbl.textContent = open ? 'Close' : 'Menu';
            });
            // Focus trapping inside mobile nav
            eMobileNav.addEventListener('keydown', function(e){
              if(!eMobileNav.classList.contains('is-open')) return;
              var focusable = Array.from(eMobileNav.querySelectorAll('a,[tabindex]:not([tabindex="-1"])'));
              if(!focusable.length) return;
              if(e.key === 'Tab'){
                var first = focusable[0], last = focusable[focusable.length-1];
                if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
                else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); }
              }
              if(e.key==='Escape'){ eMobileNav.classList.remove('is-open'); eMobileNav.style.display='none'; newBtn.setAttribute('aria-expanded','false'); newBtn.focus(); }
            });
            markActiveNav(eMobileNav);
          }
        } catch(_) {}

        // Scroll-based sticky header: show only once hero/static header is out of view
        try {
          existingHeader.classList.add('jh-header--injected');
          var heroEl = document.querySelector('.lp-hero, .hero, [aria-label="Page Header"]');
          if (heroEl && 'IntersectionObserver' in window) {
            var headerObs = new IntersectionObserver(function(entries){
              entries.forEach(function(entry){
                if (!entry.isIntersecting) {
                  existingHeader.classList.add('is-visible');
                } else {
                  existingHeader.classList.remove('is-visible');
                }
              });
            }, { threshold: 0, rootMargin: '-10px 0px 0px 0px' });
            headerObs.observe(heroEl);
          } else {
            // Fallback: always visible on pages without a hero
            existingHeader.classList.add('is-visible');
          }
        } catch(_) {
          existingHeader.classList.add('is-visible');
        }
        return; // baked-in header handled; no need to fetch partial
      }

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

      header.classList.add('jh-header--injected');
      markActiveNav(header);

      // Scroll-based visibility for injected header
      var heroElInj = document.querySelector('.lp-hero, .hero, [aria-label="Page Header"]');
      if (heroElInj && 'IntersectionObserver' in window) {
        var injObs = new IntersectionObserver(function(entries){
          entries.forEach(function(entry){
            if (!entry.isIntersecting) { header.classList.add('is-visible'); }
            else { header.classList.remove('is-visible'); }
          });
        }, { threshold: 0, rootMargin: '-10px 0px 0px 0px' });
        injObs.observe(heroElInj);
      } else {
        header.classList.add('is-visible');
      }

      // Wire up hamburger button if present
      try {
        var btn = header.querySelector('.jh-hamburger');
        var mobileNav = header.querySelector('.jh-mobile-nav');
        if (btn && mobileNav) {
          btn.addEventListener('click', function(){
            var open = mobileNav.classList.toggle('is-open');
            mobileNav.removeAttribute('hidden');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            btn.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
            var lbl = btn.querySelector('.jh-hamburger__label');
            if (lbl) lbl.textContent = open ? 'Close' : 'Menu';
            var icon = btn.firstChild;
            if (icon && icon.nodeType === 3) icon.textContent = open ? '\u2715 ' : '\u2630 ';
          });
          // Mark active links in mobile nav too
          markActiveNav(mobileNav);
        }
      } catch(_) {}

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

  
  function injectBackToTop(){
    try{
      if (document.querySelector('.jh-back-to-top')) return;
      var btn = document.createElement('button');
      btn.className = 'jh-back-to-top';
      btn.setAttribute('aria-label', 'Back to top');
      btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="18 15 12 9 6 15"/></svg>';
      document.body.appendChild(btn);
      btn.addEventListener('click', function(){
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
      if ('IntersectionObserver' in window){
        var sentinel = document.createElement('div');
        sentinel.style.cssText = 'position:absolute;top:400px;left:0;width:1px;height:1px;pointer-events:none;';
        document.body.insertBefore(sentinel, document.body.firstChild);
        var bttObs = new IntersectionObserver(function(entries){
          entries.forEach(function(entry){
            if (!entry.isIntersecting){ btn.classList.add('is-visible'); }
            else { btn.classList.remove('is-visible'); }
          });
        }, { threshold: 0 });
        bttObs.observe(sentinel);
      } else {
        window.addEventListener('scroll', function(){
          if (window.scrollY > 400) btn.classList.add('is-visible');
          else btn.classList.remove('is-visible');
        }, { passive: true });
      }
    }catch(_){}
  }


  function wireDropdowns(){
    try{
      document.querySelectorAll('.jh-nav-dropdown').forEach(function(dd){\
        var btn=dd.querySelector('.jh-nav-dropdown__btn');
        var menu=dd.querySelector('.jh-nav-dropdown__menu');
        if(!btn||btn.dataset.jhWired)return;
        btn.dataset.jhWired='1';

        function openMenu(){
          dd.classList.add('is-open');
          btn.setAttribute('aria-expanded','true');
        }
        function closeMenu(){
          dd.classList.remove('is-open');
          btn.setAttribute('aria-expanded','false');
        }

        btn.addEventListener('click',function(e){
          e.stopPropagation();
          var open=dd.classList.toggle('is-open');
          btn.setAttribute('aria-expanded',open?'true':'false');
          if(open && menu){
            var first=menu.querySelector('a[role="menuitem"]');
            if(first) first.focus();
          }
        });

        // Keyboard: ArrowDown opens and focuses first item; Escape closes
        btn.addEventListener('keydown',function(e){
          if(e.key==='ArrowDown'||e.key==='Enter'||e.key===' '){
            e.preventDefault();
            openMenu();
            if(menu){
              var first=menu.querySelector('a[role="menuitem"]');
              if(first) first.focus();
            }
          }
        });

        // Arrow navigation within the menu items
        if(menu){
          menu.addEventListener('keydown',function(e){
            var items=Array.from(menu.querySelectorAll('a[role="menuitem"]'));
            var idx=items.indexOf(document.activeElement);
            if(e.key==='ArrowDown'){
              e.preventDefault();
              var next=items[idx+1]||items[0];
              if(next) next.focus();
            } else if(e.key==='ArrowUp'){
              e.preventDefault();
              var prev=items[idx-1]||items[items.length-1];
              if(prev) prev.focus();
            } else if(e.key==='Escape'||e.key==='Tab'){
              closeMenu();
              btn.focus();
            }
          });
        }
      });
      document.addEventListener('click',function(){\
        document.querySelectorAll('.jh-nav-dropdown.is-open').forEach(function(dd){\
          dd.classList.remove('is-open');
          var b=dd.querySelector('.jh-nav-dropdown__btn');
          if(b)b.setAttribute('aria-expanded','false');
        });
      },{capture:false,once:false});
    }catch(_){}
  }

function init(){
    ensureStyles();
    ensureSkipLink();
    wireDropdowns();
    ensureMainId();
    injectHeader();
    injectFooter();
    injectBackToTop();

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

// ── FAQ accordion aria-expanded enhancement ──────────────────────────────
(function(){
  function enhanceFaqAccordions(){
    document.querySelectorAll('.faq details, details.more').forEach(function(det){
      var sum = det.querySelector('summary');
      if(!sum) return;
      if(sum.hasAttribute('data-faq-enhanced')) return;
      sum.setAttribute('data-faq-enhanced','1');
      sum.setAttribute('aria-expanded', det.open ? 'true' : 'false');
      det.addEventListener('toggle', function(){
        sum.setAttribute('aria-expanded', det.open ? 'true' : 'false');
      });
    });
  }
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', enhanceFaqAccordions);
  } else {
    enhanceFaqAccordions();
  }
})();
})();