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


def verify_output(path: Path, chapter: Chapter, *, container: str, audio_tracks: list[Track],
                  subtitle_count: int, keep_video: bool, title: str,
                  probe: Optional[Callable[[Path], dict]] = None) -> VerifyResult:
    """
    Read a finished file back with ffprobe and compare it with what was asked
    for: its length, the streams it carries and its title tag. Nothing is
    decoded, so this takes a fraction of a second per file.
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
    want_video = 1 if keep_video and not flac else 0
    if videos != want_video:
        issues.append(VerifyIssue("video", str(want_video), str(videos)))
    if not flac and kinds.count("subtitle") != subtitle_count:
        issues.append(VerifyIssue("subtitles", str(subtitle_count), str(kinds.count("subtitle"))))
    if flac and audios and audios[0].get("codec_name") != "flac":
        issues.append(VerifyIssue("codec", "flac", str(audios[0].get("codec_name") or "")))

    tags = {str(k).lower(): str(v) for k, v in ((info.get("format") or {}).get("tags") or {}).items()}
    if title and tags.get("title", "").strip() != title.strip():
        issues.append(VerifyIssue("title", title, tags.get("title", "")))
    return result


def _probe_file(path: Path) -> dict:
    result = tools.run([TOOL_PATHS["ffprobe"], "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                   str(path)], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"ffprobe exited with {result.returncode}")
    return json.loads(result.stdout)
