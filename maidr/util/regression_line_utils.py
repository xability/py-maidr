from matplotlib.lines import Line2D
from matplotlib.axes import Axes
import numpy as np
from typing import List, Union
from maidr.core.enum.smooth_keywords import SMOOTH_KEYWORDS


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


def find_smooth_lines_by_label(axes: Axes) -> List[Line2D]:
    """
    Helper to find all smooth/regression lines (Line2D) in the given axes by checking their labels.

    This function detects smooth lines by examining their labels for smooth-related keywords
    or generic '_child' labels that are commonly created by seaborn's regplot function.

    Parameters
    ----------
    axes : matplotlib.axes.Axes
        The matplotlib axes object to search for smooth lines.

    Returns
    -------
    List[Line2D]
        List of Line2D objects that have labels matching smooth keywords or generic '_child' labels.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> import seaborn as sns
    >>>
    >>> fig, ax = plt.subplots()
    >>> # Create a regplot with smooth line
    >>> sns.regplot(x=[1, 2, 3], y=[1, 2, 3], ax=ax, lowess=True)
    >>>
    >>> # Find smooth lines
    >>> smooth_lines = find_smooth_lines_by_label(ax)
    >>> print(f"Found {len(smooth_lines)} smooth lines")
    """
    smooth_lines = []
    for line in axes.get_lines():
        if isinstance(line, Line2D):
            label = line.get_label() or ""
            label_str = str(label)

            # Check if label matches smooth keywords
            if any(key in label_str.lower() for key in SMOOTH_KEYWORDS):
                smooth_lines.append(line)
            # Also check for seaborn regplot lines with generic labels (like '_child0', '_child1')
            elif label_str.startswith("_child"):
                # Lines with _child labels are likely smooth lines from seaborn regplot
                smooth_lines.append(line)

    return smooth_lines
