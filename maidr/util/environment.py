import json
import os
import subprocess
import sys
from typing import Union


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

    @staticmethod
    def initialize_llm_secrets(unique_id: str) -> str:
        """Inject the LLM API keys into the MAIDR instance."""

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        # Default settings for the MAIDR instance
        settings = {
            "vol": "0.5",
            "autoPlayRate": "500",
            "brailleDisplayLength": "32",
            "colorSelected": "#03c809",
            "MIN_FREQUENCY": "200",
            "MAX_FREQUENCY": "1000",
            "keypressInterval": "2000",
            "ariaMode": "assertive",
            "openAIAuthKey": "",
            "geminiAuthKey": "",
            "skillLevel": "basic",
            "skillLevelOther": "",
            "LLMModel": "openai",
            "LLMPreferences": "",
            "LLMOpenAiMulti": False,
            "LLMGeminiMulti": False,
            "autoInitLLM": True,
        }

        if gemini_api_key is not None and openai_api_key is not None:
            settings["geminiAuthKey"] = gemini_api_key
            settings["openAIAuthKey"] = openai_api_key
            settings["LLMOpenAiMulti"] = True
            settings["LLMGeminiMulti"] = True
            settings["LLMModel"] = "multi"
        elif openai_api_key is not None:
            settings["LLMOpenAiMulti"] = True
            settings["openAIAuthKey"] = openai_api_key
            settings["LLMModel"] = "openai"
        elif gemini_api_key is not None:
            settings["LLMGeminiMulti"] = True
            settings["geminiAuthKey"] = gemini_api_key
            settings["LLMModel"] = "gemini"

        settings_data = json.dumps(settings)

        keys_injection_script = f"""
            function addKeyValueLocalStorage(iframeId, key, value) {{
                const iframe = document.getElementById(iframeId);
                if (iframe && iframe.contentWindow) {{
                    try {{
                        iframe.contentWindow.localStorage.setItem(key, value);
                    }} catch (error) {{
                        console.error('Error accessing iframe localStorage:', error);
                    }}
                }} else {{
                    console.error('Iframe not found or inaccessible.');
                }}
            }}
            addKeyValueLocalStorage(
                '{unique_id}', 'settings_data', JSON.stringify({settings_data})
            );
        """

        return keys_injection_script
