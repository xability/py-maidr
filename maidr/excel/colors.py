"""The colors a chart is drawn in: the workbook's theme, and Excel's defaults."""

from __future__ import annotations

import colorsys
from typing import Any

from lxml import etree
from matplotlib.colors import to_rgb

from maidr.excel.formats import as_number
from maidr.excel.package import NS_A

A = f"{{{NS_A}}}"


def fill_color(fill: Any, theme: dict[str, str]) -> str | None:
    """A solid fill's color, with its luminance modifiers applied."""
    if fill is None:
        return None
    for color in fill:
        if not isinstance(color.tag, str):
            continue
        name = etree.QName(color).localname
        if name == "srgbClr":
            base = "#" + (color.get("val") or "").upper()
        elif name == "schemeClr":
            base = theme.get(color.get("val", ""))
        elif name == "sysClr":
            base = "#" + (color.get("lastClr") or "").upper()
        else:
            base = None
        if base is None or len(base) != 7:
            return None
        mod = as_number(_child_val(color, "lumMod"))
        off = as_number(_child_val(color, "lumOff"))
        return _luminance(base, (mod or 100000) / 100000, (off or 0) / 100000)
    return None


def _child_val(element: Any, name: str) -> str | None:
    child = element.find(f"{A}{name}")
    return child.get("val") if child is not None else None


def _luminance(color: str, mod: float, off: float) -> str:
    if mod == 1 and off == 0:
        return color
    r, g, b = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, lum, s = colorsys.rgb_to_hls(r, g, b)
    lum = min(1.0, max(0.0, lum * mod + off))
    r, g, b = colorsys.hls_to_rgb(h, lum, s)
    return "#{:02X}{:02X}{:02X}".format(*(round(v * 255) for v in (r, g, b)))


def default_color(index: int, theme: dict[str, str]) -> str | None:
    """
    The color Excel's default style gives series ``index``: the six theme
    accents in turn, then the six again darker, then lighter.
    """
    base = theme.get(f"accent{index % 6 + 1}")
    if base is None:
        return None
    cycle = (index // 6) % 3
    if cycle == 1:
        return _luminance(base, 0.6, 0)
    if cycle == 2:
        return _luminance(base, 0.6, 0.4)
    return base


def tint(color: str, depth: int) -> str:
    """A branch's color, lighter for each level below the top."""
    r, g, b = to_rgb(color)
    mix = min(0.15 * depth, 0.6)
    return "#{:02X}{:02X}{:02X}".format(
        *(round(255 * (c + (1 - c) * mix)) for c in (r, g, b))
    )
