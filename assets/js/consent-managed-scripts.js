(function(){
  if (window.__JH_CONSENT_MANAGED_SCRIPTS__) return;
  window.__JH_CONSENT_MANAGED_SCRIPTS__ = true;

  var COOKIEYES_SCRIPT_ID = 'cookieyes';
  var METRICOOL_SRC = 'https://tracker.metricool.com/resources/be.js';
  var METRICOOL_HASH = 'fe05ab38be8b4875d12740b632198511';
  var BOTSAILOR_SRC = 'https://botsailor.com/script/webchat-link.js?code=1744067063128291';

  function loadMetricool(){
    if (window.__JH_METRICOOL_LOADED__) return;
    window.__JH_METRICOOL_LOADED__ = true;
    var head = document.head || document.getElementsByTagName('head')[0];
    if (!head) return;
    var script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = METRICOOL_SRC;
    script.onload = function(){
      try {
        if (window.beTracker && typeof window.beTracker.t === 'function') {
          window.beTracker.t({ hash: METRICOOL_HASH });
        }
      } catch (err) {
        console.error('Metricool tracker failed to initialise', err);
      }
    };
    script.onerror = function(){ console.error('Metricool script failed to load'); };
    head.appendChild(script);
  }

  function loadBotSailor(){
    if (window.__JH_BOTSAILOR_LOADED__ || document.querySelector('script[src*="botsailor.com/script/webchat-link.js"]')) return;
    window.__JH_BOTSAILOR_LOADED__ = true;
    var script = document.createElement('script');
    script.src = BOTSAILOR_SRC;
    script.defer = true;
    script.onerror = function(){ console.error('BotSailor script failed to load'); };
    (document.body || document.documentElement).appendChild(script);
  }

  function hasConsentCategory(category){
    try {
      if (window.CookieYes && typeof window.CookieYes.consent === 'object' && window.CookieYes.consent) {
        if (window.CookieYes.consent[category] === true) return true;
      }
      if (window.cookieyes && typeof window.cookieyes.consent === 'object' && window.cookieyes.consent) {
        if (window.cookieyes.consent[category] === true) return true;
      }
      if (typeof window.getCookieYesConsent === 'function') {
        var state = window.getCookieYesConsent();
        if (state && state[category] === true) return true;
      }
      var cookie = document.cookie.split('; ').find(function(row){ return row.indexOf('cookieyes-consent=') === 0; });
      if (!cookie) return false;
      var value = decodeURIComponent(cookie.split('=').slice(1).join('='));
      var match = value.match(new RegExp('(?:^|,)' + category + ':(yes|no)(?:,|$)'));
      return !!(match && match[1] === 'yes');
    } catch (_) {
      return false;
    }
  }

  function applyConsent(){
    var canTrack = hasConsentCategory('analytics') || hasConsentCategory('marketing');
    if (!canTrack) return;
    loadMetricool();
    loadBotSailor();
  }

  function bindConsentEvents(){
    ['cookieyes_consent_update', 'cookieyes_consent_given', 'cookieyes_banner_closed'].forEach(function(evt){
      document.addEventListener(evt, applyConsent, false);
      window.addEventListener(evt, applyConsent, false);
    });
  }

  function init(){
    if (!document.getElementById(COOKIEYES_SCRIPT_ID)) return;
    bindConsentEvents();
    applyConsent();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
