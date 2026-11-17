"""
local_tags.py

Album metadata read from music files the user already has (a CD rip, the studio album, an
earlier export), turned into the same shapes the online catalogues give (metadata_sources):

  scan(paths) -> list[LocalAlbum]            one per album found among the files
  candidate(album, n) / album_info(album)    what the metadata page lists and applies
  pick_cover(album, prefer)                  the embedded picture or the folder image, by preference

A whole-disc image (one FLAC / APE / WAV for the album) is split into its songs by its CUE sheet:
the .cue beside it, or one embedded in the file's CUESHEET tag. Sheets in GBK, Shift-JIS or Big5
are read too (text_encoding).

Tags are read with ffprobe, which ships with the app; nothing is sent anywhere. The parsing is
kept apart from the ffprobe calls (read_file, group) so it can be tested on canned JSON.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Optional

from . import tools
from .jobs import Failure
from .metadata_sources import AlbumInfo, Candidate, TrackInfo
from .text_encoding import decode_text

AUDIO_TYPES = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wv", ".ape", ".aif",
               ".aiff", ".dsf", ".dff", ".tta", ".wma", ".mka", ".mpc"}
IMAGE_TYPES = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png"}
# Folder images by how surely they are the front cover; the first name found wins.
COVER_NAMES = ("cover", "folder", "front", "albumart", "album", "albumartlarge", "jacket")
COVER_PREFERENCES = ("embedded", "folder")
MAX_FILES = 300
# "CD1", "Disc 2", "DISC_03", "Disk1", "碟2" - a folder holding one disc of a set
_DISC_FOLDER = re.compile(r"^(?:cd|disc|disk|dvd|碟|盘)[\s_.-]*(\d{1,2})$", re.IGNORECASE)
# "01 - Title", "01. Title", "1-03 Title", "03_Title", "(01) Title"
_FILE_NUMBER = re.compile(r"^\s*[(\[]?(?:(\d{1,2})[-.])?(\d{1,3})[)\]]?(?:\s*[-._]\s*|\s+)(.+)$")

# Tag names as ffprobe reports them for each format, lower-cased, best first.
_KEYS = {
    "title": ("title",),
    "artist": ("artist",),
    "album": ("album",),
    "album_artist": ("album_artist", "albumartist", "album artist", "band"),
    "date": ("date", "year", "originaldate", "original_date", "originalyear"),
    "genre": ("genre",),
    "track": ("track", "tracknumber"),
    "disc": ("disc", "discnumber", "disk"),
    "mb_album": ("musicbrainz_albumid", "musicbrainz album id"),
    "cuesheet": ("cuesheet",),
}


@dataclass
class LocalFile:
    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    date: str = ""
    genre: str = ""
    track: Optional[int] = None
    disc: Optional[int] = None
    seconds: Optional[float] = None
    codec: str = ""
    picture: Optional[int] = None      # stream index of the embedded front cover, if any
    mb_album: str = ""
    named_from_file: bool = False      # no title tag: the title came from the file name
    cuesheet: str = ""                 # a CUE sheet embedded in the file (CUESHEET tag)
    start: Optional[float] = None      # a song inside a whole-disc image: where it starts, in seconds


@dataclass
class LocalAlbum:
    album: str = ""
    artist: str = ""
    album_artist: str = ""
    date: str = ""
    genre: str = ""
    folder: Optional[Path] = None
    discs: list[list[LocalFile]] = field(default_factory=list)
    codecs: list[str] = field(default_factory=list)
    mb_album: str = ""
    mixed: list[str] = field(default_factory=list)      # album fields the files disagree on
    folder_cover: Optional[Path] = None
    embedded_cover: Optional[Path] = None              # extracted into the cache by scan()

    @property
    def files(self) -> list[LocalFile]:
        return [f for disc in self.discs for f in disc]


# ---------------------------------------------------------------- finding files

def _natural(path: Path):
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", str(path))]


def collect(paths: Iterable[Path]) -> list[Path]:
    """
    The audio files among what the user picked: files as they are, folders with their direct
    subfolders ("CD1", "Disc 2" of a set). Deeper folders are left alone so picking a whole
    library by mistake does not read it all.
    """
    found: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            for child in sorted(path.iterdir(), key=_natural):
                if child.is_dir():
                    found += sorted((c for c in child.iterdir() if c.is_file() and c.suffix.lower() in AUDIO_TYPES),
                                    key=_natural)
                elif child.suffix.lower() in AUDIO_TYPES:
                    found.append(child)
        elif path.is_file() and path.suffix.lower() in AUDIO_TYPES:
            found.append(path)
        elif path.is_file() and path.suffix.lower() == ".cue":
            found += cue_audio_files(path)      # a sheet picked on its own: the image(s) it describes
    unique = list(dict.fromkeys(found))
    if not unique:
        raise Failure("local_none", "No music files were found there.")
    if len(unique) > MAX_FILES:
        raise Failure("local_too_many", f"More than {MAX_FILES} music files were picked. Pick one album at a time.",
                      limit=MAX_FILES)
    return unique


# ---------------------------------------------------------------- reading one file

def _tag_map(data: dict) -> dict[str, str]:
    """Container tags and audio-stream tags (Ogg and Opus keep theirs on the stream), keys lower-cased."""
    tags: dict[str, str] = {}
    sources = [(data.get("format") or {}).get("tags") or {}]
    sources += [s.get("tags") or {} for s in data.get("streams") or [] if s.get("codec_type") == "audio"]
    for source in sources:
        for key, value in source.items():
            text = str(value or "").strip()
            if text:
                tags.setdefault(str(key).strip().casefold(), text)
    return tags


def _first(tags: dict[str, str], name: str) -> str:
    return next((tags[k] for k in _KEYS[name] if tags.get(k)), "")


def _number(text: str) -> Optional[int]:
    """"3", "03/12", "3 of 12" -> 3."""
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) or None if match else None


def _seconds(data: dict) -> Optional[float]:
    for value in [(data.get("format") or {}).get("duration")] + [
            s.get("duration") for s in data.get("streams") or [] if s.get("codec_type") == "audio"]:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if seconds > 0:
            return seconds
    return None


def _picture(data: dict) -> Optional[int]:
    """The embedded picture to use as the cover: the one marked as the front, else the first."""
    pictures = [s for s in data.get("streams") or [] if s.get("codec_type") == "video"
                and (s.get("disposition") or {}).get("attached_pic") and s.get("codec_name") in ("mjpeg", "png")]
    front = [s for s in pictures if "front" in str((s.get("tags") or {}).get("comment", "")).casefold()]
    chosen = (front or pictures or [None])[0]
    return None if chosen is None else int(chosen.get("index", 0))


def _disc_from_folder(path: Path) -> Optional[int]:
    match = _DISC_FOLDER.match(path.parent.name.strip())
    return (int(match.group(1)) or None) if match else None


def read_file(path: Path, data: dict) -> LocalFile:
    """One file's tags from ffprobe's JSON; a file without a title tag is named from its file name."""
    tags = _tag_map(data)
    audio = next((s for s in data.get("streams") or [] if s.get("codec_type") == "audio"), {})
    item = LocalFile(Path(path), title=_first(tags, "title"), artist=_first(tags, "artist"),
                     album=_first(tags, "album"), album_artist=_first(tags, "album_artist"),
                     date=_first(tags, "date"), genre=_first(tags, "genre"),
                     track=_number(_first(tags, "track")), disc=_number(_first(tags, "disc")),
                     seconds=_seconds(data), codec=str(audio.get("codec_name") or "").upper(),
                     picture=_picture(data), mb_album=_first(tags, "mb_album"), cuesheet=_first(tags, "cuesheet"))
    if item.disc is None:
        item.disc = _disc_from_folder(item.path)
    if not item.title:
        item.named_from_file = True
        match = _FILE_NUMBER.match(item.path.stem)
        if match:
            if item.track is None:
                item.track = int(match.group(2)) or None
            if item.disc is None and match.group(1):
                item.disc = int(match.group(1)) or None
            item.title = match.group(3).strip()
        else:
            item.title = item.path.stem.strip()
    return item


# ---------------------------------------------------------------- CUE sheets

@dataclass
class CueTrack:
    number: int
    title: str = ""
    performer: str = ""
    start: Optional[float] = None      # INDEX 01, seconds into its file
    file: str = ""                     # the FILE line it falls under


@dataclass
class CueSheet:
    title: str = ""
    performer: str = ""
    date: str = ""
    genre: str = ""
    disc: Optional[int] = None
    files: list[str] = field(default_factory=list)
    tracks: list[CueTrack] = field(default_factory=list)


_CUE_LINE = re.compile(r"^\s*(REM\s+)?(\w+)\s*(.*?)\s*$", re.IGNORECASE)


def _cue_value(text: str) -> str:
    """A quoted value up to its closing quote, or the bare rest of the line."""
    text = text.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        return (text[1:end] if end > 0 else text[1:]).strip()
    return text


def _cue_file_name(rest: str) -> str:
    """FILE "name.flac" WAVE / FILE name.flac WAVE -> name.flac."""
    rest = rest.strip()
    if rest.startswith('"'):
        return _cue_value(rest)
    head, _, kind = rest.rpartition(" ")
    return head.strip() if head and kind.isalpha() else rest


def parse_cue(text: str) -> CueSheet:
    """A CUE sheet's album fields and its audio tracks (title, performer, start, file)."""
    sheet = CueSheet()
    track: Optional[CueTrack] = None
    current_file = ""
    for line in text.splitlines():
        match = _CUE_LINE.match(line)
        if not match:
            continue
        rem, key, rest = bool(match.group(1)), match.group(2).upper(), match.group(3)
        if rem:
            if track is None and key in ("DATE", "GENRE"):
                setattr(sheet, key.lower(), _cue_value(rest))
            elif track is None and key == "DISCNUMBER":
                sheet.disc = _number(_cue_value(rest))
        elif key == "FILE":
            current_file = _cue_file_name(rest)
            sheet.files.append(current_file)
        elif key == "TRACK":
            track = CueTrack(_number(rest) or len(sheet.tracks) + 1, file=current_file)
            if "AUDIO" in rest.upper():
                sheet.tracks.append(track)
        elif key == "INDEX" and track is not None:
            parts = rest.split()
            stamp = parts[1].split(":") if len(parts) == 2 else []
            if _number(parts[0] if parts else "") == 1 and len(stamp) == 3 and all(p.isdigit() for p in stamp):
                track.start = int(stamp[0]) * 60 + int(stamp[1]) + int(stamp[2]) / 75.0
        elif key in ("TITLE", "PERFORMER"):
            setattr(track if track is not None else sheet, key.lower(), _cue_value(rest))
    return sheet


def read_cue(path: Path) -> Optional[CueSheet]:
    try:
        data = path.read_bytes()[:1024 * 1024]
    except OSError:
        return None
    sheet = parse_cue(decode_text(data))
    return sheet if sheet.tracks else None


def _same_file(name: str, path: Path) -> bool:
    """A FILE line naming this audio file. Rips converted after the sheet was written keep the old
    extension ("Album.wav" for Album.flac), so the same stem is enough."""
    named = name.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return named == path.name.casefold() or named.rsplit(".", 1)[0] == path.stem.casefold()


def cue_audio_files(cue: Path) -> list[Path]:
    """The audio files beside a CUE sheet that it describes."""
    sheet = read_cue(cue)
    if sheet is None:
        return []
    try:
        audio = [p for p in cue.parent.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_TYPES]
    except OSError:
        return []
    return sorted({p for p in audio for name in sheet.files if _same_file(name, p)}, key=_natural)


def folder_cues(folder: Path) -> list[tuple[Path, CueSheet]]:
    try:
        cues = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".cue"), key=_natural)
    except OSError:
        return []
    return [(p, sheet) for p in cues for sheet in [read_cue(p)] if sheet is not None]


def _sheet_for(item: LocalFile, cues: list[tuple[Path, CueSheet]]) -> Optional[CueSheet]:
    """The sheet describing this file: one embedded in it, a .cue naming it, or a .cue of the same name."""
    if item.cuesheet:
        sheet = parse_cue(item.cuesheet)
        if sheet.tracks:
            return sheet
    for _, sheet in cues:
        if any(_same_file(name, item.path) for name in sheet.files):
            return sheet
    for path, sheet in cues:
        if path.stem.casefold() in (item.path.stem.casefold(), item.path.name.casefold()):
            return sheet
    return None


def _copy(item: LocalFile, **changes) -> LocalFile:
    return LocalFile(**{**item.__dict__, **changes})


def split_by_cue(item: LocalFile, sheet: CueSheet) -> list[LocalFile]:
    """
    One file as the songs its CUE sheet lists. A whole-disc image becomes one entry per track, each
    as long as the gap to the next track's start (the last runs to the end of the file). A file the
    sheet lists as a single track only takes the sheet's names where its own tags have none.
    """
    tracks = [t for t in sheet.tracks if _same_file(t.file, item.path)] if len(sheet.files) > 1 else list(sheet.tracks)
    if not tracks:
        return [item]
    album = dict(album=item.album or sheet.title, album_artist=item.album_artist or sheet.performer,
                 date=item.date or sheet.date, genre=item.genre or sheet.genre, disc=item.disc or sheet.disc)
    if len(tracks) == 1:
        only, changes = tracks[0], dict(album)
        if item.named_from_file and only.title:
            changes.update(title=only.title, named_from_file=False)
        if not item.artist:
            changes["artist"] = only.performer or sheet.performer
        if item.track is None:
            changes["track"] = only.number
        return [_copy(item, **changes)]
    songs = []
    for i, track in enumerate(tracks):
        start = track.start or 0.0
        end = tracks[i + 1].start if i + 1 < len(tracks) else item.seconds
        songs.append(_copy(item, **album, title=track.title or f"Track {track.number:02d}",
                           artist=track.performer or sheet.performer or item.artist, track=track.number,
                           seconds=end - start if end is not None and end > start else None,
                           start=start, named_from_file=False, cuesheet=""))
    return songs


def apply_cues(items: list[LocalFile], cues_by_folder: dict[Path, list[tuple[Path, CueSheet]]]) -> list[LocalFile]:
    """Every file, with whole-disc images split into their songs by their CUE sheets."""
    out: list[LocalFile] = []
    for item in items:
        sheet = _sheet_for(item, cues_by_folder.get(item.path.parent, []))
        out += split_by_cue(item, sheet) if sheet else [item]
    return out


# ---------------------------------------------------------------- grouping into albums

def _album_folder(path: Path) -> Path:
    """The folder an album lives in: past a "CD1" / "Disc 2" subfolder to the set's own folder."""
    parent = path.parent
    return parent.parent if _DISC_FOLDER.match(parent.name.strip()) else parent


def _majority(values: Iterable[str]) -> tuple[str, bool]:
    """The value most files carry, and whether some files carry another one."""
    counts = Counter(v for v in values if v)
    if not counts:
        return "", False
    return counts.most_common(1)[0][0], len(counts) > 1


def _strip_shared_artist(files: list[LocalFile]) -> None:
    """
    Titles taken from file names such as "01 - Artist - Song": when every one of them starts with
    the same "X - ", that is the artist, not part of the song's name.
    """
    named = [f for f in files if f.named_from_file]
    if len(named) < 2:
        return
    heads = {f.title.split(" - ", 1)[0].strip().casefold() if " - " in f.title else None for f in named}
    if len(heads) == 1 and None not in heads:
        for f in named:
            head, _, rest = f.title.partition(" - ")
            f.artist = f.artist or head.strip()
            f.title = rest.strip()


def group(files: list[LocalFile]) -> list[LocalAlbum]:
    """
    Files sorted into albums: by album tag (and album artist, so two "Greatest Hits" stay apart),
    else by folder. Within an album, by disc then track number, else by file name.
    """
    buckets: dict[tuple, list[LocalFile]] = {}
    for f in files:
        key = (("tag", f.album.casefold(), f.album_artist.casefold()) if f.album
               else ("folder", str(_album_folder(f.path)).casefold()))
        buckets.setdefault(key, []).append(f)
    albums = []
    for members in buckets.values():
        _strip_shared_artist(members)
        members.sort(key=lambda f: (f.disc or 1, f.track if f.track is not None else 10 ** 6, _natural(f.path),
                                    f.start or 0.0))
        by_disc: dict[int, list[LocalFile]] = {}
        for f in members:
            by_disc.setdefault(f.disc or 1, []).append(f)
        album, album_mixed = _majority(f.album for f in members)
        album_artist, _ = _majority(f.album_artist for f in members)
        artist, _ = _majority(f.artist for f in members)
        date, date_mixed = _majority(f.date for f in members)
        genre, _ = _majority(f.genre for f in members)
        mb_album, _ = _majority(f.mb_album for f in members)
        folder = _album_folder(members[0].path)
        albums.append(LocalAlbum(
            album=album or folder.name, artist=album_artist or artist, album_artist=album_artist or artist,
            date=date, genre=genre, folder=folder, discs=[by_disc[n] for n in sorted(by_disc)],
            codecs=sorted({f.codec for f in members if f.codec}), mb_album=mb_album,
            mixed=[name for name, flag in (("album", album_mixed), ("date", date_mixed)) if flag],
            folder_cover=folder_image(folder)))
    albums.sort(key=lambda a: _natural(a.folder or Path()))
    return albums


def folder_image(folder: Path) -> Optional[Path]:
    """The cover image beside the music: a known name first (cover, folder, front...), else a lone image."""
    try:
        images = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_TYPES]
    except OSError:
        return None
    by_name = {p.stem.casefold(): p for p in sorted(images, key=_natural)}
    for name in COVER_NAMES:
        if name in by_name:
            return by_name[name]
    for name in COVER_NAMES:      # "cover_1200", "Folder (front)"...
        found = next((p for stem, p in by_name.items() if stem.startswith(name)), None)
        if found:
            return found
    return images[0] if len(images) == 1 else None


def pick_cover(album: LocalAlbum, prefer: str = "embedded") -> Optional[Path]:
    """The cover by the user's preference, falling back to the other kind when there is none."""
    order = (album.embedded_cover, album.folder_cover)
    if prefer == "folder":
        order = order[::-1]
    return next((p for p in order if p and p.is_file()), None)


# ---------------------------------------------------------------- what the metadata page shows

def candidate(album: LocalAlbum, number: int) -> Candidate:
    return Candidate("local", str(number), album.album, album.artist, album.date, len(album.files),
                     " · ".join(x for x in ("/".join(album.codecs), album.date[:4]) if x),
                     disc_track_counts=[len(d) for d in album.discs])


def album_info(album: LocalAlbum) -> AlbumInfo:
    discs = [[TrackInfo(f.title, f.artist or album.artist, f.seconds) for f in disc] for disc in album.discs]
    return AlbumInfo("local", album.album, album.artist, album.album_artist, album.date, album.genre, "",
                     [t for disc in discs for t in disc], discs)


# ---------------------------------------------------------------- ffprobe / ffmpeg

def probe(path: Path) -> dict:
    args = [tools.TOOL_PATHS["ffprobe"], "-v", "error", "-of", "json",
            "-show_entries", "format=duration:format_tags:stream=index,codec_type,codec_name,duration"
                             ":stream_tags:stream_disposition=attached_pic",
            str(path)]
    try:
        result = tools.run(args, timeout=30)
    except FileNotFoundError as exc:
        raise Failure("local_ffprobe", "ffprobe was not found; it is needed to read music files.") from exc
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def extract_picture(item: LocalFile, cache_dir: Path) -> Optional[Path]:
    """Copy a file's embedded cover into the cache (named by the file and its date, so it is read once)."""
    if item.picture is None:
        return None
    try:
        stat = item.path.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{item.path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    for suffix in (".jpg", ".png"):
        cached = cache_dir / f"local-{key}{suffix}"
        if cached.is_file() and cached.stat().st_size:
            return cached
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw = cache_dir / f"local-{key}.part"
    args = [tools.TOOL_PATHS["ffmpeg"], "-v", "error", "-y", "-i", str(item.path), "-map", f"0:{item.picture}",
            "-c", "copy", "-f", "image2", str(raw)]
    try:
        result = tools.run(args, timeout=30)
        head = raw.read_bytes()[:8] if raw.is_file() else b""
    except (OSError, Failure):
        return None
    suffix = ".jpg" if head.startswith(b"\xff\xd8\xff") else ".png" if head.startswith(b"\x89PNG") else None
    if result.returncode != 0 or suffix is None:
        raw.unlink(missing_ok=True)
        return None
    target = raw.with_suffix(suffix)
    raw.replace(target)
    return target


def scan(paths: Iterable[Path], cache_dir: Path) -> list[LocalAlbum]:
    """Read every music file among paths and sort them into albums (embedded covers extracted)."""
    files = collect(paths)
    with ThreadPoolExecutor(max_workers=8) as pool:
        probed = list(pool.map(probe, files))
    read = [read_file(path, data) for path, data in zip(files, probed) if data]
    if not read:
        raise Failure("local_unreadable", "None of the music files could be read.")
    read = apply_cues(read, {folder: folder_cues(folder) for folder in {f.path.parent for f in read}})
    albums = group(read)
    for album in albums:
        with_picture = next((f for f in album.files if f.picture is not None), None)
        if with_picture is not None:
            album.embedded_cover = extract_picture(with_picture, cache_dir)
    return albums
