"""`grouped_by_name` is the tail every hue split ends in (#599).

Scatter and rug reached the same three decisions -- decline on an unnamed
thing, decline on fewer than two groups, come out in the legend's order -- by
two different routes, one relying on a dict built in legend order and the
other sorting against the legend's texts. Two implementations of one rule is
where drift starts, and the ordering is #502's convention rather than an
incidental.

Asserted directly here as well as through the two callers, because two of the
helper's behaviours are not reachable from either: neither passes an empty
order, and neither can pass a name its order does not mention -- both draw
their names from the same legend they order by.
"""

from __future__ import annotations


from maidr.util.hue_groups import grouped_by_name


def test_it_groups_the_positions_each_name_claims():
    assert grouped_by_name(["b", "a", "b", "a"], ["a", "b"]) == [
        ("a", [1, 3]),
        ("b", [0, 2]),
    ]


def test_the_groups_come_out_in_the_order_given():
    """Not the draw order, which is what #502 settled."""
    drawn = ["z", "y", "x"]

    assert [name for name, _ in grouped_by_name(drawn, ["x", "y", "z"])] == [
        "x",
        "y",
        "z",
    ]
    assert [name for name, _ in grouped_by_name(drawn, ["z", "y", "x"])] == [
        "z",
        "y",
        "x",
    ]


def test_positions_keep_their_drawing_order_within_a_group():
    """The order a group's own members come out in is the order they were
    drawn in, whatever the groups themselves are ordered by."""
    groups = dict(grouped_by_name(["a", "b", "a", "b", "a"], ["b", "a"]))

    assert groups["a"] == [0, 2, 4]
    assert groups["b"] == [1, 3]


def test_a_thing_no_name_claims_declines_the_whole_split():
    """A partly-named chart announces a group called "None" holding the rest.
    Worse than an unnamed one, so the split is declined outright."""
    assert grouped_by_name(["a", None, "b"], ["a", "b"]) is None


def test_one_group_is_not_a_grouping():
    assert grouped_by_name(["a", "a", "a"], ["a"]) is None


def test_nothing_drawn_is_not_a_grouping():
    assert grouped_by_name([], ["a", "b"]) is None


def test_with_no_order_the_groups_keep_the_order_they_first_appear_in():
    """Not reachable from either caller -- both pass their legend's order --
    so the fallback is defined here rather than left to chance."""
    assert grouped_by_name(["b", "a", "b"]) == [("b", [0, 2]), ("a", [1])]


def test_a_name_the_order_does_not_mention_sorts_last():
    """Also unreachable from either caller, for the same reason: each draws
    its names from the legend it orders by. Defined so that a caller reading
    names from somewhere else gets a stated answer rather than an exception --
    which is what `order.index` on a missing name would raise."""
    groups = grouped_by_name(["late", "first", "late"], ["first"])

    assert [name for name, _ in groups] == ["first", "late"]


def test_two_unmentioned_names_keep_their_order_among_themselves():
    groups = grouped_by_name(["b", "a", "known"], ["known"])

    assert [name for name, _ in groups] == ["known", "b", "a"]
