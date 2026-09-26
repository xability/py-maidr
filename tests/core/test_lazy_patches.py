"""The seaborn patches wait for seaborn to be imported.

``import maidr`` used to import seaborn (~0.8 s) just to wrap it, so a script
that only ever draws with matplotlib paid for it. The patches are now applied
from ``wrapt.when_imported`` hooks, which fire at once when the library is
already loaded and at the end of its import otherwise.

That is only a saving if it changes nothing else, so the reading is checked
in both import orders: whichever comes first, the same names end up wrapped
and a seaborn call registers the same layer types. Every check runs in a
fresh interpreter, because by the time any test here runs the suite has
already imported both libraries into this one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

_ENV = {**os.environ, "MPLBACKEND": "Agg", "MAIDR_CDN_VERSION": "latest"}


def _run(code: str, *, extra_path: str | None = None) -> subprocess.CompletedProcess:
    env = dict(_ENV)
    if extra_path is not None:
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (extra_path, env.get("PYTHONPATH")) if p
        )
    return subprocess.run(
        [sys.executable, "-W", "ignore", "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_importing_maidr_alone_loads_neither_seaborn_nor_scipy():
    """The whole point: a matplotlib-only process does not pay for them.

    scipy is only needed to extract a violin's density curve, so it is
    imported there rather than by ``import maidr``.
    """
    result = _run(
        """
        import json, sys
        import maidr
        print(json.dumps({
            name: name in sys.modules
            for name in ("seaborn", "scipy")
        }))
        """
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == {
        "seaborn": False,
        "scipy": False,
    }


_READ_THE_SEABORN_PATCHES = """
import json, sys
{imports}
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import wrapt
import seaborn.categorical
import seaborn.distributions
import seaborn._core.plot
from maidr.core.figure_manager import FigureManager

def wrapped(obj):
    return isinstance(obj, wrapt.ObjectProxy)

bindings = {{
    "seaborn.histplot": wrapped(seaborn.histplot),
    "seaborn.distributions.histplot": wrapped(seaborn.distributions.histplot),
    "seaborn.barplot": wrapped(seaborn.barplot),
    "_CategoricalPlotter.plot_bars": wrapped(
        seaborn.categorical._CategoricalPlotter.__dict__["plot_bars"]
    ),
    "_DistributionPlotter.plot_univariate_histogram": wrapped(
        seaborn.distributions._DistributionPlotter.__dict__[
            "plot_univariate_histogram"
        ]
    ),
    "seaborn.categorical._default_color": wrapped(
        seaborn.categorical._default_color
    ),
    "Plotter._plot_layer": wrapped(
        seaborn._core.plot.Plotter.__dict__["_plot_layer"]
    ),
}}

df = pd.DataFrame({{
    "g": ["a", "b", "c"] * 4,
    "h": ["x", "y"] * 6,
    "v": np.arange(12.0),
}})
layers = {{}}
for name, draw in {{
    "histplot": lambda ax: seaborn.histplot(df, x="v", hue="h", ax=ax),
    "barplot": lambda ax: seaborn.barplot(df, x="g", y="v", ax=ax, errorbar=None),
    "violinplot": lambda ax: seaborn.violinplot(df, x="g", y="v", ax=ax),
}}.items():
    fig, ax = plt.subplots()
    draw(ax)
    layers[name] = [p.type.value for p in FigureManager.get_maidr(fig).plots]
    plt.close(fig)

print(json.dumps({{"bindings": bindings, "layers": layers}}))
"""


def _read(imports: str) -> dict:
    result = _run(_READ_THE_SEABORN_PATCHES.format(imports=imports))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def seaborn_first() -> dict:
    return _read("import seaborn\nimport maidr")


@pytest.fixture(scope="module")
def maidr_first() -> dict:
    return _read("import maidr\nassert 'seaborn' not in sys.modules\nimport seaborn")


@pytest.mark.parametrize("order", ["seaborn_first", "maidr_first"])
def test_every_seaborn_binding_is_wrapped_whichever_is_imported_first(
    order, request
):
    bindings = request.getfixturevalue(order)["bindings"]
    assert bindings == {name: True for name in bindings}


@pytest.mark.parametrize("order", ["seaborn_first", "maidr_first"])
def test_a_seaborn_call_registers_as_seaborn_whichever_is_imported_first(
    order, request
):
    """Read as seaborn, not merely as the artists matplotlib was handed.

    A hue split ``histplot`` is the sharpest test of it: without the seaborn
    patch it arrives as bars, not as ``hist``.
    """
    layers = request.getfixturevalue(order)["layers"]
    assert layers == {
        "histplot": ["hist", "hist"],
        "barplot": ["bar"],
        "violinplot": ["violin_box", "violin_kde"],
    }


def test_both_orders_read_the_same(seaborn_first, maidr_first):
    assert seaborn_first == maidr_first


@pytest.mark.parametrize(
    "imports, raised_by",
    [
        pytest.param("import seaborn\nimport maidr", "import maidr", id="seaborn_first"),
        pytest.param("import maidr\nimport seaborn", "import seaborn", id="maidr_first"),
    ],
)
def test_an_old_seaborn_still_fails_readably(tmp_path, imports, raised_by):
    """#441's readable ImportError survives the patches being deferred.

    With seaborn imported first it comes out of ``import maidr``, as it always
    did. With maidr first it comes out of ``import seaborn`` -- the first
    moment the patches could be attempted -- and still before any of them is.
    A stand-in package plays the old seaborn, since the suite cannot install
    one.
    """
    fake = tmp_path / "seaborn"
    fake.mkdir()
    (fake / "__init__.py").write_text('__version__ = "0.12.2"\n')

    lines = imports.splitlines()
    result = _run(
        f"""
        {lines[0]}
        try:
            {lines[1]}
        except ImportError as error:
            print("RAISED", str(error))
        else:
            print("PASSED")
        """,
        extra_path=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout.strip().splitlines()[-1]
    assert out.startswith("RAISED"), f"{raised_by} did not raise: {out}"
    assert "0.12.2" in out and "seaborn >= 0.13" in out and "pip install" in out
