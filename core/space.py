"""Disk space: a rough estimate of what an export writes, checked before it starts."""

from __future__ import annotations

import shutil
import struct
from pathlib import Path
from typing import Optional

from . import dvd
from . import sources
from .models import Chapter, Playlist, Track
from .sources import is_mkv_source


# ---------------------------------------------------------------------------
# Disk space: a rough estimate of what an export writes, checked before it starts
# ---------------------------------------------------------------------------

SPACE_MARGIN = 1.05                  # estimates are rough: ask for 5% more...
SPACE_RESERVE = 64 * 1024 * 1024     # ...and a little room for tags, covers and the job's own files
FLAC_RATIO = 0.7                     # FLAC is typically 50-70% of the PCM it encodes; take the high end


def source_size_bytes(path: Path) -> Optional[int]:
    """
    Bytes behind one playlist / file: the .m2ts clips a Blu-ray playlist plays
    (each counted once, whole) or the MKV itself. None when it can't be told.
    """
    try:
        if path.suffix.lower() == ".mpls":
            stream = path.parent.parent / "STREAM"
            clips = {item.clip for item in sources.read_play_items(path)}
            sizes = [(stream / f"{clip}.m2ts").stat().st_size for clip in clips]
            return sum(sizes) or None
        if is_mkv_source(path):
            return path.stat().st_size or None
        title = dvd.title_of(path)
        if title is not None:          # a DVD: the image, or every VOB (nearly all of it is the main title)
            disc = title[0]
            if disc.is_file():
                return disc.stat().st_size or None
            folder = disc / "VIDEO_TS"
            return sum(p.stat().st_size for p in folder.iterdir() if p.suffix.upper() == ".VOB") or None
    except (OSError, ValueError, struct.error):
        return None
    return None


LOSSLESS_PACKED_RATIO = 0.6   # TrueHD / DTS-HD MA without a stated bitrate: about 60% of the same PCM


def _is_pcm(track: Track) -> bool:
    return "pcm" in track.codec.lower() or "pcm" in track.codec_id.lower()


def audio_rate_bytes(track: Track) -> Optional[float]:
    """
    Bytes per second of an audio track as stored: its stated bitrate, the exact
    rate of PCM, or for packed lossless audio (TrueHD, DTS-HD MA, whose rate
    discs rarely state) an estimate from its sample rate and channels.
    """
    if track.bitrate_kbps:
        return track.bitrate_kbps * 1000 / 8
    pcm = pcm_rate_bytes(track)
    if pcm is None:
        return None
    if _is_pcm(track):
        return pcm
    codec = track.codec.lower()
    if any(h in codec for h in ("truehd", "dts-hd master", "flac", "alac", "mlp")):
        return pcm * LOSSLESS_PACKED_RATIO
    return None


def pcm_rate_bytes(track: Track) -> Optional[float]:
    """The rate of the track decoded to PCM (24-bit assumed when the depth is not stated)."""
    if track.sample_rate and track.channels:
        return track.sample_rate * (track.bits_per_sample or 24) * track.channels / 8
    return None


def estimate_export_bytes(playlist: Playlist, chapters: list[Chapter], *, audio_track_ids: list[int],
                          keep_video: bool, container: str, source_size: Optional[int]) -> Optional[int]:
    """
    Space an export needs at its peak, from bitrates: the selected audio
    tracks' own rates, and for the picture (whose rate the disc does not
    state) the source's average rate minus its known audio. FLAC adds the
    whole-programme audio file it extracts first. None when there is not
    enough to go on; the caller then skips the check rather than guess.
    """
    duration = playlist.duration_seconds
    seconds = sum(((c.end_seconds if c.end_seconds is not None else duration) or 0) - c.start_seconds
                  for c in chapters)
    seconds = max(0.0, seconds)
    if not chapters or seconds <= 0:
        return 0
    selected = [t for t in playlist.audio_tracks if t.track_id in audio_track_ids]
    if not selected:
        return None
    if dvd.is_title(playlist.path):
        return None      # a DVD title is remuxed whole first, and its size is not read here

    if container.lower() == "flac":
        track = selected[0]
        stored = audio_rate_bytes(track)
        pcm = pcm_rate_bytes(track)
        out_rate = pcm * FLAC_RATIO if pcm else stored
        if stored is None or out_rate is None:
            return None
        needed = stored * (duration or seconds) + out_rate * seconds
    else:
        rates = [audio_rate_bytes(t) for t in selected]
        if any(r is None for r in rates):
            return None
        needed = sum(rates) * seconds
        if keep_video and playlist.video_track is not None:
            if not source_size or not duration:
                return None
            known_audio = sum(audio_rate_bytes(t) or 0 for t in playlist.audio_tracks)
            rest = max(0.0, source_size / duration - known_audio)     # picture, subtitles, unknown audio, overhead
            needed += rest * seconds
    return int(needed * SPACE_MARGIN + SPACE_RESERVE)


def estimate_output_bytes(playlist: Playlist, chapters: list[Chapter], *, audio_tracks: list[Track],
                          keep_video: bool, container: str, source_size: Optional[int]) -> Optional[int]:
    """
    How big the finished files will be (no working files, no safety margin): the
    selected audio at its own rate (FLAC at a typical ratio of the PCM), plus for
    MKV with picture the source's average rate minus its known audio. None when
    there is not enough to go on.
    """
    duration = playlist.duration_seconds
    seconds = max(0.0, sum(((c.end_seconds if c.end_seconds is not None else duration) or 0) - c.start_seconds
                           for c in chapters))
    if not chapters or seconds <= 0:
        return 0
    if not audio_tracks:
        return None
    if container.lower() == "flac":
        pcm = pcm_rate_bytes(audio_tracks[0])
        rate = pcm * FLAC_RATIO if pcm else audio_rate_bytes(audio_tracks[0])
        return int(rate * seconds) if rate else None
    rates = [audio_rate_bytes(t) for t in audio_tracks]
    if any(r is None for r in rates):
        return None
    total = sum(rates) * seconds
    if keep_video and playlist.video_track is not None:
        if not source_size or not duration:
            return None
        known_audio = sum(audio_rate_bytes(t) or 0 for t in playlist.audio_tracks)
        total += max(0.0, source_size / duration - known_audio) * seconds
    return int(total)


def free_space_bytes(folder: Path) -> Optional[int]:
    """Free bytes on the drive a folder is (or will be) on."""
    probe = Path(folder)
    while not probe.exists():
        if probe.parent == probe:
            return None
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None
