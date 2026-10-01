"""Per-element and per-point work in the render pipeline that changed nothing.

Three costs every large matplotlib render paid, none of which the output
depended on:

* ``XMLWriter.start`` went through a ``wrapt`` wrapper for every element of
  every SVG written in the process -- a 50,000-point scatter is 50,000
  ``<use>`` elements -- binding a proxy and re-packing the arguments each
  time, inside a render or not;
* ``json.dumps`` checked the schema for reference cycles, an insert and a
  delete in a dict of ids for every point, though the schema is never cyclic;
* an event plot keyed every event by ``MaidrKey`` members, which makes each
  point a dict the garbage collector has to track.

Each change is pinned against what it replaced -- the wrapper's rule, kept
here as the reference, and ``json.dumps`` with its defaults -- and against
coming back.
"""

from __future__ import annotations

import io
import itertools
import json
import uuid
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import wrapt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.backends.backend_svg import XMLWriter  # noqa: E402

import maidr  # noqa: E402
from maidr.core.context_manager import HighlightContextManager  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch import highlight  # noqa: E402

#: A chart builder, drawing into the axes it is handed.
Draw = Callable[[Axes], None]


@pytest.fixture(autouse=True)
def _close_figures() -> Any:
    yield
    plt.close("all")


def _render(draw: Draw, monkeypatch: pytest.MonkeyPatch) -> str:
    """
    One chart's whole rendered page, made reproducible.

    Parameters
    ----------
    draw : callable
        Draws the chart.
    monkeypatch : pytest.MonkeyPatch
        Installs the counting ``uuid4`` and pins the SVG's date.

    Returns
    -------
    str
        ``str(maidr.render(ax))``.
    """
    counter = itertools.count()
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    _, ax = plt.subplots()
    draw(ax)
    page = str(maidr.render(ax))
    plt.close("all")
    return page


def _as_the_wrapper_did(self: XMLWriter, *args: Any, **kwargs: Any) -> int:
    """The rule the ``wrapt`` wrapper on ``XMLWriter.start`` applied."""
    if HighlightContextManager.is_maidr_element(kwargs.get("id")):
        kwargs["maidr"] = HighlightContextManager.get_selector_id(kwargs.get("id"))
    return highlight._xml_start(self, *args, **kwargs)


def _walk(n: int, seed: int = 0) -> np.ndarray:
    """A reproducible random walk of ``n`` floats."""
    return np.random.default_rng(seed).normal(size=n).cumsum()


def _user_gid(ax: Axes) -> None:
    """Bars, one carrying a gid the author set."""
    bars = ax.bar(["a", "b", "c"], [3, 1, 2])
    bars[1].set_gid("mine")


CHARTS: dict[str, Draw] = {
    "scatter": lambda ax: ax.scatter(_walk(500), _walk(500, 1)),
    "bar": lambda ax: ax.bar(["a", "b", "c", "d"], [3, 1, 2, 5]),
    "line": lambda ax: ax.plot(np.arange(200.0), _walk(200)),
    "heatmap": lambda ax: ax.imshow(np.arange(12.0).reshape(3, 4)),
    "box": lambda ax: ax.boxplot([_walk(50), _walk(50, 2)]),
    "pie": lambda ax: ax.pie([3, 2, 1], labels=["a", "b", "c"]),
    "user-gid": _user_gid,
}


@pytest.mark.parametrize("name", list(CHARTS))
def test_a_page_is_written_as_the_wrapper_wrote_it(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _render(CHARTS[name], monkeypatch)

    monkeypatch.setattr(XMLWriter, "start", _as_the_wrapper_did)
    reference = _render(CHARTS[name], monkeypatch)

    assert page == reference
    assert 'maidr="' in page


def test_a_plain_savefig_writes_no_maidr_attribute() -> None:
    """Outside a render the override passes every element straight through."""
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    buffer = io.StringIO()

    fig.savefig(buffer, format="svg")

    assert "maidr=" not in buffer.getvalue()


def test_the_svg_writer_is_not_called_through_a_proxy() -> None:
    """A ``wrapt`` proxy cost 0.7-0.85 us on every element of every SVG."""
    start = XMLWriter.__dict__["start"]

    assert not isinstance(start, wrapt.ObjectProxy)
    assert start.__wrapped__ is highlight._xml_start


@pytest.mark.parametrize("data_in_svg", [True, False])
def test_the_schema_is_written_as_json_dumps_writes_it(
    data_in_svg: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skipping the cycle check changes no byte of what is written."""
    dumps = json.dumps
    written: list[tuple[Any, str]] = []

    def recording(obj: Any, **kwargs: Any) -> str:
        text = dumps(obj, **kwargs)
        written.append((obj, text))
        return text

    monkeypatch.setattr(json, "dumps", recording)
    _, ax = plt.subplots()
    ax.plot(np.arange(50.0), _walk(50))
    ax.scatter(np.arange(50.0), _walk(50, 1))

    FigureManager.get_maidr(ax.get_figure())._create_html_tag(
        use_iframe=False, data_in_svg=data_in_svg
    )

    schemas = [(obj, text) for obj, text in written if "subplots" in obj]
    assert schemas
    assert all(text == dumps(obj) for obj, text in schemas)


def test_an_event_plot_keys_its_points_by_plain_strings() -> None:
    """A dict keyed by a ``MaidrKey`` member is one the garbage collector tracks."""
    _, ax = plt.subplots()
    ax.eventplot([np.arange(20.0), np.arange(10.0) * 2])
    maidr_ = FigureManager.get_maidr(ax.get_figure())

    points = [point for plot in maidr_.plots for point in plot.render()["data"]]

    assert len(points) == 30
    assert all(type(key) is str for point in points for key in point)
