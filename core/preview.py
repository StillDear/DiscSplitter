"""
preview.py

Audio preview: decode one chapter of one audio track into a small stereo
FLAC that the GUI can play straight away.

Blu-ray playlists (.mpls) are not opened through ffmpeg's bluray: reader,
because seeking inside it is unreliable. Instead the playlist's PlayItems
are read here, the chapter time is mapped to a clip file plus an offset,
and ffmpeg seeks directly in that .m2ts - a fast keyframe seek.
"""

from __future__ import annotations

import array
import subprocess
from contextlib import ExitStack, contextmanager
import threading
from pathlib import Path
from typing import Callable, Optional

from . import bluray_iso, dvd, jobs, models, sources, tools
from .engine import TS_SUFFIXES

MAX_PREVIEW_SECONDS = 15 * 60   # a chapter longer than this is previewed from its start only
# The .mpls reader lives in sources (scans need it too); re-exported for callers here.
CLOCK = sources.MPLS_CLOCK
PlayItem = sources.PlayItem
read_play_items = sources.read_play_items
locate = sources.locate_play_item


def _start_time(path: Path) -> float:
    """First timestamp of a transport stream (m2ts clocks rarely start at zero)."""
    result = tools.run([tools.TOOL_PATHS["ffprobe"], "-v", "error", "-show_entries", "format=start_time",
                             "-of", "default=nw=1:nk=1", str(path)], timeout=60)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _by_pid(source: Path, track: models.Track) -> bool:
    """A transport stream read by the engine: its track IDs are PIDs, which ffmpeg selects with 0:i:<pid>."""
    return source.suffix.lower() in TS_SUFFIXES and bool(track.stream_id)


def _stream(source: Path, track: models.Track) -> str:
    return f"0:i:{track.stream_id:#x}" if _by_pid(source, track) else f"0:{track.track_id}"


def clip_input(source: Path, track: models.Track, audio_index: int, start: float,
               length: float) -> tuple[list[str], float]:
    """ffmpeg input arguments (seek, file, stream map) and the playable length."""
    if source.suffix.lower() == ".mpls":
        item, offset = locate(read_play_items(source), start)
        m2ts = source.parent.parent / "STREAM" / f"{item.clip}.m2ts"
        if not m2ts.is_file():
            m2ts = m2ts.with_suffix(".M2TS")
        seek = item.in_seconds + offset - _start_time(m2ts)
        length = min(length, item.length - offset)   # a preview stays inside one clip
        stream = f"0:i:{track.stream_id:#x}" if track.stream_id else f"0:a:{audio_index}"
        return ["-ss", f"{max(0.0, seek):.3f}", "-i", str(m2ts), "-map", stream], length
    if dvd.is_title(source):
        # Starting on a chapter is exact; a plain seek on a DVD lands up to a second early.
        chapter = dvd.chapter_at(source, start)
        inputs = dvd.input_args(source, chapter=chapter) if chapter else \
            dvd.input_args(source, seek=start)
        return [*inputs, "-map", f"0:{track.track_id}"], length
    if _by_pid(source, track):          # m2ts clocks rarely start at zero
        start += _start_time(source)
    return ["-ss", f"{start:.3f}", "-i", str(source), "-map", _stream(source, track)], length


def _probe_target(source: Path, track: models.Track, kind_index: int, kind: str) -> tuple[list[str], str]:
    """ffprobe input arguments and stream selector for one track of a source."""
    if source.suffix.lower() == ".mpls":
        items = read_play_items(source)
        if not items:
            return [], ""
        target = source.parent.parent / "STREAM" / f"{items[0].clip}.m2ts"
        if not target.is_file():
            target = target.with_suffix(".M2TS")
        letter = {"audio": "a", "video": "v"}.get(kind, "s")
        return [str(target)], f"i:{track.stream_id:#x}" if track.stream_id else f"{letter}:{kind_index}"
    inputs = dvd.input_args(source) if dvd.is_title(source) else [str(source)]
    return inputs, f"i:{track.stream_id:#x}" if _by_pid(source, track) else str(track.track_id)


def probe_stream(source: Path, track: models.Track, kind_index: int, kind: str = "audio") -> dict:
    """
    ffprobe's view of one stream (decoder name, profile, channel layout, sample format...).
    For video the first decoded frame is added as "frame" (scan type, colour, HDR side data).
    """
    inputs, select = _probe_target(source, track, kind_index, kind)
    if not inputs:
        return {}
    extra = ["-read_intervals", "%+#1", "-show_frames"] if kind == "video" else []
    result = tools.run([tools.TOOL_PATHS["ffprobe"], "-v", "error", "-select_streams", select,
                             "-show_streams", *extra, "-of", "json", *inputs], timeout=60)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "ffprobe failed").strip()[-400:])
    import json
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    stream = dict(streams[0]) if streams else {}
    if stream and data.get("frames"):
        stream["frame"] = data["frames"][0]
    return stream


SAMPLE_SECONDS = 60


def sample_bitrate(source: Path, track: models.Track, kind_index: int, kind: str = "video",
                   at: float = 0.0, seconds: float = SAMPLE_SECONDS) -> Optional[float]:
    """
    Average bitrate (kbps) of one stream measured over `seconds` of packets starting
    `at` seconds in: discs rarely state a video bitrate, so it is counted instead.
    """
    inputs, select = _probe_target(source, track, kind_index, kind)
    if not inputs:
        return None
    result = tools.run([tools.TOOL_PATHS["ffprobe"], "-v", "error", "-select_streams", select,
                             "-read_intervals", f"{at:.3f}%+{seconds:g}", "-show_entries", "packet=size,dts_time",
                             "-of", "json", *inputs], timeout=120)
    import json
    try:
        packets = json.loads(result.stdout or "{}").get("packets") or []
    except ValueError:
        packets = []
    size, times = 0, []
    for packet in packets:
        try:
            size += int(packet["size"])
            times.append(float(packet["dts_time"]))
        except (KeyError, TypeError, ValueError):
            continue
    span = (max(times) - min(times)) if len(times) > 1 else 0
    return size * 8 / span / 1000 if span >= 1 else None


class MountKeeper:
    """
    Keeps one Blu-ray ISO mounted between previews (mounting costs about a
    second each time). Several jobs may use the mount at once (a preview and
    the waveform scan); close() waits until none does, then ejects the image.
    """

    def __init__(self):
        self.lock = threading.Condition()
        self._image = None
        self._stack = None
        self._root = None
        self._users = 0

    @property
    def mounted(self) -> bool:
        """Whether an image is being kept mounted right now."""
        return self._image is not None

    @contextmanager
    def use(self, playlist: Path, image: Optional[Path]):
        """Yield the playlist path on disk, keeping the image mounted while the block runs."""
        if image is None:
            yield playlist
            return
        with self.lock:
            if self._image != image:
                self.lock.wait_for(lambda: self._users == 0)
                self._close()
                stack = ExitStack()
                self._root = stack.enter_context(bluray_iso.mounted(image))
                self._stack, self._image = stack, image
            root = self._root
            self._users += 1
        try:
            yield root / playlist
        finally:
            with self.lock:
                self._users -= 1
                self.lock.notify_all()

    def _close(self):
        stack, self._stack, self._image, self._root = self._stack, None, None, None
        if stack is not None:
            stack.close()

    def close(self):
        """Eject the kept image once every user is done (cancel them first)."""
        with self.lock:
            self.lock.wait_for(lambda: self._users == 0)
            self._close()


def _clip_length(start: float, end: Optional[float]) -> float:
    return min(MAX_PREVIEW_SECONDS, (end - start) if end is not None else MAX_PREVIEW_SECONDS)


def _finish(result, partial: Path, output: Path, what: str) -> Path:
    if result.returncode != 0 or not partial.is_file() or partial.stat().st_size < 1024:
        partial.unlink(missing_ok=True)
        raise RuntimeError((result.stderr or f"ffmpeg produced no {what}").strip()[-600:])
    partial.replace(output)
    return output


def render(source: Path, track: models.Track, audio_index: int, start: float, end: Optional[float],
           output: Path, cancel_event: Optional[threading.Event] = None) -> Path:
    """Decode [start, end) of one audio track to a stereo FLAC at `output`."""
    args, length = clip_input(source, track, audio_index, start, _clip_length(start, end))
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.flac")
    command = [tools.TOOL_PATHS["ffmpeg"], "-v", "error", "-y", *args,
               "-t", f"{max(0.5, length):.3f}", "-vn", "-sn", "-dn",
               "-ac", "2", "-c:a", "flac", "-compression_level", "0", str(partial)]
    return _finish(tools.run(command, timeout=600, cancel_event=cancel_event), partial, output, "audio")


def render_video(source: Path, track: models.Track, audio_index: int, video: models.Track,
                 start: float, end: Optional[float], output: Path,
                 cancel_event: Optional[threading.Event] = None) -> Path:
    """
    One chapter with picture: the video stream is copied untouched (chapters
    start on keyframes, so this is what the export will contain), the audio
    is a stereo FLAC downmix any player can handle.
    """
    args, length = clip_input(source, track, audio_index, start, _clip_length(start, end))
    audio_map = args[-2:]
    if source.suffix.lower() == ".mpls":
        video_map = ["-map", f"0:i:{video.stream_id:#x}" if video.stream_id else "0:v:0"]
    else:
        video_map = ["-map", _stream(source, video)]
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mkv")
    command = [tools.TOOL_PATHS["ffmpeg"], "-v", "error", "-y", *args[:-2], *video_map, *audio_map,
               "-t", f"{max(0.5, length):.3f}", "-sn", "-dn", "-c:v", "copy",
               "-ac", "2", "-c:a", "flac", "-compression_level", "0", str(partial)]
    return _finish(tools.run(command, timeout=900, cancel_event=cancel_event), partial, output, "video")


def _peak(chunk) -> float:
    return round(max(max(chunk), -min(chunk)) / 32768, 3)


def _ripple(chunk, parts: int = 10) -> float:
    """
    How much the level swings inside one outline step (coefficient of variation of the
    level in `parts` short frames). Speech rises and drops with every syllable and pause,
    music holds its level: talk scores high, songs and background music low.
    """
    size = max(1, len(chunk) // parts)
    levels = [sum(abs(x) for x in chunk[i:i + size]) / size for i in range(0, size * parts, size) if chunk[i:i + size]]
    mean = sum(levels) / len(levels) if levels else 0
    if mean < 20:                  # near silence: no telling
        return 0.0
    var = sum((x - mean) ** 2 for x in levels) / len(levels)
    return round(min(3.0, var ** 0.5 / mean), 3)


def _run_bytes(args: list[str], timeout: float = 300) -> bytes:
    result = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                            creationflags=tools.NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip()[-400:] or "ffmpeg failed")
    return result.stdout


def clip_peaks(clip: Path, buckets: int = 800) -> list[float]:
    """Loudness outline of a preview clip: about `buckets` peaks between 0 and 1."""
    data = _run_bytes([tools.TOOL_PATHS["ffmpeg"], "-v", "error", "-i", str(clip), "-map", "0:a:0",
                       "-ac", "1", "-ar", "4000", "-f", "s16le", "-"])
    samples = array.array("h")
    samples.frombytes(data[:len(data) - len(data) % 2])
    if not samples:
        return []
    size = max(1, len(samples) // buckets)
    return [_peak(samples[i:i + size]) for i in range(0, len(samples), size)]


DISC_RATE = 400          # samples per second decoded for the whole-disc outline
DISC_PER_SECOND = 2      # peaks kept per second


def disc_peaks(source: Path, track: models.Track, audio_index: int, total_seconds: float,
               progress: Optional[Callable[[float], None]] = None,
               cancel_event: Optional[threading.Event] = None,
               ripple: Optional[list] = None) -> list[float]:
    """
    Outline of the whole programme (DISC_PER_SECOND peaks per second), read in
    one pass. Blu-ray playlists go through ffmpeg's bluray reader, which plays
    every clip in order (no seeking needed here).
    """
    if source.suffix.lower() == ".mpls":
        disc_root = source.parent.parent.parent
        stream = f"0:i:{track.stream_id:#x}" if track.stream_id else f"0:a:{audio_index}"
        inputs = ["-playlist", str(int(source.stem)), "-i", f"bluray:{disc_root}", "-map", stream]
    elif dvd.is_title(source):
        inputs = [*dvd.input_args(source), "-map", f"0:{track.track_id}"]
    else:
        inputs = ["-i", str(source), "-map", _stream(source, track)]
    command = [tools.TOOL_PATHS["ffmpeg"], "-v", "error", *inputs, "-vn", "-sn", "-dn",
               "-ac", "1", "-ar", str(DISC_RATE), "-f", "s16le", "-"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                               creationflags=tools.NO_WINDOW)
    per_peak = DISC_RATE // DISC_PER_SECOND
    expected = max(1.0, total_seconds * DISC_RATE)
    peaks: list[float] = []
    pending = b""
    read = 0
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise jobs.JobCancelled("Waveform cancelled")
            data = process.stdout.read(per_peak * 2 * 200)
            if not data:
                break
            pending += data
            usable = len(pending) - len(pending) % (per_peak * 2)
            samples = array.array("h")
            samples.frombytes(pending[:usable])
            pending = pending[usable:]
            peaks.extend(_peak(samples[i:i + per_peak]) for i in range(0, len(samples), per_peak))
            if ripple is not None:         # filled alongside: one value per peak
                ripple.extend(_ripple(samples[i:i + per_peak]) for i in range(0, len(samples), per_peak))
            read += len(samples)
            if progress:
                progress(min(0.99, read / expected))
        process.wait(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
    if not peaks:
        raise RuntimeError("ffmpeg returned no audio for the waveform")
    return peaks
