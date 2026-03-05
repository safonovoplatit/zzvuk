import os
from pathlib import Path

# Prevent mixing Homebrew Qt frameworks with PySide6 bundled Qt.
for _key in (
    "DYLD_FRAMEWORK_PATH",
    "DYLD_LIBRARY_PATH",
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
):
    os.environ.pop(_key, None)

from PySide6.QtCore import QLibraryInfo


def _configure_qt_environment() -> None:
    # Resolve plugin paths via Qt itself (robust across PySide package layouts).
    plugins_dir = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    platforms_dir = plugins_dir / "platforms"

    os.environ["QT_PLUGIN_PATH"] = str(plugins_dir)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_dir)
    os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")


if __name__ == "__main__":
    _configure_qt_environment()
    from app.views.main_window import run

    run()
