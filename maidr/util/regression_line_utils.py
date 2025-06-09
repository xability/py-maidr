from matplotlib.lines import Line2D
import numpy as np


def find_regression_line(axes):
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
