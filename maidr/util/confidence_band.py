"""
The interval a chart shades around a line, read back off the drawing.

A band is the reason many charts are drawn the way they are: it says how much
of the trend the data supports. Announcing the line alone tells a reader the
estimate and leaves out how well determined it is -- which is the half a
sighted reader takes straight from the picture.

Two things this deliberately does not do, each because measuring showed it
wrong:

**The ring is not walked positionally.** matplotlib shades a band with a
polygon whose vertices run out along one edge and back along the other, and
individual x values appear two, three or four times, so a position in the ring
is not a fixed offset from either end. The edges are the lowest and highest
vertex at each x, which is exact and assumes nothing about orientation.

**A band is not identified by its type.** seaborn draws a violin body with
``fill_betweenx``, so a violin is the same class as a band; and
``FillBetweenPolyCollection``, the subclass matplotlib 3.10 split out, does not
exist on the older matplotlib the Python 3.9 floor resolves to. So the reading
validates itself: a region is a line's band only if it **brackets every one of
that line's samples**, which is the property a band has by construction and an
unrelated shaded region does not.

One thing it *does* assume, and has to. Reading the lowest and highest vertex
**at each x** is a reading of a vertical interval, so a region shaded the other
way about is not one this can answer for. Bracketing does not catch it: a
horizontal band around a horizontal line surrounds that line vertically too,
because it surrounds it. Measured, ``plot(val, pos)`` under
``fill_betweenx(pos, lo, hi)`` came out carrying the polygon's vertical extent
as ``yMin``/``yMax`` -- an artefact of the band being sloped, on the axis that
holds the *positions*, which the chart states no uncertainty about at all
(#601).

Which way a region was shaded is therefore asked of
:data:`maidr.patch.fillbetween.DRAWN_ALONG_Y` rather than inferred, for the
reason :data:`maidr.core.plot.outlined_histogram.OUTLINE_HORIZONTAL` gives:
the drawing cannot always say and the caller always can. Counting distinct
coordinates nearly works -- a band has one position per column and two edge
values, so the value axis generally carries twice the distinct values -- and
measurably ties on small frames whose values collide, where declining would
drop bands that read correctly today.

Lifted out of ``SmoothPlot``, which read a ``regplot``'s band this way (#451),
so a plain line can carry one too (#562).

@packageDocumentation
"""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection

#: How far a sample may sit outside a region and still count as bracketed.
#:
#: Float noise only. The band is read from the same vertices matplotlib drew,
#: so a genuine band brackets its line to within rounding; anything looser
#: would start accepting regions that merely overlap.
_TOLERANCE = 1e-9

#: Attribute :mod:`maidr.patch.fillbetween` sets on a region it drew, saying
#: which way the fill runs: ``True`` for ``fill_betweenx``, ``False`` for
#: ``fill_between``.
#:
#: Named here rather than in the patch because both sides have to agree on it
#: and only one of them can be imported from the other -- the patch imports
#: this module's reader, not the reverse.
DRAWN_ALONG_Y = "_maidr_fill_along_y"


def shaded_along_y(collection) -> bool:
    """
    Whether this region's interval runs across the page rather than up it.

    Answered from the tag :mod:`maidr.patch.fillbetween` leaves on every
    region it draws, rather than from the vertices. ``fill_betweenx`` *is*
    the horizontal spelling, so the patch knows outright what the geometry
    can only be argued about -- and the arguments lose, as this module's
    docstring records.

    An untagged region is treated as vertical, which is what every region was
    treated as before the tag existed. That keeps a shaded region some other
    library drew reading exactly as it did, and confines this to the call it
    can answer for.

    Parameters
    ----------
    collection : matplotlib.collections.PolyCollection
        A shaded region on the axes.

    Returns
    -------
    bool
        True only for a region drawn by ``fill_betweenx``.
    """
    # `bool` rather than `is True`: the patch is the only writer and it writes
    # a bool, so the two agree on every value that can reach here, and the
    # stricter spelling would be a distinction no test could tell apart.
    return bool(getattr(collection, DRAWN_ALONG_Y, False))


def band_edges_at(
    ax: Axes,
    x_data: np.ndarray,
    y_data: np.ndarray,
    taken: tuple = (),
) -> tuple:
    """
    The interval shaded around a series, at the positions it is emitted at.

    Parameters
    ----------
    ax : Axes
        The axes drawn on.
    x_data : numpy.ndarray
        The x positions the series is emitted at.
    y_data : numpy.ndarray
        The values at those positions, which a candidate region has to
        bracket to be this series' band.
    taken : tuple, optional
        Regions already claimed by another series, by reference. A chart with
        several lines has several bands, and a wide one can bracket a
        neighbour's samples as well as its own -- so a region answers for one
        series only.

    Returns
    -------
    tuple
        ``(lower, upper, collection)``, or ``(None, None, None)`` when the
        chart shades nothing around this series.
    """
    for collection in ax.collections:
        # Every shaded region is a candidate and the bracketing test decides.
        # Filtering on `FillBetweenPolyCollection` first looks tighter and is
        # not portable: matplotlib split that subclass out of `PolyCollection`
        # in 3.10, so on an older one -- which the Python 3.9 floor still
        # resolves to -- no band exists by that name and every chart silently
        # lost its interval.
        if not isinstance(collection, PolyCollection):
            continue
        # Shaded along the other axis, so its interval is not one `edges_of`
        # reads. See this module's docstring and #601.
        if shaded_along_y(collection):
            continue
        if any(collection is claimed for claimed in taken):
            continue
        bounds = edges_of(collection, x_data, y_data)
        if bounds is not None:
            return bounds[0], bounds[1], collection
    return None, None, None


def edges_of(collection, x_data: np.ndarray, y_data: np.ndarray) -> tuple | None:
    """
    One shaded region's edges, if it is this series' band.

    Interpolated rather than looked up. A curve is often thinned before it is
    emitted, and the thinning resamples to evenly spaced positions rather than
    selecting a subset -- measured on a `regplot`, only the two endpoints of a
    30-point output were among the band's own x values, so a lookup would have
    attached bounds to 2 points and left 28 silently bare. Interpolating
    between vertices is also what matplotlib does to draw the band, so it
    reads the same shape the reader sees.

    Parameters
    ----------
    collection : matplotlib.collections.PolyCollection
        A shaded region on the axes.
    x_data : numpy.ndarray
        The x positions the series is emitted at.
    y_data : numpy.ndarray
        The values at those positions.

    Returns
    -------
    tuple or None
        Lower and upper bounds at each x, or ``None`` when this region is not
        this series' band.
    """
    by_x: dict = {}
    for path in collection.get_paths():
        for x, y in path.vertices:
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            key = float(x)
            low, high = by_x.get(key, (float(y), float(y)))
            by_x[key] = (min(low, float(y)), max(high, float(y)))

    if len(by_x) < 2:
        return None

    band_x = np.array(sorted(by_x))
    lower = np.interp(x_data, band_x, np.array([by_x[x][0] for x in band_x]))
    upper = np.interp(x_data, band_x, np.array([by_x[x][1] for x in band_x]))

    # `np.interp` clamps outside the region's own x range, so a region that
    # does not span the series would still return numbers -- the bracketing
    # test is what rejects it, not the interpolation.
    if not np.all(
        (lower <= y_data + _TOLERANCE) & (y_data - _TOLERANCE <= upper)
    ):
        return None

    # Bracketing alone is not enough, measured: an **area** brackets the line
    # drawn on top of it. `ax.fill_between(x, y)` shades from the baseline up
    # to the series, so a line at `y` sits exactly on the region's upper edge
    # and every clause above holds -- and the chart would announce "2.0,
    # between 0 and 2.0", an interval it does not state and whose width is the
    # value over again.
    #
    # A band lies *around* a series; an area merely touches it. So a region
    # whose edge coincides with the series throughout is not this series'
    # interval. Isolated contact is fine, and has to be: a real band can meet
    # its line at an endpoint.
    on_upper = np.all(np.abs(upper - y_data) <= _TOLERANCE)
    on_lower = np.all(np.abs(lower - y_data) <= _TOLERANCE)
    if on_upper or on_lower:
        return None
    return lower, upper
