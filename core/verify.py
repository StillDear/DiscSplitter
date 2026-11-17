"""Checking finished files against what the export planned."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import tools
from .models import Chapter, Track
from .tools import TOOL_PATHS


# ---------------------------------------------------------------------------
# Checking finished files
# ---------------------------------------------------------------------------

@dataclass
class VerifyIssue:
    code: str                 # missing | probe | duration | audio | video | subtitles | codec | title
    expected: str = ""
    actual: str = ""


@dataclass
class VerifyResult:
    path: Path
    chapter_index: int
    issues: list[VerifyIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def duration_tolerance(container: str, keep_video: bool) -> float:
    """
    How far a file's length may differ from its chapter. Video cuts land on
    keyframes (about every second on Blu-ray), at both ends; audio-only cuts
    land on an audio frame; FLAC is cut to the sample.
    """
    if container.lower() == "flac":
        return 0.25
    return 2.5 if keep_video else 0.75


SYNC_TOLERANCE = 0.25     # sound may start a frame or two before or after the first picture, as on the disc


def verify_output(path: Path, chapter: Chapter, *, container: str, audio_tracks: list[Track],
                  subtitle_count: int, keep_video: bool, title: str,
                  probe: Optional[Callable[[Path], dict]] = None, video_count: int = 1) -> VerifyResult:
    """
    Read a finished file back with ffprobe and compare it with what was asked
    for: its length, the streams it carries, that sound and picture start
    together, and its title tag (an M2TS has none). Nothing is decoded, so this
    takes a fraction of a second per file. video_count: the video streams a
    picture copy carries (2 with a Dolby Vision enhancement layer).
    """
    result = VerifyResult(path, chapter.index)
    issues = result.issues
    if not path.is_file() or path.stat().st_size == 0:
        issues.append(VerifyIssue("missing"))
        return result
    try:
        info = (probe or _probe_file)(path)
    except Exception as exc:   # an unreadable file is exactly what this check is for
        issues.append(VerifyIssue("probe", actual=str(exc).strip().splitlines()[-1] if str(exc).strip() else ""))
        return result
    streams = info.get("streams") or []
    kinds = [s.get("codec_type") for s in streams]
    # Cover art embedded in a FLAC shows up as a video stream marked as an attached picture.
    pictures = sum(1 for s in streams if s.get("codec_type") == "video"
                   and (s.get("disposition") or {}).get("attached_pic"))
    videos = kinds.count("video") - pictures
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    flac = container.lower() == "flac"

    expected_length = chapter.duration
    try:
        actual_length = float((info.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        actual_length = None
    if expected_length is not None and actual_length is not None and \
            abs(actual_length - expected_length) > duration_tolerance(container, keep_video):
        issues.append(VerifyIssue("duration", f"{expected_length:.2f}", f"{actual_length:.2f}"))

    want_audio = 1 if flac else len(audio_tracks)
    if len(audios) != want_audio:
        issues.append(VerifyIssue("audio", str(want_audio), str(len(audios))))
    want_video = max(1, video_count) if keep_video and not flac else 0
    if videos != want_video:
        issues.append(VerifyIssue("video", str(want_video), str(videos)))
    if not flac and kinds.count("subtitle") != subtitle_count:
        issues.append(VerifyIssue("subtitles", str(subtitle_count), str(kinds.count("subtitle"))))
    if flac and audios and audios[0].get("codec_name") != "flac":
        issues.append(VerifyIssue("codec", "flac", str(audios[0].get("codec_name") or "")))
    if want_video and audios:
        offset = _start_offset(streams)
        if offset is not None and abs(offset) > SYNC_TOLERANCE:
            issues.append(VerifyIssue("sync", f"±{SYNC_TOLERANCE * 1000:.0f} ms", f"{offset * 1000:+.0f} ms"))

    tags = {str(k).lower(): str(v) for k, v in ((info.get("format") or {}).get("tags") or {}).items()}
    if title and container.lower() != "m2ts" and tags.get("title", "").strip() != title.strip():
        issues.append(VerifyIssue("title", title, tags.get("title", "")))
    return result


def excuse_silent_end(result: VerifyResult, chapter: Chapter, *, container: str, keep_video: bool,
                      sound: Callable[[float, float], Optional[float]], slack: float = 0.1) -> bool:
    """
    A file of sound only that is shorter than its chapter because the source's sound ends before the picture does
    (a closing screen with no sound after the last song): the chapter's length counts its picture, so that is not a
    file cut short. sound(start, length) gives the seconds of sound the source holds from `start` on the disc's
    timeline, None when it cannot tell. The tail is read from a little before where the file ends; when the source
    has no more sound past that point than the file has, the length issue is dropped. slack: how early the source's
    seek may land (about a second on a DVD). True when the issue was dropped.
    """
    issue = next((i for i in result.issues if i.code == "duration"), None)
    if issue is None or (keep_video and container.lower() != "flac"):
        return False
    try:
        expected, actual = float(issue.expected), float(issue.actual)
    except ValueError:
        return False
    if actual >= expected:
        return False
    lead = min(2.0, actual)
    measured = sound(chapter.start_seconds + actual - lead, expected - actual + lead)
    if measured is None or measured > lead + duration_tolerance(container, keep_video) + slack:
        return False
    result.issues.remove(issue)
    return True


def _start_offset(streams: list[dict]) -> Optional[float]:
    """How much later the first sound starts than the first picture (seconds); None when not stated."""
    def first(kind: str) -> Optional[float]:
        times = []
        for s in streams:
            if s.get("codec_type") == kind and not (s.get("disposition") or {}).get("attached_pic"):
                try:
                    times.append(float(s.get("start_time")))
                except (TypeError, ValueError):
                    pass
        return min(times) if times else None
    video, audio = first("video"), first("audio")
    return None if video is None or audio is None else audio - video


def _probe_file(path: Path) -> dict:
    result = tools.run([TOOL_PATHS["ffprobe"], "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                   str(path)], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"ffprobe exited with {result.returncode}")
    return json.loads(result.stdout)
