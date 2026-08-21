"""`extract_collection` raised `StopIteration` where its caller handles `None`.

`CollectionExtractorMixin.extract_collection` found its collection through a
bare `next()` with no default::

    return next(
        collection for collection in ax.collections
        if isinstance(collection, collection_type)
    )

so an axes holding none of that type raised rather than answering. Its only
caller is written for the other answer: `ScatterPlot._extract_plot_data` opens
with `if data is None: raise ExtractionError(...)` and `_extract_point_data`
opens with `if plot is None`. That handling could never run, and what a reader
got instead was a bare `StopIteration` -- fatal to the whole figure, naming
neither the plot type nor the artist, and nothing anyone can act on (#529).

The third of three, all in the same file:

    ContainerExtractorMixin.extract_container        #388
    ScalarMappableExtractorMixin.extract_scalar_mappable   #522 / #525
    CollectionExtractorMixin.extract_collection      this

Each of the first two was found only when some chart happened to route into
it, which is the argument for the last one not waiting for its chart. There is
no supported chart that reaches this today; the test therefore asks the lookup
and the caller directly rather than inventing one.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.collections import PathCollection, QuadMesh  # noqa: E402

from maidr.core.plot.scatterplot import ScatterPlot  # noqa: E402
from maidr.exception.extraction_error import ExtractionError  # noqa: E402
from maidr.util.mixin.extractor_mixin import CollectionExtractorMixin  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def test_an_axes_with_no_collection_of_that_type_answers_rather_than_raising():
    """A line is not a `PathCollection`, and saying so is the answer."""
    fig, ax = plt.subplots()
    ax.plot([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])

    assert CollectionExtractorMixin.extract_collection(ax, PathCollection) is None


def test_a_collection_of_another_type_is_not_offered_in_its_place():
    """
    The axes holds a collection, just not the one asked for.

    Separate from the empty case: a lookup that answered with whatever it
    found would pass that one and still hand a caller the wrong artist.
    """
    fig, ax = plt.subplots()
    ax.pcolormesh([[1.0, 2.0], [3.0, 4.0]])

    assert CollectionExtractorMixin.extract_collection(ax, QuadMesh) is not None
    assert CollectionExtractorMixin.extract_collection(ax, PathCollection) is None


def test_the_caller_raises_the_error_it_is_written_to_raise():
    """
    `ScatterPlot` names the plot type it could not read.

    This is the handling the bare `next()` made unreachable. Before the fix
    the same call raised `StopIteration` with an empty message.
    """
    fig, ax = plt.subplots()
    ax.plot([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])

    with pytest.raises(ExtractionError) as raised:
        ScatterPlot(ax).render()

    assert "point" in str(raised.value)


def test_a_scatter_is_still_found_where_there_is_one():
    """The default is for the empty case, and changes nothing where it is not."""
    fig, ax = plt.subplots()
    ax.scatter([1.0, 2.0], [3.0, 4.0])

    found = CollectionExtractorMixin.extract_collection(ax, PathCollection)

    assert isinstance(found, PathCollection)
    assert len(found.get_offsets()) == 2
