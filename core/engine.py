"""
The built-in Blu-ray engine: tsMuxeR, compiled from the source in engine/tsmuxer and shipped with the app.

It reads Blu-ray folders and ISO images without mounting them, lists a disc's titles (the main one marked),
lists a playlist's tracks and chapter marks, and cuts a playlist into transport streams or Matroska files.
It runs as a child process: a crash or a cancel never takes the app down with it.

    titles(disc)                  the disc's titles, main title first
    inspect(source)               one playlist (or .m2ts) -> Playlist with its tracks and chapter marks
    run_meta(meta, output, ...)   a mux described by a .meta file, with progress and cancel
"""

from __future__ import annotations

import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import tools
from .jobs import Failure, tool_failed
from .models import Playlist, Track

ENGINE = "tsMuxeR"
IDENTITY = "tsMuxeR version"
ROOT = Path(__file__).resolve().parent.parent
TS_SUFFIXES = {".m2ts", ".mts", ".ts", ".m2t"}

_configured: Optional[str] = None      # a path set by hand (settings); normally left alone


def set_path(path: Optional[str]) -> None:
    global _configured
    _configured = path or None


def path() -> str:
    """Where the engine is: a path set by hand, the installed app's tools folder, or the source build."""
    if _configured:
        return _configured
    if getattr(sys, "frozen", False):
        # The installer puts it in <app>/tools; PyInstaller unpacks its own copy into _MEIPASS/tools.
        for folder in (Path(sys.executable).resolve().parent, Path(getattr(sys, "_MEIPASS", "."))):
            shipped = folder / "tools" / f"{ENGINE}.exe"
            if shipped.is_file():
                return str(shipped)
    built = ROOT / "engine" / "bin" / f"{ENGINE}.exe"
    return str(built) if built.is_file() else ENGINE


_available: dict[str, bool] = {}


def available() -> bool:
    """Whether the engine runs (checked once per path)."""
    where = path()
    if where not in _available:
        _available[where] = tools.verify_tool_at_path(where, "tsmuxer", timeout=20)[0]
    return _available[where]


def require() -> str:
    if not available():
        raise Failure("tool_missing", "The built-in Blu-ray engine (tsMuxeR) was not found. From the source, build "
                                      "it with: python engine/build_engine.py", tool="tsMuxeR")
    return path()


def version() -> str:
    ok, line = tools.verify_tool_at_path(path(), "tsmuxer", timeout=20)
    return line.split(". ")[0] if ok else ""


# ---------------------------------------------------------------------------
# Naming a playlist, also inside a disc image
# ---------------------------------------------------------------------------

def source_of(playlist_path: Path, iso_image: Optional[Path] = None) -> str:
    """The engine's name for a playlist: inside an image it is image.iso/BDMV/PLAYLIST/00001.mpls (no mounting)."""
    if iso_image is None:
        return str(playlist_path)
    return f"{Path(iso_image).as_posix()}/{Path(playlist_path).as_posix()}"


def source_for(playlist: Playlist) -> str:
    return source_of(playlist.path, playlist.iso_image)


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def _listing(*args: str, timeout: float = 120) -> str:
    result = tools.run([require(), *args], timeout=timeout)
    text = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 and "Track ID:" not in text and "Title " not in text:
        raise tool_failed("tsMuxeR", text.strip())
    return text


@dataclass
class DiscTitle:
    number: int
    playlist: str            # "00001.mpls"
    seconds: float
    chapters: int
    main: bool = False
    note: str = ""


_TITLE_RE = re.compile(r"^Title\s+(\d+)\s+(\S+\.mpls)\s+(\d+):(\d\d):(\d\d)\s+(\d+)\s+chapters?\b(.*)$", re.I)


def parse_titles(text: str) -> list[DiscTitle]:
    titles = []
    for line in text.splitlines():
        m = _TITLE_RE.match(line.strip())
        if not m:
            continue
        number, name, h, mi, s, chapters, rest = m.groups()
        note = rest[rest.rfind("(") + 1:rest.rfind(")")] if "(" in rest and rest.rstrip().endswith(")") else ""
        titles.append(DiscTitle(int(number), name, int(h) * 3600 + int(mi) * 60 + int(s), int(chapters),
                                main=note.startswith("main") or "main title" in note, note=note))
    return titles


def titles(disc: Path, all_playlists: bool = False) -> list[DiscTitle]:
    """The titles of a Blu-ray folder or image, the main film first; playlists under 2 minutes are left out."""
    args = ["--all-playlists"] if all_playlists else []
    return parse_titles(_listing(*args, str(disc)))


@dataclass
class Listing:
    tracks: list[dict] = field(default_factory=list)   # one dict per "Track ID:" block
    duration: float = 0.0                               # every clip's Duration added up
    marks: list[float] = field(default_factory=list)   # chapter starts on the playlist's own timeline
    clips: list[str] = field(default_factory=list)


_FIELD_RE = re.compile(r"^(Track ID|Stream type|Stream ID|Stream info|Stream lang|Stream delay|Stream file|"
                       r"Stream name|Stream order|Secondary|Unselected|subTrack):\s*(.*)$")


def seconds_of(clock: str) -> float:
    """'01:02:03.456' -> 3723.456"""
    parts = clock.strip().split(":")
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    return total


def parse_listing(text: str) -> Listing:
    listing = Listing()
    current: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _FIELD_RE.match(line)
        if m:
            key, value = m.groups()
            if key == "Track ID":
                current = {"Track ID": value}
                listing.tracks.append(current)
            elif current is not None:
                current[key] = value
            continue
        if not line:
            current = None
        elif line.startswith("File #"):
            current = None
            listing.clips.append(line.split("name=", 1)[-1])
        elif line.startswith("Duration:"):
            listing.duration += seconds_of(line.split(":", 1)[1])
        elif line.startswith("Marks:"):
            listing.marks += [seconds_of(t) for t in line.split(":", 1)[1].split()]
    listing.marks = sorted(set(round(m, 3) for m in listing.marks))
    return listing


# The engine's codec names, as mkvmerge spells them (the rest of the app, its scoring and texts, use these).
_VIDEO = {"V_MPEG4/ISO/AVC": ("AVC/H.264/MPEG-4p10", "V_MPEG4/ISO/AVC"),
          "V_MPEGH/ISO/HEVC": ("HEVC/H.265/MPEG-H", "V_MPEGH/ISO/HEVC"),
          "V_MPEG-2": ("MPEG-1/2", "V_MPEG2"),
          "V_MS/VFW/WVC1": ("VC-1", "V_MS/VFW/FOURCC"),
          "V_MPEG4/ISO/MVC": ("MVC", "V_MPEG4/ISO/MVC"),
          "V_MPEGI/ISO/VVC": ("VVC", "V_MPEGI/ISO/VVC")}


def _audio_codec(kind: str, info: str) -> tuple[str, str]:
    """(codec, codec_id) of an audio track from its 'Stream type' and 'Stream info' lines."""
    upper = info.upper()
    if kind == "LPCM":
        return "PCM", "A_PCM/INT/BIG"
    if kind == "TRUE-HD" or "TRUE-HD" in upper:
        return ("TrueHD Atmos" if "ATMOS" in upper else "TrueHD"), "A_TRUEHD"
    if kind.startswith("E-AC3"):
        return ("E-AC-3 Atmos" if "ATMOS" in upper else "E-AC-3"), "A_EAC3"
    if kind == "AC3":
        return "AC-3", "A_AC3"
    if kind.startswith("DTS"):
        for words, name in (("MASTER AUDIO", "DTS-HD Master Audio"), ("HIGH RESOLUTION", "DTS-HD High Resolution Audio"),
                            ("EXPRESS", "DTS Express")):
            if words in upper:
                return name, "A_DTS"
        return ("DTS-ES" if "DTS-ES" in upper else "DTS"), "A_DTS"
    return kind, ""


def _number(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text, re.I)
    return float(m.group(1)) if m else None


def _channels(info: str) -> Optional[int]:
    m = re.search(r"Channels:\s*(\d+)(?:\.(\d))?", info)
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2) or 0)


def to_track(block: dict, place: int) -> Optional[Track]:
    """One listed track as a Track; None for one the playlist does not play (Unselected) or cannot be read."""
    if block.get("Unselected") == "1":
        return None
    program, kind, info = block.get("Stream ID", ""), block.get("Stream type", ""), block.get("Stream info", "")
    try:
        pid = int(block["Track ID"])
    except (KeyError, ValueError):
        return None
    language = block.get("Stream lang", "").strip()
    props = {"program": program, "engine_type": kind, "engine_info": info, "place": place}
    for key, name in (("Stream file", "stream_file"), ("Stream delay", "stream_delay"), ("subTrack", "sub_track"),
                      ("Secondary", "secondary")):
        if key in block:
            props[name] = block[key]
    if program.startswith("V_"):
        codec, codec_id = _VIDEO.get(program, (kind, program))
        size = re.search(r"Resolution:\s*(\d+):(\d+)", info)
        if size:
            props["pixel_dimensions"] = f"{size.group(1)}x{size.group(2)}"
        return Track(pid, "video", codec, codec_id, language, stream_id=pid, properties=props)
    if program.startswith("A_"):
        codec, codec_id = _audio_codec(kind, info)
        rate = _number(r"Sample Rate:\s*(\d+)\s*KHz", info)
        bits = _number(r"Bits per sample:\s*(\d+)\s*bit", info)
        bitrate = None if "Peak bitrate" in info else _number(r"(?<!Peak )Bitrate:\s*(\d+)\s*Kbps", info)
        track = Track(pid, "audio", codec, codec_id, language, channels=_channels(info),
                      sample_rate=int(rate * 1000) if rate else None, bits_per_sample=int(bits) if bits else None,
                      bitrate_kbps=bitrate, stream_id=pid, properties=props)
        if "secondary" in props:
            track.title = "Secondary"
        return track
    if program.startswith("S_"):
        codec = {"S_HDMV/PGS": "HDMV PGS", "S_TEXT/UTF8": "HDMV TextST"}.get(program, kind)
        return Track(pid, "subtitles", codec, program, language, stream_id=pid, properties=props)
    return None


def inspect(source: str) -> Playlist:
    """A playlist (or a single .m2ts) as the engine reads it. `source` may point inside an ISO image."""
    listing = parse_listing(_listing(source))
    playlist = Playlist(path=Path(source), reader="engine")
    playlist.tracks = [t for t in (to_track(b, i) for i, b in enumerate(listing.tracks)) if t is not None]
    playlist.duration_seconds = listing.duration
    # A stream file on its own has no chapters: it is one, to be split by hand.
    playlist.marks = listing.marks or ([0.0] if listing.duration > 0 else [])
    playlist.chapter_count = len(listing.marks)
    playlist.measured = True        # bitrates come with the listing; nothing more to measure with ffprobe
    return playlist


# ---------------------------------------------------------------------------
# Muxing
# ---------------------------------------------------------------------------

def clock(seconds: float) -> str:
    """A time as the engine reads it, to the microsecond: 0:06:47.991000"""
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:09.6f}"


def _quote(text: str) -> str:
    return '"' + text.replace('"', '') + '"'


def track_line(source: str, track: Track, *, matroska: bool = False, drop_core: bool = False) -> str:
    """One meta line: the codec, where the track is, and how to take it."""
    props = track.properties or {}
    program = props.get("program") or {"video": "V_MPEG4/ISO/AVC", "subtitles": "S_HDMV/PGS"}.get(track.kind, "A_AC3")
    where = source
    params = [f"track={track.stream_id or track.track_id}"]
    if props.get("stream_file"):          # a TextST subtitle plays from a clip of its own
        file = props["stream_file"]
        if "/" not in file and "\\" not in file:
            file = str(Path(source).parent.parent / "STREAM" / file)
        where = file
        if props.get("stream_delay"):
            params.append(f"timeshift={props['stream_delay']}ms")
    if props.get("sub_track"):
        params.append(f"subTrack={props['sub_track']}")
    if track.language:
        params.append(f"lang={track.language}")
    if track.kind == "audio" and props.get("secondary") and not matroska:
        params.append("secondary")
    if drop_core and track.codec_id == "A_TRUEHD":
        params.append("drop-ac3-core")
    return f"{program}, {_quote(where)}, " + ", ".join(params)


_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)% complete")


def run_meta(meta_lines: list[str], meta_path: Path, output: Path, *,
             on_progress: Optional[Callable[[float], None]] = None,
             on_tick: Optional[Callable[[], None]] = None,
             on_message: Optional[Callable[[str], None]] = None,
             cancel_event: Optional[threading.Event] = None) -> list[str]:
    """
    Write the .meta file and run the mux. on_progress gets the engine's percentage (of the whole source);
    on_tick is called with every line, so a caller can look at the files written so far. Returns the
    engine's warnings. Raises Failure with the engine's own words when the mux fails.
    """
    meta_path.write_text("\n".join(meta_lines) + "\n", encoding="utf-8")
    messages: list[str] = []
    warnings: list[str] = []

    def on_line(line: str) -> None:
        for piece in line.split("\r"):
            piece = piece.strip()
            if not piece:
                continue
            m = _PERCENT_RE.match(piece)
            if m:
                if on_progress:
                    on_progress(float(m.group(1)))
            else:
                messages.append(piece)
                if piece.lower().startswith(("warning", "error")):
                    warnings.append(piece)
                    if on_message:
                        on_message(f"tsMuxeR: {piece}")
            if on_tick:
                on_tick()

    code = tools.run_streaming([require(), str(meta_path), str(output)], on_line, cancel_event)
    if code != 0:
        raise tool_failed("tsMuxeR", "\n".join(messages[-12:]))
    return warnings
