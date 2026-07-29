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

py-maidr loads its JavaScript from a CDN by default, and resolves the current published version once per process so browsers cannot serve a stale cached copy. That means one bounded outbound request the first time a plot is rendered (or on `import maidr` in a notebook).

If you work air-gapped, behind a proxy, or in CI:

```python
maidr.save_html(plot, "out.html", use_cdn=False)  # bundled copy, no network at all
```

```sh
export MAIDR_CDN_VERSION=latest   # keep the CDN, skip the version lookup
```

See [Offline Use and the JavaScript Bundle](https://xability.github.io/py-maidr/#offline-use-and-the-javascript-bundle) for the full set of options.


## Example Code

We provide [some example code](https://github.com/xability/py-maidr/blob/main/example) for using py-maidr with matplotlib, seaborn, Jupyter Notebook, Quarto, Shiny, and Streamlit.
