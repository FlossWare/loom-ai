"""Optional Loom terminal UI integration.

The core Loom runtime deliberately has no curses dependency.  TUI code lives in
this package and talks to Loom through its public service/API interfaces.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
