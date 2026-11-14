"""
tagging.py

Turns the user's metadata choices into ffmpeg arguments for each split
chapter file. No GUI or network code - just data in, argument list out,
so it is easy to test and is shared by the pipeline and any CLI use.

Metadata is a plain JSON-serialisable dict (it is stored in the job
manifest so a resumed job tags its files identically):

    {
      "album":  {"artist", "album", "album_artist", "date", "genre"},
      "track_artists": {"3": "Artist feat. Guest"},   # chapter index -> artist override
      "audio":  {"title": "TrueHD Atmos 7.1", "language": "eng", "default": True},
      "cover":  "C:/.../cover.jpg",                   # optional local image
      "cover_mode": "both"                            # "both" | "embed" | "folder"
    }
"""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional
from uuid import uuid4

ALBUM_FIELDS = ("artist", "album", "album_artist", "date", "genre")
COVER_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def empty_metadata() -> dict:
    return {
        "album": {key: "" for key in ALBUM_FIELDS},
        "track_artists": {},
        "audio": {"title": "", "language": "", "default": True},
        "cover": "",
    }


def _clean(value) -> str:
    # ffmpeg takes each value as one argv item, so only strip control characters.
    return "".join(ch for ch in str(value or "") if ch >= " " or ch == "\t").strip()


def cover_path(metadata: Optional[dict]) -> Optional[Path]:
    path = Path(_clean((metadata or {}).get("cover")))
    if str(path) not in ("", ".") and path.suffix.lower() in COVER_TYPES and path.is_file():
        return path
    return None


def embedded_cover(metadata: Optional[dict]) -> Optional[Path]:
    if (metadata or {}).get("cover_mode", "both") in ("both", "embed"):
        return cover_path(metadata)
    return None


def artist_for(metadata: Optional[dict], index: int) -> str:
    """Per-track artist if set, else the album artist."""
    metadata = metadata or {}
    album = metadata.get("album") or {}
    return _clean((metadata.get("track_artists") or {}).get(str(index)) or album.get("artist"))


def file_tags(metadata: Optional[dict], index: int, total: int, title: str,
              track_number: Optional[int] = None) -> list[tuple[str, str]]:
    """Matroska tag names/values for one song file (the names ffmpeg would write)."""
    metadata = metadata or {}
    album = metadata.get("album") or {}
    number = index if track_number is None else track_number
    pairs = [
        ("TITLE", title),
        ("PART_NUMBER", f"{number}/{total}" if total else str(number)),
        ("ARTIST", artist_for(metadata, index)),
        ("ALBUM_ARTIST", album.get("album_artist") or album.get("artist")),
        ("ALBUM", album.get("album")),
        ("DATE", album.get("date")),
        ("GENRE", album.get("genre")),
    ]
    return [(name, _clean(value)) for name, value in pairs if _clean(value)]


def tags_xml(pairs: list[tuple[str, str]]) -> str:
    """A Matroska tags file applying to the whole file (no targets), for mkvpropedit --tags global:."""
    from xml.sax.saxutils import escape
    simple = "".join(f"<Simple><Name>{escape(name)}</Name><String>{escape(value)}</String></Simple>"
                     for name, value in pairs)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<Tags><Tag><Targets/>{simple}</Tag></Tags>\n'


def chapter_args(metadata: Optional[dict], index: int, total: int, title: str, *,
                 container: str = "mkv", track_number: Optional[int] = None) -> list[str]:
    """ffmpeg output options that tag one chapter file (placed before the output path)."""
    if not metadata and track_number is None:
        return []
    metadata = metadata or {}
    album = metadata.get("album") or {}
    args: list[str] = []

    def tag(key: str, value, spec: str = "") -> None:
        value = _clean(value)
        if value:
            args.extend([f"-metadata{spec}", f"{key}={value}"])

    tag("title", title)
    number = index if track_number is None else track_number
    tag("track", f"{number}/{total}" if total else number)
    artist = (metadata.get("track_artists") or {}).get(str(index)) or album.get("artist")
    tag("artist", artist)
    tag("album_artist", album.get("album_artist") or album.get("artist"))
    for key in ("album", "date", "genre"):
        tag(key, album.get(key))

    if container == "flac":
        return args

    audio = metadata.get("audio") or {}
    tag("title", audio.get("title"), ":s:a:0")
    tag("language", audio.get("language"), ":s:a:0")
    if "default" in audio:
        args.extend(["-disposition:a:0", "+default" if audio.get("default") else "-default"])

    cover = embedded_cover(metadata)
    if cover is not None:
        args.extend([
            "-attach", str(cover),
            "-metadata:s:t", f"mimetype={COVER_TYPES[cover.suffix.lower()]}",
            "-metadata:s:t", f"filename=cover{cover.suffix.lower()}",
        ])
    return args


def write_folder_cover(metadata: Optional[dict], output_folder: Path) -> Optional[Path]:
    """Copy the cover next to the songs as cover.jpg/.png (what Plex / Jellyfin / Kodi look for)."""
    cover = cover_path(metadata)
    if cover is None or (metadata or {}).get("cover_mode", "both") not in ("both", "folder"):
        return None
    target = output_folder / f"cover{cover.suffix.lower().replace('.jpeg', '.jpg')}"
    if not target.exists() or metadata.get('replace_folder_cover'):
        output_folder.mkdir(parents=True, exist_ok=True)
        pending = output_folder / f'.cover-{uuid4().hex}.tmp'
        try:
            shutil.copyfile(cover, pending)
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)
    return target
