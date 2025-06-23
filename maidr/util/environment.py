import json
import os
import sys


class Environment:
    _engine = "ts"

    @staticmethod
    def is_interactive_shell() -> bool:
        """Return True if the environment is an interactive shell."""
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
        """Return True if the environment is a Shiny app."""
        try:
            import shiny

            return shiny.__name__ == "shiny"
        except ImportError:
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
    def get_renderer() -> str:
        """Return renderer which can be ipython or browser."""
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
