import json
import os
import subprocess
import sys
from typing import Optional, Union

#: The pandoc writers whose output is a page a browser runs scripts in, as a
#: Quarto render names them in ``format.pandoc.to``. A dashboard is ``html``
#: there; ``ipynb``, ``commonmark``, ``latex``, ``docx`` and the rest are not
#: pages, so a chart for one of them is not written into a page either.
_QUARTO_PAGE_WRITERS = frozenset({"html", "html4", "html5", "revealjs"})

#: What a ``QUARTO_EXECUTE_INFO`` file said, by its path: the pandoc writer,
#: and the figure format the render set the kernel up with. Kept after the
#: file is gone; see :meth:`Environment.quarto_writer`.
_quarto_info: "dict[str, tuple[Optional[str], Optional[str]]]" = {}

#: Where a kernel keeps how many Quarto renders it has run charts in, on its
#: shell, which outlives the ``%reset`` each render starts with.
_RUNS_ATTRIBUTE = "_maidr_quarto_runs"

#: Set in the namespace of a render once it is counted; cleared by the
#: ``%reset`` the next render starts with.
_RUN_SENTINEL = "_maidr_quarto_run"


class Environment:
    _engine = "ts"

    @staticmethod
    def is_flask() -> bool:
        """
        Check if the current environment is a Flask application.

        This method detects Flask applications by checking if Flask's app context
        is available using `flask.has_app_context()`. The app context is Flask's
        way of tracking the current application state and is only available when
        code is running within a Flask application.

        Returns
        -------
        bool
            True if the environment is a Flask application, False otherwise.

        Examples
        --------
        >>> from maidr.util.environment import Environment
        >>> Environment.is_flask()
        False  # When not in a Flask app
        """
        # Same argument as is_notebook: an app context cannot exist unless
        # the flask package is already imported, so do not pay its import
        # on every render to learn there is none.
        if sys.modules.get("flask") is None:
            return False
        try:
            # Import Flask's has_app_context function
            from flask import has_app_context

            # has_app_context() returns True only when code is running within
            # a Flask application context. This is Flask's built-in mechanism
            # for detecting if the current execution environment is a Flask app.
            #
            # The app context is automatically created by Flask when:
            # - A Flask app is running (app.run())
            # - Code is executed within a Flask request context
            # - The app context is manually pushed
            return has_app_context()
        except ImportError:
            # Flask is not installed, so we're definitely not in a Flask app
            return False

    @staticmethod
    def is_interactive_shell() -> bool:
        """Return True if the environment is an interactive shell."""
        # See is_notebook: no shell without the package already loaded.
        if sys.modules.get("IPython") is None:
            return False
        try:
            from IPython.core.interactiveshell import InteractiveShell

            return (
                InteractiveShell.initialized()
                and InteractiveShell.instance() is not None
            )
        except ImportError:
            return False

    @staticmethod
    def is_notebook() -> bool:
        """Return True if the environment is a Jupyter notebook."""
        # An InteractiveShell cannot exist unless the IPython package is
        # already imported: get_ipython() is InteractiveShell.instance(),
        # defined in IPython.core.interactiveshell.  So a plain script must
        # not pay the ~200 ms IPython import to learn it is not a notebook
        # -- the same idiom as matplotlib.pyplot.install_repl_displayhook.
        # ``.get() is None`` also short-circuits a blocked import, where the
        # entry is a None sentinel.
        if sys.modules.get("IPython") is None:
            return False
        try:
            from IPython import get_ipython  # type: ignore

            ipy = get_ipython()
            if ipy is not None:
                # Check for Pyodide/JupyterLite specific indicators
                ipy_str = str(ipy).lower()
                if "pyodide" in ipy_str or "jupyterlite" in ipy_str:
                    return True
                # Check for other notebook indicators
                if "ipykernel" in str(ipy) or "google.colab" in str(ipy):
                    return True
                # Check for Pyodide platform
                if sys.platform == "emscripten":
                    return True
            return False
        except ImportError:
            return False

    @staticmethod
    def is_quarto() -> bool:
        """
        Return True in the kernel Quarto renders a document with.

        Quarto runs a document's Python cells in an ordinary Jupyter kernel,
        so :meth:`is_notebook` answers True there as well. What sets a render
        apart is that it is a batch run building one document: no reader waits
        on the kernel, and every cell's output ends up in the same page.

        Quarto's Jupyter engine sets ``QUARTO_FIG_FORMAT``, with
        ``QUARTO_FIG_WIDTH``, ``QUARTO_FIG_HEIGHT`` and ``QUARTO_FIG_DPI``, in
        the environment of the kernel it renders with, and has since at least
        Quarto 1.3. A kernel started by a notebook frontend has none of them.
        Were a Quarto release to stop setting it, a render would be handled
        as a notebook again: a bundle copy per chart and the bundled version,
        larger but still working.

        Returns
        -------
        bool
            True if ``QUARTO_FIG_FORMAT`` is set and not empty.
        """
        return bool(os.environ.get("QUARTO_FIG_FORMAT"))

    @staticmethod
    def quarto_writer() -> Optional[str]:
        """
        Return the pandoc writer of the Quarto render running this kernel.

        Quarto 1.8 and later name a JSON file in ``QUARTO_EXECUTE_INFO``
        that describes the document being executed, its format among it. A
        dashboard reads ``html`` here, a deck ``revealjs``, and a notebook
        target ``ipynb``.

        The variable is set once, when the kernel starts. Quarto keeps a
        kernel alive between renders -- its default in a terminal, in
        RStudio and in VS Code, and always under ``quarto preview`` -- and a
        later render in it still finds the first render's file: deleted
        once that render ended, or, when one ``quarto render`` builds
        several formats, describing the format before. So the file is
        trusted outright only in the first render this kernel runs charts
        in. In a later one it is trusted only when the figure format the
        render set the kernel up with (its setup cell's
        ``set_matplotlib_formats``) is the one the file names, and what a
        deleted file said is remembered for that. Anything else is None,
        which keeps the iframe.

        Returns
        -------
        str or None
            ``format.pandoc.to``, or None outside such a render, under an
            older Quarto, or when the render cannot be told apart from
            another.
        """
        path = os.environ.get("QUARTO_EXECUTE_INFO")
        if not path or not Environment.is_quarto():
            return None
        try:
            info = Environment._read_quarto_info(path)
            if Environment._quarto_run() <= 1:
                return info[0] if info else None
            info = info or _quarto_info.get(path)
            if info and info[1] is not None and info[1] == _figure_format():
                return info[0]
            return None
        except Exception:
            # Broad on purpose, as in is_shiny: a probe must never be why a
            # render fails, and an answer of None keeps the iframe.
            return None

    @staticmethod
    def _read_quarto_info(path: str) -> "Optional[tuple[Optional[str], Optional[str]]]":
        """The writer and figure format a ``QUARTO_EXECUTE_INFO`` file names."""
        try:
            with open(path, encoding="utf-8") as f:
                document_format = json.load(f)["format"]
        except (OSError, ValueError):
            return None
        writer = document_format["pandoc"]["to"]
        figure_format = document_format.get("execute", {}).get("fig-format")
        info = (
            writer if isinstance(writer, str) else None,
            figure_format if isinstance(figure_format, str) else None,
        )
        _quarto_info[path] = info
        return info

    @staticmethod
    def _quarto_run() -> int:
        """Which Quarto render, counting from 1, this kernel runs charts in now.

        Counted on the kernel's shell when a chart first asks in a render:
        each render starts with ``%reset``, which clears the mark the count
        leaves in the namespace. Without a shell there is one render.
        """
        if sys.modules.get("IPython") is None:
            return 1
        from IPython import get_ipython

        shell = get_ipython()
        if shell is None:
            return 1
        if not shell.user_ns.get(_RUN_SENTINEL):
            runs = getattr(shell, _RUNS_ATTRIBUTE, 0) + 1
            setattr(shell, _RUNS_ATTRIBUTE, runs)
            shell.push({_RUN_SENTINEL: runs}, interactive=False)
        return getattr(shell, _RUNS_ATTRIBUTE, 1)

    @staticmethod
    def is_quarto_page() -> bool:
        """
        Return True in a Quarto render whose output is a page a browser runs.

        That is an ``html`` document, website, book or dashboard, or a
        ``revealjs`` deck. A chart there can be written into the page itself
        rather than into an iframe: there is no notebook frontend to take
        its keys, and the page's own shortcuts are known (#895).

        Returns
        -------
        bool
            True if :meth:`quarto_writer` names such a writer.
        """
        return Environment.quarto_writer() in _QUARTO_PAGE_WRITERS

    @staticmethod
    def is_pyodide_page() -> bool:
        """
        Return True when running in Pyodide on a page's main thread, with no shell.

        ``micropip.install("maidr")`` in a plain Pyodide page has no IPython
        and no filesystem a browser can open, so ``webbrowser.open`` does
        nothing there.  What it does have is the host page's ``document``,
        which is where a chart can be put instead.  A web worker is
        Pyodide too but has no ``document``, so it answers False.  JupyterLite
        answers False as well: it has an IPython shell, and is handled as a
        notebook.

        Returns
        -------
        bool
            True if the ``js`` module exposes a ``document``, else False.
        """
        if sys.platform != "emscripten" or Environment.is_notebook():
            return False
        try:
            import js  # type: ignore[import-not-found]

            return getattr(js, "document", None) is not None
        except ImportError:
            return False

    @staticmethod
    def is_pyodide_without_page() -> bool:
        """
        Return True when running in Pyodide with no page and no shell to show in.

        A web worker -- where a host often runs Pyodide, to keep its page
        responsive -- and Node.js have neither the ``document``
        :meth:`is_pyodide_page` puts a chart in nor IPython's display.  Nor
        can they open a browser: Pyodide's ``webbrowser.open`` reaches for
        ``js.window`` and raises.  A chart reaches the reader there only as
        HTML the host puts in its page.

        Returns
        -------
        bool
            True on Emscripten outside a notebook when there is no page.
        """
        if sys.platform != "emscripten" or Environment.is_notebook():
            return False
        return not Environment.is_pyodide_page()

    @staticmethod
    def is_shiny() -> bool:
        """
        Check if the current code is running inside an active Shiny session.

        Mirrors :meth:`is_flask`, which asks Flask whether an app context is
        live rather than whether Flask is installed.  ``get_current_session()``
        is Shiny's equivalent: it returns the session only while a render
        function, reactive effect, or session-scoped callback is executing,
        which is exactly where :class:`maidr.widget.shiny.render_maidr` runs.

        Asking whether ``shiny`` merely imports would answer a different
        question.  Every process that happens to have Shiny installed --
        a plain script, a pytest run, a Flask or Streamlit app -- would take
        the Shiny rendering path and get iframe-wrapped output it never
        asked for.

        Returns
        -------
        bool
            True if a Shiny session is currently active, False otherwise.

        Examples
        --------
        >>> from maidr.util.environment import Environment
        >>> Environment.is_shiny()
        False  # When not inside a Shiny session
        """
        # Same argument as is_notebook: a live session cannot exist unless
        # the shiny package is already imported, so do not pay its import
        # (~0.2 s cold, on every render) to learn there is none.  ``.get()
        # is None`` also covers a blocked import, where the entry is a None
        # sentinel.
        if sys.modules.get("shiny") is None:
            return False
        try:
            from shiny.session import get_current_session

            return get_current_session() is not None
        except Exception:
            # Broader than ImportError on purpose: an environment probe must
            # never be the reason a render fails.  A partially installed or
            # version-skewed Shiny (its import chain reaches htmltools and
            # shinychat) raises other exception types, and a user who never
            # asked for Shiny should not see them.
            return False

    @staticmethod
    def is_vscode_notebook() -> bool:
        """Return True if the environment is a VSCode notebook."""
        try:
            if "VSCODE_PID" in os.environ or "VSCODE_JUPYTER" in os.environ:
                return True
            else:
                return False
        except ImportError:
            return False

    @staticmethod
    def is_wsl() -> bool:
        """
        Check if the current environment is WSL (Windows Subsystem for Linux).

        This method detects WSL environments by reading the `/proc/version` file
        and checking for 'microsoft' or 'wsl' keywords in the version string.
        WSL environments typically contain these identifiers in their kernel version.

        Returns
        -------
        bool
            True if the environment is WSL, False otherwise.

        Examples
        --------
        >>> from maidr.util.environment import Environment
        >>> Environment.is_wsl()
        False  # When not in WSL
        """
        try:
            with open("/proc/version", "r") as f:
                version_info = f.read().lower()
                if "microsoft" in version_info or "wsl" in version_info:
                    return True
        except FileNotFoundError:
            pass
        return False

    @staticmethod
    def get_wsl_distro_name() -> str:
        """
        Get the WSL distribution name from environment variables.

        This method retrieves the WSL distribution name from the `WSL_DISTRO_NAME`
        environment variable, which is automatically set by WSL when running
        in a WSL environment.

        Returns
        -------
        str
            The WSL distribution name (e.g., 'Ubuntu-20.04', 'Debian') if set,
            otherwise an empty string.

        Examples
        --------
        >>> from maidr.util.environment import Environment
        >>> Environment.get_wsl_distro_name()
        ''  # When not in WSL or WSL_DISTRO_NAME not set
        """
        return os.environ.get("WSL_DISTRO_NAME", "")

    @staticmethod
    def find_explorer_path() -> Union[str, None]:
        """
        Find the correct path to explorer.exe in WSL environment.

        This method checks if explorer.exe is available in the PATH
        and returns the path if found.

        Returns
        -------
        str | None
            The path to explorer.exe if found, None otherwise.

        Examples
        --------
        >>> from maidr.util.environment import Environment
        >>> Environment.find_explorer_path()
        '/mnt/c/Windows/explorer.exe'  # When found
        """
        # Check if explorer.exe is in PATH
        try:
            result = subprocess.run(
                ["which", "explorer.exe"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return None

    @staticmethod
    def get_renderer() -> str:
        """Return renderer which can be ipython or browser."""
        # See is_notebook: no shell without the package already loaded.
        if sys.modules.get("IPython") is None:
            return "browser"
        try:
            import IPython  # pyright: ignore[reportUnknownVariableType]

            ipy = (  # pyright: ignore[reportUnknownVariableType]
                IPython.get_ipython()  # pyright: ignore[reportUnknownMemberType, reportPrivateImportUsage]
            )
            if ipy is not None:
                # Check for Pyodide/JupyterLite
                ipy_str = str(ipy).lower()
                if "pyodide" in ipy_str or "jupyterlite" in ipy_str:
                    return "ipython"
                # Check for Pyodide platform
                if sys.platform == "emscripten":
                    return "ipython"
                return "ipython"
            else:
                return "browser"
        except ImportError:
            return "browser"


def _figure_format() -> Optional[str]:
    """The figure format a Quarto render set the kernel up with, or None.

    Quarto's setup cell calls ``set_matplotlib_formats(fig_format)`` at the
    start of every render, which leaves exactly one display formatter for a
    matplotlib figure: ``retina_figure`` for ``retina``, ``print_figure``
    for the others, under the format's MIME type.
    """
    from IPython import get_ipython
    from matplotlib.figure import Figure

    shell = get_ipython()
    if shell is None:
        return None
    names = {
        "image/png": "png",
        "image/svg+xml": "svg",
        "application/pdf": "pdf",
        "image/jpeg": "jpeg",
    }
    found = []
    for mime, formatter in shell.display_formatter.formatters.items():
        try:
            printer = formatter.lookup_by_type(Figure)
        except KeyError:
            continue
        # A function, or a ``functools.partial`` of one.
        name = getattr(printer, "__name__", "") or getattr(
            getattr(printer, "func", None), "__name__", ""
        )
        if mime == "image/png" and name == "retina_figure":
            found.append("retina")
        elif mime in names:
            found.append(names[mime])
    return found[0] if len(found) == 1 else None
