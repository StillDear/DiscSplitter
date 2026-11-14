"""Finding and inspecting sources: Blu-ray folders and images, DVDs, Matroska files; playlist scoring."""

from __future__ import annotations

import dataclasses
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import bluray_iso
from . import dvd
from . import tools
from .models import Playlist, Track
from .tools import TOOL_PATHS


# ---------------------------------------------------------------------------
# Disc / folder scanning
# ---------------------------------------------------------------------------


def find_playlists(disc_folder: Path) -> list[Path]:
    """Find .mpls playlist files under BDMV/PLAYLIST (ignores BACKUP)."""
    playlist_dir = disc_folder / "BDMV" / "PLAYLIST"
    if not playlist_dir.is_dir():
        return []
    return sorted(playlist_dir.glob("*.mpls"))


def is_mkv_source(source: Path) -> bool:
    """Whether source is an existing Matroska file supported by the GUI."""
    return source.is_file() and source.suffix.lower() in {".mkv", ".mk3d", ".mka"}


def find_sources(source: Path) -> list[Path]:
    """Find Blu-ray playlists or top-level Matroska files, preferring BDMV."""
    if is_mkv_source(source):
        return [source]
    if not source.is_dir():
        return []
    if (source / "BDMV").is_dir():
        return find_playlists(source)
    return sorted(p for p in source.iterdir() if is_mkv_source(p))


def scan_source(source: Path) -> list[Playlist]:
    """Inspect a GUI source while retaining the legacy disc scan entry point."""
    if bluray_iso.is_iso(source):
        image = source.resolve()
        # DVD images are read straight from the file by ffmpeg; no mounting.
        if dvd.iso_looks_like_dvd(image):
            return dvd.scan(image)
        with bluray_iso.mounted(image) as root:
            if not (root / "BDMV").is_dir() and (root / "VIDEO_TS").is_dir():
                is_dvd = True
            else:
                is_dvd = False
                found = [dataclasses.replace(playlist, path=playlist.path.relative_to(root), iso_image=image)
                         for playlist in scan_disc_folder(root)]
        return dvd.scan(image) if is_dvd else found
    disc = dvd.disc_folder(source)
    if disc is not None:
        return dvd.scan(disc)
    candidates = find_sources(source)
    if source.is_dir() and ((source / "BDMV").is_dir() or not candidates):
        return scan_disc_folder(source)
    return [inspect_playlist(p) for p in candidates]


_GENERIC_NAMES = {"video_ts", "dvdimage", "image", "disc", "disk", "dvd", "bdmv", "bd"}


def source_name_path(source: Path) -> Path:
    """Use the source filename without its extension for album naming."""
    named = source.with_suffix("") if is_mkv_source(source) or bluray_iso.is_iso(source) else source
    # "VIDEO_TS" or "DVDIMAGE.ISO" say nothing about the album: the folder around them does.
    if named.name.lower() in _GENERIC_NAMES and named.parent != named:
        return named.parent
    return named


def inspect_playlist(playlist_path: Path) -> Playlist:
    """
    Run `mkvmerge -J` on a playlist and parse the resulting JSON for
    tracks and chapter count.

    JSON (rather than the human-readable `mkvmerge -i` text output) is
    used deliberately: the text format isn't a stable interface - its
    wording, spacing, and line layout can shift between MKVToolNix
    versions or with locale settings, which is exactly the kind of thing
    that quietly breaks a regex without any obvious error. The JSON
    schema is the format MKVToolNix documents and maintains for tooling.
    """
    if dvd.is_title(playlist_path):
        return dvd.inspect(playlist_path)
    result = tools.run([TOOL_PATHS["mkvmerge"], "-J", str(playlist_path)], timeout=60)
    # mkvmerge returns 0 for a clean read and 1 for warnings (still usable
    # output), but 2 means it couldn't read the file at all - in that case
    # stdout won't have useful track/chapter info, so surface the real
    # error instead of silently reporting "no Atmos track".
    if result.returncode >= 2:
        raise RuntimeError(
            f"mkvmerge could not read {playlist_path.name}:\n{result.stderr or result.stdout}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"mkvmerge produced output that wasn't valid JSON for "
            f"{playlist_path.name}: {exc}\n"
            f"First 2000 chars of output:\n{result.stdout[:2000]}"
        ) from exc

    pl = Playlist(path=playlist_path)

    for t in data.get("tracks", []):
        props = t.get("properties") or {}
        track_id = t.get("id")
        if track_id is None:
            continue  # malformed entry - skip rather than crash on a bad track_id
        pl.tracks.append(
            Track(
                track_id=track_id,
                kind=t.get("type", ""),
                codec=t.get("codec", ""),
                codec_id=props.get("codec_id", "") or "",
                language=props.get("language", "") or "",
                channels=props.get("audio_channels"),
                title=props.get("track_name", "") or "",
                sample_rate=props.get("audio_sampling_frequency"),
                bits_per_sample=props.get("audio_bits_per_sample"),
                default_track=props.get("default_track"),
                stream_id=props.get("stream_id") if playlist_path.suffix.lower() == ".mpls" else None,
                properties=dict(props),
            )
        )

    chapters = data.get("chapters") or []
    if chapters:
        # mkvmerge -J groups chapters into one "edition"; a Blu-ray
        # playlist normally has exactly one, so take the first.
        pl.chapter_count = chapters[0].get("num_entries", 0)

    duration_ns = ((data.get("container") or {}).get("properties") or {}).get("duration")
    if duration_ns:
        pl.duration_seconds = duration_ns / 1_000_000_000
    elif playlist_path.suffix.lower() == ".mpls":
        # mkvmerge leaves the duration out for some playlists (seen on ISO images):
        # the PlayItems' in/out times give it exactly.
        try:
            pl.duration_seconds = sum(item.length for item in read_play_items(playlist_path))
        except (OSError, ValueError, struct.error):
            pass

    _enrich_bitrates_ffprobe(pl)

    return pl


# ---------------------------------------------------------------------------
# Blu-ray playlist (.mpls) PlayItems
# ---------------------------------------------------------------------------

MPLS_CLOCK = 45_000             # MPLS timestamps tick at 45 kHz


@dataclass
class PlayItem:
    clip: str          # e.g. "00001" -> BDMV/STREAM/00001.m2ts
    in_seconds: float  # position in the clip's own timeline
    out_seconds: float

    @property
    def length(self) -> float:
        return max(0.0, self.out_seconds - self.in_seconds)


def read_play_items(mpls: Path) -> list[PlayItem]:
    """The playlist's PlayItems, in order (angles beyond the first are ignored)."""
    data = mpls.read_bytes()
    if data[:4] != b"MPLS":
        raise ValueError(f"{mpls.name} is not a Blu-ray playlist")
    start = struct.unpack_from(">I", data, 8)[0]
    count = struct.unpack_from(">H", data, start + 6)[0]
    items, pos = [], start + 10
    for _ in range(count):
        length = struct.unpack_from(">H", data, pos)[0]
        clip = data[pos + 2:pos + 7].decode("ascii", "replace")
        in_time, out_time = struct.unpack_from(">II", data, pos + 14)
        items.append(PlayItem(clip, in_time / MPLS_CLOCK, out_time / MPLS_CLOCK))
        pos += 2 + length
    return items


def locate_play_item(items: list[PlayItem], seconds: float) -> tuple[PlayItem, float]:
    """Map a playlist time to (play item, seconds into that item)."""
    elapsed = 0.0
    for item in items:
        if seconds < elapsed + item.length:
            return item, max(0.0, seconds - elapsed)
        elapsed += item.length
    if not items:
        raise ValueError("The playlist has no clips")
    return items[-1], items[-1].length   # past the end: clamp


def _enrich_bitrates_ffprobe(playlist: Playlist) -> None:
    """
    Best-effort fill-in of Track.bitrate_kbps via ffprobe, since mkvmerge
    -J doesn't report bitrate at all. Failure here (missing ffprobe,
    unreadable file, unexpected output) is never fatal to a scan - it
    just means the picker shows a track without a bitrate figure, which
    is far better than blocking or guessing a wrong number.

    Matched by position: ffprobe and mkvmerge both enumerate a Blu-ray
    playlist's streams in on-disc order, so the Nth audio stream ffprobe
    reports is assumed to be the Nth audio track mkvmerge reported. If
    the counts don't match (a sign the assumption broke for this file),
    nothing is filled in rather than risk mislabelling a track.
    """
    audio_tracks = playlist.audio_tracks
    if not audio_tracks:
        return

    try:
        result = tools.run(
            [
                TOOL_PATHS["ffprobe"], "-v", "quiet", "-print_format", "json",
                "-show_streams", "-select_streams", "a", str(playlist.path),
            ],
            timeout=60,
        )
        if result.returncode != 0:
            return
        streams = json.loads(result.stdout).get("streams", [])
    except (RuntimeError, json.JSONDecodeError, OSError):
        return

    if len(streams) != len(audio_tracks):
        return  # ordering assumption unverifiable - don't guess

    for track, stream in zip(audio_tracks, streams):
        bit_rate = stream.get("bit_rate")
        if bit_rate is None:
            # Common for lossless DTS-HD MA/TrueHD: ffprobe sometimes
            # only tags the embedded DTS/AC-3 core's bitrate via
            # BPS-style tags rather than the top-level field.
            tags = stream.get("tags") or {}
            bit_rate = tags.get("BPS") or tags.get("BPS-eng")
        if bit_rate is None and track.sample_rate and track.bits_per_sample and track.channels:
            # PCM/LPCM is uncompressed, so its bitrate is exactly
            # derivable rather than best-effort - compute it directly
            # instead of relying on ffprobe reporting it.
            codec_lower = track.codec.lower()
            if "pcm" in codec_lower:
                bit_rate = track.sample_rate * track.bits_per_sample * track.channels
        try:
            if bit_rate is not None:
                track.bitrate_kbps = float(bit_rate) / 1000
        except (TypeError, ValueError):
            pass


def scan_disc_folder(disc_folder: Path) -> list[Playlist]:
    """Inspect every playlist in a disc folder, return list of Playlist."""
    return [inspect_playlist(p) for p in find_playlists(disc_folder)]


# ---------------------------------------------------------------------------
# Playlist scoring
# ---------------------------------------------------------------------------

@dataclass
class PlaylistScore:
    playlist: Playlist
    score: float
    reasons: list[str] = field(default_factory=list)
    duplicate_of: Optional[Path] = None  # set if this looks like a duplicate/alternate angle of a higher-scored playlist


def score_playlists(
    playlists: list[Playlist],
    expected_chapter_count: Optional[int] = None,
    expected_duration_seconds: Optional[float] = None,
) -> list[PlaylistScore]:
    """
    Score every scanned playlist as a candidate for "the" concert
    feature, replacing the old heuristic of silently picking whichever
    Atmos playlist happened to have the most chapters. Atmos is treated
    as a bonus signal, not a requirement, so non-Atmos discs are scored
    fairly too. Returns
    PlaylistScore objects sorted highest-score first, each carrying the
    reasons behind its score so the UI can show its work and the user can
    confirm (or override) the pick, instead of a single silent choice.

    expected_chapter_count / expected_duration_seconds: optional values
    from an external source (e.g. a user-imported tracklist). When given,
    playlists matching them closely get a bonus. Both are unused for now -
    they exist so a future tracklist-import feature can feed into playlist
    selection without changing this function's shape.
    """
    scored: list[PlaylistScore] = []

    for pl in playlists:
        score = 0.0
        reasons: list[str] = []

        if pl.has_atmos:
            score += 100
            atmos = pl.atmos_track
            reasons.append(f"Has a Dolby Atmos/TrueHD track (ID {atmos.track_id})")
        else:
            best = pl.best_default_audio_track()
            if best is not None:
                codec_lower = best.codec.lower()
                is_lossless = any(
                    h in codec_lower
                    for h in ("truehd", "dts-hd master", "flac", "pcm", "lpcm", "alac")
                )
                if is_lossless:
                    score += 70
                    reasons.append(f"No Atmos, but best available track is lossless ({best.codec})")
                else:
                    score += 30
                    reasons.append(f"No Atmos or lossless track - best available is {best.codec}")
            else:
                reasons.append("No audio track at all - cannot be the right playlist")

        if pl.chapter_count > 0:
            score += min(pl.chapter_count * 2, 40)
            reasons.append(f"{pl.chapter_count} chapters")
        else:
            reasons.append("No chapters - can't be split into songs even if selected")

        if pl.video_track is not None:
            score += 10
            reasons.append(f"Includes a video track ({pl.video_track.codec})")
        else:
            reasons.append("No video track - audio-only playlist")

        if pl.duration_seconds > 0:
            minutes = pl.duration_seconds / 60
            # A real concert feature usually runs from roughly 20 minutes
            # to a few hours. Duration mainly helps rule out menus,
            # trailers, and short bonus clips rather than reward length
            # for its own sake, so this is capped and lightly weighted
            # rather than dominating the score.
            score += min(minutes, 180) * 0.15
            reasons.append(f"Runs {minutes:.0f} minutes")

        # Playlist number is a weak signal - naming conventions vary by
        # studio/authoring tool - so it only nudges close ties, never
        # dominates the score on its own.
        try:
            score -= int(pl.path.stem) * 0.01
        except ValueError:
            pass

        if expected_chapter_count is not None and pl.chapter_count == expected_chapter_count:
            score += 15
            reasons.append(f"Chapter count matches the expected tracklist ({expected_chapter_count})")

        if expected_duration_seconds is not None and pl.duration_seconds > 0:
            if abs(pl.duration_seconds - expected_duration_seconds) < 30:
                score += 15
                reasons.append("Duration matches the expected tracklist closely")

        scored.append(PlaylistScore(playlist=pl, score=score, reasons=reasons))

    _flag_duplicate_angles(scored)

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def _flag_duplicate_angles(scored: list[PlaylistScore]) -> None:
    """
    Blu-rays sometimes expose the same underlying content as several
    playlists - alternate angles, region variants, a "clean" vs
    "with-recap" cut. These share duration, chapter count, and track
    layout almost exactly, so group candidates by that signature and mark
    every playlist but the highest-scored one in each group as a likely
    duplicate, rather than presenting near-identical entries as separate
    top candidates.
    """
    def signature(pl: Playlist) -> tuple:
        track_sig = tuple(sorted((t.kind, t.codec) for t in pl.tracks))
        return (pl.chapter_count, round(pl.duration_seconds), track_sig)

    groups: dict[tuple, list[PlaylistScore]] = {}
    for s in scored:
        groups.setdefault(signature(s.playlist), []).append(s)

    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda s: s.score, reverse=True)
        primary = group[0]
        for dup in group[1:]:
            dup.duplicate_of = primary.playlist.path
            dup.score -= 50
            dup.reasons.append(
                f"Same duration/chapters/tracks as {primary.playlist.path.name} "
                f"- likely a duplicate or alternate angle"
            )
