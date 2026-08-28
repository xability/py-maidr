from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.wordcloudplot import cloud_shown


@wrapt.patch_function_wrapper(Axes, "imshow")
def wordcloud(wrapped, instance, args, kwargs):
    """
    Register a ``wordcloud.WordCloud`` shown with ``imshow`` as a word cloud.

    ``WordCloud`` renders to a bitmap and the conventional way to display one
    is ``ax.imshow(wc)``, so a cloud arrives at MAIDR through the same entry
    point a heatmap does. It is not one: the array is ``(M, N, 3)`` colour,
    and ``maidr.patch.heatmap`` declines exactly that shape (#564) because
    there is no number per cell to announce. Measured before this patch, a
    figure holding only a cloud registered no layer at all and
    ``FigureManager.get_maidr`` raised ``UnsupportedPlotError``.

    So the cloud is not being *misread* today, it is unread — and the fix is
    additive. This wrapper looks at what is being shown rather than at what
    it rasterises to, and hands the object itself to the layer, which reads
    the terms off ``words_``.

    Two wrappers now sit on ``Axes.imshow``, this one and the heatmap's. That
    is deliberate rather than a merge into ``heat``: the two answer different
    questions about the same call, and only one of them can be true. The
    heatmap wrapper declines a colour image whether or not it is a cloud, so
    the pair cannot both register a layer for one call.

    ``wc.to_array()`` and ``wc.to_image()`` are not recognised, and cannot
    be: both hand ``imshow`` a plain array, and the terms are not in it. A
    cloud displayed that way stays a picture, which is the honest answer.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.imshow``.
    instance : Axes
        The axes the call was made on.
    args : tuple
        Its positional arguments.
    kwargs : dict
        Its keyword arguments.

    Returns
    -------
    AxesImage
        Whatever ``Axes.imshow`` returned, untouched.
    """
    cloud = cloud_shown(args, kwargs)

    # Not a cloud, or a nested draw: leave it to the heatmap wrapper and to
    # whatever outer call is already recording.
    if cloud is None or ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    with ContextManager.set_internal_context():
        plot = wrapped(*args, **kwargs)

    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.WORD_CLOUD, cloud=cloud)

    return plot
