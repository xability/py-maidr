"""`tick_step` is shared by the scatter and the rug (#605 review)."""

from __future__ import annotations

import numpy as np

from maidr.util.grid_axes import tick_step


def test_evenly_spaced_ticks_name_their_interval():
    assert tick_step(np.array([0.0, 2.0, 4.0, 6.0])) == 2.0


def test_uneven_ticks_name_none():
    """Grid navigation walks in equal increments, so an axis whose ticks are
    not evenly spaced has no step to give."""
    assert tick_step(np.array([0.0, 1.0, 5.0, 10.0])) is None


def test_fewer_than_two_ticks_name_no_interval():
    assert tick_step(np.array([1.0])) is None
    assert tick_step(np.array([])) is None
    assert tick_step(None) is None


def test_a_descending_axis_gives_a_negative_step():
    """Reported rather than corrected: the callers' own validity checks
    reject a step that is not positive, and which of them should is theirs to
    decide -- a scatter declines both its axes together where a rug declines
    only the one its observations lie along."""
    assert tick_step(np.array([6.0, 4.0, 2.0])) == -2.0
