"""Win32 control layer: a cached-element driver for Windows desktop applications.

The driver needs Windows (pywin32 / pywinauto) only when it is used, so the names
below are resolved lazily and `import mozaik_automation.automation` works anywhere.
"""

__all__ = ["CachedElement", "ElementCache", "FastMozaikDriver", "CachedWin32Driver"]


def __getattr__(name):
    if name in __all__:
        from mozaik_automation.automation import fast_driver

        return getattr(fast_driver, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
