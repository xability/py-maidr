"""Tests for the document-order pass a walked-out-of-draw-order layer needs.

The frontend pairs data index k with the k-th element a positional selector
resolves to, in document order. :func:`maidr.core.maidr._order_tagged_groups`
moves a layer's tagged groups into the order of its elements when a layer
asks for it, and leaves the document alone whenever it cannot do that
without guessing.
"""

from __future__ import annotations

from lxml import etree

from maidr.core.maidr import _order_tagged_groups


class _Artist:
    """The one method of an artist the pass reads."""

    def __init__(self, gid: str) -> None:
        self._gid = gid

    def get_gid(self) -> str:
        return self._gid


def _svg(*groups: str) -> etree._Element:
    body = "".join(f'<g id="{gid}" maidr="s"><path/></g>' for gid in groups)
    return etree.fromstring(
        f'<svg xmlns="http://www.w3.org/2000/svg"><g id="axes">'
        f'<g id="patch_1"><path/></g>{body}<g id="text_1"><path/></g>'
        f"</g></svg>".encode()
    )


def _ids(root: etree._Element) -> list[str]:
    return [child.get("id") for child in root.xpath('//*[@id="axes"]')[0]]


class TestReordering:
    def test_groups_follow_the_elements(self):
        root = _svg("a", "b", "c")

        _order_tagged_groups(root, "s", [_Artist("c"), _Artist("b"), _Artist("a")])

        assert _ids(root) == ["patch_1", "c", "b", "a", "text_1"]

    def test_only_the_layers_own_slots_are_used(self):
        # The groups take one another's places: an artist drawn before or
        # after the layer stays where it was.
        root = _svg("a", "b")
        axes = root.xpath('//*[@id="axes"]')[0]
        axes.insert(2, etree.fromstring('<g id="between"><path/></g>'))

        _order_tagged_groups(root, "s", [_Artist("b"), _Artist("a")])

        assert _ids(root) == ["patch_1", "b", "between", "a", "text_1"]

    def test_no_placeholder_is_left_behind(self):
        root = _svg("a", "b")

        _order_tagged_groups(root, "s", [_Artist("b"), _Artist("a")])

        assert not root.xpath("//comment()")

    def test_an_already_ordered_layer_is_untouched(self):
        root = _svg("a", "b")
        before = etree.tostring(root)

        _order_tagged_groups(root, "s", [_Artist("a"), _Artist("b")])

        assert etree.tostring(root) == before


class TestLeftAsDrawn:
    """A match that is not one to one is not acted on."""

    def test_a_missing_group(self):
        root = _svg("a", "b")

        _order_tagged_groups(root, "s", [_Artist("c"), _Artist("b"), _Artist("a")])

        assert _ids(root) == ["patch_1", "a", "b", "text_1"]

    def test_an_artist_that_was_not_drawn(self):
        root = _svg("a", "b")

        _order_tagged_groups(root, "s", [_Artist("x"), _Artist("a")])

        assert _ids(root) == ["patch_1", "a", "b", "text_1"]

    def test_a_shared_gid(self):
        # A user's own gid is kept verbatim on every artist it was set on
        # (#753), so two groups can carry the same id; which is which is
        # then unknowable and the document is left alone.
        root = _svg("same", "same")

        _order_tagged_groups(root, "s", [_Artist("same"), _Artist("same")])

        assert _ids(root) == ["patch_1", "same", "same", "text_1"]

    def test_another_layers_groups_are_not_touched(self):
        root = etree.fromstring(
            b'<svg xmlns="http://www.w3.org/2000/svg"><g id="axes">'
            b'<g id="a" maidr="s"><path/></g><g id="b" maidr="s"><path/></g>'
            b'<g id="c" maidr="t"><path/></g><g id="d" maidr="t"><path/></g>'
            b"</g></svg>"
        )

        _order_tagged_groups(root, "s", [_Artist("b"), _Artist("a")])

        assert _ids(root) == ["b", "a", "c", "d"]
