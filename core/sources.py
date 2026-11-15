"""Finding and inspecting sources: Blu-ray folders and images, DVDs, Matroska files; playlist scoring."""

from __future__ import annotations

import dataclasses
import json
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import bluray_iso
from . import dvd
from . import engine
from . import tools
from .jobs import Failure
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


def is_bluray_file(source: Path) -> bool:
    """A single Blu-ray playlist (.mpls) or transport stream (.m2ts, .ts) opened on its own."""
    return source.is_file() and (source.suffix.lower() == ".mpls" or source.suffix.lower() in engine.TS_SUFFIXES)


def find_sources(source: Path) -> list[Path]:
    """Find Blu-ray playlists or top-level Matroska files, preferring BDMV."""
    if is_mkv_source(source):
        return [source]
    if not source.is_dir():
        return []
    if (source / "BDMV").is_dir():
        return find_playlists(source)
    return sorted(p for p in source.iterdir() if is_mkv_source(p))


def _bluray_root(source: Path) -> Optional[Path]:
    """The disc folder of a Blu-ray folder given as the folder holding BDMV, or as BDMV itself."""
    if (source / "BDMV").is_dir():
        return source
    if source.name.upper() == "BDMV" and (source / "PLAYLIST").is_dir():
        return source.parent
    return None


def scan_with_engine(disc: Path, image: Optional[Path] = None) -> list[Playlist]:
    """
    A Blu-ray folder or image read by the built-in engine, without mounting: its titles (playlists under two
    minutes, copies and menus loops left out, unless nothing else is left), the main title marked.
    `disc` is the folder or the image; playlists of an image keep a path relative to it.
    """
    found = engine.titles(disc) or engine.titles(disc, all_playlists=True)
    names = [(t.playlist, t.main) for t in found]

    def read(entry: tuple[str, bool]) -> Playlist:
        name, main = entry
        relative = Path("BDMV") / "PLAYLIST" / name
        playlist = engine.inspect(engine.source_of(relative, image) if image else str(disc / relative))
        playlist.path = relative if image else disc / relative
        playlist.iso_image, playlist.main_title = image, main
        return playlist

    if len(names) < 2:
        return [read(n) for n in names]
    with ThreadPoolExecutor(max_workers=min(SCAN_WORKERS, len(names))) as pool:
        return list(pool.map(read, names))


def scan_source(source: Path) -> list[Playlist]:
    """Inspect a GUI source while retaining the legacy disc scan entry point."""
    if is_bluray_file(source):
        return [inspect_playlist(source)]
    if bluray_iso.is_iso(source):
        image = source.resolve()
        # DVD images are read straight from the file by ffmpeg; no mounting.
        if dvd.iso_looks_like_dvd(image):
            return dvd.scan(image)
        if engine.available():
            try:
                found = scan_with_engine(image, image)
            except Failure:
                found = []      # not a Blu-ray the engine reads (a DVD it was not recognised as): look inside
            if found:
                return found
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
    root = _bluray_root(source) if source.is_dir() else None
    if root is not None and engine.available():
        found = scan_with_engine(root)
        if found:
            return found
    candidates = find_sources(source)
    if source.is_dir() and ((source / "BDMV").is_dir() or not candidates):
        return scan_disc_folder(source)
    return _inspect_all(candidates)


_GENERIC_NAMES = {"video_ts", "dvdimage", "image", "disc", "disk", "dvd", "bdmv", "bd"}


def source_name_path(source: Path) -> Path:
    """Use the source filename without its extension for album naming."""
    if is_bluray_file(source) and source.parent.parent.name.upper() == "BDMV":
        source = source.parent.parent.parent       # BDMV/PLAYLIST/00001.mpls: the disc folder names the album
    named = source.with_suffix("") if is_mkv_source(source) or bluray_iso.is_iso(source) or is_bluray_file(source)         else source
    # "VIDEO_TS" or "DVDIMAGE.ISO" say nothing about the album: the folder around them does.
    if named.name.lower() in _GENERIC_NAMES and named.parent != named:
        return named.parent
    return named


def inspect_playlist(playlist_path: Path, use_engine: bool = True) -> Playlist:
    """
    Run `mkvmerge -J` on a playlist and parse the resulting JSON for
    tracks and chapter count. Audio bitrates are not part of it (mkvmerge
    does not report them): audio_bitrates() measures them with ffprobe for
    the one playlist that gets used, not for every playlist of a scan.

    JSON (rather than the human-readable `mkvmerge -i` text output) is
    used deliberately: the text format isn't a stable interface - its
    wording, spacing, and line layout can shift between MKVToolNix
    versions or with locale settings, which is exactly the kind of thing
    that quietly breaks a regex without any obvious error. The JSON
    schema is the format MKVToolNix documents and maintains for tooling.
    """
    if dvd.is_title(playlist_path):
        return dvd.inspect(playlist_path)
    suffix = playlist_path.suffix.lower()
    # use_engine=False reads it as mkvmerge numbers its tracks (to resume a job checkpointed that way).
    if (suffix == ".mpls" or suffix in engine.TS_SUFFIXES) and use_engine and engine.available():
        playlist = engine.inspect(str(playlist_path))
        playlist.path = playlist_path
        return playlist
    result = tools.run([TOOL_PATHS["mkvmerge"], "-J", str(playlist_path)], timeout=60)
    # mkvmerge returns 0 for a clean read and 1 for warnings (still usable
    # output), but 2 means it couldn't read the file at all - in that case
    # stdout won't have useful track/chapter info, so surface the real
    # error instead of silently reporting "no Atmos track".
    if result.returncode >= 2:
        raise Failure("tool_failed", f"mkvmerge could not read {playlist_path.name}:\n{result.stderr or result.stdout}",
                      detail=result.stderr or result.stdout, tool="mkvmerge")

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
    """The playlist's PlayItems, in order (angles beyond the first are ignored). Also inside an image."""
    data = engine.read_file(mpls)
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


def clip_file(stream_folder: Path, clip: str) -> Path:
    """A clip's .m2ts in a STREAM folder (on a drive or inside an image), whichever case its name is in."""
    file = stream_folder / f"{clip}.m2ts"
    if not engine.file_exists(file) and engine.file_exists(file.with_suffix(".M2TS")):
        return file.with_suffix(".M2TS")
    return file


def clip_info_file(stream_folder: Path, clip: str) -> Path:
    """A clip's .clpi (BDMV/CLIPINF), next to its STREAM folder, whichever case its name is in."""
    file = stream_folder.parent / "CLIPINF" / f"{clip}.clpi"
    if not engine.file_exists(file) and engine.file_exists(file.with_suffix(".CLPI")):
        return file.with_suffix(".CLPI")
    return file


SOURCE_PACKET = 192      # bytes per packet of a Blu-ray transport stream (.m2ts)


def read_key_pictures(clpi: Path) -> list[tuple[float, int]]:
    """
    The key pictures of a clip, from its entry point map: (seconds on the clip's own clock, byte offset in the .m2ts)
    in order. Opening the clip at one of these offsets starts it at that picture, without asking ffmpeg to seek.
    """
    data = engine.read_file(clpi)
    if data[:4] != b"HDMV":
        raise ValueError(f"{clpi.name} is not a Blu-ray clip information file")
    cpi = struct.unpack_from(">I", data, 16)[0]
    if not cpi or struct.unpack_from(">I", data, cpi)[0] == 0:
        return []
    ep_map = cpi + 6                                   # after the length and the CPI type
    if not data[ep_map + 1]:                           # number of streams with entry points
        return []
    # The first stream (the main video): its entry points' coarse and fine tables.
    # 16 bits PID, then 48: reserved 10, stream type 4, coarse entries 16, fine entries 18; then the table's address.
    counts = int.from_bytes(data[ep_map + 4:ep_map + 10], "big")
    coarse_count, fine_count = (counts >> 18) & 0xFFFF, counts & 0x3FFFF
    table = ep_map + struct.unpack_from(">I", data, ep_map + 10)[0]
    fine_table = table + struct.unpack_from(">I", data, table)[0]
    coarse = []
    for i in range(coarse_count):
        head, spn = struct.unpack_from(">II", data, table + 4 + 8 * i)
        coarse.append((head >> 14, head & 0x3FFF, spn))      # first fine entry, PTS bits 32..19, SPN
    pictures = []
    for c, (first, pts_coarse, spn_coarse) in enumerate(coarse):
        last = coarse[c + 1][0] if c + 1 < len(coarse) else fine_count
        for f in range(first, last):
            entry = struct.unpack_from(">I", data, fine_table + 4 * f)[0]
            # The coarse part holds PTS bits 32..19 and the fine part 19..9: bit 19 is the fine part's.
            pts = ((pts_coarse & ~1) << 19) + (((entry >> 17) & 0x7FF) << 9)
            spn = (spn_coarse & ~0x1FFFF) + (entry & 0x1FFFF)
            pictures.append((pts / 90_000, spn * SOURCE_PACKET))
    return pictures


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


def audio_bitrates(playlist: Playlist, path: Optional[Path] = None) -> dict[int, float]:
    """
    Best-effort bitrates (kbps by track ID) of a playlist's audio tracks via
    ffprobe, since mkvmerge -J doesn't report bitrate at all. `path` is where
    the playlist can be read now (a mounted disc image); default: its own path.
    Failure here (missing ffprobe, unreadable file, unexpected output) is never
    fatal - it just means a track is shown without a bitrate figure, which is
    far better than blocking or guessing a wrong number.

    Matched by position: ffprobe and mkvmerge both enumerate a Blu-ray
    playlist's streams in on-disc order, so the Nth audio stream ffprobe
    reports is assumed to be the Nth audio track mkvmerge reported. If
    the counts don't match (a sign the assumption broke for this file),
    nothing is returned rather than risk mislabelling a track.
    """
    audio_tracks = playlist.audio_tracks
    if not audio_tracks or dvd.is_title(playlist.path):     # a DVD title's rates come with its scan
        return {}

    try:
        result = tools.run(
            [
                TOOL_PATHS["ffprobe"], "-v", "quiet", "-print_format", "json",
                "-show_streams", "-select_streams", "a", str(path or playlist.path),
            ],
            timeout=60,
        )
        if result.returncode != 0:
            return {}
        streams = json.loads(result.stdout).get("streams", [])
    except (RuntimeError, json.JSONDecodeError, OSError):
        return {}

    if len(streams) != len(audio_tracks):
        return {}  # ordering assumption unverifiable - don't guess

    rates: dict[int, float] = {}
    for track, stream in zip(audio_tracks, streams):
        bit_rate = stream.get("bit_rate")
        if bit_rate is None:
            # Common for lossless DTS-HD MA/TrueHD: ffprobe sometimes
            # only tags the embedded DTS/AC-3 core's bitrate via
            # BPS-style tags rather than the top-level field.
            tags = stream.get("tags") or {}
            bit_rate = tags.get("BPS") or tags.get("BPS-eng")
        if bit_rate is None and track.is_pcm and track.sample_rate and track.bits_per_sample and track.channels:
            # PCM/LPCM is uncompressed, so its bitrate follows exactly from its format.
            bit_rate = track.sample_rate * track.bits_per_sample * track.channels
        try:
            if bit_rate is not None:
                rates[track.track_id] = float(bit_rate) / 1000
        except (TypeError, ValueError):
            pass
    return rates


def apply_bitrates(playlist: Playlist, rates: dict[int, float]) -> None:
    for track in playlist.audio_tracks:
        if track.track_id in rates:
            track.bitrate_kbps = rates[track.track_id]


SCAN_WORKERS = 4        # playlists read at once: a disc can hold hundreds, each one mkvmerge call


def _inspect_all(paths: list[Path]) -> list[Playlist]:
    """Inspect several playlists side by side, in the order given (the first error is raised)."""
    if len(paths) < 2:
        return [inspect_playlist(p) for p in paths]
    with ThreadPoolExecutor(max_workers=min(SCAN_WORKERS, len(paths))) as pool:
        return list(pool.map(inspect_playlist, paths))


def scan_disc_folder(disc_folder: Path) -> list[Playlist]:
    """Inspect every playlist in a disc folder, return list of Playlist."""
    return _inspect_all(find_playlists(disc_folder))


# ---------------------------------------------------------------------------
# Playlist scoring
# ---------------------------------------------------------------------------

class Reason(str):
    """
    One thing that counted for or against a playlist. It *is* its English wording (prints and
    joins like any str); `code` and `value` say what it means, so a UI translates and ranks
    reasons without ever parsing that wording.
    """
    code: str
    value: str

    def __new__(cls, code: str, value: object = ""):
        reason = super().__new__(cls, REASON_TEXT[code].format(value))
        reason.code, reason.value = code, str(value)
        return reason

    def __reduce__(self):   # keep the meaning when copied or pickled
        return (Reason, (self.code, self.value))


REASON_TEXT = {
    "atmos": "Has a Dolby Atmos/TrueHD track (ID {})",
    "lossless": "No Atmos, but best available track is lossless ({})",
    "lossy": "No Atmos or lossless track - best available is {}",
    "no_audio": "No audio track at all - cannot be the right playlist",
    "chapters": "{} chapters",
    "main_title": "Main title of the disc (plays the most footage)",
    "no_chapters": "No chapters - can't be split into songs even if selected",
    "video": "Includes a video track ({})",
    "no_video": "No video track - audio-only playlist",
    "minutes": "Runs {} minutes",
    "duplicate": "Same duration/chapters/tracks as {} - likely a duplicate or alternate angle",
}


@dataclass
class PlaylistScore:
    playlist: Playlist
    score: float
    reasons: list[Reason] = field(default_factory=list)
    duplicate_of: Optional[Path] = None  # set if this looks like a duplicate/alternate angle of a higher-scored playlist


def score_playlists(playlists: list[Playlist]) -> list[PlaylistScore]:
    """
    Score every scanned playlist as a candidate for "the" concert
    feature, replacing the old heuristic of silently picking whichever
    Atmos playlist happened to have the most chapters. Atmos is treated
    as a bonus signal, not a requirement, so non-Atmos discs are scored
    fairly too. Returns
    PlaylistScore objects sorted highest-score first, each carrying the
    reasons behind its score so the UI can show its work and the user can
    confirm (or override) the pick, instead of a single silent choice.
    """
    scored: list[PlaylistScore] = []

    for pl in playlists:
        score = 0.0
        reasons: list[Reason] = []

        if pl.has_atmos:
            score += 100
            atmos = pl.atmos_track
            reasons.append(Reason("atmos", atmos.track_id))
        else:
            best = pl.best_default_audio_track()
            if best is not None:
                if best.is_lossless:
                    score += 70
                    reasons.append(Reason("lossless", best.codec))
                else:
                    score += 30
                    reasons.append(Reason("lossy", best.codec))
            else:
                reasons.append(Reason("no_audio"))

        if pl.chapter_count > 0:
            score += min(pl.chapter_count * 2, 40)
            reasons.append(Reason("chapters", pl.chapter_count))
        else:
            reasons.append(Reason("no_chapters"))

        if pl.main_title:
            # The engine's pick: the playlist that plays the most of the disc's footage.
            score += 25
            reasons.append(Reason("main_title"))

        if pl.video_track is not None:
            score += 10
            reasons.append(Reason("video", pl.video_track.codec))
        else:
            reasons.append(Reason("no_video"))

        if pl.duration_seconds > 0:
            minutes = pl.duration_seconds / 60
            # A real concert feature usually runs from roughly 20 minutes
            # to a few hours. Duration mainly helps rule out menus,
            # trailers, and short bonus clips rather than reward length
            # for its own sake, so this is capped and lightly weighted
            # rather than dominating the score.
            score += min(minutes, 180) * 0.15
            reasons.append(Reason("minutes", f"{minutes:.0f}"))

        # Playlist number is a weak signal - naming conventions vary by
        # studio/authoring tool - so it only nudges close ties, never
        # dominates the score on its own.
        if pl.path.suffix.lower() == ".mpls":
            try:
                score -= int(pl.path.stem) * 0.01
            except ValueError:
                pass

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
            dup.reasons.append(Reason("duplicate", primary.playlist.path.name))
