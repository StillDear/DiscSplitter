"""
Chapter preview as one explicit state machine (no Qt: the backend forwards to it).

    off -> loading -> ready | error       (a clip was asked for and must be rendered first)
    off -> ready                          (the clip was already on disk)
    any -> loading | ready                (another chapter / track was asked for)
    any -> off                            (stop)

Renders run in the background; several may exist at once (the wanted clip and a
prefetch of the next chapter). Only the clip the player waits for (`wanted`)
moves the state; a result for anything else just ends that render.
"""
from __future__ import annotations

import threading
from enum import Enum


class State(str, Enum):
    OFF = 'off'
    LOADING = 'loading'
    READY = 'ready'
    ERROR = 'error'


class PreviewSession:
    def __init__(self):
        self.state = State.OFF
        self.listen = False     # quick listening from the paste dialog: sound only, the opening only
        self.wanted = ''        # clip path the player waits for
        self.error = ''
        self.renders = {}       # clip path -> (serial, cancel event, worker kept alive)
        self.serial = 0

    @property
    def active(self) -> bool:
        return self.state is not State.OFF

    def want(self, target: str, ready: bool):
        """Ask for a clip; every other render except a prefetch of it is cancelled."""
        self.wanted, self.error = target, ''
        self.cancel(keep=target)
        self.state = State.READY if ready else State.LOADING

    def stop(self):
        self.state, self.listen, self.wanted, self.error = State.OFF, False, '', ''
        self.cancel()

    # ------------------------------------------------------------ background renders
    def rendering(self, target: str) -> bool:
        return target in self.renders

    def begin_render(self, target: str, make_worker):
        """Register a render: make_worker(serial, cancel_event) builds it; returns the worker."""
        self.serial += 1
        cancel = threading.Event()
        worker = make_worker(self.serial, cancel)
        self.renders[target] = (self.serial, cancel, worker)
        return worker

    def end_render(self, serial: int):
        """A render finished (or failed): its clip path, or None when it had been cancelled."""
        for target, (number, _, _) in list(self.renders.items()):
            if number == serial:
                del self.renders[target]
                return target
        return None

    def cancel(self, keep: str = ''):
        for target, (_, cancel, _) in list(self.renders.items()):
            if target != keep:
                cancel.set()
                del self.renders[target]

    def arrived(self, target: str) -> bool:
        """The wanted clip is ready to play (False: not wanted any more)."""
        if self.state is State.OFF or target != self.wanted:
            return False
        self.state = State.READY
        return True

    def failed(self, target: str, message: str) -> bool:
        if self.state is State.OFF or target != self.wanted:
            return False
        self.state, self.error = State.ERROR, message
        return True
