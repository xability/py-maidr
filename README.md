<div align="center">

<img src="https://raw.githubusercontent.com/xability/maidr/refs/heads/main/docs/logo.svg" width="350px" alt="A stylized MAIDR logo, with curved characters for M A, a hand pointing for an I, the D character, and R represented in braille."/>

<hr style="color:transparent" />
<br />
</div>

# py-maidr

Python binder for maidr library

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

Please visit the [user guide](https://xability.github.io/py-maidr/) page.

## Offline and Restricted-Network Use

py-maidr loads its JavaScript from a CDN by default, and resolves the current published version so browsers cannot serve a stale cached copy. That costs one bounded outbound request, the first time a plot is rendered. `import maidr` itself makes no request.

If you work air-gapped, behind a proxy, or in CI:

```sh
export MAIDR_CDN_VERSION=bundled  # serve the version in this wheel, no lookup
export MAIDR_USE_CDN=false        # or skip the CDN entirely
```

`bundled` is usually the best choice for restricted networks: it emits an immutable
CDN URL — so browser caching still works correctly — without contacting anything.

See [Offline Use and the JavaScript Bundle](https://xability.github.io/py-maidr/#offline-use-and-the-javascript-bundle) for the full set of options.


## Example Code

We provide [some example code](https://github.com/xability/py-maidr/blob/main/example) for using py-maidr with matplotlib, seaborn, Jupyter Notebook, Quarto, Shiny, and Streamlit.
