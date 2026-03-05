from pathlib import Path
from .languages.base import LanguagePlugin
from .languages.python import PythonPlugin
from .languages.javascript import JavaScriptPlugin

# All supported file extensions mapped to plugin instances.
# To add a new language: import its plugin and add its extensions here.
PLUGINS: dict[str, LanguagePlugin] = {
    ".py":  PythonPlugin(),
    ".js":  JavaScriptPlugin(),
    ".jsx": JavaScriptPlugin(),
}


def get_plugin(path: Path) -> LanguagePlugin | None:
    """Return the plugin for this file's extension, or None if unsupported."""
    return PLUGINS.get(path.suffix)
