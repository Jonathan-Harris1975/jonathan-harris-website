
(function(){
  if(window.__JH_GOLD_STANDARD__) return; window.__JH_GOLD_STANDARD__ = true;
  function el(tag, attrs, html){ var n=document.createElement(tag); if(attrs){Object.keys(attrs).forEach(function(k){n.setAttribute(k,attrs[k]);});} if(html!==undefined) n.innerHTML=html; return n; }
  function addFooterTopics(){
    var discover = Array.from(document.querySelectorAll('.footer-panel')).find(function(p){ return /Discover/i.test(p.textContent||'');});
    if(!discover || discover.querySelector('.jh-topic-links')) return;
    var wrap=el('div',{'class':'jh-topic-links'},'<a href="/catalogue/artificial-intelligence/">Artificial Intelligence</a><a href="/catalogue/healthcare/">Healthcare</a><a href="/catalogue/ethics/">Ethics</a><a href="/catalogue/law/">Law</a>');
    discover.appendChild(wrap);
  }
  function addHubIntro(){
    if(!location.pathname.startsWith('/catalogue/') || document.querySelector('.jh-hub-intro')) return;
    var main=document.querySelector('main'); if(!main) return;
    var section=el('section',{'class':'jh-hub-intro','aria-label':'Topic hub quick links'});
    section.innerHTML='<h2>Use this topic hub to find the right next step</h2><p>Start with the books in this topic, then use the links below to move into the wider catalogue, the podcast, the newsletter, or related AI topics.</p><div class="jh-hub-actions"><a class="jh-hub-cta jh-hub-cta--primary" href="/ebooks/">Browse all eBooks</a><a class="jh-hub-cta" href="/podcast/">Listen to the podcast</a><a class="jh-hub-cta" href="/newsletter/">Join the newsletter</a><a class="jh-hub-cta" href="/topics/">Explore AI topics</a></div>';
    var first = main.querySelector('.breadcrumbs, .jh-breadcrumbs, h2, section, article');
    if(first) first.insertAdjacentElement('beforebegin', section); else main.prepend(section);
  }
  function addJourneyPanel(){
    if(!location.pathname.includes('/ebooks/') || document.querySelector('.jh-journey-panel')) return;
    var main=document.querySelector('main'); if(!main) return;
    var panel=el('section',{'class':'jh-journey-panel','aria-label':'Continue exploring'});
    var title=(document.querySelector('h1')||{}).textContent||'this title';
    panel.innerHTML='<h2>Keep exploring the Jonathan Harris AI library</h2><p>You have reached <strong>'+title.replace(/</g,'&lt;')+'</strong>. Use the links below to continue into the wider catalogue, the podcast, the newsletter, or a related topic hub.</p><div class="jh-journey-actions"><a href="/ebooks/">Browse all books</a><a href="/podcast/">Podcast</a><a href="/newsletter/">Newsletter</a><a href="/topics/">AI topics</a></div><p class="jh-related-callout">A quick route to more books, the podcast, and the newsletter.</p>';
    main.appendChild(panel);
  }
  function upgradeLegacyFooter(){
    document.querySelectorAll('footer.site-footer').forEach(function(f){
      if(f.closest('#siteFooter')) return;
      if((f.textContent||'').trim()==='© 2026 Jonathan Harris'){
        var mount=document.getElementById('siteFooter');
        if(!mount){ mount=el('div',{id:'siteFooter'}); f.insertAdjacentElement('beforebegin', mount); }
        f.remove();
      }
    });
  }
  function addMissingAlt(){
    document.querySelectorAll('img').forEach(function(img){
      if(img.hasAttribute('aria-hidden') || img.getAttribute('role')==='presentation') return;
      var alt=img.getAttribute('alt');
      if(alt && alt.trim()) return;
      var src=img.getAttribute('src')||'';
      var guess=src.split('/').pop().split('?')[0].replace(/[-_]/g,' ').replace(/webp|jpg|jpeg|png|avif|svg/ig,'').trim();
      img.setAttribute('alt', guess ? guess.replace(/\s+/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase();}) : 'Jonathan Harris website image');
    });
  }
  function init(){ addFooterTopics(); addHubIntro(); addJourneyPanel(); upgradeLegacyFooter(); addMissingAlt(); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
