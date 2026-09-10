__version__ = "0.12.8"

from .ui_layout_patch import install as _install_ui_layout_patch

_install_ui_layout_patch()
del _install_ui_layout_patch

from .ui_recruitment_patch import install as _install_ui_recruitment_patch

_install_ui_recruitment_patch()
del _install_ui_recruitment_patch

from .ui_recruitment_persistence_patch import install as _install_ui_recruitment_persistence_patch

_install_ui_recruitment_persistence_patch()
del _install_ui_recruitment_persistence_patch
