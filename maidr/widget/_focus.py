"""Keeping a reader's place when Shiny replaces a chart.

A Shiny output is replaced wholesale on every reactive flush, taking the
focused element with it.  For a chart that is navigated by keyboard, that
ejects the reader to the top of the document mid-read, with nothing said
(#484).  The script here puts focus back.
"""

from __future__ import annotations

#: Installed once per page, alongside the first rendered chart.
#:
#: Two things rule out an event-driven version, and both were established
#: in a browser rather than reasoned about.  Removing the focused element
#: does not reliably fire ``blur``/``focusout``; and moving focus *into*
#: an iframe fires no ``focusin`` in the parent document at all --
#: ``document.activeElement`` simply becomes the frame.  Since a chart is
#: rendered into an iframe today, an event-driven version sees nothing at
#: all on the path that matters.  So "the chart had focus" is established
#: by sampling, and the re-render is detected by observing the container.
#:
#: The conditions are deliberately narrow, because the failure mode of
#: being too eager is worse than the bug: focus is restored only when the
#: element that held it has left the document *and* focus landed nowhere.
#: A reader who tabs away, clicks another control, or moves focus on
#: purpose is never pulled back, and a chart nobody had focused never
#: takes focus at all.
FOCUS_RESTORE_JS = """
(function () {
  if (window.__maidrShinyFocusRestore) return;
  window.__maidrShinyFocusRestore = true;

  var CHART = 'iframe, [role="img"], [role="application"]';
  var SAMPLE = 200;
  var held = null;
  var observed = new WeakSet();

  function adrift() {
    var a = document.activeElement;
    return !a || a === document.body || a === document.documentElement;
  }

  function sample() {
    if (adrift()) return;
    var a = document.activeElement;
    var c = a.closest && a.closest('.shiny-html-output');
    held = c && c.id && c.querySelector(CHART) ? { id: c.id, el: a } : null;
  }

  function restore(container) {
    if (!held || held.id !== container.id) return;
    if (held.el.isConnected) return;
    if (!adrift()) return;
    var target = container.querySelector(CHART);
    if (!target) return;
    target.focus();
    held = { id: container.id, el: target };
  }

  function watch() {
    var containers = document.querySelectorAll('.shiny-html-output');
    for (var i = 0; i < containers.length; i++) {
      var c = containers[i];
      if (observed.has(c) || !c.id) continue;
      observed.add(c);
      new MutationObserver(
        (function (el) { return function () { restore(el); }; })(c)
      ).observe(c, { childList: true, subtree: true });
    }
  }

  setInterval(function () { sample(); watch(); }, SAMPLE);
})();
"""

__all__ = ["FOCUS_RESTORE_JS"]
