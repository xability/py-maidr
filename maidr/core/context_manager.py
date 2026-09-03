from __future__ import annotations

import contextlib
import contextvars

import wrapt

from maidr.core.plot.boxplot import BoxPlotContainer


class ContextManager:
    _internal_context = contextvars.ContextVar("internal_context", default=False)

    @classmethod
    def is_internal_context(cls):
        return cls._internal_context.get()

    @classmethod
    @contextlib.contextmanager
    def set_internal_context(cls):
        token_internal_context = cls._internal_context.set(True)
        try:
            yield
        finally:
            cls._internal_context.reset(token_internal_context)


@wrapt.decorator
def manage_context(wrapped=None, _=None, args=None, kwargs=None):
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        return wrapped(*args, **kwargs)


class BoxplotContextManager(ContextManager):
    _bxp_context = contextvars.ContextVar("bxp_context", default=BoxPlotContainer())

    @classmethod
    @contextlib.contextmanager
    def set_internal_context(cls):
        with super(BoxplotContextManager, cls).set_internal_context():
            token = cls._bxp_context.set(BoxPlotContainer())
            try:
                yield cls.get_bxp_context()
            finally:
                cls._bxp_context.reset(token)

    @classmethod
    def get_bxp_context(cls) -> BoxPlotContainer:
        return cls._bxp_context.get()

    @classmethod
    def add_bxp_context(cls, bxp_context: dict) -> None:
        cls.get_bxp_context().add_artists(bxp_context)

    @classmethod
    def set_bxp_orientation(cls, orientation: str) -> None:
        cls.get_bxp_context().set_orientation(orientation)


class HighlightContextManager:
    """Carries a render's highlight wiring from extraction to the SVG writer.

    Held in :class:`contextvars.ContextVar`\ s rather than as class
    attributes, matching :class:`ContextManager` above. That is not a style
    choice: the artist ``draw`` methods and ``XMLWriter.start`` are patched
    *class-wide*, so every render in the process reads this state while
    ``savefig`` walks its figure.

    As plain class attributes it was safe only because every render ran
    serialised on one thread. It stopped being safe when the Shiny renderer
    began rendering off the event loop (#504): two **different** figures
    drawing at once would overwrite each other's tagged artists, and
    artists checked after the overwrite would match nothing, so
    ``XMLWriter.start`` never injected their ``maidr`` attribute. Measured
    before the change -- four concurrent renders of distinct figures went
    from 61 selectors each to ``[7, 1, 1, 1]``. A valid SVG, with the
    interactive layer silently gone.

    ``contextvars`` is the right tool rather than a wider lock because a
    render's wiring is genuinely per-render: ``asyncio.to_thread`` runs the
    call in a *copy* of the context, so each render gets its own view and
    concurrent renders of distinct figures stay parallel, which is what
    moving off the loop was for.

    One subtlety worth stating, because it is the way this fix is usually
    got wrong: ``copy_context()`` copies the variable-to-value mapping, not
    the values. A single shared ``dict`` left as a default would still be
    shared through the copy, so :meth:`set_maidr_elements` installs a fresh
    mapping for each render rather than mutating one in place.
    """

    _elements: contextvars.ContextVar[dict] = contextvars.ContextVar(
        "maidr_highlight_elements"
    )
    # Keyed by `id(artist)`, not the artist: `Artist` does not define
    # `__eq__`, so the list `in`/`index` this replaced were identity tests
    # already, and a dict makes each draw a lookup instead of a scan of the
    # whole tagged list -- which made a render quadratic in its artists,
    # 2 s of a 5 s render at 5000 bars (#695). An id cannot be reused
    # mid-render: the figure being drawn owns every artist in the mapping.
    _selector_by_element: contextvars.ContextVar[dict] = contextvars.ContextVar(
        "maidr_selector_by_element"
    )

    @classmethod
    def is_maidr_element(cls, gid):
        return gid in cls._elements.get({})

    @classmethod
    def get_selector_id(cls, gid):
        return cls._elements.get({})[gid]

    @classmethod
    @contextlib.contextmanager
    def set_maidr_element(cls, element, gid):
        # `gid`, not `id` as the neighbours have it: this one needs the
        # builtin to key the lookup.
        selector_id = cls._selector_by_element.get({}).get(id(element))
        if selector_id is None:
            yield
            return

        elements = cls._elements.get({})
        try:
            elements[gid] = selector_id
            yield
        finally:
            del elements[gid]

    @classmethod
    @contextlib.contextmanager
    def set_maidr_elements(cls, elements: list, selector_ids: list):
        # A fresh mapping per render, not a shared one mutated in place:
        # `copy_context()` copies the variable-to-value mapping, so a single
        # dict installed once would still be shared across every concurrent
        # render. See the class docstring.
        #
        # `zip` would silently drop the tail of a mismatched pair, where the
        # old `selector_ids[index]` raised; keep the failure loud.
        if len(elements) != len(selector_ids):
            raise ValueError(
                f"{len(elements)} elements to highlight but "
                f"{len(selector_ids)} selector ids; they must pair one to one"
            )

        # `setdefault` keeps the first selector for an artist listed twice,
        # which is what `list.index` gave and what #376 relies on.
        selector_by_element: dict = {}
        for element, selector_id in zip(elements, selector_ids):
            selector_by_element.setdefault(id(element), selector_id)

        token_elements = cls._elements.set({})
        token_selectors = cls._selector_by_element.set(selector_by_element)
        try:
            yield
        finally:
            cls._elements.reset(token_elements)
            cls._selector_by_element.reset(token_selectors)
