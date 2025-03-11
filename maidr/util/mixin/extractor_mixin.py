from __future__ import annotations

from typing import Any

from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey


class ContainerExtractorMixin:
    @staticmethod
    def extract_container(
        ax: Axes,
        container_type: type,
        include_all: bool = False,
    ) -> Any:
        """Retrieve containers of a specified type from an Axes object."""
        if ax is None or ax.containers is None:
            return None

        # If include_all is True, return a list of all containers of the specified type.
        if include_all:
            return [
                container
                for container in ax.containers
                if isinstance(container, container_type)
            ]

        # Otherwise, return the first container of the specified type.
        return next(
            container
            for container in ax.containers
            if isinstance(container, container_type)
        )


class LevelExtractorMixin:
    @staticmethod
    def extract_level(ax: Axes, key: MaidrKey = MaidrKey.X) -> list[str] | None:
        """Retrieve label texts from Axes based on the specified Maidr key."""
        if ax is None:
            return None

        level = None
        if MaidrKey.X == key:
            level = [label.get_text() for label in ax.get_xticklabels()]
        elif MaidrKey.Y == key:
            level = [label.get_text() for label in ax.get_yticklabels()]
        elif MaidrKey.FILL == key:
            level = [container.get_label() for container in ax.containers]

        return level


class LineExtractorMixin:
    @staticmethod
    def extract_line(ax: Axes) -> Line2D | None:
        """Retrieve the last line object from Axes, if available."""
        if ax is None or ax.get_lines() is None:
            return None

        # Since the upstream MaidrJS library currently supports only the last plot line,
        # `maidr` package supports the same.
        return ax.get_lines()[-1]

    @staticmethod
    def extract_lines(ax: Axes) -> list[Line2D] | None:
        """Retrieve all line objects from Axes, if available."""
        if ax is None or ax.get_lines() is None:
            return None

        # Since the upstream MaidrJS library currently supports only the last plot line,
        # `maidr` package supports the same.
        return ax.get_lines()


class CollectionExtractorMixin:
    @staticmethod
    def extract_collection(ax: Axes, collection_type: type) -> Any:
        """Retrieve the first collection of a specified type from an Axes object."""
        if ax is None or ax.collections is None:
            return None

        # We assume only one collection of each type is present to avoid plot clutter,
        # even though multiples are technically possible.
        return next(
            collection
            for collection in ax.collections
            if isinstance(collection, collection_type)
        )


class ScalarMappableExtractorMixin:
    @staticmethod
    def extract_scalar_mappable(ax: Axes) -> ScalarMappable | None:
        """Retrieve the first collection ScalarMappable from an Axes object."""
        if ax is None or ax.get_children() is None:
            return None

        # We assume only one ScalarMappable is present to avoid plot clutter,
        # even though multiples are technically possible.
        return next(sm for sm in ax.get_children() if isinstance(sm, ScalarMappable))
