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
#:
#: The price of not being event-driven is a poll that never stops: a
#: 200 ms timer, running for the life of the tab, re-scanning
#: ``.shiny-html-output`` on every tick. On a dashboard with many charts
#: that is a small continuous cost paid whether or not anyone ever
#: touches a chart. It is deliberate rather than overlooked -- there is
#: no signal to wait on instead -- and it is the first thing to revisit
#: if the runtime ever exposes a focus event that crosses the frame
#: boundary.
FOCUS_RESTORE_JS = """
(function () {
  if (window.__maidrShinyFocusRestore) return;
  window.__maidrShinyFocusRestore = true;

  // `[data-maidr-chart]` rather than a bare `iframe`: a host page may put
  // its own iframe in the same output container, and treating that as the
  // chart would force focus onto someone else's embed. The roles cover
  // the non-iframe render, where the runtime owns the element and marks
  // it itself.
  var CHART = '[data-maidr-chart], [role="img"], [role="application"]';
  var SAMPLE = 200;
  var held = null;
  var observed = [];

  function adrift() {
    var a = document.activeElement;
    return !a || a === document.body || a === document.documentElement;
  }

  function sample() {
    if (adrift()) return;
    var a = document.activeElement;
    if (!a.closest) { held = null; return; }
    // The chart itself, not merely something in a container that has one.
    // A caption or a download link beside the chart is a place a reader
    // may have gone on purpose, and losing it should not send them to the
    // chart instead.
    var chart = a.closest(CHART);
    var c = a.closest('.shiny-html-output');
    held = chart && c && c.id ? { id: c.id, el: chart } : null;
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
    // Drop observers whose container has left the page. `removeUI` and an
    // unmounting `conditionalPanel` both do that, and without this the
    // list grows for the life of a session that adds and removes outputs.
    for (var i = observed.length - 1; i >= 0; i--) {
      if (!observed[i].container.isConnected) {
        observed[i].observer.disconnect();
        observed.splice(i, 1);
      }
    }

    var containers = document.querySelectorAll('.shiny-html-output');
    for (var j = 0; j < containers.length; j++) {
      var c = containers[j];
      if (!c.id) continue;
      var seen = false;
      for (var k = 0; k < observed.length; k++) {
        if (observed[k].container === c) { seen = true; break; }
      }
      if (seen) continue;
      var obs = new MutationObserver(
        (function (el) { return function () { restore(el); }; })(c)
      );
      obs.observe(c, { childList: true, subtree: true });
      observed.push({ container: c, observer: obs });
    }
  }

  setInterval(function () { sample(); watch(); }, SAMPLE);
})();
"""

__all__ = ["FOCUS_RESTORE_JS"]
