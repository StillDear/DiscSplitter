from pathlib import Path
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if os.name == 'nt':
    os.environ.setdefault('QT_QPA_FONTDIR', 'C:/Windows/Fonts')

import pytest
from PySide6.QtGui import QGuiApplication


def pytest_configure(config):
    # Python 3.13's Windows mode=0700 drops sandbox ACL entries. Use ordinary
    # inherited permissions for test artifacts, all confined to this workspace.
    Path(config.rootpath, config.getini('cache_dir'), 'v', 'cache').mkdir(parents=True, exist_ok=True)
    # pytest's own abandoned cache staging directories contain no test sources.
    config.addinivalue_line('norecursedirs', 'pytest-cache-files-*')
    config.addinivalue_line('markers', 'engine: runs the built-in Blu-ray engine (engine/bin/tsMuxeR.exe)')


@pytest.fixture(autouse=True)
def _engine_only_when_asked(request, monkeypatch):
    """
    Tests fake mkvmerge on made-up discs; the built-in engine would read those discs for real. It is
    switched off unless a test is marked @pytest.mark.engine (then skipped when it has not been built).
    """
    from core import engine
    if request.node.get_closest_marker('engine') is None:
        monkeypatch.setattr(engine, 'available', lambda: False)
    elif not engine.available():
        pytest.skip('the engine has not been built (python engine/build_engine.py)')


@pytest.fixture
def tmp_path():
    import shutil
    import uuid
    root = Path(__file__).resolve().parent / 'runtime'
    root.mkdir(exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    yield path
    assert path.parent == root
    shutil.rmtree(path)


@pytest.fixture(scope='session')
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication([])
    return app


@pytest.fixture
def backend(qt_app, monkeypatch, tmp_path):
    from gui import settings
    from gui.backend import Backend
    from gui.controllers.exporter import ExportController
    monkeypatch.setattr(settings, 'SETTINGS_PATH', tmp_path / 'settings.json')
    monkeypatch.setattr(settings, 'system_language', lambda: 'zh')     # the same on every machine
    monkeypatch.setattr(ExportController, 'LOG_DIR', tmp_path / 'logs')
    result = Backend(smoke=True)
    yield result
    result.pool.waitForDone(5000)
    qt_app.processEvents()
