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


def _serve(app: str):
    """Run one of ``apps/`` under Shiny and yield its URL, then stop it."""
    pytest.importorskip("shiny")
    port = _free_port()
    env = {
        **os.environ,
        # Building a CDN URL would resolve the published version over the
        # network; these tests inline the bundle and must not need one.
        "MAIDR_CDN_VERSION": "latest",
        "MPLBACKEND": "Agg",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "shiny", "run", "--port", str(port), str(APPS / app)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + _BOOT_TIMEOUT
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"the app exited early:\n{proc.stdout.read()}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        else:  # pragma: no cover - only on a very slow machine
            pytest.fail(f"the app did not start within {_BOOT_TIMEOUT}s")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


@pytest.fixture(scope="session")
def focus_app_url():
    """The app used by the focus-restore tests."""
    yield from _serve("focus_app.py")


@pytest.fixture(scope="session")
def offline_app_url():
    """The app used by the offline-report test, on the default ``use_cdn``."""
    yield from _serve("offline_app.py")


@pytest.fixture
def page(browser, focus_app_url):
    """A page with the chart loaded and its runtime up."""
    pg = browser.new_page()
    pg.goto(focus_app_url, wait_until="networkidle")
    pg.wait_for_timeout(_SETTLE_MS)
    yield pg
    pg.close()
