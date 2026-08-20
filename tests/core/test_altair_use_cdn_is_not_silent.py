"""``use_cdn=False`` on an Altair chart says it cannot be honoured.

The Altair path renders through the upstream Vega-Lite adapter, which is
published only on a CDN, so there is nothing to inline and the flag cannot
be obeyed. It was accepted and discarded in silence, which fails the one
reader it matters to: ``use_cdn=False`` means they cannot reach a CDN, so
they got a chart that never initialises and no reason why (#521).

Whether the flag should one day be honoured is a packaging question about
maidr's own ``vegalite.js``. Saying so is not, and is what these pin.
"""

from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402

alt = pytest.importorskip("altair")

_COMPLAINT = "cannot be honoured"


@pytest.fixture(autouse=True)
def _restore_default():
    before = maidr.get_use_cdn()
    yield
    maidr.set_use_cdn(before)
    plt.close("all")


def _chart():
    frame = pd.DataFrame({"cat": list("abc"), "val": [1, 2, 3]})
    return alt.Chart(frame).mark_bar().encode(x="cat", y="val")


def _complaints(call) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    return [str(w.message) for w in caught if _COMPLAINT in str(w.message)]


def test_an_offline_altair_render_is_told_it_cannot_be_offline():
    said = _complaints(lambda: maidr.render(_chart(), use_cdn=False))

    assert len(said) == 1
    # Naming the pieces matters more than the wording: without them the
    # reader cannot tell what would have to travel with the page.
    assert "vega" in said[0] and "vegalite.js" in said[0]


def test_save_html_says_it_too(tmp_path):
    """The entry point an offline reader is most likely to use."""
    target = tmp_path / "chart.html"

    said = _complaints(
        lambda: maidr.save_html(_chart(), file=str(target), use_cdn=False)
    )

    assert len(said) == 1


def test_show_says_it_too(monkeypatch):
    """The third entry point, which nothing else here reaches.

    `show` warns before it hands off to a renderer, so the renderer is
    stubbed rather than exercised -- opening a browser is not what this
    is about, and letting it try would make the test depend on a display.
    """
    monkeypatch.setattr(
        "maidr.altair.altair_maidr.AltairMaidr.show", lambda self, renderer: None
    )

    said = _complaints(lambda: maidr.show(_chart(), use_cdn=False))

    assert len(said) == 1


@pytest.mark.parametrize("mode", [True, "auto", None], ids=["cdn", "auto", "default"])
def test_every_other_mode_stays_quiet(mode):
    """Only an explicit offline request is worth interrupting for.

    ``"auto"`` has no fallback on this path either, but a reader on it has
    not said they are offline, and warning on the common case is noise.
    """
    assert not _complaints(lambda: maidr.render(_chart(), use_cdn=mode))


def test_a_process_wide_default_of_false_also_warns():
    """`use_cdn=None` defers to the default, so the check must resolve it.

    Reading the caller's argument alone would let `set_use_cdn(False)`
    through -- the same silent discard, reached by the other door.
    """
    maidr.set_use_cdn(False)

    assert _complaints(lambda: maidr.render(_chart()))


def test_a_matplotlib_chart_is_not_warned_about():
    """It honours the flag by inlining the bundle, so it has nothing to say."""
    fig, ax = plt.subplots()
    ax.bar(["p", "q"], [1, 2])

    assert not _complaints(lambda: maidr.render(fig, use_cdn=False))
