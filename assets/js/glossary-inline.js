(function() {
  'use strict';

  /**
   * Glossary in-page search:
   * Filters <dt>/<dd> pairs in real time as the user types.
   * Shows a "no results" message if nothing matches.
   */
  function initGlossarySearch() {
    var main = document.getElementById('main');
    if (!main) return;

    // Build search wrapper and input
    var wrap = document.createElement('div');
    wrap.className = 'glossary-search-wrap';
    wrap.setAttribute('role', 'search');
    wrap.setAttribute('aria-label', 'Search glossary terms');

    wrap.innerHTML = '<svg class="glossary-search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>'
      + '<input type="search" id="glossary-search" class="glossary-search-input" placeholder="Search AI terms..." autocomplete="off" aria-label="Filter glossary terms" spellcheck="false" />'
      + '<div id="glossary-no-results" class="glossary-no-results" role="status" aria-live="polite">No terms found for that search.</div>';

    // Insert before the <dl> element
    var dl = main.querySelector('dl');
    if (dl) {
      main.insertBefore(wrap, dl);
    } else {
      main.insertBefore(wrap, main.firstChild);
    }

    var noResults = document.getElementById('glossary-no-results');
    var input = document.getElementById('glossary-search');
    if (!input) return;

    input.addEventListener('input', function() {
      var query = input.value.trim().toLowerCase();
      var terms = document.querySelectorAll('#main dl dt');
      var visibleCount = 0;

      terms.forEach(function(dt) {
        var dd = dt.nextElementSibling;
        var text = (dt.textContent + ' ' + (dd ? dd.textContent : '')).toLowerCase();
        var matches = !query || text.indexOf(query) !== -1;

        // Show/hide dt and its corresponding dd
        if(matches){dt.removeAttribute('hidden');}else{dt.setAttribute('hidden','');}
        if (dd && dd.tagName === 'DD') {
          if(matches){dd.removeAttribute('hidden');}else{dd.setAttribute('hidden','');}
        }

        // Show/hide associated sticky letter header
        var prev = dt.previousElementSibling;
        if (prev && prev.classList && prev.classList.contains('glossary-sticky-letter')) {
          // Will be re-evaluated below
        }

        if (matches) visibleCount++;
      });

      // Update sticky letter headers: hide if no terms in that letter group are visible
      document.querySelectorAll('.glossary-sticky-letter').forEach(function(header) {
        var next = header.nextElementSibling;
        var hasVisible = false;
        while (next && !(next.classList && next.classList.contains('glossary-sticky-letter'))) {
          if (next.tagName === 'DT' && !next.hasAttribute('hidden')) {
            hasVisible = true;
            break;
          }
          next = next.nextElementSibling;
        }
        if(hasVisible){header.removeAttribute('hidden');}else{header.setAttribute('hidden','');}
      });

      // Show "no results" message
      if (noResults) {
        if(visibleCount === 0 && query){noResults.removeAttribute('hidden');}else{noResults.setAttribute('hidden','');}
      }
    });
  }

  /**
   * Sticky alphabetical section headers:
   * Inserts a sticky letter header (e.g. "A", "B", "C") before each
   * group of glossary terms sharing the same first letter.
   * On mobile these remain visible as the user scrolls.
   */
  function injectStickyLetterHeaders() {
    var dl = document.querySelector('#main dl');
    if (!dl) return;

    var terms = dl.querySelectorAll('dt');
    var currentLetter = '';

    terms.forEach(function(dt) {
      var letter = (dt.textContent || '').trim().charAt(0).toUpperCase();
      if (letter && letter !== currentLetter) {
        currentLetter = letter;
        var header = document.createElement('div');
        header.className = 'glossary-sticky-letter';
        header.setAttribute('aria-hidden', 'true');
        header.textContent = letter;
        dl.insertBefore(header, dt);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      injectStickyLetterHeaders();
      initGlossarySearch();
    });
  } else {
    injectStickyLetterHeaders();
    initGlossarySearch();
  }
})();
