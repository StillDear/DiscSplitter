"""Disc data: tracks, playlists and chapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Losslessly packed audio, as named in mkvmerge's / ffprobe's codec strings (PCM is told by Track.is_pcm).
PACKED_LOSSLESS = ("truehd", "mlp", "dts-hd master", "flac", "alac")


@dataclass
class Track:
    track_id: int
    kind: str           # "video" | "audio" | "subtitles"
    codec: str           # human-readable codec string from mkvmerge JSON, e.g. "TrueHD Atmos"
    codec_id: str = ""   # internal codec id, e.g. "A_TRUEHD", "V_MPEG4/ISO/AVC"
    language: str = ""   # ISO 639-2 code, e.g. "eng" - empty if not set on the track
    channels: Optional[int] = None   # audio channel count, None for non-audio tracks
    title: str = ""       # track name/title embedded in the container, if any
    sample_rate: Optional[int] = None       # Hz, from mkvmerge's audio_sampling_frequency
    bits_per_sample: Optional[int] = None   # from mkvmerge's audio_bits_per_sample
    bitrate_kbps: Optional[float] = None    # best-effort only - see enrich_bitrates_ffprobe();
                                              # None whenever it couldn't be determined, rather
                                              # than guessing, since a wrong bitrate is worse than
                                              # no bitrate shown
    default_track: Optional[bool] = None
    stream_id: Optional[int] = None   # transport-stream PID on Blu-ray (mkvmerge "number"), used for previews
    properties: dict = field(default_factory=dict, repr=False, compare=False)   # raw mkvmerge track properties

    @property
    def is_atmos(self) -> bool:
        return "atmos" in self.codec.lower()

    @property
    def is_pcm(self) -> bool:
        """Uncompressed audio (LPCM): its bitrate follows exactly from rate, depth and channels."""
        return "pcm" in self.codec.lower() or "pcm" in self.codec_id.lower()

    @property
    def is_lossless(self) -> bool:
        return self.is_pcm or any(hint in self.codec.lower() for hint in PACKED_LOSSLESS)

    @property
    def channel_layout(self) -> str:
        """
        Best-effort "2.0" / "5.1" / "7.1" style layout string. mkvmerge
        only reports a raw channel count, not the front/LFE split, so
        this covers the layouts that actually ship on Blu-ray audio discs
        rather than guessing at anything more exotic.
        """
        if not self.channels:
            return ""
        return {1: "1.0", 2: "2.0", 6: "5.1", 8: "7.1"}.get(self.channels, str(self.channels))

    @property
    def display_label(self) -> str:
        """
        Human-readable summary for a track picker, e.g.:
        "DTS-HD Master Audio - 5.1, 96kHz, 8407kbps, 24-bit [eng]"
        Degrades gracefully - any field mkvmerge/ffprobe couldn't
        determine is simply left out rather than shown as a placeholder.
        """
        parts = []
        if self.channel_layout:
            parts.append(self.channel_layout)
        if self.sample_rate:
            khz = self.sample_rate / 1000
            parts.append(f"{khz:g}kHz")
        if self.bitrate_kbps:
            parts.append(f"{self.bitrate_kbps:.0f}kbps")
        if self.bits_per_sample:
            parts.append(f"{self.bits_per_sample}-bit")

        label = self.codec or "Unknown codec"
        if parts:
            label += " - " + ", ".join(parts)
        if self.language:
            label += f" [{self.language}]"
        if self.title:
            label += f' "{self.title}"'
        return label


@dataclass
class Playlist:
    path: Path
    tracks: list[Track] = field(default_factory=list)
    chapter_count: int = 0
    duration_seconds: float = 0.0
    iso_image: Optional[Path] = None  # ISO playlists use a path relative to the disc root.
    measured: bool = field(default=False, compare=False)   # audio bitrates were looked up (sources.audio_bitrates)
    # Who read it: "mkvmerge" (track IDs are mkvmerge's numbers) or "engine" (the built-in tsMuxeR; track IDs are
    # the transport stream PIDs, which the engine also cuts by).
    reader: str = field(default="mkvmerge", compare=False)
    marks: Optional[list[float]] = field(default=None, compare=False, repr=False)   # chapter starts, from the engine
    main_title: bool = field(default=False, compare=False)   # the engine's pick for the disc's main title
    marks_exact: bool = field(default=False, compare=False)  # marks from their 45 kHz ticks, not rounded to the ms

    @property
    def by_engine(self) -> bool:
        return self.reader == "engine"

    @property
    def atmos_track(self) -> Optional[Track]:
        for t in self.tracks:
            if t.is_atmos:
                return t
        return None

    @property
    def video_track(self) -> Optional[Track]:
        for t in self.tracks:
            if t.kind == "video":
                return t
        return None

    @property
    def picture_tracks(self) -> list[Track]:
        """
        The video a copy of the picture carries: the main video, plus a Dolby Vision enhancement layer
        that a disc plays alongside it. Picture-in-picture (secondary) and the 3D right eye are left out.
        """
        main = self.video_track
        if main is None:
            return []
        extra = [t for t in self.tracks if t.kind == "video" and t is not main and not t.properties.get("secondary")
                 and t.codec_id == main.codec_id == "V_MPEGH/ISO/HEVC"]
        return [main, *extra]

    @property
    def has_atmos(self) -> bool:
        return self.atmos_track is not None

    @property
    def audio_tracks(self) -> list[Track]:
        """Every audio track on this playlist, in mkvmerge/disc order."""
        return [t for t in self.tracks if t.kind == "audio"]

    @property
    def subtitle_tracks(self) -> list[Track]:
        return [t for t in self.tracks if t.kind == "subtitles"]

    def best_default_audio_track(self) -> Optional[Track]:
        """
        The track to pre-select in a track picker: the Atmos track if
        there is one (matches the old auto-pick behaviour exactly), else
        the "best" remaining audio track by a simple, defensible
        preference order - lossless codec first, then more channels,
        then higher bit depth. Never silently outranks an explicit user
        choice; this is only ever used as the initial dropdown value.
        """
        if self.has_atmos:
            return self.atmos_track
        tracks = self.audio_tracks
        if not tracks:
            return None

        return max(tracks, key=lambda t: (t.is_lossless, t.channels or 0, t.bits_per_sample or 0))

    def best_music_track(self) -> Optional[Track]:
        """
        The track to pre-select for a sound-only (FLAC) export: the lossless
        stereo mix when the disc has one (the best by sample rate and bit
        depth), since that is the album-style listen; otherwise the same
        pick as best_default_audio_track().
        """
        stereo = [t for t in self.audio_tracks if t.channels == 2 and t.is_lossless]
        if stereo:
            return max(stereo, key=lambda t: (t.sample_rate or 0, t.bits_per_sample or 0))
        return self.best_default_audio_track()


def default_title(index: int) -> str:
    """What a chapter without a title is called (in file names and the title tag)."""
    return f"Track {index:02d}"


@dataclass
class Chapter:
    index: int
    start_seconds: float
    end_seconds: Optional[float] = None   # filled in after all chapters read
    name: str = ""                        # final song title used for the output filename
    embedded_name: str = ""               # ChapterString read from the source, if any
    language: str = ""                    # ChapterLanguage of the embedded name, if any

    @property
    def duration(self) -> Optional[float]:
        """Length in seconds; None for a last chapter that runs to the end of the source."""
        return None if self.end_seconds is None else self.end_seconds - self.start_seconds

    @property
    def title(self) -> str:
        """The song title, or "Track 07" for a chapter that was given none."""
        return self.name or default_title(self.index)
