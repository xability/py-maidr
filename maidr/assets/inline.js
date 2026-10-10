/* maidr inline: the charts py-maidr writes into a page Quarto renders (#895).
 *
 * Each chart is an <svg maidr="{json}"> in a .maidr-inline wrapper, and
 * maidr.js binds it from that attribute, as it does inside a frame. A chart
 * in a frame had a document to itself: no key it was sent reached the page,
 * the frame named it, and maidr.js painted the frame's body for high
 * contrast. This script gives an inline chart those back, much as r-maidr's
 * inst/maidr-knitr/knitr-inline.js does for an R chart in the same pages, and
 * runs once however many charts carry it.
 *
 * maidr.js listens for its keys on the document and does not stop them, so
 * no listener of this script can keep a key from the page without keeping it
 * from maidr.js too. The page's shortcuts are held off where the page asks
 * whether to act -- reveal.js's keyboardCondition, Quarto's search, a bslib
 * card's Escape -- and only while the focus is in a chart. */
(function () {
  'use strict';
  if (window.__maidrInline) return;
  window.__maidrInline = true;

  // An inline chart, or any chart maidr.js mounted on the page.
  var CHART = '.maidr-inline, article[id^="maidr-article-"]';
  // The element maidr.js makes focusable around a chart's svg.
  var PLOT = 'figure[id^="maidr-figure"] > [tabindex]';

  function inChart(node) {
    return !!(node && node.closest && node.closest(CHART));
  }

  function focusInChart() {
    return inChart(document.activeElement);
  }

  function wrapperOf(node) {
    return node && node.closest ? node.closest('.maidr-inline') : null;
  }

  // --- require.js ------------------------------------------------------------

  // Quarto puts require.js on every page a Jupyter render writes HTML into.
  // maidr.js and its locale packs are UMD, so under it they hand themselves to
  // define() as anonymous modules and never run: no chart is bound, and no
  // error says so. A script passed here runs its factory itself instead;
  // every other script's define() reaches require.js unchanged.
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
  window.__maidrInlineWithoutAmd = withoutAmd;

  // A locale pack maidr.js adds to the page for a reader's language.
  var PACK = /\/locale-[a-z]{2,3}(?:-[A-Za-z0-9]+)?\.js(?:[?#]|$)/;

  // --- Names ---------------------------------------------------------------

  // Until maidr.js has put its focusable element around a chart, the svg is
  // a named picture, so a reader whose maidr.js never loaded still hears
  // what it is. Once that element is there, maidr.js names it, and the svg
  // leaves the accessibility tree: reveal.js reads a slide's text aloud when
  // it is shown, and would read the chart's. The chart's title, which named
  // its frame (#453), describes the element instead, after the caption of a
  // Quarto figure around it.
  function settle() {
    var svgs = document.querySelectorAll('svg[data-maidr-inline]');
    for (var i = 0; i < svgs.length; i++) {
      var svg = svgs[i];
      var plot = svg.closest(PLOT);
      if (!plot) continue;
      svg.removeAttribute('data-maidr-inline');
      svg.removeAttribute('role');
      svg.removeAttribute('aria-label');
      svg.setAttribute('aria-hidden', 'true');
      describe(plot);
      fitChart(wrapperOf(plot));
    }
  }

  function describe(plot) {
    var wrapper = wrapperOf(plot);
    if (!wrapper) return;
    var ids = [];
    var title = wrapper.querySelector(':scope > .maidr-inline-title[id]');
    if (title) ids.push(title.id);
    var host = wrapper.parentNode && wrapper.parentNode.closest &&
      wrapper.parentNode.closest('[aria-describedby]');
    if (host && !inChart(host)) ids.push(host.getAttribute('aria-describedby'));
    var value = ids.join(' ');
    if (value && plot.getAttribute('aria-describedby') !== value) {
      plot.setAttribute('aria-describedby', value);
    }
  }

  // --- maidr's dialogs -------------------------------------------------------

  // Text of maidr's dialogs that MUI sizes from its theme: 1rem under MUI's
  // default theme, or 0.875rem for body2.
  var DIALOG_TEXT = '[role="dialog"] .MuiTypography-body1, [role="dialog"] .MuiTypography-body2, ' +
    '[role="dialog"] .MuiInputBase-root';

  // The font size an element with these classes, or this font size, comes
  // out at at the root, where no rule of the page for a place in it applies.
  function probeFontSize(className, fontSize) {
    var probe = document.createElement('maidr-inline-probe');
    probe.className = className;
    probe.style.setProperty('display', 'none', 'important');
    if (fontSize) probe.style.setProperty('font-size', fontSize, 'important');
    document.documentElement.appendChild(probe);
    try {
      return parseFloat(getComputedStyle(probe).fontSize);
    } finally {
      probe.remove();
    }
  }

  // maidr opens its dialogs inside the chart, so they take the page's sizes:
  // a deck that zooms its slides zooms them past the window, and their text
  // is in rem. Each wrapper carries, for inline.css, the zoom that undoes the
  // page's, the size one rem of MUI's theme came out at, and the zoom that
  // brings that to the reader's default font size.
  function sizeDialogs(wrapper) {
    if (!wrapper) return;
    var host = 1;
    for (var node = wrapper.parentElement; node; node = node.parentElement) {
      var z = parseFloat(getComputedStyle(node).zoom);
      if (z > 0) host *= z;
    }
    wrapper.style.setProperty('--maidr-inline-unzoom', String(1 / host));
    var text = wrapper.querySelector(DIALOG_TEXT);
    if (!text) return;
    var size = text.classList.contains('MuiTypography-body2') ? 0.875 : 1;
    var rem = Math.round(probeFontSize(text.className) / size * 100) / 100;
    var medium = probeFontSize('', 'medium');
    if (!(rem > 0) || !(medium > 0)) return;
    wrapper.style.setProperty('--maidr-inline-rem', rem + 'px');
    wrapper.style.setProperty('--maidr-inline-zoom', String(rem < medium ? medium / rem : 1));
  }

  // --- Dashboards ------------------------------------------------------------

  // A Quarto dashboard sizes each card to the window and hides what does not
  // fit. A chart taller than its card is shrunk to it, keeping its shape and
  // a line for maidr's text below it. A card sized by its content never
  // overflows, so only an overflowing one shrinks its chart.
  var FITTED = '.html-fill-item > .maidr-inline';

  function fitChart(wrapper) {
    if (!wrapper || !wrapper.matches(FITTED)) return;
    var box = wrapper.parentElement;
    var svg = wrapper.querySelector('svg.maidr-inline-svg');
    if (!box || !svg) return;
    svg.style.maxHeight = '';
    svg.style.width = '';
    var over = box.scrollHeight - box.clientHeight;
    if (over <= 1) return;
    var line = 2.5 * parseFloat(getComputedStyle(wrapper).fontSize);
    var height = svg.getBoundingClientRect().height - over - line;
    svg.style.width = 'auto';
    svg.style.maxHeight = Math.max(height, 96) + 'px';
  }

  function fitCharts() {
    var wrappers = document.querySelectorAll(FITTED);
    if (!wrappers.length) return;
    var observer = window.ResizeObserver && new ResizeObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        var wrapper = entries[i].target.querySelector(':scope > .maidr-inline');
        // Fitted in the next frame: fitting in the callback resizes the box
        // it observes in the same frame, which the browser reports.
        if (wrapper) requestAnimationFrame(fitChart.bind(null, wrapper));
      }
    });
    for (var i = 0; i < wrappers.length; i++) {
      fitChart(wrappers[i]);
      if (observer) observer.observe(wrappers[i].parentElement);
    }
  }

  // --- High contrast ---------------------------------------------------------

  // maidr.js paints document.body for high contrast. In a frame that was the
  // chart's own body; inline it is the whole page. While maidr has it painted,
  // the page is given its own colours back and the chart's wrapper takes
  // maidr's, which is what the frame looked like. The body's inline style is
  // left as maidr.js wrote it -- inline.css overrides it -- so that maidr.js
  // putting it back is a change this sees, whenever it happens: high
  // contrast turned off, or the reader leaving the chart.
  var painted = null;
  var pageInline = null;

  function bodyColours() {
    var style = document.body.style;
    return [style.getPropertyValue('background-color'), style.getPropertyValue('color')];
  }

  function unpaint() {
    var root = document.documentElement;
    root.classList.remove('maidr-inline-contrast');
    if (painted) {
      painted.style.removeProperty('background-color');
      painted.style.removeProperty('color');
      painted = null;
    }
  }

  // The page's colours, read before maidr paints the body over them.
  function notePageColours() {
    if (!document.body || document.documentElement.classList.contains('maidr-inline-contrast')) return;
    var computed = getComputedStyle(document.body);
    var root = document.documentElement.style;
    root.setProperty('--maidr-inline-page-bg', computed.backgroundColor);
    root.setProperty('--maidr-inline-page-fg', computed.color);
    pageInline = bodyColours();
  }

  function followContrast() {
    var now = bodyColours();
    if (!pageInline || (now[0] === pageInline[0] && now[1] === pageInline[1])) {
      unpaint();
      return;
    }
    var wrapper = wrapperOf(document.activeElement);
    if (!wrapper) {
      // The page changed its own body, not maidr.
      unpaint();
      pageInline = now;
      return;
    }
    if (painted && painted !== wrapper) unpaint();
    wrapper.style.setProperty('background-color', now[0]);
    wrapper.style.setProperty('color', now[1]);
    painted = wrapper;
    document.documentElement.classList.add('maidr-inline-contrast');
  }

  function watchContrast() {
    if (!document.body || !window.MutationObserver) return;
    notePageColours();
    new MutationObserver(followContrast)
      .observe(document.body, { attributes: true, attributeFilter: ['style'] });
  }

  // --- Host page shortcuts ---------------------------------------------------

  // reveal.js (Quarto revealjs) reads keyboardCondition on every keydown;
  // whatever the deck set is kept.
  function shimReveal() {
    var reveal = window.Reveal;
    if (!reveal || reveal.__maidrInline || typeof reveal.configure !== 'function' ||
        typeof reveal.getConfig !== 'function') {
      return;
    }
    reveal.__maidrInline = true;
    function apply() {
      var previous = reveal.getConfig().keyboardCondition;
      reveal.configure({
        keyboardCondition: function () {
          if (focusInChart()) return false;
          if (typeof previous === 'function') return previous.apply(this, arguments);
          if (previous === 'focused') return reveal.isFocused();
          return true;
        }
      });
    }
    if (typeof reveal.isReady === 'function' && reveal.isReady()) {
      apply();
    } else if (typeof reveal.on === 'function') {
      reveal.on('ready', apply);
    } else {
      reveal.__maidrInline = false;
    }
  }

  // The search of a Quarto website or book opens on f, s or / outside a form
  // field, through window.quartoOpenSearch, looked up when the key is let go.
  function shimQuartoSearch() {
    var open = window.quartoOpenSearch;
    if (typeof open !== 'function' || open.__maidrInline) return;
    var guarded = function () {
      if (focusInChart()) return;
      return open.apply(this, arguments);
    };
    guarded.__maidrInline = true;
    window.quartoOpenSearch = guarded;
  }

  // A bslib card shown full screen (a Quarto dashboard's) leaves it on
  // Escape pressed anywhere, through a listener on the document that it
  // keeps on the card's instance. The one for a card around a chart ignores
  // the keys pressed in the chart, where Escape closes maidr's own modes.
  function shimCard(card) {
    var Card = window.bslib && window.bslib.Card;
    var instance = Card && typeof Card.getInstance === 'function' && Card.getInstance(card);
    if (!instance || instance.__maidrInline || typeof instance._exitFullScreenOnEscape !== 'function') {
      return;
    }
    instance.__maidrInline = true;
    var previous = instance._exitFullScreenOnEscape;
    var guarded = function (event) {
      if (inChart(event.target)) return;
      return previous.call(instance, event);
    };
    if (card.getAttribute('data-full-screen') === 'true') {
      document.removeEventListener('keydown', previous, false);
      document.addEventListener('keydown', guarded, false);
    }
    instance._exitFullScreenOnEscape = guarded;
  }

  function shimCards(node) {
    for (var card = node.closest('.bslib-card'); card;
      card = card.parentElement && card.parentElement.closest('.bslib-card')) {
      shimCard(card);
    }
  }

  function shimHosts() {
    shimReveal();
    shimQuartoSearch();
  }

  // --- Shift+Tab out of a chart ----------------------------------------------

  // On a reveal.js slide a chart is often the first thing Tab reaches, and
  // Shift+Tab from it would leave the page for the browser's own controls,
  // where no key reaches the deck. maidr.js hands the reader to the slide
  // when its chart is framed (FrameFocusService); this does the same inline,
  // and only when nothing on the page comes before the chart.
  var TABBABLE = 'a[href],area[href],button:not([disabled]),input:not([disabled]),' +
    'select:not([disabled]),textarea:not([disabled]),iframe,audio[controls],video[controls],' +
    '[contenteditable]:not([contenteditable="false"]),[tabindex]:not([tabindex^="-"])';

  function reachable(element) {
    if (element.closest('[hidden],[aria-hidden="true"],[inert]')) return false;
    var style = getComputedStyle(element);
    return style.display !== 'none' && style.visibility !== 'hidden';
  }

  function takeFocus(element) {
    var added = !element.hasAttribute('tabindex');
    if (added) element.setAttribute('tabindex', '-1');
    element.focus();
    if (document.activeElement === element) return true;
    if (added) element.removeAttribute('tabindex');
    return false;
  }

  function handOff(event) {
    if (event.key !== 'Tab' || !event.shiftKey || event.altKey || event.ctrlKey ||
        event.metaKey || event.defaultPrevented) {
      return;
    }
    var active = document.activeElement;
    var wrapper = wrapperOf(active);
    if (!wrapper || active.closest('[role="dialog"],[aria-modal="true"]')) return;
    var stops = document.querySelectorAll(TABBABLE);
    for (var i = 0; i < stops.length && stops[i] !== active; i++) {
      if (reachable(stops[i])) return;
    }
    event.preventDefault();
    var section = wrapper.closest('section,article,[role="region"]');
    var candidates = section ? [section] : [];
    for (var node = wrapper.parentElement; node; node = node.parentElement) {
      if (node !== section) candidates.push(node);
    }
    for (var j = 0; j < candidates.length; j++) {
      if (takeFocus(candidates[j])) return;
    }
    active.blur();
  }

  // --- Quarto cross-reference previews ---------------------------------------

  // Hovering a reference to a Quarto figure shows a copy of it in a tippy
  // popup: a second chart with the same ids and a second tab stop. The copy
  // is made inert and loses its ids, its tab stops and the attribute maidr.js
  // binds by; its url(#..) references still find the original's definitions.
  function quietPreview(root) {
    if (!root.querySelector(CHART + ', svg[maidr]')) return;
    root.setAttribute('inert', '');
    var nodes = root.querySelectorAll('[id], [tabindex], [maidr], [maidr-data]');
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].removeAttribute('id');
      nodes[i].removeAttribute('tabindex');
      nodes[i].removeAttribute('maidr');
      nodes[i].removeAttribute('maidr-data');
    }
  }

  // --- Start -----------------------------------------------------------------

  var settling = false;
  function settleSoon() {
    if (settling) return;
    settling = true;
    requestAnimationFrame(function () {
      settling = false;
      settle();
    });
  }

  // Created before maidr.js loads, so this sees a preview's copy first.
  if (window.MutationObserver) {
    new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var added = records[i].addedNodes;
        for (var j = 0; j < added.length; j++) {
          var node = added[j];
          if (node.nodeType !== 1) continue;
          // Seen before it runs: a script added with a src waits for it.
          if (node.tagName === 'SCRIPT' && PACK.test(node.src || '')) {
            withoutAmd(node);
            continue;
          }
          var root = node.closest('[data-tippy-root]') ||
            (node.querySelector && node.querySelector('[data-tippy-root]'));
          if (root) quietPreview(root);
        }
      }
      settleSoon();
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  window.addEventListener('keydown', function (event) {
    if (!focusInChart()) return;
    shimHosts();
    handOff(event);
  }, true);

  document.addEventListener('focusin', function (event) {
    var target = event.target;
    if (!inChart(target)) return;
    notePageColours();
    shimHosts();
    shimCards(target);
    if (target.matches && target.matches(PLOT)) describe(target);
    sizeDialogs(wrapperOf(target));
  }, true);

  function onReady() {
    shimHosts();
    watchContrast();
    settle();
    window.addEventListener('load', function () {
      shimHosts();
      settle();
      fitCharts();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
