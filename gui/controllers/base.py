"""What every controller shares: its own slice of the UI state, and the app's services."""
from __future__ import annotations

from PySide6.QtCore import QObject, Property, QUrl, Signal


def local_path(text: str) -> str:
    """A path as QML hands it over: a file: URL from a dialog or a drop, or a plain path typed in."""
    text = str(text or '').strip()
    return QUrl(text).toLocalFile() if text.startswith('file:') else text


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
    working = property(lambda self: self.app.working)    # a job is running: no other may start
    disc = property(lambda self: self.app.disc)          # the disc being worked on
    dialogRequested = property(lambda self: self.app.dialogRequested)

    def put(self, **values):
        """
        Update this controller's own slice of the state. Another controller's state is changed by
        calling that controller (it knows what else has to follow); the page by show().
        """
        foreign = [key for key in values if key not in self._view]
        assert not foreign, f'{type(self).__name__} does not own {foreign}'
        if self.update_view(values):
            self.app.changed.emit()

    def show(self, page):
        """Go to a page of the app (a sub-page remembers where Back leads)."""
        self.app.show_page(page)

    def task(self, *args, **kwargs):
        return self.app.task(*args, **kwargs)

    def notify(self, *args, **kwargs):
        self.app.notify(*args, **kwargs)

    def report(self, exc):
        self.app.report(exc)

    def tr(self, key):
        return self.app.tr(key)
