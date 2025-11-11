from __future__ import annotations

import wrapt
import uuid
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
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
    
    def __init__(self, ax, box_data, orientation="vert"):
        super().__init__(ax, PlotType.BOX)
        self.box_data = box_data
        self.orientation = orientation
        
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


def create_violin_box_elements(ax, box_stats, orientation="vert"):
    """
    Create box plot elements (lines) for violin plot based on calculated statistics.
    
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
    dict : Box plot elements with keys: boxes, medians, whiskers, caps, fliers
    """
    if box_stats is None:
        return {"boxes": [], "medians": [], "whiskers": [], "caps": [], "fliers": []}
    
    # Get the center position for the violin (assuming single violin)
    if orientation == "vert":
        # For vertical violin, center on x-axis
        x_center = 0  # or get from violin position
        y_min = box_stats[MaidrKey.MIN.value]
        y_max = box_stats[MaidrKey.MAX.value]
        y_q1 = box_stats[MaidrKey.Q1.value]
        y_q2 = box_stats[MaidrKey.Q2.value]
        y_q3 = box_stats[MaidrKey.Q3.value]
        
        # Create box (Q1 to Q3)
        box_width = 0.4  # Adjust as needed
        box_x = [x_center - box_width/2, x_center + box_width/2, x_center + box_width/2, x_center - box_width/2, x_center - box_width/2]
        box_y = [y_q1, y_q1, y_q3, y_q3, y_q1]
        
        # Create median line
        median_line = Line2D([x_center - box_width/2, x_center + box_width/2], [y_q2, y_q2], 
                           color='black', linewidth=1)
        
        # Create whiskers (vertical lines)
        whisker_width = 0.1
        lower_whisker = Line2D([x_center, x_center], [y_min, y_q1], color='black', linewidth=1)
        upper_whisker = Line2D([x_center, x_center], [y_q3, y_max], color='black', linewidth=1)
        
        # Create caps (horizontal lines at whisker ends)
        cap_length = 0.2
        lower_cap = Line2D([x_center - cap_length/2, x_center + cap_length/2], [y_min, y_min], color='black', linewidth=1)
        upper_cap = Line2D([x_center - cap_length/2, x_center + cap_length/2], [y_max, y_max], color='black', linewidth=1)
        
    else:
        # For horizontal violin, center on y-axis
        y_center = 0  # or get from violin position
        x_min = box_stats[MaidrKey.MIN.value]
        x_max = box_stats[MaidrKey.MAX.value]
        x_q1 = box_stats[MaidrKey.Q1.value]
        x_q2 = box_stats[MaidrKey.Q2.value]
        x_q3 = box_stats[MaidrKey.Q3.value]
        
        # Create box (Q1 to Q3)
        box_height = 0.4  # Adjust as needed
        box_x = [x_q1, x_q1, x_q3, x_q3, x_q1]
        box_y = [y_center - box_height/2, y_center + box_height/2, y_center + box_height/2, y_center - box_height/2, y_center - box_height/2]
        
        # Create median line
        median_line = Line2D([x_q2, x_q2], [y_center - box_height/2, y_center + box_height/2], 
                           color='black', linewidth=1)
        
        # Create whiskers (horizontal lines)
        whisker_height = 0.1
        lower_whisker = Line2D([x_min, x_q1], [y_center, y_center], color='black', linewidth=1)
        upper_whisker = Line2D([x_q3, x_max], [y_center, y_center], color='black', linewidth=1)
        
        # Create caps (vertical lines at whisker ends)
        cap_length = 0.2
        lower_cap = Line2D([x_min, x_min], [y_center - cap_length/2, y_center + cap_length/2], color='black', linewidth=1)
        upper_cap = Line2D([x_max, x_max], [y_center - cap_length/2, y_center + cap_length/2], color='black', linewidth=1)
    
    # Add elements to the plot
    ax.add_line(median_line)
    ax.add_line(lower_whisker)
    ax.add_line(upper_whisker)
    ax.add_line(lower_cap)
    ax.add_line(upper_cap)
    
    return {
        "boxes": [],  # No box polygon for violin plots
        "medians": [median_line],
        "whiskers": [lower_whisker, upper_whisker],
        "caps": [lower_cap, upper_cap],
        "fliers": []  # No outliers for now
    }


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

    print(f"[DEBUG] inner={inner}, has_box_stats={has_box_stats}")

    # Execute the original violinplot and capture box plot stats if present
    bxp_stats = None
    if has_box_stats:
        # Use BoxplotContextManager to capture bxp stats when box plot is created
        with BoxplotContextManager.set_internal_context() as bxp_context:
            BoxplotContextManager.set_bxp_orientation(orientation)
            plot = wrapped(*args, **kwargs)
            
            # Check if box plot stats were captured
            captured_stats = bxp_context.bxp_stats()
            print(f"[DEBUG] Captured bxp_stats: boxes={len(captured_stats.get('boxes', []))}, "
                  f"medians={len(captured_stats.get('medians', []))}, "
                  f"whiskers={len(captured_stats.get('whiskers', []))}, "
                  f"caps={len(captured_stats.get('caps', []))}")
            if (captured_stats.get("boxes") or captured_stats.get("medians") or 
                captured_stats.get("whiskers") or captured_stats.get("caps")):
                bxp_stats = captured_stats
                print(f"[DEBUG] Using captured bxp_stats")
                if bxp_context.orientation():
                    orientation_str = (
                        "horz" if bxp_context.orientation() in ("h", "y", "horz") 
                        else "vert"
                    )
            else:
                print(f"[DEBUG] Captured stats empty, will use fallback")
    else:
        # If no box stats expected, use regular internal context
        with ContextManager.set_internal_context():
            plot = wrapped(*args, **kwargs)

    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    if ax is None:
        return plot

    # Always register box plot layer by calculating stats from raw data
    # This works regardless of whether inner='box' is set
    print(f"[DEBUG] Attempting to register BOX layer for violin plot")
    
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
    
    print(f"[DEBUG] Extracted violin data: x_col={x_col}, y_col={y_col}, has_data={data_df is not None}")
    
    # Extract the y column from the DataFrame if we have it
    if data_df is not None and isinstance(data_df, pd.DataFrame):
        if y_col and isinstance(y_col, str) and y_col in data_df.columns:
            # Check if we have multiple groups (x parameter exists)
            if x_col and isinstance(x_col, str) and x_col in data_df.columns:
                # Multiple violins - calculate stats for each group
                print(f"[DEBUG] Multiple violins detected, calculating box stats per group")
                all_box_data = []
                
                # Group data by x values
                for group_name, group_data in data_df.groupby(x_col):
                    group_y_values = group_data[y_col].dropna().values
                    if len(group_y_values) > 0:
                        group_box_stats = calculate_box_stats_from_violin_data(group_y_values, orientation_str)
                        if group_box_stats is not None:
                            # Create box plot data for this group
                            group_box_data = create_violin_box_data(group_box_stats, str(group_name))
                            all_box_data.extend(group_box_data)
                            print(f"[DEBUG] Calculated box stats for group '{group_name}': {group_box_stats}")
                
                if all_box_data:
                    print(f"[DEBUG] Created box data for {len(all_box_data)} groups")
                    # Create custom violin box plot and add it to MAIDR
                    try:
                        # Get the MAIDR instance for this figure
                        maidr_instance = FigureManager._get_maidr(ax.get_figure(), PlotType.SMOOTH)
                        
                        # Create our custom violin box plot
                        violin_box_plot = ViolinBoxPlot(ax, all_box_data, orientation_str)
                        
                        # Add it to the MAIDR instance
                        maidr_instance.plots.append(violin_box_plot)
                        maidr_instance.selector_ids.append(str(uuid.uuid4()))
                        
                        print(f"[DEBUG] ✓ BOX layer registered successfully for violin plot with {len(all_box_data)} groups")
                    except Exception as e:
                        print(f"[DEBUG] ✗ BOX registration failed: {e}")
                        import traceback
                        traceback.print_exc()
            else:
                # Single violin - use all y values
                violin_data = data_df[y_col].dropna().values
        elif x_col and orientation_str == "horz":
            # For horizontal plots, x is the numeric column
            if isinstance(x_col, str) and x_col in data_df.columns:
                violin_data = data_df[x_col].dropna().values
    else:
        # Fallback: try to get data directly
        if y_col:
            violin_data = y_col
        elif x_col:
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
        print(f"[DEBUG] Single violin detected, extracted violin data: {type(violin_data)}, length: {len(violin_data)}")
        
        # Calculate box plot statistics from the violin data
        box_stats = calculate_box_stats_from_violin_data(violin_data, orientation_str)
        print(f"[DEBUG] Calculated box stats: {box_stats}")
        
        if box_stats is not None:
            # Create box plot elements
            box_elements = create_violin_box_elements(ax, box_stats, orientation_str)
            print(f"[DEBUG] Created box elements: {len(box_elements['medians'])} medians, "
                  f"{len(box_elements['whiskers'])} whiskers, {len(box_elements['caps'])} caps")
            
            # Create proper box plot data structure for MAIDR
            box_data = create_violin_box_data(box_stats, "Violin")
            print(f"[DEBUG] Created box data: {box_data}")
            
            # Create custom violin box plot and add it to MAIDR
            try:
                # Get the MAIDR instance for this figure
                maidr_instance = FigureManager._get_maidr(ax.get_figure(), PlotType.SMOOTH)
                
                # Create our custom violin box plot
                violin_box_plot = ViolinBoxPlot(ax, box_data, orientation_str)
                
                # Add it to the MAIDR instance
                maidr_instance.plots.append(violin_box_plot)
                maidr_instance.selector_ids.append(str(uuid.uuid4()))
                
                print(f"[DEBUG] ✓ BOX layer registered successfully for violin plot")
            except Exception as e:
                print(f"[DEBUG] ✗ BOX registration failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[DEBUG] Could not calculate box stats from violin data")
    elif violin_data is None:
        print(f"[DEBUG] Could not extract violin data for box plot calculation")

    # Register KDE (violin shape) as SMOOTH layer
    # Violin plots create filled polygons for the KDE distribution
    print(f"[DEBUG] Looking for violin polygons (KDE shapes)...")
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
    print(f"[DEBUG] Found {len(violin_polys)} violin polygon(s)")
    for i, violin_poly in enumerate(violin_polys):
        print(f"[DEBUG] Registering SMOOTH layer {i+1}/{len(violin_polys)}")
        if violin_poly.get_gid() is None:
            gid = f"maidr-{uuid.uuid4()}"
            violin_poly.set_gid(gid)
            violin_poly.set_label(f"Violin {gid}")  # Set label for identification

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
            ),
            )

    return plot
