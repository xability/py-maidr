"""The warning the docs quote is the warning the code raises.

`docs/index.qmd` quotes the mid-render race warning verbatim, so a reader
can recognise it when it appears. That makes the message part of the
public-facing contract, and a quote is exactly the kind of thing that
goes stale silently: the code changes, the docs keep describing the old
text, and nobody finds out until someone searches the docs for a warning
they are looking at and gets nothing (review of #549).

Two of today's fixes were this same class -- a docs link to a closed
issue (#537) and a test pointing at a symbol that had moved (#541) -- so
the drift is worth a test rather than a note.
"""

from __future__ import annotations

import pathlib
import re
import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.util.render_census import (  # noqa: E402
    artist_census,
    warn_if_figure_changed,
)

_DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs" / "index.qmd"

#: The figure's name varies by figure, so both sides are compared with it
#: removed rather than with a fixture that pins one.
_NAMED_FIGURE = re.compile(r"figure (?:\d+|at 0x[0-9a-f]+)")


def _raised_message() -> str:
    """The message the code actually produces, for a figure it can name."""
    figure, axes = plt.subplots()
    axes.bar(["a"], [1])
    before = artist_census(figure)
    axes.set_title("changed")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warn_if_figure_changed(before, figure)
        return str(caught[0].message)
    finally:
        plt.close(figure)


def _quoted_message() -> str:
    """The message the docs tell a reader to expect."""
    quoted = [
        line.lstrip("> ").strip()
        for line in _DOCS.read_text(encoding="utf-8").splitlines()
        if line.startswith("> maidr:")
    ]
    assert len(quoted) == 1, f"expected one quoted maidr warning, found {len(quoted)}"
    return quoted[0]


def test_the_docs_quote_the_warning_the_code_raises():
    """Compared with the figure's name removed from both sides.

    The name is the one part that legitimately differs between a quote and
    any given occurrence -- `figure 2` in the docs, whatever number or
    address the reader's own figure has. Everything else must match, since
    the point of quoting it is that a reader can recognise it.
    """
    raised = _NAMED_FIGURE.sub("figure", _raised_message())
    quoted = _NAMED_FIGURE.sub("figure", _quoted_message())

    assert raised == quoted, (
        "docs/index.qmd quotes a warning maidr no longer raises:\n"
        f"  docs: {quoted}\n"
        f"  code: {raised}"
    )
