/* maidr inline, for a maidr.js older than 4.15.0 (#895).
 *
 * Copies of what maidr.js does itself from 4.15.0, for a chart written into a
 * page Quarto renders. A chart carries this beside inline.js only when its
 * render loads an older maidr.js, or one whose version it cannot tell (a pin
 * to `latest`); see carries_copies in maidr/util/inline_chart.py. Each copy,
 * and the change to maidr.js that ships it:
 *
 * - High contrast: maidr.js paints document.body, which inline is the whole
 *   page (xability/maidr#1388 paints the chart).
 * - The page's shortcuts, the Shift+Tab hand-off on a deck's slide and the
 *   search key of reveal.js's plugin (xability/maidr#1390, which says so in
 *   maidrLive.features.hostGuards; these defer to it, for a pin to `latest`).
 *
 * maidr.js listens for its keys on the document and does not stop them, so
 * no listener of this script can keep a key from the page without keeping it
 * from maidr.js too. The page's shortcuts are held off where the page asks
 * whether to act -- reveal.js's keyboardCondition, Quarto's search, a bslib
 * card's Escape -- and only while the focus is in a chart, unless maidr.js
 * does so itself.
 *
 * inline-compat.css holds the stylesheet's copies, and inline-amd.js the
 * one of what maidr.js 4.15.0 does on a page with require.js
 * (xability/maidr#1385). */
(function () {
  'use strict';
  if (window.__maidrInlineCompat) return;
  window.__maidrInlineCompat = true;

  // An inline chart, or any chart maidr.js mounted on the page.
  var CHART = '.maidr-inline, article[id^="maidr-article-"]';

  function inChart(node) {
    return !!(node && node.closest && node.closest(CHART));
  }

  function focusInChart() {
    return inChart(document.activeElement);
  }

  function wrapperOf(node) {
    return node && node.closest ? node.closest('.maidr-inline') : null;
  }

  // --- High contrast ---------------------------------------------------------

  // maidr.js paints document.body for high contrast. In a frame that was the
  // chart's own body; inline it is the whole page. While maidr has it painted,
  // the page is given its own colours back and the chart's wrapper takes
  // maidr's, which is what the frame looked like. The body's inline style is
  // left as maidr.js wrote it -- inline-compat.css overrides it -- so that
  // maidr.js putting it back is a change this sees, whenever it happens: high
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

  // A maidr.js that keeps the page's shortcuts off a chart's keys itself --
  // these guards, the Shift+Tab hand-off and reveal.js's search key below --
  // says so in maidrLive.features, and is left to it. It marks what it wraps
  // with __maidrHostGuard, and honours this script's __maidrInline, so that
  // whichever of the two comes first wraps an object and the other leaves it.
  function nativeGuards() {
    var live = window.maidrLive;
    return !!(live && live.features && live.features.hostGuards >= 1);
  }

  function isGuarded(target) {
    return !!(target.__maidrInline || target.__maidrHostGuard);
  }

  // reveal.js (Quarto revealjs) reads keyboardCondition on every keydown;
  // whatever the deck set is kept.
  function shimReveal() {
    var reveal = window.Reveal;
    if (!reveal || isGuarded(reveal) || typeof reveal.configure !== 'function' ||
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
    if (typeof open !== 'function' || isGuarded(open)) return;
    var guarded = function () {
      if (focusInChart()) return;
      return open.apply(this, arguments);
    };
    guarded.__maidrInline = true;
    window.quartoOpenSearch = guarded;
  }

  // Spelt in two parts: Quarto's dashboard filter moves any cell output that
  // holds the Lua pattern 'bslib-' -- which matches 'bsli' -- out of its
  // card, as a component of its own.
  var BSLIB = 'bs' + 'lib';

  // A bslib card shown full screen (a Quarto dashboard's) leaves it on
  // Escape pressed anywhere, through a listener on the document that it
  // keeps on the card's instance. The one for a card around a chart ignores
  // the keys pressed in the chart, where Escape closes maidr's own modes.
  function shimCard(card) {
    var Card = window[BSLIB] && window[BSLIB].Card;
    var instance = Card && typeof Card.getInstance === 'function' && Card.getInstance(card);
    if (!instance || isGuarded(instance) || typeof instance._exitFullScreenOnEscape !== 'function') {
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
    if (nativeGuards()) return;
    for (var card = node.closest('.' + BSLIB + '-card'); card;
      card = card.parentElement && card.parentElement.closest('.' + BSLIB + '-card')) {
      shimCard(card);
    }
  }

  function shimHosts() {
    if (nativeGuards()) return;
    shimReveal();
    shimQuartoSearch();
  }

  // reveal.js's search plugin opens on Ctrl+Shift+F (Cmd on a Mac) from a
  // listener of its own on the document, which keyboardCondition does not
  // reach. Its test is a capital F with Ctrl or Cmd held, so Ctrl+F with
  // Caps Lock on opens it too. The key is stopped on the root element as it
  // bubbles up: after the React handlers inside the page have had it --
  // among them the recorder that takes a new shortcut in maidr's settings --
  // and before the document. maidr.js's own shortcuts listen on the document
  // too, so the stopped key reaches them no more than the plugin, and it is
  // stopped only on a deck that has the plugin: anywhere else it may be a
  // shortcut the reader gave a command of maidr's.
  function shimRevealSearch(event) {
    if (!(event.ctrlKey || event.metaKey) || event.key !== 'F' || nativeGuards()) {
      return;
    }
    var reveal = window.Reveal;
    if (window.RevealSearch ||
        (reveal && typeof reveal.hasPlugin === 'function' && reveal.hasPlugin('search'))) {
      event.stopPropagation();
    }
  }

  // --- Shift+Tab out of a chart ----------------------------------------------

  // On a reveal.js slide a chart is often the first thing Tab reaches, and
  // Shift+Tab from it would leave the page for the browser's own controls,
  // where no key reaches the deck. maidr.js hands the reader to the slide
  // when its chart is framed (FrameFocusService); this does the same inline,
  // only in a deck and only when nothing on the page comes before the chart.
  // On any other page the browser's own Shift+Tab is the right answer: the
  // elements above a chart are its wrappers or the page's.
  var TABBABLE = 'a[href],area[href],button:not([disabled]),input:not([disabled]),' +
    'select:not([disabled]),textarea:not([disabled]),iframe,audio[controls],video[controls],' +
    '[contenteditable]:not([contenteditable="false"]),[tabindex]';

  // A negative tabindex takes any of these out of the tab order, a link or a
  // button as much as anything. Read from the attribute, as the browser reads
  // it, not from tabIndex, which is -1 in Chromium for an editable element
  // that has no tabindex and is a tab stop all the same.
  function reachable(element) {
    if (parseInt(element.getAttribute('tabindex'), 10) < 0) return false;
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
        event.metaKey || event.defaultPrevented || !window.Reveal || nativeGuards()) {
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

  // --- Start -----------------------------------------------------------------

  window.addEventListener('keydown', function (event) {
    if (!focusInChart()) return;
    shimHosts();
    handOff(event);
  }, true);

  document.documentElement.addEventListener('keydown', function (event) {
    if (focusInChart()) shimRevealSearch(event);
  }, false);

  document.addEventListener('focusin', function (event) {
    var target = event.target;
    if (!inChart(target)) return;
    notePageColours();
    shimHosts();
    shimCards(target);
  }, true);

  function onReady() {
    shimHosts();
    watchContrast();
    window.addEventListener('load', shimHosts);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})();
