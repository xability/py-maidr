import json
import os
from typing import Literal


class Environment:
    _engine = "js"

    @classmethod
    def _set_engine(cls, engine: Literal["js", "ts"]) -> None:
        """Set the engine to use for the MAIDR instance."""
        cls._engine = engine

    @classmethod
    def get_engine(cls) -> str:
        """Get the engine to use for the MAIDR instance."""
        return cls._engine

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

            return get_ipython() is not None and (
                "ipykernel" in str(get_ipython())
                or "google.colab" in str(get_ipython())
            )
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
            renderer = "ipython" if ipy else "browser"
        except ImportError:
            renderer = "browser"
        return renderer

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
