"""Fixtures for the browser tests: a running Shiny app and a real browser.

These are the only tests that check the thing the library actually
promises -- that a chart can be reached and driven from the keyboard.
Everything else in the suite asserts on emitted markup, which cannot tell
a working chart from a well-formed one.

Skipped unless ``--run-browser`` is given, and skipped anyway when
Playwright or a browser binary is missing, so a contributor without
either sees no failures.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

APPS = Path(__file__).parent / "apps"

#: How long to wait for uvicorn to bind, and for the ~1.5 MB inlined
#: bundle to parse in the frame. Generous on purpose: a CI runner is
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
        # network; these tests inline the bundle and must not need one.
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
def two_charts_app_url():
    """Two charts, both re-rendering, for the isolation test."""
    yield from _serve("two_charts_app.py")


@pytest.fixture(scope="session")
def streamlit_keys_app_url():
    """A Streamlit app with a rerun counter, for the key-collision test."""
    yield from _serve("streamlit_keys_app.py", runner="streamlit")


@pytest.fixture
def page(browser, focus_app_url):
    """A page with the chart loaded and its runtime up."""
    pg = browser.new_page()
    pg.goto(focus_app_url, wait_until="networkidle")
    pg.wait_for_timeout(_SETTLE_MS)
    yield pg
    pg.close()
