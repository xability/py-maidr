from __future__ import annotations

import contextlib
import contextvars
import threading

import wrapt

from maidr.core.plot.boxplot import BoxPlotContainer


class ContextManager:
    _instance = None
    _lock = threading.Lock()

    _internal_context = contextvars.ContextVar("internal_context", default=False)

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ContextManager, cls).__new__()
        return cls._instance

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
    _instance = None
    _lock = threading.Lock()

    elements = {}
    elements_to_highlight = []
    selector_ids = []

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(HighlightContextManager, cls).__new__()
        return cls._instance

    @classmethod
    def is_maidr_element(cls, id):
        return id in cls.elements

    @classmethod
    def get_selector_id(cls, id):
        return cls.elements[id]

    @classmethod
    @contextlib.contextmanager
    def set_maidr_element(cls, element, id):
        if element not in cls.elements_to_highlight:
            yield
            return

        try:
            cls.elements[id] = cls.selector_ids[
                cls.elements_to_highlight.index(element)
            ]
            yield
        finally:
            del cls.elements[id]

    @classmethod
    @contextlib.contextmanager
    def set_maidr_elements(cls, elements: list, selector_ids: list):
        cls.elements_to_highlight = elements
        cls.selector_ids = selector_ids
        try:
            yield
        finally:
            cls.elements_to_highlight.clear()
