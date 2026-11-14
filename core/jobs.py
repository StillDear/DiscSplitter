"""Cancellation and progress messages shared by every long-running step."""

from __future__ import annotations

from typing import Optional


class JobCancelled(Exception):
    """Raised when a running job is stopped via a cancel_event."""


class ProgressEvent(str):
    """
    A progress message that also says what it means, so a UI never has to
    parse the wording. It *is* the message text (prints, logs and compares
    like any str, so progress_cb=print keeps working); the meaning rides along:

    stage:   "extracting" | "splitting" | "cleanup" | "" (no change)
    chapter: the chapter the message is about, or None
    status:  that chapter's (or, without a chapter, the job's) state:
             "running" | "done" | "failed" | "cancelled" | ""

    Messages without a meaning (mkvmerge warnings, resume notes) stay plain str.
    """
    stage: str
    chapter: Optional[int]
    status: str

    def __new__(cls, text: str, stage: str = "", chapter: Optional[int] = None, status: str = ""):
        event = super().__new__(cls, text)
        event.stage, event.chapter, event.status = stage, chapter, status
        return event

    def __reduce__(self):   # keep the meaning when copied or pickled
        return (ProgressEvent, (str(self), self.stage, self.chapter, self.status))


def extracting(text: str) -> ProgressEvent:
    return ProgressEvent(text, stage="extracting")


def splitting(index: int, name: str) -> ProgressEvent:
    return ProgressEvent(f"Splitting chapter {index}: {name}", "splitting", index, "running")


def already_done(index: int, name: str) -> ProgressEvent:
    return ProgressEvent(f"Chapter {index} ({name}) already done - skipping.", "splitting", index, "done")


def cleaning_up() -> ProgressEvent:
    return ProgressEvent("Cleaning up temporary files...", stage="cleanup")


def job_failed(exc: BaseException) -> ProgressEvent:
    return ProgressEvent(f"Failed: {exc}", status="failed")


def job_cancelled() -> ProgressEvent:
    return ProgressEvent("Cancelled.", status="cancelled")
