from __future__ import annotations

import os


def _configure_qt_plugins() -> None:
    try:
        from PySide6.QtCore import QCoreApplication, QLibraryInfo
    except ImportError:
        return

    plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    if not plugins:
        return

    if not os.environ.get("QT_PLUGIN_PATH"):
        os.environ["QT_PLUGIN_PATH"] = plugins
    if not os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(plugins, "platforms")

    QCoreApplication.addLibraryPath(plugins)


if __name__ == "__main__":
    _configure_qt_plugins()

    from app.views.main_window import run

    run()
