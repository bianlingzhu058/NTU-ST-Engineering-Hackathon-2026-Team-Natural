"""Import built-in skill modules so their decorators register their names."""

# Keep the full runtime catalog registered. The UI's objective editor presents
# only the browsing and launch subset from ``catalog.py``.
from . import browser as browser
from . import launch as launch
from . import office as office

__all__ = ["browser", "launch", "office"]
