"""Every announcement reaches the reader in a freshly inserted alert (#235).

A screen reader user in Firefox on Windows arrowed through a chart and heard
nothing, and pressing ``t`` to toggle text mode was silent too, while the
same chart spoke in Chrome. The cause was in ``maidr.js``, and it was about
*how* the text reached the page rather than *what* it said.

Up to ``maidr.js`` 3.50.0 every announcement went through one long-lived
``<div role="alert">`` whose text was rewritten in place. Chrome treats an
alert as an assertive live region, so it spoke each rewrite. Firefox does
not, outside macOS and Android:

* ``accessible/base/ARIAMap.cpp`` gives ``alert`` an implied ``aria-live``
  of ``assertive`` only ``#if defined(XP_MACOSX) || defined(ANDROID)``, and
  ``eNoLiveAttr`` everywhere else, so on Windows the element is not a live
  region at all;
* what Firefox raises instead is an alert event, and only when an alert is
  created (``DocAccessible::CreateSubtree``) or something is inserted into
  one (``DocAccessible::FireEventsOnInsertion``). A text node rewritten in
  place goes through ``TextUpdater``, which fires text-change events and
  nothing else.

So NVDA and JAWS in Firefox heard the first message and then silence. The
upstream fix renders each announcement into a new ``role="alert"`` element,
keyed on a revision counter so that even an identical repeat is a new
element: navigation text in xability/maidr#530 (3.50.1), notifications such
as the ``t`` toggle in xability/maidr#629 (3.72.0), and arrow navigation
again after 3.72.0 dropped it, in xability/maidr#633 (3.72.1).

This pins that pattern in the bundle py-maidr ships, through two of the ways
py-maidr puts the bundle on a page: a saved document, and a notebook frame
that evaluates the bundle from a string. It is deliberately stricter than
Firefox: a node added to an alert that is already there would also raise
the event, but the test holds the bundle to the one shape upstream settled
on -- a new alert per announcement -- rather than to every shape Gecko
happens to accept.

It runs in Chromium only, which is enough: what is asserted is the DOM each
browser builds its accessibility tree from, not the tree itself. It cannot
show that a screen reader speaks -- only that each announcement arrives in
the form Firefox needs in order to raise the event a screen reader speaks
from. A bundle update that goes back to rewriting an existing alert fails
here, naming the key that did it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from unittest import mock

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.util.environment import Environment

if TYPE_CHECKING:
    from matplotlib.figure import Figure
    from playwright.sync_api import Browser, Frame, Page

pytestmark = pytest.mark.browser

#: The article ``maidr.js`` wraps a chart in once it has taken the chart
#: over. Waited for rather than a global such as ``window.maidrLive`` so the
#: test also runs against the older bundles it exists to reject, which set
#: no such global.
_CHART_READY = "() => document.querySelector('article[id^=maidr-article-]') !== null"
_PARSE_TIMEOUT_MS = 30_000

#: How long a key press is given to reach the page.
_SETTLE_MS = 700

#: The role of whatever holds focus in the chart's document.
_FOCUSED_ROLE = "() => document.activeElement?.getAttribute('role') ?? null"

#: Records how each announcement reached a `role="alert"` element: `new`
#: when the alert element itself was inserted (with its text already in
#: it), `rewritten` when a text node inside an existing alert changed, and
#: `added` when a node was put into an existing alert.
_RECORD_ALERTS = """() => {
  window.__maidrAlerts = [];
  const inAlert = (node) => {
    const el = node.nodeType === 1 ? node : node.parentElement;
    return Boolean(el && el.closest('[role=alert]'));
  };
  new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'characterData') {
        if (inAlert(r.target)) {
          window.__maidrAlerts.push({kind: 'rewritten', text: r.target.data});
        }
        continue;
      }
      if (inAlert(r.target)) {
        for (const node of r.addedNodes) {
          window.__maidrAlerts.push({kind: 'added', text: node.textContent});
        }
        continue;
      }
      for (const node of r.addedNodes) {
        if (node.nodeType !== 1) continue;
        const alerts = node.matches('[role=alert]')
          ? [node] : [...node.querySelectorAll('[role=alert]')];
        for (const alert of alerts) {
          window.__maidrAlerts.push({kind: 'new', text: alert.textContent});
        }
      }
    }
  }).observe(document.body, {childList: true, subtree: true, characterData: true});
}"""

#: Bars a, b, c of heights 1, 3, 2: distinct values, so each stop's
#: announcement says which bar it is.
_BARS = (["a", "b", "c"], [1, 3, 2])


def _chart() -> Figure:
    """
    A three-bar chart.

    Returns
    -------
    matplotlib.figure.Figure
        The figure, for the caller to render and close.
    """
    fig, ax = plt.subplots()
    ax.bar(*_BARS)
    ax.set_title("Sales")
    return fig


def _saved(tmp_path: Path) -> str:
    """
    The page the browser renderer opens: ``save_html`` with its ``lib/``.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Where to write the page.

    Returns
    -------
    str
        The page's ``file://`` URL.
    """
    out = tmp_path / "chart.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(_chart(), str(out), use_cdn=False)
    finally:
        plt.close("all")
    return out.as_uri()


def _notebook(tmp_path: Path) -> str:
    """
    A page shaped like a notebook: the parent stash, then a srcdoc frame.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Where to write the page.

    Returns
    -------
    str
        The page's ``file://`` URL.
    """
    source = json.dumps(maidr.read_bundled_js()).replace("</", "<\\/")
    try:
        with mock.patch.object(Environment, "is_notebook", return_value=True):
            frame = str(maidr.render(_chart(), use_cdn=False))
    finally:
        plt.close("all")
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><body><script>window.__maidrJsSource = {source};"
        f"</script>{frame}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


def _point(i: int) -> re.Pattern:
    """
    What an announcement of bar ``i`` says, verbose or terse.

    The label then the value -- "X is b, Y is 3" or "b, 3" -- as whole
    words, so a stray digit elsewhere in the text cannot pass for it.

    Parameters
    ----------
    i : int
        The bar's index in ``_BARS``.

    Returns
    -------
    re.Pattern
        A pattern an announcement of that bar matches.
    """
    labels, heights = _BARS
    return re.compile(rf"\b{labels[i]}\b.*\b{heights[i]}\b")


def _press(page: Page, chart: Frame, key: str) -> list[dict]:
    """
    Press ``key`` and report how the announcements it made reached an alert.

    Parameters
    ----------
    page : playwright.sync_api.Page
        The page receiving the key.
    chart : playwright.sync_api.Frame
        The chart's document, where ``_RECORD_ALERTS`` is installed.
    key : str
        The key to press.

    Returns
    -------
    list of dict
        One ``{"kind": "new" | "rewritten" | "added", "text": ...}`` per
        change.
    """
    chart.evaluate("() => { window.__maidrAlerts.length = 0; }")
    page.keyboard.press(key)
    page.wait_for_timeout(_SETTLE_MS)
    return chart.evaluate("() => window.__maidrAlerts")


@pytest.mark.parametrize("build", [_saved, _notebook], ids=["save_html", "notebook"])
def test_every_announcement_arrives_in_a_new_alert(
    browser: Browser, tmp_path: Path, build: Callable[[Path], str]
) -> None:
    """Arrows, ``t`` and a same-text repeat each insert a new alert."""
    # English, so the text-mode message can be recognised by its words.
    context = browser.new_context(locale="en-US")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(build(tmp_path), wait_until="load")
        # The chart's own document: the page itself, or the notebook's frame.
        chart = page.frames[-1]
        chart.wait_for_function(_CHART_READY, timeout=_PARSE_TIMEOUT_MS)

        # Arrive the way a keyboard reader does, from the top of the page.
        page.keyboard.press("Tab")
        page.wait_for_timeout(_SETTLE_MS)
        focused = chart.evaluate(_FOCUSED_ROLE)
        assert focused == "application", f"Tab did not reach the chart: {focused}"
        chart.evaluate(_RECORD_ALERTS)

        steps = [
            ("ArrowRight", _point(0)),
            ("ArrowRight", _point(1)),
            ("ArrowRight", _point(2)),
            # Fixed by #629 separately from navigation, so pinned separately.
            ("t", re.compile(r"\bText mode\b")),
            ("ArrowLeft", _point(1)),
            # Space repeats the current point: the same text as the last
            # announcement, which an in-place rewrite would not even change.
            ("Space", _point(1)),
        ]
        for key, expected in steps:
            arrived = _press(page, chart, key)
            by_kind: dict[str, list[str]] = {"new": [], "rewritten": [], "added": []}
            for change in arrived:
                by_kind[change["kind"]].append(change["text"])
            assert not by_kind["rewritten"], (
                f"{key}: the announcement rewrote the text of an existing "
                f"role=alert ({by_kind['rewritten']}). Firefox on Windows "
                "raises no alert event for that, so NVDA and JAWS stay "
                "silent -- see this module's docstring (#235)."
            )
            assert not by_kind["added"], (
                f"{key}: the announcement was put into an existing role=alert "
                f"({by_kind['added']}) rather than a new one, which is not "
                "the pattern this pins -- see this module's docstring."
            )
            new = by_kind["new"]
            assert any(expected.search(text) for text in new), (
                f"{key}: no new role=alert element matched "
                f"{expected.pattern!r}; new alerts: {new}"
            )
        assert not errors, errors
    finally:
        context.close()
