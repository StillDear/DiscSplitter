"""Side jobs: background work that never marks the app busy (probing a stream, drawing the waveform)."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from core import jobs


class SideJob(QObject):
    """
    One kind of background work, of which only the latest request matters. Starting it again (or
    cancel()) drops the run before it: that run is told to stop through its cancel event, and
    whatever it still reports is ignored.

    The work is a function fn(cancel_event, report_progress) run on its own thread. Its result
    goes to done(result), an error to failed(exc) and report_progress(fraction) to
    progress(fraction), all on the GUI thread. A run that raises JobCancelled just ends.
    """
    _finished = Signal(int, object, object)
    _progressed = Signal(int, float)

    def __init__(self, parent, done, failed=None, progress=None):
        super().__init__(parent)
        self.done, self.failed, self.progress = done, failed, progress
        self.serial = 0
        self._cancel = None
        self._finished.connect(self._deliver)
        self._progressed.connect(self._report)

    @property
    def running(self) -> bool:
        return self._cancel is not None

    def start(self, fn):
        self.cancel()
        serial, cancel = self.serial, threading.Event()
        self._cancel = cancel

        def run():
            try:
                result, error = fn(cancel, lambda fraction: self._progressed.emit(serial, fraction)), None
            except jobs.JobCancelled:
                return
            except Exception as exc:        # reported to failed() on the GUI thread
                result, error = None, exc
            self._finished.emit(serial, result, error)      # queued to the GUI thread
        threading.Thread(target=run, daemon=True).start()

    def cancel(self):
        if self._cancel is not None:
            self._cancel.set()
            self._cancel = None
        self.serial += 1

    def _deliver(self, serial, result, error):
        if serial != self.serial:
            return
        self._cancel = None
        if error is None:
            self.done(result)
        elif self.failed is not None:
            self.failed(error)

    def _report(self, serial, fraction):
        if serial == self.serial and self.progress is not None:
            self.progress(fraction)
