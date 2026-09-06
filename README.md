<div align="center">

<img src="https://raw.githubusercontent.com/xability/maidr/refs/heads/main/docs/logo.svg" width="350px" alt="A stylized MAIDR logo, with curved characters for M A, a hand pointing for an I, the D character, and R represented in braille."/>

<hr style="color:transparent" />
<br />

[![PyPI](https://img.shields.io/pypi/v/maidr.svg)](https://pypi.org/project/maidr/)
[![Python versions](https://img.shields.io/pypi/pyversions/maidr.svg)](https://pypi.org/project/maidr/)
[![Downloads](https://img.shields.io/pepy/dt/maidr.svg)](https://pepy.tech/project/maidr)
[![CI](https://github.com/xability/py-maidr/actions/workflows/ci.yml/badge.svg)](https://github.com/xability/py-maidr/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/maidr.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-py.maidr.ai-1f6feb.svg)](https://py.maidr.ai/)

</div>

# py-maidr

Make matplotlib, seaborn, Plotly, and Altair charts accessible — MAIDR
(Multimodal Access and Interactive Data Representation) for Python.

## Overview

py-maidr makes data visualizations accessible to blind and low-vision readers.
`import maidr` and your existing plotting code renders an interactive figure that
can be **navigated by keyboard**, **heard as sonification**, **read on a braille
display**, and **described as text** — the same chart in four modalities instead
of one.

Nothing about how you plot changes. py-maidr patches matplotlib and seaborn at
import time, so `plt.show()` produces accessible HTML instead of a static image;
Plotly and Altair figures go through the same `maidr.show()` entry point. It
works in a plain script, a Jupyter notebook, Quarto, Shiny, and Streamlit.

## Quickstart

```python
import matplotlib.pyplot as plt
import seaborn as sns

import maidr  # the whole integration

penguins = sns.load_dataset("penguins")

fig, ax = plt.subplots()
sns.barplot(x="species", y="body_mass_g", data=penguins, ax=ax)

maidr.show(fig)
```

`maidr.save_html(fig, "penguins.html")` writes the same plot to a standalone HTML
file instead of displaying it. Because importing `maidr` also activates its
matplotlib backend, a plain `plt.show()` renders accessible output too.

## What is supported

| | |
|---|---|
| **Plotting libraries** | matplotlib, seaborn (including `seaborn.objects`), Plotly, Altair — plus mplfinance for financial charts (candlestick, volume, moving averages) |
| **Environments** | Python scripts, Jupyter, Quarto, Shiny for Python, Streamlit |
| **Plot types** | 38 — see [Plot Type Stability](https://py.maidr.ai/stability.html) for which fifteen are settled and which twenty-three are experimental |

Plot types not yet supported fall back to a static image with a warning, so a
plot is never lost.

## Keyboard shortcuts

Press **Tab** (or click) to focus a rendered plot, move between data points with the **arrow keys**, and toggle **B** braille, **T** text, **S** sonification, and **R** review mode. Four global shortcuts open maidr's own interfaces:

| Action | Windows / Linux | macOS |
|---|---|---|
| Show or hide the keyboard shortcut help | Ctrl + / | Command + / |
| Open the command palette listing every available command | Ctrl + Shift + P | Command + Shift + P |
| Open the AI chat (requires your own API key, entered in Settings, or a local Ollama server) | Shift + / (that is, **?**) | Shift + / (**?**) |
| Open Settings | Ctrl + , | Command + , |

The full list, including autoplay, label announcements, and layer switching, is in the [maidr controls documentation](https://maidr.ai/docs/CONTROLS.html).

## Install and Upgrade

```sh
# install the latest release from PyPI
pip install -U maidr
```

```sh
# or install the development version from GitHub
pip install -U git+https://github.com/xability/py-maidr.git
```

## User Guide

Please visit the [user guide](https://py.maidr.ai/) page.

## Offline and Restricted-Network Use

py-maidr loads its JavaScript from a CDN by default, and resolves the current published version so browsers cannot serve a stale cached copy. That costs one bounded outbound request, the first time a plot is rendered. `import maidr` itself makes no request.

If you work air-gapped, behind a proxy, or in CI:

```sh
export MAIDR_CDN_VERSION=bundled  # serve the version in this wheel, no lookup
export MAIDR_USE_CDN=false        # or skip the CDN entirely
```

`bundled` is usually the best choice for restricted networks: it emits an immutable
CDN URL — so browser caching still works correctly — without contacting anything.
It is also the only one of the two that covers **Altair** charts: the Altair adapter
has no offline path and always references the CDN, so `MAIDR_USE_CDN=false` does not
apply to it, while `MAIDR_CDN_VERSION=bundled` still removes the lookup.

See [Offline Use and the JavaScript Bundle](https://py.maidr.ai/#offline-use-and-the-javascript-bundle) for the full set of options.


## Example Code

We provide [some example code](https://github.com/xability/py-maidr/blob/main/example) for using py-maidr with matplotlib, seaborn, Jupyter Notebook, Quarto, Shiny, and Streamlit.

Shiny support requires the optional extra `pip install "maidr[shiny]"`, which
provides `output_maidr()` and `@render_maidr` in `maidr.widget.shiny`.
Streamlit support requires `pip install "maidr[streamlit]"`, which provides
`render_maidr()` and `maidr_html()` in `maidr.widget.streamlit`.

## Using with AI coding agents

If an AI coding agent (Claude Code, Codex, Cursor, GitHub Copilot, and others) writes your plotting code, install the
[maidr skill](https://github.com/xability/maidr-skill) with `npx skills add xability/maidr-skill`. The agent then
routes every matplotlib, seaborn, Plotly, or Altair chart through py-maidr, verifies the output, and hands back an
accessible HTML file or chat artifact instead of a static image.

## Contributing

Bug reports, plot types and documentation fixes are all welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a development environment
and shape a change, and [CONDUCT.md](CONDUCT.md) for our code of conduct.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
