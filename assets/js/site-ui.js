(function(){
  const FOOTER_TARGET_ID = "siteFooter";
  const FOOTER_URL = "/assets/partials/footer.html";
  const LOADER_ID = "pageLoader";

  function hideLoader(){
    const el = document.getElementById(LOADER_ID);
    if (!el) return;
    el.classList.add("hide");
    window.setTimeout(() => { try { el.remove(); } catch(_){} }, 350);
  }

  async function injectFooter(){
    const mount = document.getElementById(FOOTER_TARGET_ID);
    if (!mount) return;
    try{
      const res = await fetch(FOOTER_URL, { cache: "no-store" });
      if (!res.ok) throw new Error("footer fetch failed");
      const html = await res.text();
      mount.innerHTML = html;
    }catch(e){
      // Minimal fallback so pages never look broken
      mount.innerHTML = '<footer style="background-color:#0D1420; color:#D1D5DB; font-family:Arial, Helvetica, sans-serif; font-size:14px; padding:20px 15px; text-align:center;" role="contentinfo" aria-label="Website Footer"><div style="max-width:1200px; margin:0 auto;">© 2026 Jonathan Harris. All rights reserved.</div></footer>';
    }
  }

  // Expose for other scripts (books.js)
  window.__JH_HIDE_LOADER__ = hideLoader;

  document.addEventListener("DOMContentLoaded", function(){
    injectFooter();
    // Detail pages don't have catalogue render events: hide loader on DOM ready
    // Catalogue page will call hideLoader after render; this is a safe fallback.
    window.setTimeout(hideLoader, 1200);
  });
})();