import os

def _sanitize_qt_environment():
    # Let PySide6/Qt resolve its own bundled plugins in a clean environment.
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "DYLD_LIBRARY_PATH"):
        os.environ.pop(key, None)


if __name__ == "__main__":
    _sanitize_qt_environment()
    from app.views.main_window import run

    run()
