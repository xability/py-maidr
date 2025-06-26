from matplotlib.lines import Line2D
import numpy as np
from maidr.core.enum.smooth_keywords import SMOOTH_KEYWORDS


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


def find_smooth_lines_by_label(axes):
    """
    Helper to find all smooth/regression lines (Line2D) in the given axes by checking their labels.

    Parameters
    ----------
    axes : matplotlib.axes.Axes
        The matplotlib axes object to search for smooth lines.

    Returns
    -------
    list
        List of Line2D objects that have labels matching smooth keywords.
    """
    smooth_lines = []
    for line in axes.get_lines():
        if isinstance(line, Line2D):
            label = line.get_label() or ""
            label_str = str(label)
            if any(key in label_str.lower() for key in SMOOTH_KEYWORDS):
                smooth_lines.append(line)
            elif label_str.startswith("_child"):
                smooth_lines.append(line)
    return smooth_lines
