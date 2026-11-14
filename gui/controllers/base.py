"""What every controller shares: its own slice of the UI state, and the app's services."""
from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal


class View(QObject):
    """
    A slice of the UI state that QML binds to as `<owner>.view`. Each slice has its own change
    signal, so an update to one (an export log line) does not re-evaluate bindings on the others.
    """
    viewChanged = Signal()

    def __init__(self, parent=None, **values):
        super().__init__(parent)
        self._view = values

    @Property('QVariantMap', notify=viewChanged)
    def view(self):
        return self._view

    def update_view(self, values: dict) -> bool:
        """Apply values; announce and return True only when something really changed."""
        # A value passed again as the same object may have been edited in place, so it counts as a change.
        if all(key in self._view and self._view[key] is not value and self._view[key] == value
               for key, value in values.items()):
            return False
        self._view = {**self._view, **values}
        self.viewChanged.emit()
        return True


class Controller(View):
    """One area of the app (the disc, previews, track names, metadata, the export), owned by the Backend."""

    def __init__(self, app, **view):
        super().__init__(app, **view)
        self.app = app

    # The app's services, so controller code reads the same as it would on the app itself.
    cfg = property(lambda self: self.app.cfg)
    smoke = property(lambda self: self.app.smoke)
    state = property(lambda self: self.app.state)        # every slice, read-only
    disc = property(lambda self: self.app.disc)          # the disc being worked on
    dialogRequested = property(lambda self: self.app.dialogRequested)

    def put(self, **values):
        self.app.put(**values)

    def task(self, *args, **kwargs):
        return self.app.task(*args, **kwargs)

    def notify(self, *args, **kwargs):
        self.app.notify(*args, **kwargs)

    def tr(self, key):
        return self.app.tr(key)
