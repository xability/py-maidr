"""Fixtures for the browser tests: a running Shiny app and a real browser,
and maidr's files on jsDelivr for a page pinned to a release of it.

These are the only tests that check the thing the library actually
promises -- that a chart can be reached and driven from the keyboard.
Everything else in the suite asserts on emitted markup, which cannot tell
a working chart from a well-formed one.

Skipped unless ``--run-browser`` is given, and skipped anyway when
Playwright or a browser binary is missing, so a contributor without
either sees no failures.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

APPS = Path(__file__).parent / "apps"

#: The last maidr.js without what a chart written into a Quarto page carries
#: copies of (``maidr.util.inline_chart.COPIES_SHIPPED_IN``). A render pinned
#: to it carries them, and the Quarto tests run on it as well as on the
#: bundled maidr.js, which does not need them.
OLDER_MAIDR_JS = "4.14.0"

#: Where a render pinned to a release loads maidr.js and its locale packs.
JSDELIVR = "https://cdn.jsdelivr.net/npm/maidr@"

#: How long to wait for uvicorn to bind, and for the ~1.9 MB bundle to
#: load and parse in the frame. Generous on purpose: a CI runner is
#: slower than a laptop, and a flaky browser test is worse than none.
_BOOT_TIMEOUT = 90.0
_SETTLE_MS = 12_000


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _chromium_path() -> str | None:
    """Find a Chromium that Playwright can drive, without downloading one.

    Playwright pins an exact build and refuses anything else, so an
    environment that ships its own browser needs ``executable_path``.
    Returns ``None`` when nothing usable is present, which is a skip
    rather than a failure.
    """
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if root and Path(root).is_dir():
        for pattern in ("chromium-*/chrome-linux/chrome", "chromium-*/chrome-mac/*"):
            found = sorted(Path(root).glob(pattern))
            if found:
                return str(found[-1])
    return shutil.which("chromium") or shutil.which("chromium-browser")


@pytest.fixture(scope="session")
def browser():
    """A Playwright Chromium, or a skip if none can be driven."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright is not installed"
    ).sync_playwright

    with sync_playwright() as p:
        launch: dict = {"args": ["--no-sandbox"]}
        exe = _chromium_path()
        if exe:
            launch["executable_path"] = exe
        try:
            b = p.chromium.launch(**launch)
        except Exception as error:  # pragma: no cover - environment dependent
            pytest.skip(f"could not launch Chromium: {error}")
        yield b
        b.close()


def _serve(app: str, *, runner: str = "shiny"):
    """Run one of ``apps/`` and yield its URL, then stop it.

    ``runner`` picks the framework's own launcher, so the app is served
    the way a user serves it rather than through a test harness.
    """
    pytest.importorskip(runner)
    port = _free_port()
    env = {
        **os.environ,
        # Building a CDN URL would resolve the published version over the
        # network; these tests use the bundled copy and must not need one.
        "MAIDR_CDN_VERSION": "latest",
        "MPLBACKEND": "Agg",
    }
    if runner == "streamlit":
        command = [
            sys.executable, "-m", "streamlit", "run", str(APPS / app),
            "--server.port", str(port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ]
    elif runner == "gradio":
        # A Gradio app is a script that calls ``launch()``; the port is the
        # one ``GRADIO_SERVER_PORT`` names, which ``launch()`` reads.
        command = [sys.executable, str(APPS / app)]
        env["GRADIO_SERVER_PORT"] = str(port)
        env["GRADIO_ANALYTICS_ENABLED"] = "False"
    else:
        command = [
            sys.executable, "-m", "shiny", "run", "--port", str(port), str(APPS / app)
        ]

    # A file rather than a pipe, and nobody has to drain it. A pipe holds
    # about 64 KB before the writer blocks, and nothing here reads it
    # until the app exits -- so a chatty enough server (Streamlit's access
    # logs, several re-renders per test) would wedge on write and the
    # fixture would hang rather than fail, which is the worst way for a
    # CI job to go wrong.
    log = tempfile.NamedTemporaryFile(  # noqa: SIM115 - closed in `finally`
        mode="w+", suffix=".log", prefix=f"{app}.", delete=False
    )
    proc = subprocess.Popen(
        command, stdout=log, stderr=subprocess.STDOUT, env=env, text=True
    )

    def _output() -> str:
        log.flush()
        log.seek(0)
        return log.read()[-4000:]

    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + _BOOT_TIMEOUT
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"the app exited early:\n{_output()}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        else:  # pragma: no cover - only on a very slow machine
            pytest.fail(f"the app did not start within {_BOOT_TIMEOUT}s:\n{_output()}")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
        log.close()
        os.unlink(log.name)


@pytest.fixture(scope="session")
def focus_app_url():
    """The app used by the focus-restore tests."""
    yield from _serve("focus_app.py")


@pytest.fixture(scope="session")
def offline_app_url():
    """The app used by the offline-report test, on the default ``use_cdn``."""
    yield from _serve("offline_app.py")


@pytest.fixture(scope="session")
def module_app_url():
    """Two instances of a module that each render a chart."""
    yield from _serve("module_app.py")


@pytest.fixture(scope="session")
def two_charts_app_url():
    """Two charts, both re-rendering, for the isolation test."""
    yield from _serve("two_charts_app.py")


#: Where ``apps/served_bundle_app.py`` mounts its Shiny app; kept in step
#: with the ``PREFIX`` there.
SERVED_BUNDLE_PREFIX = "/deep/prefix"


@pytest.fixture(scope="session")
def served_bundle_app_url():
    """Two offline charts mounted under a prefix, for the served-bundle tests.

    Yields the page's own URL, prefix and trailing slash included: Shiny
    resolves its routes and dependencies against it, so the slash is part
    of the address rather than decoration.
    """
    for url in _serve("served_bundle_app.py"):
        yield f"{url}{SERVED_BUNDLE_PREFIX}/"


@pytest.fixture(scope="session")
def streamlit_keys_app_url():
    """A Streamlit app with a rerun counter, for the key-collision test."""
    yield from _serve("streamlit_keys_app.py", runner="streamlit")


@pytest.fixture(scope="session")
def streamlit_rerun_app_url():
    """An uncached Streamlit chart beside two checkboxes, for the rerun test."""
    yield from _serve("streamlit_rerun_app.py", runner="streamlit")


@pytest.fixture(scope="session")
def gradio_app_url():
    """A Gradio app with a chart built with it and one a slider replaces."""
    yield from _serve("gradio_app.py", runner="gradio")


@pytest.fixture
def page(browser, focus_app_url):
    """A page with the chart loaded and its runtime up."""
    pg = browser.new_page()
    pg.goto(focus_app_url, wait_until="networkidle")
    pg.wait_for_timeout(_SETTLE_MS)
    yield pg
    pg.close()


class JsDelivr:
    """maidr's files on jsDelivr, fetched by Python and handed to a page.

    A render pinned to a release loads it from jsDelivr. Python fetches each
    file a page asks for, once a session, and the page is given it, so the
    browser needs no network, or proxy, of its own.
    """

    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    def fetch(self, url: str) -> bytes:
        """The file at ``url``, fetched the first time it is asked for."""
        if url not in self._files:
            with urllib.request.urlopen(url, timeout=60) as response:
                self._files[url] = response.read()
        return self._files[url]

    def serve(self, page) -> None:
        """Answer the page's requests for maidr's files on jsDelivr."""

        def fulfil(route) -> None:
            url = route.request.url
            try:
                body = self.fetch(url)
            except OSError:
                route.abort()
                return
            content_type = mimetypes.guess_type(url.split("?")[0])[0]
            if content_type is None:
                content_type = "application/octet-stream"
            elif content_type.startswith("text/"):
                # As jsDelivr says: the bundle is UTF-8, which a page that
                # names no charset would not read it as.
                content_type += "; charset=utf-8"
            route.fulfill(
                status=200,
                body=body,
                content_type=content_type,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        page.route(f"{JSDELIVR}*/**", fulfil)


@pytest.fixture(scope="session")
def jsdelivr() -> JsDelivr:
    """maidr's files on jsDelivr, or a skip when :data:`OLDER_MAIDR_JS` cannot be had."""
    cdn = JsDelivr()
    try:
        cdn.fetch(f"{JSDELIVR}{OLDER_MAIDR_JS}/dist/maidr.js")
    except OSError as error:
        pytest.skip(f"maidr@{OLDER_MAIDR_JS} could not be fetched: {error}")
    return cdn
