"""Let in-table text fields go when the user clicks somewhere else."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from shiboken6 import isValid


class OutsideClickRelease(QObject):
    """
    Qt Quick only moves focus to items that take it, so a click on empty space, a row or
    the waveform leaves a text field focused (and its orange edge lit). Fields that set
    `releaseOnOutsideClick` lose focus on any press outside them that lands nowhere else.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            item = self.window.activeFocusItem()
            if item is not None and item.property('releaseOnOutsideClick') is True:
                if not item.contains(item.mapFromScene(event.scenePosition())):
                    # After the press is handled: if it gave focus to something else, leave that be.
                    QTimer.singleShot(0, lambda: self.release(item))
        return False

    def release(self, item):
        if isValid(item) and self.window.activeFocusItem() == item:
            item.setFocus(False)
