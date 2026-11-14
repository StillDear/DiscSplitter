"""
The export lifecycle as one explicit state machine (no Qt: the backend forwards to it).

    idle | finished -> [confirm_resume] -> [confirm_duplicate] -> [confirm_collision] -> [confirm_space] -> running
    running -> finished                  (done or failed)
    running -> cancelling -> finished    (cancelled)

Each bracketed question is asked only when needed, and dismissing it goes back to idle. A transition that is not in
TRANSITIONS is refused (and logged) instead of silently corrupting the job:
for example a second launch while one runs, or a cancel when nothing runs.
"""
from __future__ import annotations

import logging
import threading
from enum import Enum

log = logging.getLogger(__name__)


class Phase(str, Enum):
    IDLE = 'idle'
    CONFIRM_RESUME = 'confirm_resume'          # a checkpoint exists: resume it or start fresh?
    CONFIRM_DUPLICATE = 'confirm_duplicate'    # two chapters would get the same file name
    CONFIRM_COLLISION = 'confirm_collision'    # files already exist: overwrite, skip or elsewhere?
    CONFIRM_SPACE = 'confirm_space'            # the drive looks too full: export anyway or elsewhere?
    RUNNING = 'running'
    CANCELLING = 'cancelling'
    FINISHED = 'finished'                      # result holds done / failed / cancelled


CONFIRMING = frozenset({Phase.CONFIRM_RESUME, Phase.CONFIRM_DUPLICATE, Phase.CONFIRM_COLLISION, Phase.CONFIRM_SPACE})
ACTIVE = frozenset({Phase.RUNNING, Phase.CANCELLING})

TRANSITIONS = {
    Phase.IDLE: CONFIRMING | {Phase.RUNNING},
    Phase.FINISHED: CONFIRMING | {Phase.RUNNING},
    # Resume re-reads the playlist, then goes through the same checks as a new export.
    Phase.CONFIRM_RESUME: {Phase.IDLE, Phase.CONFIRM_DUPLICATE, Phase.CONFIRM_COLLISION, Phase.CONFIRM_SPACE,
                           Phase.RUNNING},
    Phase.CONFIRM_DUPLICATE: {Phase.IDLE, Phase.CONFIRM_COLLISION, Phase.CONFIRM_SPACE, Phase.RUNNING},
    Phase.CONFIRM_COLLISION: {Phase.IDLE, Phase.CONFIRM_SPACE, Phase.RUNNING},
    Phase.CONFIRM_SPACE: {Phase.IDLE, Phase.RUNNING},
    Phase.RUNNING: {Phase.CANCELLING, Phase.FINISHED},
    Phase.CANCELLING: {Phase.FINISHED},
}


class ExportFlow:
    def __init__(self):
        self.phase = Phase.IDLE
        self.result = 'idle'        # outcome of the last job: done / failed / cancelled
        self.manifest = None        # resumable checkpoint at the current destination, if any
        self.pending = None         # export prepared and waiting for confirmation / launch
        self.cancel_event = None    # set only while a job runs
        self.output = None          # album folder of the running or last job

    @property
    def active(self) -> bool:
        return self.phase in ACTIVE

    @property
    def confirming(self) -> bool:
        return self.phase in CONFIRMING

    def go(self, target: Phase) -> bool:
        if target not in TRANSITIONS.get(self.phase, ()):
            log.warning('export: refused transition %s -> %s', self.phase.value, target.value)
            return False
        self.phase = target
        return True

    # ------------------------------------------------------------ before the job
    def ask(self, question: Phase) -> bool:
        """Wait for the user's answer to one of the CONFIRMING questions."""
        assert question in CONFIRMING
        return self.go(question)

    def prepare(self, pending: dict) -> bool:
        """Remember what to export; refused while a job runs."""
        if self.active:
            return False
        self.pending = pending
        return True

    def abort(self) -> bool:
        """The user dismissed a question (or a step before launch failed): forget the prepared export."""
        self.pending = None
        return self.confirming and self.go(Phase.IDLE)

    def reset_stale(self) -> bool:
        """A new request starts over; a question left unanswered (e.g. resume failed) is dropped. False while running."""
        if self.active:
            return False
        self.abort()
        return True

    # ------------------------------------------------------------ the job
    def launch(self):
        """Start the prepared export: returns it, or None when there is none or a job already runs."""
        if self.pending is None or not self.go(Phase.RUNNING):
            return None
        pending, self.pending = self.pending, None
        self.cancel_event = threading.Event()
        self.output = pending['output']
        self.result = 'running'
        return pending

    def cancel(self) -> bool:
        if not self.go(Phase.CANCELLING):
            return False
        self.cancel_event.set()
        self.result = 'cancelling'
        return True

    def finish(self, failed: bool, cancelled: bool):
        """The worker returned. Gives the result, or None for a stray call when no job runs."""
        if not self.go(Phase.FINISHED):
            return None
        self.cancel_event = None
        self.result = 'cancelled' if cancelled else 'failed' if failed else 'done'
        return self.result
