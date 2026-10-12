/* maidr inline, on a page with require.js, for a UMD maidr.js or locale pack (#895).
 *
 * Quarto puts require.js on every page a Jupyter render writes HTML into.
 * maidr.js and its locale packs older than 4.15.0 are UMD, so under it they
 * hand themselves to define() as anonymous modules and never run: no chart is
 * bound, or the reader's language never arrives, and no error says so. From
 * 4.15.0 each runs first and registers with define() afterwards
 * (xability/maidr#1385).
 *
 * A chart carries this when its render loads an older maidr.js, whose packs
 * sit beside it (with inline-compat.js), and when a directory of locale packs
 * is configured (set_locale_base_url, MAIDR_LOCALE_BASE_URL), whose packs may
 * be of any release; see carries_amd_shim in maidr/util/inline_chart.py. A
 * pack from 4.15.0 or later handed to it runs as it would have anyway. */
(function () {
  'use strict';
  if (window.__maidrInlineWithoutAmd) return;

  // A script passed here runs its factory itself instead; every other
  // script's define() reaches require.js unchanged.
  var noAmd = [];
  function withoutAmd(script) {
    var amd = window.define;
    if (typeof amd !== 'function' || !amd.amd) return;
    noAmd.push(script);
    if (amd.__maidrInline) return;
    var shim = function () {
      var factory = arguments[arguments.length - 1];
      if (noAmd.indexOf(document.currentScript) >= 0 && typeof factory === 'function') {
        return factory();
      }
      return amd.apply(this, arguments);
    };
    for (var key in amd) shim[key] = amd[key];
    shim.__maidrInline = true;
    window.define = shim;
  }
  // The loader hands it an older maidr.js; see loader_js.
  window.__maidrInlineWithoutAmd = withoutAmd;

  // A locale pack maidr.js adds to the page for a reader's language.
  var PACK = /\/locale-[a-z]{2,3}(?:-[A-Za-z0-9]+)?\.js(?:[?#]|$)/;

  // Created before maidr.js loads, so this sees a locale pack it adds.
  if (window.MutationObserver) {
    new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var added = records[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var node = added[j];
          // Seen before it runs: a script added with a src waits for it.
          if (node.nodeType === 1 && node.tagName === 'SCRIPT' && PACK.test(node.src || '')) {
            withoutAmd(node);
          }
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
