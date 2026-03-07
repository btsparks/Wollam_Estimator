"""WEIS NiceGUI state management — safe wrappers around app.storage.

Uses app.storage.browser (cookie-based) for state that must survive
page navigation via ui.navigate.to().
"""

from nicegui import app


def get(key: str, default=None):
    """Get a value from browser storage. Returns default if not connected."""
    try:
        return app.storage.browser.get(key, default)
    except RuntimeError:
        return default


def set(key: str, value):
    """Set a value in browser storage. No-op if not connected."""
    try:
        app.storage.browser[key] = value
    except (RuntimeError, TypeError):
        pass


def pop(key: str, default=None):
    """Pop a value from browser storage. Returns default if not connected."""
    try:
        return app.storage.browser.pop(key, default)
    except RuntimeError:
        return default


def setdefault(key: str, default):
    """Set default value if key doesn't exist. Returns default if not connected."""
    try:
        if key not in app.storage.browser:
            app.storage.browser[key] = default
        return app.storage.browser[key]
    except RuntimeError:
        return default
