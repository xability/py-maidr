"""A ``maidr`` tab in TensorBoard: every chart of the log directory, accessible.

Installed with ``pip install "maidr[tensorboard]"``, TensorBoard finds this
plugin through its ``tensorboard_plugins`` entry point and shows a **maidr**
tab beside its own dashboards. The tab lists the charts py-maidr reads from
the log directory TensorBoard was started with -- scalars, distributions,
histograms, a hyperparameter sweep and the Embedding Projector's embeddings
-- and shows the one picked, read by maidr: from the keyboard, as sound, as
text and in braille.

TensorBoard imports this module, not ``import maidr``; it is the one module
of py-maidr that imports TensorBoard.
"""

from __future__ import annotations

import html
import json
import os
import threading
import warnings
from typing import Any, Callable

from tensorboard.plugins import base_plugin
from werkzeug import wrappers

#: The charts a log directory can offer, in the order the tab lists them.
_KINDS = (
    "scalars",
    "distributions",
    "histograms",
    "pr_curves",
    "hparams",
    "projector",
    "profile",
)

#: What names a chart of each kind, beyond its kind.
_REQUIRED = {
    "scalars": ("tag",),
    "distributions": ("tag", "run"),
    "histograms": ("tag", "run"),
    "pr_curves": ("tag",),
    "projector": ("tag",),
}

#: One chart is drawn at a time; see :func:`chart_page`.
_LOCK = threading.Lock()

#: The tab's page: a labelled picker, a reload button and the chart's frame.
_INDEX_JS = """
export async function render() {
  document.body.innerHTML = `
    <style>
      body { font-family: Roboto, sans-serif; margin: 16px; color: #212121; }
      label { margin-right: 8px; font-weight: 500; }
      select, button { font-size: 14px; padding: 4px 8px; margin-right: 8px; }
      iframe { width: 100%; height: 80vh; border: 1px solid #e0e0e0; margin-top: 12px; }
    </style>
    <h1 style="font-size: 20px">Accessible charts</h1>
    <p id="status" role="status"></p>
    <label for="chart">Chart</label>
    <select id="chart"></select>
    <button id="reload" type="button">Reload</button>
    <iframe id="frame" title="Chart"></iframe>`;
  const select = document.getElementById("chart");
  const frame = document.getElementById("frame");
  const status = document.getElementById("status");
  const show = () => {
    const option = select.selectedOptions[0];
    if (!option) return;
    frame.title = option.textContent;
    frame.src = "./chart?" + option.value;
  };
  const load = async () => {
    const kept = select.value;
    let charts;
    try {
      const response = await fetch("./charts");
      charts = await response.json();
      if (!response.ok) throw new Error(charts.error || response.statusText);
    } catch (error) {
      status.textContent = `Could not read the log directory: ${error.message}`;
      return;
    }
    select.replaceChildren(...charts.map(chart => {
      const option = document.createElement("option");
      option.value = new URLSearchParams(chart.query).toString();
      option.textContent = chart.title;
      return option;
    }));
    if ([...select.options].some(option => option.value === kept)) select.value = kept;
    status.textContent = charts.length
      ? `${charts.length} charts. Pick one; Reload reads the log directory again.`
      : "This log directory holds no chart maidr reads yet.";
    show();
  };
  select.addEventListener("change", show);
  document.getElementById("reload").addEventListener("click", load);
  await load();
}
"""


class MaidrPlugin(base_plugin.TBPlugin):
    """
    TensorBoard's **maidr** tab.

    Parameters
    ----------
    context : tensorboard.plugins.base_plugin.TBContext
        What TensorBoard hands its plugins; only ``logdir`` is read.
    """

    plugin_name = "maidr"

    def __init__(self, context: Any) -> None:
        self._logdir = getattr(context, "logdir", None) or ""

    def is_active(self) -> bool:
        """Whether there is a log directory to read charts from."""
        return bool(self._logdir) and os.path.isdir(self._logdir)

    def frontend_metadata(self) -> Any:
        """The tab: its name, and the ES module that draws it."""
        return base_plugin.FrontendMetadata(
            es_module_path="/index.js", tab_name="maidr", disable_reload=True
        )

    def get_plugin_apps(self) -> dict[str, Callable]:
        """The tab's routes."""
        return {
            "/index.js": self._index_js,
            "/charts": self._charts,
            "/chart": self._chart,
        }

    @wrappers.Request.application
    def _index_js(self, request: Any) -> Any:
        return wrappers.Response(_INDEX_JS, content_type="application/javascript")

    @wrappers.Request.application
    def _charts(self, request: Any) -> Any:
        try:
            charts = list_charts(self._logdir)
        except Exception as error:  # noqa: BLE001 - the tab says why, not a bare 500
            return wrappers.Response(
                json.dumps({"error": f"{type(error).__name__}: {error}"}),
                status=500,
                content_type="application/json",
            )
        return wrappers.Response(json.dumps(charts), content_type="application/json")

    @wrappers.Request.application
    def _chart(self, request: Any) -> Any:
        query = {key: request.args.get(key) for key in ("kind", "tag", "run", "index")}
        try:
            html = chart_page(self._logdir, **query)
        except (KeyError, ValueError) as error:
            return wrappers.Response(str(error), status=404, content_type="text/plain")
        return wrappers.Response(html, content_type="text/html; charset=utf-8")


def list_charts(logdir: str) -> list[dict]:
    """
    The charts a log directory offers, each a title and the query that shows it.

    Parameters
    ----------
    logdir : str
        The log directory.

    Returns
    -------
    list of dict
        ``{"title": ..., "query": {"kind": ..., ...}}`` per chart.
    """
    from maidr.tensorboard import (
        load_hparams,
        load_histograms,
        load_pr_curves,
        load_scalars,
    )
    from maidr.tensorboard.projector import _CONFIG, load_embeddings

    charts: list[dict] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for tag in load_scalars(logdir):
            charts.append(
                {"title": f"Scalars: {tag}", "query": {"kind": "scalars", "tag": tag}}
            )
        histograms = load_histograms(logdir)
        for kind in ("distributions", "histograms"):
            for tag, by_run in histograms.items():
                for run in by_run:
                    charts.append(
                        {
                            "title": f"{kind.capitalize()}: {tag} ({run})",
                            "query": {"kind": kind, "tag": tag, "run": run},
                        }
                    )
        for tag in load_pr_curves(logdir):
            charts.append(
                {
                    "title": f"PR curves: {tag}",
                    "query": {"kind": "pr_curves", "tag": tag},
                }
            )
        if load_hparams(logdir):
            for index, name in enumerate(("parallel coordinates", "scatter matrix")):
                charts.append(
                    {
                        "title": f"HParams: {name}",
                        "query": {"kind": "hparams", "index": str(index)},
                    }
                )
        if _can_convert_profiles():
            from maidr.tensorboard.profile import find_profiles

            for session in find_profiles(logdir):
                for index, name in enumerate(("step time", "top operations")):
                    charts.append(
                        {
                            "title": f"Profile {session}: {name}",
                            "query": {
                                "kind": "profile",
                                "tag": session,
                                "index": str(index),
                            },
                        }
                    )
        if os.path.isfile(os.path.join(logdir, _CONFIG)):
            for embedding in load_embeddings(logdir):
                charts.append(
                    {
                        "title": f"Projector: {embedding.name}",
                        "query": {"kind": "projector", "tag": embedding.name},
                    }
                )
    return charts


def chart_page(
    logdir: str,
    kind: str | None,
    tag: str | None = None,
    run: str | None = None,
    index: str | None = None,
) -> str:
    """
    One chart of a log directory as a complete, self-contained HTML page.

    Parameters
    ----------
    logdir : str
        The log directory.
    kind : str
        One of ``scalars``, ``distributions``, ``histograms``, ``hparams``
        or ``projector``.
    tag, run, index : str, optional
        Which chart of that kind: its tag, its run, or for ``hparams`` its
        position (``0`` parallel coordinates, ``1`` scatter matrix).

    Returns
    -------
    str
        The page, with maidr.js inlined so it works without a network.

    Raises
    ------
    KeyError
        If there is no such chart.
    ValueError
        If ``kind`` is not one of the above.
    """
    import maidr
    from maidr.widget.streamlit import maidr_html

    if kind not in _KINDS:
        raise ValueError(f"no chart kind {kind!r}; the kinds are {', '.join(_KINDS)}")
    given = {"tag": tag, "run": run}
    for name in _REQUIRED.get(kind, ()):
        if not given[name]:
            raise KeyError(f"a {kind} chart is named by its {name}")
    # pyplot and the figure manager are shared by every request a threaded
    # server handles at once, so one chart is drawn and closed at a time.
    with _LOCK:
        return _chart_page(logdir, kind, tag, run, index, maidr, maidr_html)


def _chart_page(
    logdir: str,
    kind: str,
    tag: str | None,
    run: str | None,
    index: str | None,
    maidr: Any,
    maidr_html: Callable,
) -> str:
    """Draw, render and close the chart :func:`chart_page` names."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if kind == "scalars":
            charts = maidr.read_tensorboard_scalars(logdir, tags=[tag])
        elif kind == "distributions":
            charts = maidr.read_tensorboard_distributions(
                logdir, tags=[tag], runs=[run]
            )
        elif kind == "histograms":
            charts = maidr.read_tensorboard_histograms(logdir, tags=[tag], runs=[run])
        elif kind == "pr_curves":
            charts = maidr.read_tensorboard_pr_curves(logdir, tags=[tag])
        elif kind == "hparams":
            charts = maidr.read_tensorboard_hparams(logdir)
        elif kind == "profile":
            # The chart is named, not counted: a profile with no steps has no
            # step-time graph, and position 0 would then be another chart.
            from maidr.tensorboard.profile import CHARTS

            charts = maidr.read_tensorboard_profile(
                logdir, session=tag, charts=[CHARTS[int(index or 0)]]
            )
        else:
            charts = [
                chart
                for chart in maidr.read_tensorboard_projector(logdir)
                if chart.tag == tag
            ]
    # Every chart drawn is closed, the one shown or not, so a long-running
    # TensorBoard does not keep a figure per request.
    position = int(index or 0) if kind == "hparams" else 0
    if not 0 <= position < len(charts):
        for every in charts:
            maidr.close(every)
        raise KeyError(f"no {kind} chart {tag or index!r} in this log directory")
    chart = charts[position]
    try:
        body = maidr_html(chart.figure, use_cdn=False)
    finally:
        for every in charts:
            maidr.close(every)
    title = chart.tag if kind != "hparams" else "Hyperparameters"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title></head><body>{body}</body></html>"
    )


def _can_convert_profiles() -> bool:
    """Whether the profile plugin's converter is installed."""
    import importlib.util

    if importlib.util.find_spec("xprof") is not None:
        return True
    try:
        return (
            importlib.util.find_spec("tensorboard_plugin_profile.convert") is not None
        )
    except ModuleNotFoundError:
        return False
