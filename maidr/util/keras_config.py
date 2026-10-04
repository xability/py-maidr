"""Read the layer graph of a Keras model from its config, without Keras.

A Keras model's config -- what ``model.get_config()`` returns, and what
``model.to_json()`` and the ``TensorBoard`` callback write -- lists its
layers and, for a functional model, which layer's output each one is called
on. That is the whole graph, so it is read from there and Keras is never
imported: a model saved as JSON, or logged to TensorBoard, is drawn on a
machine without it.

Both config formats are read. Keras 3 writes a layer's inputs as
``inbound_nodes = [{"args": [...], "kwargs": {...}}]``, each tensor a
``__keras_tensor__`` whose ``keras_history`` is ``[layer, node, tensor]``;
Keras 2 writes ``inbound_nodes = [[[layer, node, tensor, kwargs], ...]]``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any

__all__ = ["keras_config", "keras_graph"]

#: The class names of a model, whose layers form a graph of their own.
_MODELS = {"Functional", "Model", "Sequential"}
_INPUT_LAYER = "InputLayer"

#: Config keys summarised as a node's attributes, and what each is called.
_SUMMARY = (
    ("units", "Units"),
    ("filters", "Filters"),
    ("kernel_size", "Kernel size"),
    ("pool_size", "Pool size"),
    ("strides", "Strides"),
    ("activation", "Activation"),
    ("rate", "Rate"),
)


def keras_config(model: Any) -> dict:
    """
    The config of a Keras model, as ``{"class_name": ..., "config": ...}``.

    Parameters
    ----------
    model : keras.Model, dict or str
        A built Keras model, its ``get_config()`` dictionary, or the JSON
        ``model.to_json()`` returns.

    Returns
    -------
    dict
        The model's class name and its config.

    Raises
    ------
    TypeError
        If ``model`` is none of these, or a model whose config Keras cannot
        give, such as a subclassed model without ``get_config``.
    ValueError
        If ``model`` is a string that is not a model's JSON.
    """
    if isinstance(model, (str, bytes)):
        try:
            model = json.loads(model)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"maidr reads a model's JSON, as model.to_json() writes it: {error}"
            ) from None
    if isinstance(model, Mapping):
        if isinstance(model.get("config"), (Mapping, list)):
            return {"class_name": model.get("class_name"), "config": model["config"]}
        if isinstance(model.get("layers"), list):
            return {"class_name": None, "config": dict(model)}
        raise ValueError(
            "maidr reads a model's config, with its layers; this dictionary "
            "has none."
        )
    if hasattr(model, "get_config") and hasattr(model, "layers"):
        try:
            return keras_config(model.to_json())
        except Exception:  # noqa: BLE001 - Keras raises several types here
            pass
        try:
            config = model.get_config()
        except Exception as error:  # noqa: BLE001
            raise TypeError(
                "maidr reads a model's graph from its config, and Keras could "
                f"not give one for this model: {error}"
            ) from None
        return {"class_name": type(model).__name__, "config": config}
    raise TypeError(
        "maidr draws a Keras model, its get_config() dictionary or its "
        f"to_json() string, not {type(model).__name__}."
    )


def keras_graph(
    model: Any, *, expand_nested: bool = False
) -> tuple[str | None, list[dict]]:
    """
    The layer graph of a Keras model, as the directed graph trace reads it.

    Parameters
    ----------
    model : keras.Model, dict or str
        A built Keras model, its ``get_config()`` dictionary, or the JSON
        ``model.to_json()`` returns.
    expand_nested : bool, default False
        Whether a model used as a layer is drawn as its own layers, in a
        scope named for it, rather than as one node.

    Returns
    -------
    name : str or None
        The model's name, if its config gives one.
    nodes : list of dict
        One per layer, in the config's order: ``id``, ``label``, ``inputs``,
        ``attributes`` and, inside a nested model, ``path``. A layer's id is
        its name, prefixed with the nested models it is in and ``/``.
    """
    config = keras_config(model)
    live = _live_layers(model, []) if not isinstance(model, (str, Mapping)) else {}
    reader = _Reader(expand_nested, live)
    reader.model(config, [], None)
    body = config["config"]
    name = body.get("name") if isinstance(body, Mapping) else None
    return name, reader.nodes


class _Reader:
    """Collects the nodes of a model and of the models nested in it."""

    def __init__(self, expand_nested: bool, live: dict[str, Any]) -> None:
        self.expand_nested = expand_nested
        self.live = live
        self.nodes: list[dict] = []

    def model(
        self, entry: Mapping, path: list[str], feeds: list[list[str]] | None
    ) -> list[list[str]]:
        """
        Add a model's layers; return the node ids behind each of its outputs.

        ``feeds`` are the node ids behind each of a nested model's inputs,
        which stand in for its own input layers; ``None`` at the top, where
        the input layers are nodes.
        """
        body = entry.get("config")
        layers = body if isinstance(body, list) else (body or {}).get("layers", [])
        layers = [layer for layer in layers if isinstance(layer, Mapping)]
        if _is_functional(entry, layers):
            return self._functional(body, layers, path, feeds)
        return self._sequential(layers, path, feeds)

    def _sequential(
        self, layers: list[Mapping], path: list[str], feeds: list[list[str]] | None
    ) -> list[list[str]]:
        previous = [i for feed in feeds for i in feed] if feeds is not None else []
        for layer in layers:
            if _class(layer) == _INPUT_LAYER and feeds is not None:
                continue
            outputs = self._layer(layer, path, previous, [previous])
            previous = [i for output in outputs for i in output]
        return [previous]

    def _functional(
        self,
        body: Mapping,
        layers: list[Mapping],
        path: list[str],
        feeds: list[list[str]] | None,
    ) -> list[list[str]]:
        inputs = [name for name, _ in _refs(body.get("input_layers", []))]
        produced: dict[str, list[list[str]]] = {}

        def resolve(name: str, tensor: int) -> list[str]:
            outputs = produced.get(name, [])
            if not outputs:
                return []
            return outputs[tensor] if tensor < len(outputs) else outputs[0]

        calls = []
        for layer in layers:
            name = _name(layer)
            refs = list(_refs(layer.get("inbound_nodes", [])))
            if _class(layer) == _INPUT_LAYER and feeds is not None:
                at = inputs.index(name) if name in inputs else -1
                produced[name] = [feeds[at] if 0 <= at < len(feeds) else []]
                continue
            sources = [resolve(source, tensor) for source, tensor in refs]
            flat = list(dict.fromkeys(i for ids in sources for i in ids))
            start = len(self.nodes)
            produced[name] = self._layer(layer, path, flat, sources)
            calls.append((refs, flat, start, len(self.nodes)))
        # A layer called again on a later layer's output -- a shared or tied
        # layer -- names a source that was not read yet on the first pass;
        # now that every output is known, its nodes that take input from
        # outside the call gain the sources they missed.
        for refs, flat, start, end in calls:
            late = [
                i
                for source, tensor in refs
                for i in resolve(source, tensor)
                if i not in flat
            ]
            if not late:
                continue
            inside = {node["id"] for node in self.nodes[start:end]}
            for node in self.nodes[start:end]:
                if not inside.intersection(node["inputs"]):
                    node["inputs"] = list(dict.fromkeys([*node["inputs"], *late]))
        return [
            resolve(name, tensor)
            for name, tensor in _refs(body.get("output_layers", []))
        ]

    def _layer(
        self,
        layer: Mapping,
        path: list[str],
        inputs: list[str],
        feeds: list[list[str]],
    ) -> list[list[str]]:
        """Add one layer, or a nested model's layers; return its outputs."""
        name = _name(layer)
        if _is_model(layer) and self.expand_nested:
            return self.model(layer, [*path, name], feeds)
        node_id = "/".join([*path, name])
        attributes: dict[str, object] = {"Layer type": _class(layer) or "Layer"}
        attributes.update(_summary(layer))
        attributes.update(_live_summary(self.live.get(node_id)))
        node: dict = {"id": node_id, "label": name}
        if path:
            node["path"] = list(path)
        node["inputs"] = list(dict.fromkeys(inputs))
        node["attributes"] = attributes
        self.nodes.append(node)
        return [[node_id]]


def _is_functional(entry: Mapping, layers: list[Mapping]) -> bool:
    """A model whose layers say what they are called on, rather than a stack."""
    if _class(entry) == "Sequential":
        return False
    if _class(entry) in ("Functional", "Model"):
        return True
    return any("inbound_nodes" in layer for layer in layers)


def _is_model(layer: Mapping) -> bool:
    config = layer.get("config")
    return _class(layer) in _MODELS or (
        isinstance(config, Mapping) and isinstance(config.get("layers"), list)
    )


def _class(entry: Mapping) -> str | None:
    name = entry.get("class_name")
    return str(name) if name is not None else None


def _name(layer: Mapping) -> str:
    """A layer's name: Keras 3 and 2 both write it beside the config and in it."""
    config = layer.get("config")
    name = layer.get("name")
    if name is None and isinstance(config, Mapping):
        name = config.get("name")
    return str(name if name is not None else _class(layer) or "layer")


def _refs(value: Any) -> Iterator[tuple[str, int]]:
    """
    Every tensor a structure names, as ``(layer, tensor index)``, in order.

    A Keras 3 tensor is ``{"class_name": "__keras_tensor__", "config":
    {"keras_history": [layer, node, tensor]}}``; a Keras 2 one, and an entry
    of ``input_layers`` or ``output_layers``, is ``[layer, node, tensor,
    ...]``. Either may be nested in lists and dictionaries.
    """
    if isinstance(value, Mapping):
        if value.get("class_name") == "__keras_tensor__":
            history = (value.get("config") or {}).get("keras_history")
            if _is_history(history):
                yield str(history[0]), int(history[2])
            return
        for item in value.values():
            yield from _refs(item)
    elif isinstance(value, (list, tuple)):
        if _is_history(value):
            yield str(value[0]), int(value[2])
            return
        for item in value:
            yield from _refs(item)


def _is_history(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 3
        and isinstance(value[0], str)
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value[1:3])
    )


def _summary(layer: Mapping) -> dict[str, object]:
    """A few of a layer's settings, where its config has them."""
    config = layer.get("config")
    if not isinstance(config, Mapping):
        return {}
    summary: dict[str, object] = {}
    if _class(layer) == _INPUT_LAYER:
        # What an input layer outputs is the batch it is declared with.
        shape = config.get("batch_shape", config.get("batch_input_shape"))
        if isinstance(shape, (list, tuple)):
            summary["Output shape"] = _shape(shape)
    if _is_model(layer):
        layers = config.get("layers", [])
        summary["Layers"] = sum(
            1
            for inner in layers
            if isinstance(inner, Mapping) and _class(inner) != _INPUT_LAYER
        )
    for key, label in _SUMMARY:
        value = config.get(key)
        if key == "activation" and value == "linear":
            continue
        if isinstance(value, (list, tuple)) and all(isinstance(v, int) for v in value):
            value = "x".join(str(v) for v in value)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            summary[label] = value
    return summary


def _shape(shape: Any) -> str:
    """A shape as Keras prints it, ``None`` for the batch: ``(None, 8)``."""
    return str(tuple(None if size is None else size for size in shape))


def _live_layers(model: Any, path: list[str]) -> dict[str, Any]:
    """A built model's layers by node id, the nested models' among them."""
    found: dict[str, Any] = {}
    try:
        layers = list(model.layers)
    except Exception:  # noqa: BLE001 - only a built model has them
        return found
    for layer in layers:
        name = str(getattr(layer, "name", ""))
        found["/".join([*path, name])] = layer
        if hasattr(layer, "layers") and hasattr(layer, "get_config"):
            found.update(_live_layers(layer, [*path, name]))
    return found


def _live_summary(layer: Any) -> dict[str, object]:
    """What a built layer knows and its config does not: shape and size."""
    if layer is None:
        return {}
    summary: dict[str, object] = {}
    try:
        summary["Output shape"] = _shape(layer.output.shape)
    except Exception:  # noqa: BLE001 - a layer called twice has no one output
        pass
    try:
        summary["Parameters"] = int(layer.count_params())
    except Exception:  # noqa: BLE001 - an unbuilt layer cannot count them
        pass
    return summary
