from __future__ import annotations

import wrapt
import uuid
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
import numpy as np

from maidr.core.context_manager import BoxplotContextManager, ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import common


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def sns_violin(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.violinplot to register BOX and SMOOTH (KDE) layers for MAIDR.
    A violin plot consists of a KDE (density distribution) as smooth curves.
    If inner='box' or inner='quartiles' is set, also registers BOX layer with
    min, max, median, Q1, Q3 statistics extracted from the box plot elements.
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

    # Register box plot layer if we have box stats
    if has_box_stats:
        # If bxp_stats were captured, validate they have meaningful data
        # Check if bxp_stats exists AND has at least one non-empty list
        has_valid_bxp_stats = False
        if bxp_stats:
            # Check if any list has elements
            if (len(bxp_stats.get("boxes", [])) > 0 or 
                len(bxp_stats.get("medians", [])) > 0 or 
                len(bxp_stats.get("whiskers", [])) > 0 or 
                len(bxp_stats.get("caps", [])) > 0):
                has_valid_bxp_stats = True
        
        if has_valid_bxp_stats:
            # Ensure all required lists exist (even if empty)
            boxes = bxp_stats.get("boxes", [])
            medians = bxp_stats.get("medians", [])
            whiskers = bxp_stats.get("whiskers", [])
            caps = bxp_stats.get("caps", [])
            fliers = bxp_stats.get("fliers", [])
            
            # Register if we have at least one type of box plot element
            # Box polygons are optional (newer seaborn may not create them)
            # Whiskers and caps should be in pairs, but allow if empty
            has_any_elements = (
                len(boxes) > 0 or
                len(medians) > 0 or
                len(whiskers) > 0 or
                len(caps) > 0
            )
            
            # If whiskers or caps exist, ensure they're properly paired
            whiskers_paired = len(whiskers) == 0 or len(whiskers) % 2 == 0
            caps_paired = len(caps) == 0 or len(caps) % 2 == 0
            
            if has_any_elements and whiskers_paired and caps_paired:
                print(f"[DEBUG] Attempting to register BOX layer with captured stats")
                try:
                    # Register box plot layer using captured bxp_stats
                    FigureManager.create_maidr(
                        ax, PlotType.BOX, bxp_stats=bxp_stats, orientation=orientation_str
                    )
                    print(f"[DEBUG] ✓ BOX layer registered successfully")
                except Exception as e:
                    # If registration fails, fall through to manual extraction
                    print(f"[DEBUG] ✗ BOX registration failed: {e}")
                    import traceback
                    traceback.print_exc()
                    pass
        else:
            print(f"[DEBUG] bxp_stats is empty/dict, using fallback extraction")
            try:
                # Fallback: Robust line-based extraction of box plot elements
                # Strategy: Identify medians, whiskers, and caps from Line2D objects
                # using peak-to-peak ranges and relative positioning
                
                box_polys = []
                median_lines = []
                whisker_lines = []
                cap_lines = []
                
                # Optional: Try to find box polygons (but don't rely on them)
                # Identify violin polygons to exclude them
                violin_poly_ids = set()
                for collection in ax.collections:
                    if isinstance(collection, PolyCollection):
                        if hasattr(collection, "get_paths") and collection.get_paths():
                            path = collection.get_paths()[0]
                            if len(path.vertices) > 10:
                                if collection.get_gid():
                                    violin_poly_ids.add(collection.get_gid())
                
                # Extract box polygons (optional - may not exist in newer seaborn)
                for collection in ax.collections:
                    if isinstance(collection, PolyCollection):
                        if hasattr(collection, "get_paths") and collection.get_paths():
                            path = collection.get_paths()[0]
                            if 4 <= len(path.vertices) <= 10:
                                if collection.get_gid() not in violin_poly_ids:
                                    box_polys.append(collection)
                
                for artist in ax.artists:
                    if isinstance(artist, PolyCollection):
                        if hasattr(artist, "get_paths") and artist.get_paths():
                            path = artist.get_paths()[0]
                            if 4 <= len(path.vertices) <= 10:
                                if artist.get_gid() not in violin_poly_ids:
                                    box_polys.append(artist)
                
                # Extract and classify lines using robust peak-to-peak ranges
                all_lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
                print(f"[DEBUG] Found {len(all_lines)} total Line2D objects")
                
                if len(all_lines) == 0:
                    # No lines found, skip registration
                    print(f"[DEBUG] No lines found, skipping box plot registration")
                else:
                    # Get axes ranges for relative threshold calculation
                    xlim = ax.get_xlim()
                    ylim = ax.get_ylim()
                    x_range = abs(xlim[1] - xlim[0]) if xlim[1] != xlim[0] else 1
                    y_range = abs(ylim[1] - ylim[0]) if ylim[1] != ylim[0] else 1
                    
                    # Calculate ranges for each line using np.ptp (peak-to-peak)
                    for idx, line in enumerate(all_lines):
                        xdata = np.asarray(line.get_xdata())
                        ydata = np.asarray(line.get_ydata())
                        
                        if len(xdata) < 2 or len(ydata) < 2:
                            print(f"[DEBUG] Line {idx}: skipping (insufficient data points)")
                            continue
                        
                        dx = np.ptp(xdata)  # peak-to-peak x range
                        dy = np.ptp(ydata)  # peak-to-peak y range
                        
                        print(f"[DEBUG] Line {idx}: dx={dx:.2f} ({dx/x_range*100:.1f}% of x_range), "
                              f"dy={dy:.2f} ({dy/y_range*100:.1f}% of y_range), "
                              f"x_range={x_range:.2f}, y_range={y_range:.2f}")
                        
                        # Use relative thresholds (robust to scale)
                        # For single violin plots, x_range can be near zero, so use absolute minimum
                        x_rel_threshold = max(x_range * 0.02, 0.1)  # At least 0.1 units
                        y_rel_threshold = max(y_range * 0.02, 0.1)  # At least 0.1 units
                        
                        if orientation_str == "vert":
                            # Vertical orientation: whiskers are vertical, medians/caps are horizontal
                            
                            # Median: long horizontal line (perpendicular to whiskers)
                            # For single violin: dx can be very small (≈0), but dy should be tiny
                            # Condition: very small y-range (< 2% or < 0.5 units), and points in same y
                            if dy < max(y_rel_threshold, 0.5) and len(ydata) >= 2:
                                # Check if it's horizontal: y values are nearly constant
                                if not any(id(line) == id(m) for m in median_lines):
                                    median_lines.append(line)
                                    print(f"[DEBUG] Line {idx}: Classified as MEDIAN (dy={dy:.2f})")
                            # Whisker: long vertical line (aligned with value axis)
                            # Condition: very small x-range (< 2% or < 0.1 units), large y-range (> 10% of y_range)
                            elif dx < max(x_rel_threshold, 0.1):
                                whisker_thresh_y = max(y_rel_threshold * 5, y_range * 0.1)
                                if dy > whisker_thresh_y:
                                    if not any(id(line) == id(w) for w in whisker_lines):
                                        whisker_lines.append(line)
                                        print(f"[DEBUG] Line {idx}: Classified as WHISKER (dx={dx:.2f}, dy={dy:.2f})")
                            # Cap: short horizontal segment at whisker ends
                            # Condition: small y-range (< 2% or < 0.5 units), small x-range
                            elif dy < max(y_rel_threshold, 0.5) and dx > 0.05 and dx < max(x_range * 0.2, 1.0):
                                if not any(id(line) == id(c) for c in cap_lines):
                                    cap_lines.append(line)
                                    print(f"[DEBUG] Line {idx}: Classified as CAP (dx={dx:.2f}, dy={dy:.2f})")
                            else:
                                print(f"[DEBUG] Line {idx}: Not classified (dx={dx:.2f}, dy={dy:.2f}, "
                                      f"x_range={x_range:.2f}, y_range={y_range:.2f})")
                        else:
                            # Horizontal orientation: mirrored conditions
                            # Median: long vertical line
                            if dx < x_rel_threshold and dy > y_rel_threshold * 3:
                                if not any(id(line) == id(m) for m in median_lines):
                                    median_lines.append(line)
                            # Whisker: long horizontal line
                            elif dy < y_rel_threshold and dx > x_rel_threshold * 5:
                                if not any(id(line) == id(w) for w in whisker_lines):
                                    whisker_lines.append(line)
                            # Cap: short vertical segment
                            elif dx < x_rel_threshold and 0 < dy < y_range * 0.2:
                                if not any(id(line) == id(c) for c in cap_lines):
                                    cap_lines.append(line)
                    
                    # Register if we found at least medians OR (whiskers + caps)
                    # Box polygons are optional
                    print(f"[DEBUG] Classified lines: {len(median_lines)} medians, "
                          f"{len(whisker_lines)} whiskers, {len(cap_lines)} caps, "
                          f"{len(box_polys)} box polygons")
                    has_medians = len(median_lines) > 0
                    has_whiskers_and_caps = (len(whisker_lines) >= 2) and (len(cap_lines) >= 2)
                    
                    # Ensure whiskers and caps are properly paired (even counts)
                    # BoxPlotExtractor expects pairs: [lower, upper, lower, upper, ...]
                    paired_whiskers = whisker_lines[:len(whisker_lines)//2*2] if len(whisker_lines) >= 2 else []
                    paired_caps = cap_lines[:len(cap_lines)//2*2] if len(cap_lines) >= 2 else []
                    
                    print(f"[DEBUG] Registration check: has_medians={has_medians}, "
                          f"has_whiskers_and_caps={has_whiskers_and_caps}, has_box_polys={len(box_polys) > 0}, "
                          f"paired_whiskers={len(paired_whiskers)}")
                    
                    if has_medians or has_whiskers_and_caps or box_polys:
                        
                        # Construct bxp_stats - allow empty boxes (common in newer seaborn)
                        constructed_stats = {
                            "boxes": box_polys,
                            "medians": median_lines,
                            "whiskers": paired_whiskers,
                            "caps": paired_caps,
                            "fliers": []
                        }
                        
                        # Only register if we have meaningful data
                        # Need at least: medians OR (paired whiskers + paired caps)
                        can_register = (
                            len(median_lines) > 0 or
                            (len(paired_whiskers) >= 2 and len(paired_caps) >= 2) or
                            len(box_polys) > 0
                        )
                        
                        if can_register:
                            print(f"[DEBUG] Attempting to register BOX layer with fallback stats: "
                                  f"boxes={len(box_polys)}, medians={len(median_lines)}, "
                                  f"whiskers={len(paired_whiskers)}, caps={len(paired_caps)}")
                            try:
                                # Register box plot with extracted elements
                                FigureManager.create_maidr(
                                    ax, PlotType.BOX, bxp_stats=constructed_stats, orientation=orientation_str
                                )
                                print(f"[DEBUG] ✓ BOX layer registered successfully (fallback)")
                            except Exception as e:
                                # If registration fails (e.g., extraction error), continue
                                # This allows the smooth layer to still be registered
                                print(f"[DEBUG] ✗ BOX registration failed (fallback): {e}")
                                import traceback
                                traceback.print_exc()
                                pass
                        else:
                            print(f"[DEBUG] Cannot register: no valid box plot elements found")
            except Exception as e:
                print(f"[DEBUG] Fallback extraction failed: {e}")
                import traceback
                traceback.print_exc()

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
