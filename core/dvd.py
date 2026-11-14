"""
dvd.py

DVD-Video sources: a VIDEO_TS folder or a DVD ISO image.

Everything goes through ffmpeg's dvdvideo reader, which opens both the folder
and the ISO directly (no mounting) and can start and stop exactly on a
chapter. A DVD title is represented by a made-up path next to the disc,
"<disc>/Title 01.dvdtitle", so the rest of the app can keep passing one path
around; title_of() turns it back into (disc, title number).

Exports remux the title once into a Matroska file (stream copy; DVD LPCM is
rewritten as plain PCM, which is lossless) and then follow the normal MKV
route from there.
"""

from __future__ import annotations

import functools
import json
import re
import threading
from pathlib import Path
from typing import Callable, Optional

from . import tools
from .jobs import extracting
from .models import Chapter, Playlist, Track
from .tools import TOOL_PATHS

SUFFIX = ".dvdtitle"
MAX_TITLES = 99
_TITLE_RE = re.compile(r"^Title (\d{1,2})$")

_CODECS = {
    "mpeg2video": "MPEG-2", "mpeg1video": "MPEG-1", "pcm_dvd": "LPCM", "ac3": "AC-3", "eac3": "E-AC-3",
    "dts": "DTS", "mp2": "MP2", "mp1": "MP1", "dvd_subtitle": "VobSub",
}
_KINDS = {"video": "video", "audio": "audio", "subtitle": "subtitles"}


# ------------------------------------------------------------------ paths
def title_path(disc: Path, number: int) -> Path:
    return disc / f"Title {number:02d}{SUFFIX}"


def title_of(path: Path) -> Optional[tuple[Path, int]]:
    """(disc, title number) for a DVD title path, else None."""
    if path.suffix.lower() != SUFFIX:
        return None
    match = _TITLE_RE.match(path.stem)
    return (path.parent, int(match.group(1))) if match else None


def is_title(path: Path) -> bool:
    return title_of(Path(path)) is not None


def disc_folder(source: Path) -> Optional[Path]:
    """The DVD root for a folder that holds VIDEO_TS (or is VIDEO_TS itself)."""
    if not source.is_dir():
        return None
    if (source / "VIDEO_TS").is_dir() and not (source / "BDMV").is_dir():
        return source
    if source.name.upper() == "VIDEO_TS" and any(p.suffix.upper() == ".IFO" for p in source.iterdir()):
        return source.parent
    return None


def iso_looks_like_dvd(image: Path) -> bool:
    """A DVD image names VIDEO_TS in its first few megabytes; a Blu-ray one does not."""
    try:
        with open(image, "rb") as f:
            head = f.read(8 << 20)
    except OSError:
        return False
    return b"VIDEO_TS" in head and b"BDMV" not in head


@functools.lru_cache(maxsize=4)
def _supported(ffmpeg: str) -> bool:
    result = tools.run([ffmpeg, "-hide_banner", "-demuxers"], timeout=30)
    return any(line.split()[1:2] == ["dvdvideo"] for line in result.stdout.splitlines() if line.strip())


def supported() -> bool:
    """Whether the configured ffmpeg was built with the DVD reader (libdvdnav)."""
    try:
        return _supported(TOOL_PATHS["ffmpeg"])
    except Exception:
        return False


def require_support() -> None:
    if not supported():
        raise RuntimeError(
            "This ffmpeg cannot read DVDs (it was built without the dvdvideo reader). "
            "Use a full ffmpeg build, such as the gyan.dev \"full\" build, and choose it in Settings.")


def input_args(path: Path, *, chapter: Optional[int] = None, last_chapter: Optional[int] = None,
               seek: Optional[float] = None, preindex: bool = False) -> list[str]:
    """ffmpeg/ffprobe input options for one DVD title, ending with "-i <disc>"."""
    disc, number = title_of(Path(path))
    args = ["-f", "dvdvideo", "-title", str(number)]
    if preindex:
        args += ["-preindex", "1"]
    if chapter:
        args += ["-chapter_start", str(chapter), "-chapter_end", str(last_chapter or chapter)]
    elif seek:
        args += ["-ss", f"{seek:.3f}"]
    return args + ["-i", str(disc)]


# ------------------------------------------------------------------ reading
def _probe(path: Path, *, preindex: bool = False, timeout: float = 120) -> dict:
    result = tools.run([TOOL_PATHS["ffprobe"], "-v", "error", *input_args(path, preindex=preindex),
                             "-show_streams", "-show_chapters", "-show_format", "-of", "json"], timeout=timeout)
    data = {}
    try:
        data = json.loads(result.stdout or "{}")
    except ValueError:
        pass
    if result.returncode != 0 or not data.get("streams"):
        detail = "\n".join(line for line in (result.stderr or "").splitlines()
                           if "Unable to open device file" not in line).strip()
        raise RuntimeError(detail[-600:] or f"ffprobe could not read {path.name}")
    return data


def _track(stream: dict) -> Optional[Track]:
    kind = _KINDS.get(stream.get("codec_type", ""))
    if kind is None:
        return None
    name = stream.get("codec_name", "")
    tags = stream.get("tags") or {}
    bits = None
    if kind == "audio":
        bits = int(stream.get("bits_per_raw_sample") or 0) or (24 if stream.get("sample_fmt") == "s32" else 16
                                                                if name == "pcm_dvd" else None)
    track = Track(
        track_id=int(stream["index"]), kind=kind, codec=_CODECS.get(name, name.upper()), codec_id=name,
        language=tags.get("language", "") or "", channels=stream.get("channels"), title=tags.get("title", "") or "",
        sample_rate=int(stream["sample_rate"]) if stream.get("sample_rate") else None, bits_per_sample=bits,
        default_track=None, properties=dict(stream))
    rate = stream.get("bit_rate")
    if rate and str(rate).isdigit():
        track.bitrate_kbps = int(rate) / 1000
    elif name == "pcm_dvd" and track.sample_rate and bits and track.channels:
        track.bitrate_kbps = track.sample_rate * bits * track.channels / 1000
    return track


def _playlist(path: Path, data: dict) -> Playlist:
    playlist = Playlist(path=path)
    playlist.tracks = [t for t in (_track(s) for s in data.get("streams", [])) if t is not None]
    playlist.chapter_count = len(data.get("chapters") or [])
    try:
        playlist.duration_seconds = float((data.get("format") or {}).get("duration") or 0)
    except ValueError:
        pass
    return playlist


def inspect(path: Path) -> Playlist:
    return _playlist(Path(path), _probe(Path(path)))


def scan(disc: Path) -> list[Playlist]:
    """Every title on the disc (titles are numbered 1..n without gaps)."""
    require_support()
    titles = []
    for number in range(1, MAX_TITLES + 1):
        path = title_path(disc, number)
        try:
            titles.append(inspect(path))
        except RuntimeError as exc:
            if number == 1:
                raise RuntimeError(f"Could not read the DVD (is it encrypted or incomplete?):\n{exc}") from exc
            break
    return [t for t in titles if t.duration_seconds > 0 and (t.audio_tracks or t.video_track)]


@functools.lru_cache(maxsize=8)
def _chapters(path: str, stamp: tuple) -> tuple:
    # -preindex reads the title's navigation data once, so chapter times match the real stream
    # (the IFO's own times drift by seconds over a long title).
    data = _probe(Path(path), preindex=True, timeout=900)
    out = []
    for i, chapter in enumerate(data.get("chapters") or [], start=1):
        start, end = float(chapter["start_time"]), float(chapter["end_time"])
        out.append((i, start, end if end > start else None))
    return tuple(out)


def _stamp(path: Path) -> tuple:
    disc = title_of(path)[0]
    try:
        info = disc.stat()
        return info.st_size, int(info.st_mtime)
    except OSError:
        return ()


def read_chapters(path: Path) -> list[Chapter]:
    path = Path(path)
    return [Chapter(i, start, end) for i, start, end in _chapters(str(path), _stamp(path))]


def chapter_at(path: Path, seconds: float, tolerance: float = 0.5) -> Optional[int]:
    """The chapter that starts at `seconds` (previews then start exactly on it)."""
    try:
        chapters = read_chapters(path)
    except RuntimeError:
        return None
    return next((c.index for c in chapters if abs(c.start_seconds - seconds) <= tolerance), None)


# ------------------------------------------------------------------ export
def remux(path: Path, output: Path, *, tracks: Optional[list[Track]] = None,
          progress_cb: Optional[Callable[[str], None]] = None,
          cancel_event: Optional[threading.Event] = None) -> Path:
    """
    Copy one DVD title into a Matroska file with its chapters. With `tracks`,
    only those streams (in that order); otherwise every stream, so the file's
    track numbers match the title's stream numbers. DVD LPCM is rewritten as
    plain PCM (Matroska cannot hold it as is); nothing else is touched.
    """
    path = Path(path)
    playlist = inspect(path)
    chosen = tracks if tracks is not None else playlist.tracks
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mkv")
    args = [TOOL_PATHS["ffmpeg"], "-v", "error", "-y", *input_args(path, preindex=True)]
    for track in chosen:
        args += ["-map", f"0:{track.track_id}"]
    args += ["-map_chapters", "0", "-c", "copy"]
    for position, track in enumerate(chosen):
        if track.codec_id == "pcm_dvd":
            args += [f"-c:{position}", "pcm_s24le" if (track.bits_per_sample or 16) > 16 else "pcm_s16le"]
    args.append(str(partial))
    if progress_cb:
        progress_cb(extracting(
            f"Copying DVD title {title_of(path)[1]} ({len(chosen)} stream(s)) -> {output.name}"))
    result = tools.run(args, timeout=7200, cancel_event=cancel_event)
    if result.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        detail = "\n".join(line for line in (result.stderr or "").splitlines()
                           if "Unable to open device file" not in line).strip()
        raise RuntimeError(f"ffmpeg could not copy the DVD title:\n{detail[-800:]}")
    partial.replace(output)
    return output
