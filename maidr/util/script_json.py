"""JSON for a JavaScript literal inside an HTML ``<script>`` element."""

from __future__ import annotations

import json
from typing import Any


def script_json(value: Any) -> str:
    """
    Serialize ``value`` for a JS literal inside an HTML ``<script>``.

    ``<``, ``>`` and ``&`` are written as JSON ``\\u`` escapes, as Jinja's
    ``htmlsafe_json_dumps`` writes them, so no text the caller supplies -- a
    title reading ``</script>``, or ``<!--<script>``, which would otherwise
    put the HTML parser in a state where the real end tag no longer closes
    the element -- can be read as markup. U+2028/U+2029 are escaped because
    JSON allows them where a JS string literal did not until ES2019.

    Parameters
    ----------
    value : Any
        A JSON-serializable value.

    Returns
    -------
    str
        The JSON, with no character the HTML tokenizer acts on.
    """
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
