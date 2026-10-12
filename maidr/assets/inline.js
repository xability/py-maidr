/* maidr inline: the charts py-maidr writes into a page Quarto renders (#895).
 *
 * Each chart is an <svg maidr="{json}"> in a .maidr-inline wrapper, and
 * maidr.js binds it from that attribute, as it does inside a frame. A chart
 * in a frame had a document to itself: the frame named it and sized it, and
 * its ids and stylesheets were its own. This script gives an inline chart
 * those back, much as r-maidr's inst/maidr-knitr/knitr-inline.js does for an
 * R chart in the same pages, and runs once however many charts carry it.
 *
 * What else a frame kept from the page -- the page's shortcuts, its
 * stylesheets' hold on the focus ring, the body maidr.js painted for high
 * contrast, the require.js Quarto puts on it -- maidr.js 4.15.0 and later
 * keeps from it itself. A render that loads an older maidr.js carries
 * inline-compat.js and inline-compat.css as well, with copies of those. */
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

  // --- Names ---------------------------------------------------------------

  // Until maidr.js has put its focusable element around a chart, the
  // wrapper is a named picture, so a reader whose maidr.js never loaded
  // still hears what it is: the cell's fig-alt, or else the chart's title.
  // The svg is hidden from the start: reveal.js reads a slide's text aloud
  // when it is shown, and a chart drawn with svg.fonttype 'none' has its
  // tick labels as text. Once maidr's element is there, maidr.js names it
  // and the wrapper's name goes. The element is then described by the
  // fig-alt, as r-maidr describes its charts by fig.alt; by the chart's
  // title, which named its frame (#453), unless maidr.js already names the
  // chart by it (xability/maidr#1384); and by the caption of a Quarto
  // figure around it.
  function settle() {
    var wrappers = document.querySelectorAll('.maidr-inline[data-maidr-inline]');
    for (var i = 0; i < wrappers.length; i++) {
      var wrapper = wrappers[i];
      var plot = wrapper.querySelector(PLOT);
      if (!plot) continue;
      wrapper.removeAttribute('data-maidr-inline');
      wrapper.removeAttribute('role');
      wrapper.removeAttribute('aria-label');
      describe(plot);
      fitChart(wrapper);
    }
    liftStyles();
  }

  // Each chart carries its stylesheets, so that a cell whose output is
  // hidden takes nothing from the next. In the page they move to the head,
  // one copy of the shared one: reveal.js's search walks the text of a
  // slide, <style> included, and rewrites the words it finds there.
  function liftStyles() {
    var styles = document.querySelectorAll('.maidr-inline > style');
    for (var i = 0; i < styles.length; i++) {
      var style = styles[i];
      if (style.hasAttribute('data-maidr-inline-css') &&
          document.head.querySelector('style[data-maidr-inline-css]')) {
        style.remove();
      } else {
        document.head.appendChild(style);
      }
    }
  }

  // maidr.js describes the element too, by its keyboard instructions, under
  // ids that start with maidr-instruction- (xability/maidr#1384). Those are
  // kept, after the page's: a reader hears what the chart is before how to
  // use it, and maidr adds and takes away its own as the reader enters and
  // uses the chart.
  var MAIDR_INSTRUCTION = 'maidr-instruction-';

  // Whether maidr.js already names the chart by this text: from
  // xability/maidr#1384 it names a chart by its title, then its type.
  function namedBy(plot, element) {
    var text = (element.textContent || '').trim();
    return !!text && (plot.getAttribute('aria-label') || '').indexOf(text) === 0;
  }

  function describe(plot) {
    var wrapper = wrapperOf(plot);
    if (!wrapper) return;
    var ids = [];
    var alt = wrapper.querySelector(':scope > .maidr-inline-alt[id]');
    if (alt) ids.push(alt.id);
    var title = wrapper.querySelector(':scope > .maidr-inline-title[id]');
    if (title && !namedBy(plot, title)) ids.push(title.id);
    var host = wrapper.parentNode && wrapper.parentNode.closest &&
      wrapper.parentNode.closest('[aria-describedby]');
    if (host && !inChart(host)) ids.push(host.getAttribute('aria-describedby'));
    if (!ids.length) return;
    var current = plot.getAttribute('aria-describedby') || '';
    var maidrIds = current.split(/\s+/).filter(function (id) {
      return id.indexOf(MAIDR_INSTRUCTION) === 0;
    });
    var value = ids.concat(maidrIds).join(' ');
    if (current !== value) {
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

  // A Quarto dashboard shows a plain figure as large as its card allows,
  // keeping its shape, centred in it (.quarto-dashboard-img-contain: width
  // and height 100%, object-fit: contain); and as wide as the card where the
  // card takes its height from what it holds: a scrolling dashboard, a row
  // that does not fill, a phone's single column. A chart is given the same
  // size and place, less a line kept below it for maidr's text. inline.css
  // centres it across the card; the card scrolls to maidr's braille and
  // review fields when they are open, and to a text longer than the line.
  var FITTED = '.html-fill-item > .maidr-inline';

  // The height of a line of maidr's text, which is set in the wrapper's.
  function textLine(wrapper) {
    var style = getComputedStyle(wrapper);
    var line = parseFloat(style.lineHeight);
    return line > 0 ? line : 1.5 * parseFloat(style.fontSize);
  }

  // A box's padding and border on one side.
  function edges(style, side) {
    return parseFloat(style['padding' + side]) + parseFloat(style['border' + side + 'Width']);
  }

  // A chart is fitted with the other charts of its card's body, which
  // shares its height among them.
  function fitChart(wrapper) {
    if (!wrapper || !wrapper.matches(FITTED)) return;
    var body = wrapper.parentElement.parentElement;
    if (body) fitCard(body);
  }

  function fitCard(body) {
    // Each chart's output box, and the card's body around them, which a
    // card can share among several outputs: a print() before a chart, two
    // charts from one cell.
    var wrappers = body.querySelectorAll(':scope > .html-fill-item > .maidr-inline');
    var charts = [];
    for (var i = 0; i < wrappers.length; i++) {
      var svg = wrappers[i].querySelector('svg.maidr-inline-svg');
      var view = svg && svg.viewBox && svg.viewBox.baseVal;
      if (!view || !(view.width > 0) || !(view.height > 0)) continue;
      var box = wrappers[i].parentElement;
      charts.push({ wrapper: wrappers[i], box: box, size: svg.style, view: view,
        scrolled: box.scrollTop });
    }
    // None, or a hidden tab or page: fitted when shown, which resizes it.
    if (!charts.length || !body.clientWidth) return;
    var chart;
    for (i = 0; i < charts.length; i++) {
      chart = charts[i];
      chart.wrapper.style.paddingTop = '';
      chart.box.style.flexBasis = '';
      chart.size.maxHeight = 'none';
      chart.size.width = '0px';
      chart.size.height = '0px';
    }
    // Whether the card sizes its body or the body takes its height from what
    // it holds: one the card sizes keeps its height whatever the charts'.
    charts[0].size.height = '4000px';
    var tall = body.clientHeight;
    charts[0].size.height = '0px';
    var layout = getComputedStyle(body);
    var sized = Math.abs(tall - body.clientHeight) < 1 &&
      /flex/.test(layout.display) && /^column/.test(layout.flexDirection);
    for (i = 0; i < charts.length; i++) {
      chart = charts[i];
      chart.style = getComputedStyle(chart.box);
      var width = chart.box.clientWidth - parseFloat(chart.style.paddingLeft) -
        parseFloat(chart.style.paddingRight);
      chart.scale = width / chart.view.width;
      // The body shares its height among its outputs in proportion to the
      // height each would have at the card's width (flex: 1 1 auto), which
      // for a plain figure is the image's. A chart's box asks for the
      // image's, whatever size the chart is then given in it.
      if (sized) {
        chart.box.style.flexBasis = chart.view.height * chart.scale +
          edges(chart.style, 'Top') + edges(chart.style, 'Bottom') + 'px';
      }
    }
    for (i = 0; i < charts.length; i++) {
      chart = charts[i];
      var room = 0;
      if (sized) {
        room = chart.box.clientHeight - parseFloat(chart.style.paddingTop) -
          parseFloat(chart.style.paddingBottom) - textLine(chart.wrapper);
        chart.scale = Math.min(chart.scale, Math.max(room, 96) / chart.view.height);
      }
      var height = chart.view.height * chart.scale;
      chart.size.width = chart.view.width * chart.scale + 'px';
      chart.size.height = height + 'px';
      // Centred down its box, with the line for maidr's text below it.
      if (room > height) chart.wrapper.style.paddingTop = (room - height) / 2 + 'px';
    }
    for (i = 0; i < charts.length; i++) charts[i].box.scrollTop = charts[i].scrolled;
  }

  // maidr's braille and review fields open below the chart, and a card that
  // fills with the chart scrolls to them. The browser scrolls to a field as
  // it takes the focus, when it is out of view then; one in view then can
  // still grow past the card's edge after.
  var FIELDS = 'textarea[id^="maidr-braille-textarea"], input[id^="maidr-review-input"]';

  function keepInView(target) {
    var wrapper = wrapperOf(target);
    if (!wrapper || !wrapper.matches(FITTED) || !target.matches(FIELDS)) return;
    requestAnimationFrame(function () {
      if (document.activeElement === target) {
        target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    });
  }

  // maidr's text, below the chart, is given one line. A longer one -- a
  // value that wraps in a narrow card -- grows past a card the chart fills,
  // and the card is scrolled as far as it takes to show it, as the reader
  // moves through the chart. The chart keeps its size: one that shrank and
  // grew back as the text did would move every mark under a reader's
  // magnifier. The instructions maidr shows as the chart takes the focus are
  // left where they run: scrolled to, the chart would move away from a
  // reader coming into it, and from under the pointer that clicked it.
  var TEXT = '[id^="maidr-text-container"]';
  var textObserver = null;
  // The chart the reader has pressed a key in since the focus came into it.
  var steered = null;

  function showText(wrapper) {
    if (!wrapper || wrapper !== steered || !wrapper.matches(FITTED) ||
        !wrapper.contains(document.activeElement)) return;
    var text = wrapper.querySelector(TEXT);
    // The text's own element and the rotor's below it.
    var area = text && text.parentElement;
    if (!area) return;
    var box = wrapper.parentElement;
    var top = box.getBoundingClientRect().top + box.clientTop;
    var r = area.getBoundingClientRect();
    var over = r.bottom - (top + box.clientHeight);
    // No further than keeps the text's first line in view.
    if (over > 0.5) box.scrollTop += Math.min(over, Math.max(0, r.top - top));
  }

  // maidr.js puts its text in the chart's figure when the chart takes the
  // focus, and takes it out when it loses it; the figure grows with it.
  function watchText(target, from) {
    var wrapper = wrapperOf(target);
    if (wrapperOf(from) !== wrapper) steered = null;
    if (!wrapper || !wrapper.matches(FITTED) || !window.ResizeObserver) return;
    var figure = wrapper.querySelector('figure[id^="maidr-figure"]');
    if (!figure) return;
    if (!textObserver) {
      textObserver = new ResizeObserver(function (entries) {
        for (var i = 0; i < entries.length; i++) showText(wrapperOf(entries[i].target));
      });
    }
    textObserver.observe(figure);
  }

  function fitCharts() {
    var wrappers = document.querySelectorAll(FITTED);
    if (!wrappers.length) return;
    var observer = window.ResizeObserver && new ResizeObserver(function (entries) {
      var bodies = [];
      for (var i = 0; i < entries.length; i++) {
        var body = entries[i].target.parentElement;
        if (body && bodies.indexOf(body) < 0) bodies.push(body);
      }
      // Fitted in the next frame: fitting in the callback resizes the box
      // it observes in the same frame, which the browser reports.
      requestAnimationFrame(function () {
        for (var j = 0; j < bodies.length; j++) fitCard(bodies[j]);
      });
    });
    for (var i = 0; i < wrappers.length; i++) {
      fitChart(wrappers[i]);
      if (observer) observer.observe(wrappers[i].parentElement);
    }
  }

  // --- Quarto cross-reference previews ---------------------------------------

  // Hovering a reference to a Quarto figure shows a copy of it in a tippy
  // popup: a second chart with the same ids and a second tab stop. The copy
  // is made inert and loses its tab stops and the attribute maidr.js binds
  // by, and every id the page already has; its url(#..) references find the
  // original's definitions then. A copy of a figure on another page, which
  // Quarto fetches, keeps the ids nothing else on this page has, or its
  // glyphs and markers would find nothing.
  function quietPreview(root) {
    if (!root.querySelector(CHART + ', svg[maidr]')) return;
    root.setAttribute('inert', '');
    var nodes = root.querySelectorAll('[id], [tabindex], [maidr], [maidr-data]');
    for (var i = 0; i < nodes.length; i++) {
      var id = nodes[i].id;
      if (id && document.getElementById(id) !== nodes[i]) nodes[i].removeAttribute('id');
      nodes[i].removeAttribute('tabindex');
      nodes[i].removeAttribute('maidr');
      nodes[i].removeAttribute('maidr-data');
    }
  }

  // --- An output shown twice -------------------------------------------------

  // A page can hold one chart's output twice -- a cell embedded twice, or a
  // chart displayed twice -- and then holds its ids twice, so each copy's
  // selectors find the other copy's marks. The second copy is given ids of
  // its own before maidr.js binds it: held when it is added, and renamed
  // once all of it is there, which its own loader below it says; or at once
  // when it arrives whole, after the page has loaded.
  var HELD = 'data-maidr-inline-held';
  var UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g;

  function hold(svg) {
    if (!svg.id || document.querySelectorAll('[id="' + svg.id + '"]').length < 2) {
      return false;
    }
    svg.setAttribute(HELD, svg.getAttribute('maidr'));
    svg.removeAttribute('maidr');
    return true;
  }

  function hex(length) {
    var bytes = new Uint8Array(length);
    window.crypto.getRandomValues(bytes);
    var out = '';
    for (var i = 0; i < length; i++) out += (bytes[i] % 16).toString(16);
    return out;
  }

  function freshUuid() {
    var h = hex(32);
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-4' + h.slice(13, 16) + '-a' +
      h.slice(17, 20) + '-' + h.slice(20);
  }

  // py-maidr's ids are uuids or carry the chart's key, so a fresh value for
  // each, written wherever it occurs in the copy -- ids, references, the
  // schema held for maidr.js -- gives the copy ids of its own.
  function rekey(svg) {
    var tokens = {};
    var key = /maidr-inline-(m[0-9a-f]{12})/.exec(svg.getAttribute('class') || '');
    if (key) tokens[key[1]] = 'm' + hex(12);
    var named = [svg].concat(Array.prototype.slice.call(svg.querySelectorAll('[id], [maidr]')));
    for (var i = 0; i < named.length; i++) {
      var found = (named[i].id + ' ' + (named[i] === svg ? '' : named[i].getAttribute('maidr') || ''))
        .match(UUID) || [];
      for (var j = 0; j < found.length; j++) {
        if (!tokens[found[j]]) tokens[found[j]] = freshUuid();
      }
    }
    var pattern = new RegExp(Object.keys(tokens).join('|'), 'g');
    var swap = function (value) {
      return value.replace(pattern, function (token) { return tokens[token]; });
    };
    var elements = [svg].concat(Array.prototype.slice.call(svg.querySelectorAll('*')));
    for (var k = 0; k < elements.length; k++) {
      var attributes = Array.prototype.slice.call(elements[k].attributes);
      for (var m = 0; m < attributes.length; m++) {
        // Not the class: it names the chart's style, which every copy shares.
        if (attributes[m].name === 'class') continue;
        var swapped = swap(attributes[m].value);
        if (swapped !== attributes[m].value) elements[k].setAttribute(attributes[m].name, swapped);
      }
    }
    var wrapper = wrapperOf(svg);
    var title = wrapper && wrapper.querySelector(':scope > .maidr-inline-title[id]');
    if (title) title.id = swap(title.id);
    var schema = svg.getAttribute(HELD);
    svg.removeAttribute(HELD);
    svg.setAttribute('maidr', schema);
  }

  window.__maidrInlineClaim = function (script) {
    var wrapper = wrapperOf(script);
    var svg = wrapper && wrapper.querySelector('svg[' + HELD + ']');
    if (svg) rekey(svg);
  };

  function holdCopies(node) {
    var svgs = node.matches('.maidr-inline svg[maidr]') ? [node]
      : node.querySelectorAll('.maidr-inline svg[maidr]');
    for (var i = 0; i < svgs.length; i++) {
      if (hold(svgs[i]) && document.readyState !== 'loading') rekey(svgs[i]);
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
          var root = node.closest('[data-tippy-root]') ||
            (node.querySelector && node.querySelector('[data-tippy-root]'));
          if (root) {
            quietPreview(root);
            continue;
          }
          holdCopies(node);
        }
      }
      settleSoon();
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  window.addEventListener('keydown', function (event) {
    if (!focusInChart()) return;
    steered = wrapperOf(document.activeElement);
  }, true);

  document.addEventListener('focusin', function (event) {
    var target = event.target;
    if (!inChart(target)) return;
    if (target.matches && target.matches(PLOT)) describe(target);
    sizeDialogs(wrapperOf(target));
    keepInView(target);
    watchText(target, event.relatedTarget);
  }, true);

  function onReady() {
    settle();
    window.addEventListener('load', function () {
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
