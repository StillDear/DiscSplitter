"""
Desktop integration: remember the window's size and position, show export
progress on the Windows taskbar button, and tell the user when an export
finishes while they are working in another window.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QRect, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QWindow

from . import settings


# ---------------------------------------------------------------- geometry

def restore_geometry(window: QWindow, saved) -> bool:
    """Apply a saved [x, y, width, height, maximized]; ignore it if no screen shows the title bar."""
    try:
        x, y, width, height, maximized = saved
        rect = QRect(int(x), int(y), int(width), int(height))
    except (TypeError, ValueError):
        return False
    rect.setWidth(max(rect.width(), window.minimumWidth()))
    rect.setHeight(max(rect.height(), window.minimumHeight()))
    title_bar = QRect(rect.x() + 40, rect.y(), max(1, rect.width() - 80), 32)
    if not any(screen.availableGeometry().intersects(title_bar) for screen in QGuiApplication.screens()):
        return False   # e.g. the monitor it was on has been unplugged
    window.setGeometry(rect)
    if maximized:
        window.setVisibility(QWindow.Visibility.Maximized)
    return True


# ---------------------------------------------------------------- taskbar

class _Taskbar:
    """Minimal ITaskbarList3 wrapper (progress on the taskbar button); a no-op off Windows."""
    NONE, INDETERMINATE, NORMAL, ERROR, PAUSED = 0, 1, 2, 4, 8

    def __init__(self, window: QWindow):
        self.window = window
        self.ok = False
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [('Data1', ctypes.c_ulong), ('Data2', ctypes.c_ushort),
                            ('Data3', ctypes.c_ushort), ('Data4', ctypes.c_ubyte * 8)]

            def guid(text):
                value = uuid.UUID(text)
                return GUID(value.time_low, value.time_mid, value.time_hi_version,
                            (ctypes.c_ubyte * 8)(*value.bytes[8:]))

            ole32 = ctypes.OleDLL('ole32')
            ole32.CoInitialize(None)   # Qt has already initialised COM on this thread; harmless if so
            pointer = ctypes.c_void_p()
            ole32.CoCreateInstance(ctypes.byref(guid('56FDF344-FD6D-11D0-958A-006097C9A090')), None, 1,
                                   ctypes.byref(guid('EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF')), ctypes.byref(pointer))
            vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]

            def method(index, *argtypes):
                return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtable[index])

            self._pointer = pointer
            method(3)(pointer)                                       # HrInit
            self._set_value = method(9, wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)
            self._set_state = method(10, wintypes.HWND, ctypes.c_int)
            self.ok = True
        except Exception:
            self.ok = False

    def _hwnd(self):
        return int(self.window.winId())

    def state(self, flag: int) -> None:
        if self.ok:
            self._set_state(self._pointer, self._hwnd(), flag)

    def value(self, done: int, total: int) -> None:
        if self.ok and total > 0:
            self._set_value(self._pointer, self._hwnd(), max(0, min(done, total)), total)


# ---------------------------------------------------------------- glue

class Desktop(QObject):
    def __init__(self, app, window: QWindow, backend, icon_path: str):
        super().__init__(window)
        self.app, self.window, self.backend = app, window, backend
        self.normal = None
        self.total = 0
        self.running = False
        self.error_shown = False
        self.tray = None
        self.icon_path = icon_path

        restore_geometry(window, backend.cfg.get('window_geometry') or None)
        self.remember()
        for signal in (window.xChanged, window.yChanged, window.widthChanged, window.heightChanged, window.visibilityChanged):
            signal.connect(self.remember)
        app.aboutToQuit.connect(self.save)

        self.taskbar = _Taskbar(window)
        backend.changed.connect(self.sync)
        window.activeChanged.connect(self.on_active)

    # geometry ------------------------------------------------------------
    def remember(self, *_):
        if self.window.visibility() == QWindow.Visibility.Windowed:
            self.normal = self.window.geometry()

    def save(self):
        rect = self.normal or self.window.geometry()
        maximized = self.window.visibility() in (QWindow.Visibility.Maximized, QWindow.Visibility.FullScreen)
        self.backend.cfg['window_geometry'] = [rect.x(), rect.y(), rect.width(), rect.height(), maximized]
        if not self.backend.smoke:
            settings.save(self.backend.cfg)

    # progress ------------------------------------------------------------
    def sync(self):
        state = self.backend.state
        running = bool(state.get('pipeline')) and state.get('result') in ('running', 'cancelling')
        if running and not self.running:
            self.total = max(1, int(state.get('remaining') or state.get('chapterSelected') or 1))
            self.error_shown = False
        if running:
            if state.get('stage') == 'extracting':
                self.taskbar.state(_Taskbar.INDETERMINATE)
            else:
                self.taskbar.state(_Taskbar.PAUSED if state.get('result') == 'cancelling' else _Taskbar.NORMAL)
                self.taskbar.value(int(state.get('completed') or 0), self.total)
        elif self.running:
            self.finished(state)
        elif self.error_shown and state.get('page') != 'done':
            self.taskbar.state(_Taskbar.NONE)
            self.error_shown = False
        self.running = running

    def finished(self, state):
        result = state.get('result')
        if result == 'failed':
            self.taskbar.state(_Taskbar.ERROR)
            self.taskbar.value(1, 1)
            self.error_shown = True
        else:
            self.taskbar.state(_Taskbar.NONE)
        if result == 'cancelled' or self.window.isActive():
            return
        self.window.alert(0)   # flash the taskbar button until the window is activated
        tr = self.backend.tr
        if result == 'done':
            title, text = tr('notifyDoneTitle'), tr('notifyDoneText').format(n=state.get('completed') or 0)
        else:
            title, text = tr('notifyFailedTitle'), tr('notifyFailedText')
        self.notify(title, text, failed=result != 'done')

    def notify(self, title, text, failed=False):
        try:
            from PySide6.QtWidgets import QApplication, QSystemTrayIcon
        except ImportError:
            return
        if not isinstance(self.app, QApplication) or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self.tray is None:
            self.tray = QSystemTrayIcon(QIcon(self.icon_path), self)
            self.tray.setToolTip('DiscSplitter')
            self.tray.messageClicked.connect(self.bring_to_front)
            self.tray.activated.connect(lambda *_: self.bring_to_front())
        self.tray.show()
        icon = QSystemTrayIcon.MessageIcon.Warning if failed else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(title, text, icon, 8000)

    def bring_to_front(self):
        if self.window.visibility() == QWindow.Visibility.Minimized:
            self.window.showNormal()
        self.window.raise_()
        self.window.requestActivate()

    def on_active(self):
        # The tray icon only exists to carry the notification.
        if self.window.isActive() and self.tray is not None:
            QTimer.singleShot(1500, lambda: self.tray.hide() if self.tray and self.window.isActive() else None)
