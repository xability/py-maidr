from __future__ import annotations

import wrapt
import uuid
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from maidr.core.context_manager import BoxplotContextManager, ContextManager
from maidr.core.enum import PlotType, MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.core.plot import MaidrPlot
from maidr.patch.common import common


class ViolinBoxPlot(MaidrPlot):
    """
    Custom plot class for violin box plots that directly provides box plot data.
    """
    
    def __init__(self, ax, box_data, orientation="vert", elements_info=None, box_elements_list=None):
        super().__init__(ax, PlotType.BOX)
        self.box_data = box_data
        self.orientation = orientation
        self._support_highlighting = True
        # Initialize elements_map similar to BoxPlot
        self.elements_map = {
            "min": [],
            "max": [],
            "median": [],
            "boxes": [],
            "outliers": [],
        }
        self.lower_outliers_count = []
        
        # Store element references for proper tracking (similar to BoxPlot)
        # These elements must be in self._elements for the highlighting system to work
        # The highlighting system collects elements from plot.elements and registers them
        # when they're drawn, so they get the 'maidr' attribute in the SVG
        if box_elements_list:
            self._elements.extend(box_elements_list)
        
        # Store element info if provided
        if elements_info:
            self._store_elements_info(elements_info)
        
    def _store_elements_info(self, elements_info):
        """Store element IDs from elements_info into elements_map."""
        # elements_info is a list of dicts, one per violin/box
        # Each dict has: min_gid, max_gid, median_gid, box_gid (optional)
        for elem_info in elements_info:
            if "min_gid" in elem_info:
                self.elements_map["min"].append(elem_info["min_gid"])
            if "max_gid" in elem_info:
                self.elements_map["max"].append(elem_info["max_gid"])
            if "median_gid" in elem_info:
                self.elements_map["median"].append(elem_info["median_gid"])
            if "box_gid" in elem_info:
                self.elements_map["boxes"].append(elem_info["box_gid"])
            else:
                # If no box_gid, use median_gid as fallback (for IQR selector)
                if "median_gid" in elem_info:
                    self.elements_map["boxes"].append(elem_info["median_gid"])
            # Outliers are empty for violin plots
            self.elements_map["outliers"].append("")
            self.lower_outliers_count.append(0)
        
    def _get_selector(self) -> list[dict]:
        """Return selectors for boxplot elements, similar to BoxPlot._get_selector()."""
        mins, maxs, medians, boxes, outliers = self.elements_map.values()
        selector = []
        
        for (
            min_gid,
            max_gid,
            median_gid,
            box_gid,
            outlier_gid,
            lower_outliers_count,
        ) in zip(
            mins,
            maxs,
            medians,
            boxes,
            outliers,
            self.lower_outliers_count,
        ):
            selector_dict = {}
            
            # For violin plots, elements are Line2D which become paths in SVG
            # The GID is set on the Line2D element using set_gid()
            # Use the EXACT same selector format as regular boxplots: g[id='...'] > path
            # This matches how matplotlib structures boxplot elements in SVG
            # If Line2D elements aren't wrapped in groups, we may need to wrap them manually
            # or use a different element type that gets wrapped automatically
            if min_gid:
                selector_dict[MaidrKey.MIN.value] = f"g[id='{min_gid}'] > path"
            if max_gid:
                selector_dict[MaidrKey.MAX.value] = f"g[id='{max_gid}'] > path"
            if median_gid:
                selector_dict[MaidrKey.Q2.value] = f"g[id='{median_gid}'] > path"
            if box_gid:
                selector_dict[MaidrKey.IQ.value] = f"g[id='{box_gid}'] > path"
            # Outliers are empty for violin plots
            selector_dict[MaidrKey.LOWER_OUTLIER.value] = []
            selector_dict[MaidrKey.UPPER_OUTLIER.value] = []
            
            selector.append(selector_dict)
        
        return selector if self.orientation == "vert" else list(reversed(selector))
        
    def _extract_plot_data(self):
        """Return the box plot data directly."""
        return self.box_data
        
    def render(self):
        """Generate the MAIDR schema for this violin box plot."""
        maidr_schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self.ax.get_title(),
            MaidrKey.AXES: self._extract_axes_data(),
            MaidrKey.DATA: self._extract_plot_data(),
            MaidrKey.ORIENTATION: self.orientation,
        }
        # Add selectors if we have element IDs
        if self.elements_map["min"] or self.elements_map["max"] or self.elements_map["median"]:
            maidr_schema[MaidrKey.SELECTOR] = self._get_selector()
        return maidr_schema


def calculate_box_stats_from_violin_data(data, orientation="vert"):
    """
    Calculate box plot statistics (Q1, Q2, Q3, IQR, min, max) from violin plot data.
    
    Parameters:
    -----------
    data : array-like
        The data used to create the violin plot
    orientation : str
        "vert" for vertical violin plots, "horz" for horizontal
        
    Returns:
    --------
    dict : Box plot statistics with keys: q1, q2, q3, iqr, min, max
    """
    if data is None or len(data) == 0:
        return None
        
    # Convert to numpy array and remove NaN values
    data_array = np.asarray(data)
    data_clean = data_array[~np.isnan(data_array)]
    
    if len(data_clean) == 0:
        return None
    
    # Calculate quartiles
    q1 = np.percentile(data_clean, 25)
    q2 = np.percentile(data_clean, 50)  # median
    q3 = np.percentile(data_clean, 75)
    
    # Calculate IQR
    iqr = q3 - q1
    
    # Calculate whiskers (1.5 * IQR rule)
    lower_whisker = q1 - 1.5 * iqr
    upper_whisker = q3 + 1.5 * iqr
    
    # Find actual min/max within whisker range
    data_within_whiskers = data_clean[(data_clean >= lower_whisker) & (data_clean <= upper_whisker)]
    
    if len(data_within_whiskers) > 0:
        min_val = np.min(data_within_whiskers)
        max_val = np.max(data_within_whiskers)
    else:
        min_val = np.min(data_clean)
        max_val = np.max(data_clean)
    
    return {
        MaidrKey.Q1.value: float(q1),
        MaidrKey.Q2.value: float(q2),
        MaidrKey.Q3.value: float(q3),
        MaidrKey.IQ.value: float(iqr),
        MaidrKey.MIN.value: float(min_val),
        MaidrKey.MAX.value: float(max_val)
    }


def create_violin_box_elements(ax, box_stats, orientation="vert", x_position=0):
    """
    Create box plot elements (lines) for violin plot based on calculated statistics.
    Assigns GIDs to elements for highlighting.
    
    Parameters:
    -----------
    ax : matplotlib.axes.Axes
        The axes object
    box_stats : dict
        Box plot statistics from calculate_box_stats_from_violin_data
    orientation : str
        "vert" for vertical violin plots, "horz" for horizontal
        
    Returns:
    --------
    tuple : (elements_dict, elements_info_dict)
        elements_dict: Box plot elements with keys: boxes, medians, whiskers, caps, fliers
        elements_info_dict: Dict with GIDs for selectors: min_gid, max_gid, median_gid
    """
    if box_stats is None:
        return ({"boxes": [], "medians": [], "whiskers": [], "caps": [], "fliers": []}, {})
    
    # Get the center position for the violin
    if orientation == "vert":
        # For vertical violin, center on x-axis at the specified position
        x_center = x_position
        y_min = box_stats[MaidrKey.MIN.value]
        y_max = box_stats[MaidrKey.MAX.value]
        y_q1 = box_stats[MaidrKey.Q1.value]
        y_q2 = box_stats[MaidrKey.Q2.value]
        y_q3 = box_stats[MaidrKey.Q3.value]
        
        # Create box (Q1 to Q3) - IQR rectangle
        box_width = 0.4  # Adjust as needed
        box_rect = Rectangle(
            (x_center - box_width/2, y_q1),  # bottom-left corner
            box_width,  # width
            y_q3 - y_q1,  # height (Q3 - Q1)
            linewidth=1,
            edgecolor='black',
            facecolor='none'
        )
        
        # Create median line
        median_line = Line2D([x_center - box_width/2, x_center + box_width/2], [y_q2, y_q2], 
                           color='black', linewidth=1)
        
        # Create whiskers (vertical lines)
        _whisker_width = 0.1  # kept for potential future customization
        lower_whisker = Line2D([x_center, x_center], [y_min, y_q1], color='black', linewidth=1)
        upper_whisker = Line2D([x_center, x_center], [y_q3, y_max], color='black', linewidth=1)
        
        # Create caps (horizontal lines at whisker ends)
        cap_length = 0.2
        lower_cap = Line2D([x_center - cap_length/2, x_center + cap_length/2], [y_min, y_min], color='black', linewidth=1)
        upper_cap = Line2D([x_center - cap_length/2, x_center + cap_length/2], [y_max, y_max], color='black', linewidth=1)
        
    else:
        # For horizontal violin, center on y-axis at the specified position
        y_center = x_position  # For horizontal, x_position is actually y_position
        x_min = box_stats[MaidrKey.MIN.value]
        x_max = box_stats[MaidrKey.MAX.value]
        x_q1 = box_stats[MaidrKey.Q1.value]
        x_q2 = box_stats[MaidrKey.Q2.value]
        x_q3 = box_stats[MaidrKey.Q3.value]
        
        # Create box (Q1 to Q3) - IQR rectangle
        box_height = 0.4  # Adjust as needed
        box_rect = Rectangle(
            (x_q1, y_center - box_height/2),  # bottom-left corner
            x_q3 - x_q1,  # width (Q3 - Q1)
            box_height,  # height
            linewidth=1,
            edgecolor='black',
            facecolor='none'
        )
        
        # Create median line
        median_line = Line2D([x_q2, x_q2], [y_center - box_height/2, y_center + box_height/2], 
                           color='black', linewidth=1)
        
        # Create whiskers (horizontal lines)
        _whisker_height = 0.1  # kept for potential future customization
        lower_whisker = Line2D([x_min, x_q1], [y_center, y_center], color='black', linewidth=1)
        upper_whisker = Line2D([x_q3, x_max], [y_center, y_center], color='black', linewidth=1)
        
        # Create caps (vertical lines at whisker ends)
        cap_length = 0.2
        lower_cap = Line2D([x_min, x_min], [y_center - cap_length/2, y_center + cap_length/2], color='black', linewidth=1)
        upper_cap = Line2D([x_max, x_max], [y_center - cap_length/2, y_center + cap_length/2], color='black', linewidth=1)
    
    # Assign GIDs to elements for highlighting
    min_gid = f"maidr-{uuid.uuid4()}"
    max_gid = f"maidr-{uuid.uuid4()}"
    median_gid = f"maidr-{uuid.uuid4()}"
    box_gid = f"maidr-{uuid.uuid4()}"
    
    lower_cap.set_gid(min_gid)
    upper_cap.set_gid(max_gid)
    median_line.set_gid(median_gid)
    box_rect.set_gid(box_gid)
    
    # Also set GIDs on whiskers for completeness (though they're not used in selectors)
    lower_whisker.set_gid(f"maidr-{uuid.uuid4()}")
    upper_whisker.set_gid(f"maidr-{uuid.uuid4()}")
    
    # Add elements to the plot
    ax.add_patch(box_rect)  # Add box rectangle first
    ax.add_line(median_line)
    ax.add_line(lower_whisker)
    ax.add_line(upper_whisker)
    ax.add_line(lower_cap)
    ax.add_line(upper_cap)
    
    elements_dict = {
        "boxes": [box_rect],  # Box rectangle for IQR
        "medians": [median_line],
        "whiskers": [lower_whisker, upper_whisker],
        "caps": [lower_cap, upper_cap],
        "fliers": []  # No outliers for now
    }
    
    elements_info = {
        "min_gid": min_gid,
        "max_gid": max_gid,
        "median_gid": median_gid,
        "box_gid": box_gid,  # Box GID for IQR highlighting
    }
    
    return (elements_dict, elements_info)


def create_violin_box_data(box_stats, level="Violin"):
    """
    Create proper box plot data structure for violin plot.
    
    Parameters:
    -----------
    box_stats : dict
        Box plot statistics from calculate_box_stats_from_violin_data
    level : str
        Level/fill value for the box plot data
        
    Returns:
    --------
    list : Box plot data in the format expected by MAIDR
    """
    if box_stats is None:
        return []
    
    return [{
        MaidrKey.FILL.value: level,
        MaidrKey.MIN.value: box_stats[MaidrKey.MIN.value],
        MaidrKey.Q1.value: box_stats[MaidrKey.Q1.value],
        MaidrKey.Q2.value: box_stats[MaidrKey.Q2.value],
        MaidrKey.Q3.value: box_stats[MaidrKey.Q3.value],
        MaidrKey.MAX.value: box_stats[MaidrKey.MAX.value],
        MaidrKey.LOWER_OUTLIER.value: [],  # No outliers for violin plots
        MaidrKey.UPPER_OUTLIER.value: [],  # No outliers for violin plots
    }]


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def sns_violin(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.violinplot to register BOX and SMOOTH (KDE) layers for MAIDR.
    A violin plot consists of a KDE (density distribution) as smooth curves.
    Always registers BOX layer with min, max, median, Q1, Q3 statistics
    calculated from the raw data, regardless of whether inner='box' is set.
    """
    # Track if we're in internal context to avoid recursion
    if BoxplotContextManager.is_internal_context() or ContextManager.is_internal_context():
        plot = wrapped(*args, **kwargs)
        return plot

    # Determine orientation
    orientation = kwargs.get("orient", "v")
    if orientation == "h" or orientation == "y":
        orientation_str = "horz"
    else:
        orientation_str = "vert"

    # Get box plot statistics if inner='box' or inner='quartiles' is set
    inner = kwargs.get("inner", None)
    has_box_stats = inner in ("box", "quartiles", "quart")

    # Execute the original violinplot and capture box plot stats if present
    _bxp_stats = None
    if has_box_stats:
        # Use BoxplotContextManager to capture bxp stats when box plot is created
        with BoxplotContextManager.set_internal_context() as bxp_context:
            BoxplotContextManager.set_bxp_orientation(orientation)
            plot = wrapped(*args, **kwargs)
            
            # Check if box plot stats were captured
            captured_stats = bxp_context.bxp_stats()
            if (captured_stats.get("boxes") or captured_stats.get("medians") or 
                captured_stats.get("whiskers") or captured_stats.get("caps")):
                _bxp_stats = captured_stats
                if bxp_context.orientation():
                    orientation_str = (
                        "horz" if bxp_context.orientation() in ("h", "y", "horz") 
                        else "vert"
                    )
    else:
        # If no box stats expected, use regular internal context
        with ContextManager.set_internal_context():
            plot = wrapped(*args, **kwargs)

    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    if ax is None:
        return plot

    # Always register box plot layer by calculating stats from raw data
    # This works regardless of whether inner='box' is set
    
    # Extract the original data from the violin plot arguments
    # Handle seaborn API: x="col1", y="col2", data=df
    violin_data = None
    data_df = None
    x_col = None
    y_col = None
    
    # Get the data DataFrame
    if 'data' in kwargs:
        data_df = kwargs['data']
    elif len(args) > 0:
        # Check if first arg is a DataFrame
        if isinstance(args[0], pd.DataFrame):
            data_df = args[0]
    
    # Get column names
    if 'x' in kwargs:
        x_col = kwargs['x']
    if 'y' in kwargs:
        y_col = kwargs['y']
    
    # Extract the y column from the DataFrame if we have it
    if data_df is not None and isinstance(data_df, pd.DataFrame):
        if y_col is not None and isinstance(y_col, str) and y_col in data_df.columns:
            # Check if we have multiple groups (x parameter exists)
            if x_col is not None and isinstance(x_col, str) and x_col in data_df.columns:
                # Multiple violins - calculate stats for each group
                all_box_data = []
                all_elements_info = []
                all_box_elements = []  # Collect all elements for tracking
                
                # Get the actual visual order from the axes tick labels (matches seaborn's display order)
                # This is critical to ensure box plot data matches the visual violin order
                if orientation_str == "vert":
                    tick_labels = [label.get_text() for label in ax.get_xticklabels()]
                    tick_positions = ax.get_xticks()
                else:
                    tick_labels = [label.get_text() for label in ax.get_yticklabels()]
                    tick_positions = ax.get_yticks()
                
                # Match tick positions to groups and sort by position to ensure correct visual order
                position_group_pairs = []
                if tick_labels and len(tick_labels) > 0 and len(tick_positions) == len(tick_labels):
                    # Create pairs of (position, group) for each tick
                    for tick_pos, tick_label in zip(tick_positions, tick_labels):
                        # Try to find matching group in the data
                        for group in data_df[x_col].unique():
                            if str(group) == str(tick_label) or str(group) == tick_label:
                                position_group_pairs.append((tick_pos, group))
                                break
                
                # If we couldn't match all, create pairs from unique() order
                if len(position_group_pairs) != len(tick_positions):
                    unique_groups_list = list(data_df[x_col].unique())
                    if len(tick_positions) == len(unique_groups_list):
                        position_group_pairs = list(zip(tick_positions, unique_groups_list))
                    else:
                        # Fallback: use sequential positions
                        if orientation_str == "vert":
                            fallback_positions = list(range(len(unique_groups_list)))
                        else:
                            fallback_positions = list(range(len(unique_groups_list)))
                        position_group_pairs = list(zip(fallback_positions, unique_groups_list))
                
                # Sort by position to ensure left-to-right (or bottom-to-top) order
                position_group_pairs.sort(key=lambda x: x[0])
                
                # Extract groups in sorted order
                unique_groups = [group for _, group in position_group_pairs]
                _sorted_tick_positions = [pos for pos, _ in position_group_pairs]
                
                # Create mapping: tick position -> group name
                position_to_group = {pos: group for pos, group in position_group_pairs}
                
                _group_positions = {group: idx for idx, group in enumerate(unique_groups)}
                
                # Create a position-indexed dictionary to ensure correct ordering
                # This ensures box plot data and selectors match by position index
                position_indexed_data = {}
                for group_idx, (tick_pos, group_name) in enumerate(position_group_pairs):
                    group_data = data_df[data_df[x_col] == group_name]
                    group_y_values = group_data[y_col].dropna().values
                    if len(group_y_values) > 0:
                        group_box_stats = calculate_box_stats_from_violin_data(group_y_values, orientation_str)
                        if group_box_stats is not None:
                            position_indexed_data[group_idx] = {
                                'tick_pos': tick_pos,
                                'group_name': group_name,
                                'box_stats': group_box_stats
                            }
                
                # Now iterate through sorted positions to create data and elements in correct order
                for group_idx in sorted(position_indexed_data.keys()):
                    item = position_indexed_data[group_idx]
                    tick_pos = item['tick_pos']
                    group_name = item['group_name']
                    group_box_stats = item['box_stats']
                    
                    # Create box plot data for this group
                    group_box_data = create_violin_box_data(group_box_stats, str(group_name))
                    all_box_data.extend(group_box_data)
                    
                    # Create box plot elements for this group
                    # Use the actual tick position to ensure correct placement
                    box_elements, elements_info = create_violin_box_elements(ax, group_box_stats, orientation_str, x_position=tick_pos)
                    all_elements_info.append(elements_info)
                    
                    # Collect elements for tracking
                    if box_elements:
                        all_box_elements.extend(box_elements.get("boxes", []) + 
                                               box_elements.get("medians", []) + 
                                               box_elements.get("whiskers", []) + 
                                               box_elements.get("caps", []))
                
                if all_box_data:
                    # Create custom violin box plot and add it to MAIDR
                    try:
                        # Get the MAIDR instance for this figure
                        maidr_instance = FigureManager._get_maidr(ax.get_figure(), PlotType.SMOOTH)
                        
                        # Create our custom violin box plot with element info for selectors
                        violin_box_plot = ViolinBoxPlot(ax, all_box_data, orientation_str, 
                                                       elements_info=all_elements_info,
                                                       box_elements_list=all_box_elements)
                        
                        # Add it to the MAIDR instance
                        maidr_instance.plots.append(violin_box_plot)
                        maidr_instance.selector_ids.append(str(uuid.uuid4()))
                    except Exception:
                        import traceback
                        traceback.print_exc()
            else:
                # Single violin - use all y values
                violin_data = data_df[y_col].dropna().values
        elif x_col is not None and orientation_str == "horz":
            # For horizontal plots, x is the numeric column
            if isinstance(x_col, str) and x_col in data_df.columns:
                violin_data = data_df[x_col].dropna().values
    else:
        # Fallback: try to get data directly
        if y_col is not None:
            # Handle pandas Series - check if it's not empty
            if isinstance(y_col, pd.Series):
                if not y_col.empty:
                    violin_data = y_col
            else:
                violin_data = y_col
        elif x_col is not None:
            # Handle pandas Series - check if it's not empty
            if isinstance(x_col, pd.Series):
                if not x_col.empty:
                    violin_data = x_col
            else:
                violin_data = x_col
        elif len(args) > 0:
            violin_data = args[0]
    
    # If violin_data is still a string or non-numeric, try to extract from the plot
    if violin_data is not None and not isinstance(violin_data, (np.ndarray, list, pd.Series)):
        if isinstance(violin_data, str):
            # It's a column name, but we don't have the DataFrame
            # Try to get it from the axes collections
            violin_data = None
    
    # Handle single violin case (no grouping)
    if violin_data is not None and isinstance(violin_data, (np.ndarray, list, pd.Series)):
        # Calculate box plot statistics from the violin data
        box_stats = calculate_box_stats_from_violin_data(violin_data, orientation_str)
        
        if box_stats is not None:
            # Create box plot elements
            box_elements, elements_info = create_violin_box_elements(ax, box_stats, orientation_str)
            
            # Create proper box plot data structure for MAIDR
            box_data = create_violin_box_data(box_stats, "Violin")
            
            # Create custom violin box plot and add it to MAIDR
            try:
                # Get the MAIDR instance for this figure
                maidr_instance = FigureManager._get_maidr(ax.get_figure(), PlotType.SMOOTH)
                
                # Collect elements for tracking
                # These must be the actual matplotlib artist objects (Line2D, Rectangle, etc.)
                # that were added to the axes, so they can be registered with HighlightContextManager
                box_elements_list = (box_elements.get("boxes", []) + 
                                   box_elements.get("medians", []) + 
                                   box_elements.get("whiskers", []) + 
                                   box_elements.get("caps", []))
                
                # Create our custom violin box plot with element info for selectors
                violin_box_plot = ViolinBoxPlot(ax, box_data, orientation_str, 
                                               elements_info=[elements_info],
                                               box_elements_list=box_elements_list)
                
                # Add it to the MAIDR instance
                maidr_instance.plots.append(violin_box_plot)
                maidr_instance.selector_ids.append(str(uuid.uuid4()))
            except Exception:
                import traceback
                traceback.print_exc()

    # Register KDE (violin shape) as SMOOTH layer
    # Violin plots create filled polygons for the KDE distribution
    violin_polys = []
    for collection in ax.collections:
        if isinstance(collection, PolyCollection):
            # Check if it's the violin shape (not box elements)
            if hasattr(collection, "get_paths") and collection.get_paths():
                path = collection.get_paths()[0]
                vertices = path.vertices
                if len(vertices) > 10:  # Violins have many vertices, boxes have few
                    violin_polys.append(collection)

    # Register each violin shape as a SMOOTH layer
    # Follow the same pattern as histogram: register each element using common()
    
    # Get group names if available (for multiple violins)
    # Match violin polygons to groups by their x-position (for vertical) or y-position (for horizontal)
    # Use the same position-based matching as box plot data to ensure consistent ordering
    group_names = None
    violin_poly_with_positions = []
    
    if data_df is not None and isinstance(data_df, pd.DataFrame):
        if x_col is not None and isinstance(x_col, str) and x_col in data_df.columns:
            # Get tick positions and labels to match polygons (same as box plot data)
            if orientation_str == "vert":
                tick_labels = [label.get_text() for label in ax.get_xticklabels()]
                tick_positions = ax.get_xticks()
            else:
                tick_labels = [label.get_text() for label in ax.get_yticklabels()]
                tick_positions = ax.get_yticks()
            
            # Create mapping: tick position -> group name (same logic as box plot data)
            position_to_group = {}
            position_group_pairs_smooth = []
            if tick_labels and len(tick_labels) > 0 and len(tick_positions) == len(tick_labels):
                for pos, tick_label in zip(tick_positions, tick_labels):
                    # Find matching group in the data
                    for group in data_df[x_col].unique():
                        if str(group) == str(tick_label) or str(group) == tick_label:
                            position_to_group[pos] = str(group)
                            position_group_pairs_smooth.append((pos, str(group)))
                            break
            
            # Sort by position to match box plot data order
            if position_group_pairs_smooth:
                position_group_pairs_smooth.sort(key=lambda x: x[0])
                position_to_group = {pos: group for pos, group in position_group_pairs_smooth}
            
            # Match each violin polygon to its group by position
            sorted_tick_pos_list = sorted(position_to_group.keys()) if position_to_group else []
            
            for violin_poly in violin_polys:
                path = violin_poly.get_paths()[0]
                vertices = np.asarray(path.vertices)
                
                # Get the center x-position (for vertical) or y-position (for horizontal)
                if orientation_str == "vert":
                    # For vertical: use the x-coordinate (center of violin)
                    poly_position = np.mean(vertices[:, 0])
                else:
                    # For horizontal: use the y-coordinate (center of violin)
                    poly_position = np.mean(vertices[:, 1])
                
                # Find the nearest tick position from sorted list
                if sorted_tick_pos_list:
                    nearest_tick_pos = min(sorted_tick_pos_list, key=lambda x: abs(x - poly_position))
                    group_name = position_to_group.get(nearest_tick_pos, None)
                else:
                    group_name = None
                
                violin_poly_with_positions.append((poly_position, group_name, violin_poly))
            
            # Sort by position to match visual order (left-to-right for vertical, bottom-to-top for horizontal)
            violin_poly_with_positions.sort(key=lambda x: x[0])
            
            # Extract group names in the sorted order (matches box plot data order)
            group_names = [item[1] for item in violin_poly_with_positions if item[1] is not None]
            
            # Fallback if we couldn't match all
            if not group_names or len(group_names) != len(violin_polys):
                if tick_labels and len(tick_labels) > 0:
                    group_names = []
                    for tick_label in tick_labels:
                        for group in data_df[x_col].unique():
                            if str(group) == str(tick_label) or str(group) == tick_label:
                                group_names.append(str(group))
                                break
                if not group_names or len(group_names) != len(violin_polys):
                    group_names = [str(g) for g in data_df[x_col].unique()]
                    violin_poly_with_positions = [(i, group_names[i] if i < len(group_names) else None, poly) 
                                                   for i, poly in enumerate(violin_polys)]
    
    # Use sorted polygons if we matched them, otherwise use original order
    if violin_poly_with_positions:
        sorted_violin_polys = [item[2] for item in violin_poly_with_positions]
    else:
        sorted_violin_polys = violin_polys
        if group_names is None and data_df is not None and x_col is not None:
            group_names = [str(g) for g in data_df[x_col].unique()]
    
    for i, violin_poly in enumerate(sorted_violin_polys):
        if violin_poly.get_gid() is None:
            gid = f"maidr-{uuid.uuid4()}"
            violin_poly.set_gid(gid)
            violin_poly.set_label(f"Violin {gid}")

        # Extract the boundary of the polygon
        path = violin_poly.get_paths()[0]
        boundary = np.asarray(path.vertices)

        # Create a Line2D from the boundary for the smooth layer
        # Ensure the Line2D has proper data structure for density extraction
        kde_line = Line2D(boundary[:, 0], boundary[:, 1], marker='', linestyle='-')
        kde_line.set_gid(violin_poly.get_gid())
        kde_line.set_label(f"Violin KDE {violin_poly.get_gid()}")
        # Ensure the line data is accessible via get_xydata()
        kde_line.set_data(boundary[:, 0], boundary[:, 1])

        # Get the group name for this violin (from sorted order, matches box plot data order)
        violin_fill = None
        if group_names and i < len(group_names):
            violin_fill = group_names[i]
        elif len(violin_polys) == 1:
            # Single violin case
            violin_fill = "Violin"

        # Register as SMOOTH layer using common() pattern (like histogram does)
        # Use lambda to return the axes since plot is already created
        common(
            PlotType.SMOOTH,
            lambda *a, **k: ax,
            instance,
            args,
            dict(
                kwargs,
                regression_line=kde_line,
                violin_poly=violin_poly,
                poly_gid=violin_poly.get_gid(),
                is_polycollection=True,
                violin_fill=violin_fill,  # Pass the category name
            ),
            )

    return plot
