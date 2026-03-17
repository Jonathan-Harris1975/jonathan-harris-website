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
          .jh-header--injected{position:fixed;top:0;left:0;right:0;z-index:2500;background:rgba(13,20,32,0.96);backdrop-filter:saturate(1.2) blur(12px);-webkit-backdrop-filter:saturate(1.2) blur(12px);border-bottom:1px solid rgba(255,255,255,0.10);opacity:1;pointer-events:auto;transform:translateY(0);transition:opacity 0.28s ease,transform 0.28s ease;}.jh-header--injected.is-visible{opacity:1;pointer-events:auto;transform:translateY(0);}.jh-header{z-index:2500;}
          .jh-header__inner{max-width:1120px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;}
          .jh-brand{color:#E5E7EB;text-decoration:none;font-weight:800;letter-spacing:-0.2px;white-space:nowrap;display:flex;align-items:center;gap:8px;}
          .jh-topnav{display:flex;align-items:center;gap:10px;flex-wrap:nowrap;}
          .jh-topnav a{color:#E5E7EB;text-decoration:none;font-weight:600;font-size:14px;padding:7px 9px;border-radius:10px;white-space:nowrap;}
          .jh-topnav a:hover,.jh-topnav a:focus{background:rgba(255,255,255,0.08);outline:2px solid rgba(147,197,253,0.55);outline-offset:2px;}
          .jh-topnav a[aria-current="page"]{background:rgba(79,70,229,0.20);border:1px solid rgba(79,70,229,0.35);border-bottom:2px solid #93C5FD;font-weight:700;}
          .jh-hamburger{display:none;background:rgba(79,70,229,0.92);border:1px solid rgba(79,70,229,0.6);border-radius:14px;color:#fff;cursor:pointer;font-size:18px;line-height:1;padding:9px 12px;margin-left:auto;min-width:44px;min-height:44px;box-shadow:0 10px 24px rgba(79,70,229,0.24);}
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
            .jh-hamburger{display:inline-flex;align-items:center;justify-content:center;}
            .jh-header__inner{padding:10px 14px;gap:10px;}
            .jh-brand__text{font-size:16px;line-height:1.1;}
            .jh-header-spacer{height:56px;}
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

  const PARTIAL_CACHE = new Map();

  async function fetchPartial(url){
    try{
      if (PARTIAL_CACHE.has(url)) return PARTIAL_CACHE.get(url);
      const res = await fetch(url, { cache: "force-cache" });
      if (!res.ok) return "";
      const html = await res.text();
      PARTIAL_CACHE.set(url, html);
      return html;
    }catch(_){
      return "";
    }
  }

  function setBodyScrollLock(locked){
    try{
      document.documentElement.classList.toggle('jh-nav-open', !!locked);
      document.body.classList.toggle('jh-nav-open', !!locked);
    }catch(_){ }
  }

  function updateNavOverlay(visible){
    try{
      const overlay = document.getElementById('jh-nav-overlay');
      if (!overlay) return;
      overlay.classList.toggle('is-active', !!visible);
      overlay.setAttribute('aria-hidden', visible ? 'false' : 'true');
    }catch(_){ }
  }

  function getFocusableElements(container){
    try{
      if (!container) return [];
      return Array.from(container.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter(function(el){
        return !el.hasAttribute('hidden') && el.getAttribute('aria-hidden') !== 'true';
      });
    }catch(_){
      return [];
    }
  }

  function setMobileNavState(mobileNav, button, isOpen){
    try{
      if (!mobileNav || !button) return;
      const open = !!isOpen;
      mobileNav.classList.toggle('is-open', open);
      if (open){
        mobileNav.removeAttribute('hidden');
        mobileNav.style.display = 'flex';
      }else{
        mobileNav.setAttribute('hidden', '');
        mobileNav.style.display = 'none';
      }
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      button.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
      var lbl = button.querySelector('.jh-hamburger__label');
      if (lbl) lbl.textContent = open ? 'Close' : 'Menu';
      setBodyScrollLock(open);
      updateNavOverlay(open);
    }catch(_){ }
  }

  function wireMobileNav(header){
    try{
      if (!header || header.dataset.jhMobileNavWired === '1') return;
      const button = header.querySelector('.jh-hamburger');
      const mobileNav = header.querySelector('.jh-mobile-nav');
      if (!button || !mobileNav) return;
      header.dataset.jhMobileNavWired = '1';

      if (!mobileNav.id) mobileNav.id = 'jh-mobile-nav';
      button.setAttribute('aria-controls', mobileNav.id);
      setMobileNavState(mobileNav, button, false);

      button.addEventListener('click', function(){
        const open = button.getAttribute('aria-expanded') === 'true';
        setMobileNavState(mobileNav, button, !open);
        if (!open){
          const first = getFocusableElements(mobileNav)[0];
          if (first) first.focus();
        } else {
          button.focus();
        }
      });

      mobileNav.addEventListener('click', function(evt){
        const link = evt.target && evt.target.closest ? evt.target.closest('a[href]') : null;
        if (link) setMobileNavState(mobileNav, button, false);
      });

      mobileNav.addEventListener('keydown', function(evt){
        if (evt.key === 'Escape'){
          evt.preventDefault();
          setMobileNavState(mobileNav, button, false);
          button.focus();
          return;
        }
        if (evt.key !== 'Tab') return;
        const focusable = getFocusableElements(mobileNav);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (evt.shiftKey && document.activeElement === first){
          evt.preventDefault();
          last.focus();
        } else if (!evt.shiftKey && document.activeElement === last){
          evt.preventDefault();
          first.focus();
        }
      });

      document.addEventListener('keydown', function(evt){
        if (evt.key === 'Escape' && button.getAttribute('aria-expanded') === 'true'){
          setMobileNavState(mobileNav, button, false);
          button.focus();
        }
      });

      window.addEventListener('resize', function(){
        if (window.innerWidth > 768 && button.getAttribute('aria-expanded') === 'true'){
          setMobileNavState(mobileNav, button, false);
        }
      }, { passive: true });
    }catch(_){ }
  }

  async function injectHeader(){
    try{
      const html = await fetchPartial(HEADER_URL);
      if (!html) return;

      const wrapper = document.createElement('div');
      wrapper.innerHTML = html;
      let nextHeader = wrapper.querySelector('.jh-header') || wrapper.firstElementChild;
      if (!nextHeader) return;

      let header = document.querySelector('.jh-header');
      if (header){
        header.replaceWith(nextHeader);
        header = nextHeader;
      } else {
        const skipLink = document.querySelector('.skip-link');
        if (skipLink && skipLink.parentNode === document.body){
          skipLink.insertAdjacentElement('afterend', nextHeader);
        } else {
          document.body.insertBefore(nextHeader, document.body.firstChild);
        }
        header = nextHeader;
      }

      header.classList.add('jh-header--injected');
      header.dataset.jhShared = '1';
      markActiveNav(header);
      wireMobileNav(header);
      wireDropdowns();
      syncHeaderVisibility(header, findHeaderRevealAnchor(), header.querySelector('.jh-mobile-nav'), header.querySelector('.jh-hamburger'));
    }catch(_){ }
  }

  function strengthenEmbeddedForms(){
    try{
      document.querySelectorAll('iframe[src*="form.jotform.com"]').forEach(function(frame, index){
        if (frame.dataset.jhFormStrengthened === '1') return;
        frame.dataset.jhFormStrengthened = '1';
        if (!frame.getAttribute('title')){
          frame.setAttribute('title', 'Embedded form ' + (index + 1));
        }
        frame.setAttribute('loading', frame.getAttribute('loading') || 'lazy');
        frame.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
        frame.removeAttribute('onload');
      });
    }catch(_){ }
  }

  function findHeroHost(){
    // Prefer the existing hero/header section so nav feels native.
    return (
      document.querySelector('section[aria-label="Page Header"]') ||
      document.querySelector('section[aria-label*="header" i]') ||
      document.querySelector('header.hero') ||
      document.querySelector('.lp-hero') ||
      document.querySelector('.hero') ||
      document.querySelector('.dark-section') ||
      document.querySelector('.about-banner') ||
      null
    );
  }

  function findHeaderRevealAnchor(){
    return (
      document.querySelector('.lp-hero') ||
      document.querySelector('header.hero') ||
      document.querySelector('.hero') ||
      document.querySelector('.dark-section') ||
      document.querySelector('.about-banner') ||
      document.querySelector('section[aria-label="Page Header"]') ||
      document.querySelector('section[aria-label*="header" i]') ||
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

  function syncHeaderVisibility(header, heroEl, mobileNav, button){
    if (!header) return;

    function closeMobileNav(){
      if (!mobileNav) return;
      if (button) {
        setMobileNavState(mobileNav, button, false);
      } else {
        mobileNav.classList.remove('is-open');
        mobileNav.style.display = 'none';
        mobileNav.setAttribute('hidden','');
      }
    }

    function setVisible(visible){
      header.classList.toggle('is-visible', !!visible);
      if (!visible) closeMobileNav();
    }

    function revealThreshold(){
      const target = heroEl || findHeaderRevealAnchor();
      if (!target) return 0;
      const rect = target.getBoundingClientRect();
      const scrollTop = window.scrollY || window.pageYOffset || 0;
      const top = rect.top + scrollTop;
      const height = Math.max(rect.height, target.offsetHeight || 0, 0);
      return Math.max(0, top + Math.max(96, height - 96));
    }

    function updateVisibility(){
      const target = heroEl || findHeaderRevealAnchor();
      if (!target){
        header.classList.remove('jh-header--hero-mode');
        setVisible(true);
        return;
      }

      header.classList.add('jh-header--hero-mode');
      const shouldShow = (window.scrollY || window.pageYOffset || 0) >= revealThreshold();
      setVisible(shouldShow);
    }

    updateVisibility();
    window.addEventListener('scroll', updateVisibility, { passive: true });
    window.addEventListener('resize', updateVisibility, { passive: true });
    window.addEventListener('orientationchange', updateVisibility, { passive: true });
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
      const html = await fetchPartial(FOOTER_URL);
      if (!html) return;

      let target = document.getElementById(FOOTER_TARGET_ID);
      const existing = document.querySelector('footer.site-footer');

      if (existing){
        if (existing.parentElement && existing.parentElement.id === FOOTER_TARGET_ID){
          target = existing.parentElement;
        } else if (target) {
          existing.remove();
        } else {
          target = document.createElement('div');
          target.id = FOOTER_TARGET_ID;
          existing.replaceWith(target);
        }
      }

      if (!target) target = ensureFooterTarget();
      target.innerHTML = html;
      target.dataset.jhShared = '1';
    }catch(_){ }
  }



  function normaliseCanonicalUrl(url){
    try{
      const parsed = new URL(url, window.location.origin);
      parsed.hash = "";
      const cleanPath = parsed.pathname.replace(/\/{2,}/g, "/");
      parsed.pathname = cleanPath === "/" ? "/" : cleanPath.replace(/\/+$/, "") + "/";
      return parsed.toString();
    }catch(_){
      return window.location.origin + "/";
    }
  }

  function ensureCanonical(){
    try{
      const canonicalHref = normaliseCanonicalUrl(window.location.href);
      let canonical = document.querySelector('link[rel="canonical"]');

      if (!canonical){
        canonical = document.createElement("link");
        canonical.setAttribute("rel", "canonical");
        document.head.appendChild(canonical);
      }

      canonical.setAttribute("href", canonicalHref);
    }catch(_){}
  }

  function ensureImagePreloads(){
    try{
      const path = (location.pathname || "/").replace(/\/+$/, "/") || "/";
      const hrefs = ["https://images.jonathan-harris.online/site-logo"];

      if (path === "/"){
        hrefs.push("https://images.jonathan-harris.online/headshot");
      }

      hrefs.forEach(function(href){
        if (document.querySelector('link[rel="preload"][as="image"][href="' + href + '"]')) return;
        const link = document.createElement("link");
        link.rel = "preload";
        link.as = "image";
        link.href = href;
        if (href.indexOf("site-logo") !== -1) link.setAttribute("fetchpriority", "high");
        document.head.appendChild(link);
      });
    }catch(_){}
  }

  function injectBreadcrumbSchema(){
    try{
      const path = (location.pathname || "/").replace(/\/+$/, "/") || "/";
      const existing = document.getElementById("jh-breadcrumb-schema");
      if (existing) existing.remove();

      const hasBakedBreadcrumb = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).some(function(node){
        return /"@type"\s*:\s*"BreadcrumbList"/.test(node.textContent || "");
      });
      if (hasBakedBreadcrumb || document.querySelector('[data-jh-ai-pack]')) return;

      const segs = path.split("/").filter(Boolean);
      if (!segs.length) return;

      const itemList = [{
        "@type":"ListItem",
        "position":1,
        "name":"Home",
        "item":"https://jonathan-harris.online/"
      }];

      let accum = "/";
      segs.forEach(function(seg, i){
        accum += seg + "/";
        itemList.push({
          "@type":"ListItem",
          "position": i + 2,
          "name": prettyLabel(seg),
          "item": "https://jonathan-harris.online" + accum
        });
      });

      const script = document.createElement("script");
      script.type = "application/ld+json";
      script.id = "jh-breadcrumb-schema";
      script.textContent = JSON.stringify({
        "@context":"https://schema.org",
        "@type":"BreadcrumbList",
        "itemListElement": itemList
      });
      document.head.appendChild(script);
    }catch(_){}
  }

  function lazyLoadLargeImages(){
    try{
      const hero = document.querySelector(".lp-hero, header.hero, .hero, .about-banner, .dark-section");
      const largeImageSelector = 'img:not([loading="eager"])';
      document.querySelectorAll(largeImageSelector).forEach(function(img){
        if (!img || img.dataset.jhImageOptimised === "true") return;

        const isInsideHeader = !!img.closest(".jh-header");
        const isHeroImage = !!(hero && hero.contains(img));
        const declaredLarge = (parseInt(img.getAttribute("width") || "0", 10) >= 120) || (parseInt(img.getAttribute("height") || "0", 10) >= 120);
        const classHints = /(hero|banner|cover|card__img|author__img|featured|thumbnail|poster|image)/i.test((img.className || "").toString());

        if (!isInsideHeader && !isHeroImage && (declaredLarge || classHints)){
          img.loading = "lazy";
        }

        if (!img.hasAttribute("decoding")){
          img.setAttribute("decoding", "async");
        }

        img.dataset.jhImageOptimised = "true";
      });
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
            <p>Weekly AI updates. Short. Useful. Zero breathless hype.</p>
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

  

  function quietDecorativeIcons(){
    try{
      document.querySelectorAll('.card__emoji,.topic-card__icon,.affiliate-disclosure__icon,.compare-scroll-cue').forEach(function(el){
        el.setAttribute('aria-hidden','true');
      });
      document.querySelectorAll('.footer-social a svg,.footer-social a img').forEach(function(el){
        el.setAttribute('aria-hidden','true');
        el.removeAttribute('aria-label');
        el.removeAttribute('role');
        el.setAttribute('focusable','false');
      });
      document.querySelectorAll('a > svg:only-child, button > svg:only-child').forEach(function(el){
        var labelledParent = el.parentElement && (el.parentElement.getAttribute('aria-label') || el.parentElement.textContent.trim());
        if (labelledParent){
          el.setAttribute('aria-hidden','true');
          el.removeAttribute('aria-label');
          el.removeAttribute('role');
          el.setAttribute('focusable','false');
        }
      });
    }catch(_){}
  }

  function injectBackToTop(){
    try{
      if (
        document.querySelector('.jh-back-to-top') ||
        document.querySelector('.btt-btn') ||
        document.querySelector('[aria-label="Back to top"]')
      ) return;
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
      document.querySelectorAll('.jh-nav-dropdown').forEach(function(dd){
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
          // FIX #4: Close open dropdown with Escape key from the button itself
          if(e.key==='Escape' && dd.classList.contains('is-open')){
            e.preventDefault();
            closeMenu();
            btn.focus();
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
      document.addEventListener('click',function(){
        document.querySelectorAll('.jh-nav-dropdown.is-open').forEach(function(dd){
          dd.classList.remove('is-open');
          var b=dd.querySelector('.jh-nav-dropdown__btn');
          if(b)b.setAttribute('aria-expanded','false');
        });
      },{capture:false,once:false});
    }catch(_){}
  }


  /**
   * UX AUDIT FIX (March 2026 — Mobile UX #3):
   * Close the hamburger menu when the user taps outside the nav panel.
   * Creates a semi-transparent overlay behind the mobile nav; tapping it
   * dismisses the menu without requiring the user to find the close button.
   */
  function injectMobileNavOverlay() {
    try {
      if (document.getElementById('jh-nav-overlay')) return;
      var overlay = document.createElement('div');
      overlay.id = 'jh-nav-overlay';
      overlay.className = 'jh-nav-overlay';
      overlay.setAttribute('aria-hidden', 'true');
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function() {
        document.querySelectorAll('.jh-mobile-nav.is-open').forEach(function(nav) {
          var ownerHeader = nav.closest('.jh-header') || document;
          var button = ownerHeader.querySelector('.jh-hamburger');
          if (button) setMobileNavState(nav, button, false);
        });
      });
    } catch (_) {}
  }

async function init(){
    ensureStyles();
    ensureSkipLink();
    ensureMainId();
    ensureCanonical();
    ensureImagePreloads();
    strengthenEmbeddedForms();
    await injectHeader();
    await injectFooter();
    wireDropdowns();
    quietDecorativeIcons();
    injectBackToTop();
    injectMobileNavOverlay();
    lazyLoadLargeImages();

    if (!is404Page()){
      injectBreadcrumbs();
      injectBreadcrumbSchema();
      injectInlineNewsletterCta();
    } else {
      // Clean up anything injected before (safety)
      document.querySelectorAll(".jh-breadcrumbs, .jh-inline-cta, #jh-breadcrumb-schema").forEach(el=>el.remove());
    }

    hideLoader();
  }

if (document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  }else{
    init();
  }

  window.addEventListener("load", function(){
    lazyLoadLargeImages();
  }, { once: true });


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

