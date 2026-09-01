__version__ = "0.12.8"

from .ui_layout_patch import install as _install_ui_layout_patch

_install_ui_layout_patch()
del _install_ui_layout_patch
