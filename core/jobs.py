"""Cancellation and progress messages shared by every long-running step."""

from __future__ import annotations

from typing import Optional


class JobCancelled(Exception):
    """Raised when a running job is stopped via a cancel_event."""


class Failure(RuntimeError):
    """
    Something went wrong that the user will read about. str() is the full English message, as
    before (logs, tests, the command line); the meaning rides along so a UI can say it in its
    own language instead of showing that wording:

    code:   what happened: "tool_failed" | "tool_timeout" | "tool_missing" | "no_chapters" |
            "tracks_unavailable" | "dvd_unsupported" | "dvd_unreadable" | "iso_failed" |
            "iso_missing" | "unreachable" | "http_error" | "bad_response" | "region_blocked"
    params: the names that go into the sentence (tool="mkvmerge", host="musicbrainz.org", ...)
    detail: the tool's or system's own words, shown under the sentence as they are
    """

    def __init__(self, code: str, message: str, detail: str = "", **params):
        super().__init__(message)
        self.code, self.detail, self.params = code, str(detail or "").strip(), params


def tool_failed(tool: str, output: str, what: str = "") -> Failure:
    """An external tool ended with an error; `what` says which step ("on chapter 3")."""
    head = f"{tool} failed{' ' + what if what else ''}"
    return Failure("tool_failed", f"{head}:\n{output}", detail=output, tool=tool)


class ProgressEvent(str):
    """
    A progress message that also says what it means, so a UI never has to
    parse the wording. It *is* the message text (prints, logs and compares
    like any str, so progress_cb=print keeps working); the meaning rides along:

    stage:   "extracting" | "splitting" | "cleanup" | "" (no change)
    chapter: the chapter the message is about, or None
    status:  that chapter's (or, without a chapter, the job's) state:
             "running" | "done" | "failed" | "cancelled" | ""

    fraction: how far into that chapter the job is (0..1), on the frequent
             updates of a running chapter only; these are not worth a log line

    Messages without a meaning (mkvmerge warnings, resume notes) stay plain str.
    """
    stage: str
    chapter: Optional[int]
    status: str
    fraction: Optional[float]

    def __new__(cls, text: str, stage: str = "", chapter: Optional[int] = None, status: str = "",
                fraction: Optional[float] = None):
        event = super().__new__(cls, text)
        event.stage, event.chapter, event.status, event.fraction = stage, chapter, status, fraction
        return event

    def __reduce__(self):   # keep the meaning when copied or pickled
        return (ProgressEvent, (str(self), self.stage, self.chapter, self.status, self.fraction))


def extracting(text: str) -> ProgressEvent:
    return ProgressEvent(text, stage="extracting")


def splitting(index: int, name: str) -> ProgressEvent:
    return ProgressEvent(f"Splitting chapter {index}: {name}", "splitting", index, "running")


def chapter_progress(index: int, fraction: float) -> ProgressEvent:
    return ProgressEvent(f"Chapter {index}: {fraction:.0%}", "splitting", index, "running", fraction)


def already_done(index: int, name: str) -> ProgressEvent:
    return ProgressEvent(f"Chapter {index} ({name}) already done - skipping.", "splitting", index, "done")


def cleaning_up() -> ProgressEvent:
    return ProgressEvent("Cleaning up temporary files...", stage="cleanup")


def job_failed(exc: BaseException) -> ProgressEvent:
    return ProgressEvent(f"Failed: {exc}", status="failed")


def job_cancelled() -> ProgressEvent:
    return ProgressEvent("Cancelled.", status="cancelled")
