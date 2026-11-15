"""PySide6 / Qt Quick entry point, including a warning-strict offline smoke run."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtCore import QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from gui import smoke
from gui.backend import Backend
from gui.focus import OutsideClickRelease


def assert_qml_sources(qml_dir=None):
    """Prevent font-dependent icon glyphs from returning to the QML UI."""
    qml_dir = qml_dir or Path(__file__).resolve().parent / 'qml'
    forbidden = {chr(code) for code in (0x21BB, 0x25C9, 0x25CB, 0x25A1, 0x25CE, 0x2713)}
    for path in qml_dir.rglob('*.qml'):
        source = path.read_bytes()
        assert not source.startswith(b'\xef\xbb\xbf'), f'UTF-8 BOM in {path}'
        found = forbidden.intersection(source.decode('utf-8'))
        assert not found, f'Font-dependent icon glyphs in {path}: {sorted(found)}'


def load_engine(backend):
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty('backend', backend)
    disc = backend.disc
    for name, model in dict(playlist=disc.playlist_model, audio=disc.audio_model, subtitle=disc.subtitle_model,
                            chapter=disc.chapter_model, export=disc.export_model, review=backend.names.review_model,
                            release=backend.names.release_model, tool=backend.tool_model,
                            meta=backend.metadata.meta_model).items():
        context.setContextProperty(name + 'Model', model)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parent / 'qml' / 'Main.qml')))
    for window in engine.rootObjects():
        OutsideClickRelease(window)
    return engine


def apply_qt_proxy(cfg):
    """Use the same proxy for images QML loads (search result thumbnails) as for Python requests."""
    from urllib.parse import urlsplit
    from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
    mode = cfg.get('proxy_mode', 'system')
    url = cfg.get('proxy_url', '')
    if mode == 'custom' and url:
        parts = urlsplit(url)
        QNetworkProxyFactory.setUseSystemConfiguration(False)
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy, parts.hostname, parts.port))
    elif mode == 'none':
        QNetworkProxyFactory.setUseSystemConfiguration(False)
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
    else:
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.DefaultProxy))
        QNetworkProxyFactory.setUseSystemConfiguration(True)


def system_scale() -> int:
    """Windows display scaling in percent (Qt has made the process DPI aware by now)."""
    if sys.platform != 'win32':
        return 100
    try:
        import ctypes
        return round(ctypes.windll.user32.GetDpiForSystem() * 100 / 96)
    except Exception:
        return 100


def system_accent(app) -> str:
    """Windows accent colour as #RRGGBB (Qt 6.6+ exposes it as QPalette.Accent)."""
    try:
        from PySide6.QtGui import QPalette
        return app.palette().color(QPalette.ColorRole.Accent).name().upper()
    except Exception:
        return '#60CDFF'


def apply_native_titlebar(window, cfg, app):
    """Make the native Windows caption match the app theme (dark mode + caption colour)."""
    import ctypes
    from PySide6.QtCore import Qt
    theme = cfg.get('theme', 'dark')
    dark = theme == 'dark' or (theme == 'system' and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    try:
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        flag = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(flag), ctypes.sizeof(flag))  # DWMWA_USE_IMMERSIVE_DARK_MODE
        r, g, b = (0x0C, 0x0E, 0x12) if dark else (0xEE, 0xF0, 0xF3)          # Theme.bg
        caption = ctypes.c_uint(r | (g << 8) | (b << 16))                      # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))  # DWMWA_CAPTION_COLOR (Win11)
    except Exception:
        pass  # Older Windows: keep the default caption.


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--smoke-screenshots', type=Path)
    args = parser.parse_args(argv)
    if args.smoke_test:
        assert_qml_sources()
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        os.environ.setdefault('QSG_RHI_BACKEND', 'software')
        if sys.platform == 'win32':
            # Offscreen Qt has no Windows font backend. Use an existing local
            # directory and explicitly load installed system fonts below; do not
            # scan every font/shortcut in the Windows Fonts virtual directory.
            os.environ.setdefault('QT_QPA_FONTDIR', str(Path(__file__).parent / 'qml'))
    warnings = []
    def handler(kind, context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            warnings.append(message)
        print(message, file=sys.stderr)
    previous = qInstallMessageHandler(handler) if args.smoke_test else None
    if not args.smoke_test and 'QT_SCALE_FACTOR' not in os.environ:
        from gui import settings
        from gui import logic
        factor = logic.scale_factor(settings.load())
        if factor:
            # Absolute scale: ignore Windows display scaling, then apply the chosen factor.
            os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
            os.environ['QT_SCALE_FACTOR'] = factor
    QQuickStyle.setStyle('Basic')
    app = QApplication(sys.argv[:1])
    if args.smoke_test and sys.platform == 'win32':
        fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('segoeui.ttf', 'seguisb.ttf', 'seguisym.ttf', 'msyh.ttc', 'consola.ttf'):
            if (fonts / name).is_file():
                QFontDatabase.addApplicationFont(str(fonts / name))
    app.setApplicationName('DiscSplitter')
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'disc_splitter.ico')))
    backend = Backend(smoke=args.smoke_test)
    backend.put(systemAccent=system_accent(app), systemScale=system_scale(),
                startScale=str(backend.cfg.get('interface_scale', 'system')))
    if args.smoke_test:
        smoke.populate(backend)
    apply_qt_proxy(backend.cfg)
    backend.configChanged.connect(lambda: apply_qt_proxy(backend.cfg))
    engine = load_engine(backend)
    if not engine.rootObjects():
        return 1
    if not args.smoke_test and sys.platform == 'win32':
        window = engine.rootObjects()[0]
        sync = lambda: apply_native_titlebar(window, backend.cfg, app)
        backend.configChanged.connect(sync)
        app.styleHints().colorSchemeChanged.connect(lambda *_: sync())
        sync()
    if not args.smoke_test:
        from gui.desktop import Desktop
        Desktop(app, engine.rootObjects()[0], backend, str(Path(__file__).parent / 'disc_splitter.ico'))   # owned by the window
    if args.smoke_test:
        smoke.run(app, backend, engine.rootObjects()[0], warnings, args.smoke_screenshots)
    code = app.exec()
    # Destroy QML while its Python context objects are still alive.
    engine.deleteLater()
    app.processEvents()
    if args.smoke_test:
        qInstallMessageHandler(previous)
        if warnings:
            print(f'Smoke FAILED: {len(warnings)} Qt/QML warning(s)', file=sys.stderr)
            return 1
        print('Smoke PASS: all screens, delegates, dialogs, languages and themes; zero Qt/QML warnings.')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
