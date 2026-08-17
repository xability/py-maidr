from matplotlib.lines import Line2D
from matplotlib.axes import Axes
import numpy as np
from typing import Union


def find_regression_line(axes: Axes) -> Union[Line2D, None]:
    """
    Helper to find the regression line (Line2D) in the given axes.
    """
    return next(
        (
            artist
            for artist in axes.get_children()
            if isinstance(artist, Line2D)
            and artist.get_label() not in (None, "", "_nolegend_")
            and artist.get_xydata() is not None
            and np.asarray(artist.get_xydata()).size > 0
        ),
        None,
    )
