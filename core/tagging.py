"""
The user's tag choices, turned into what an export writes: FLAC tags and cover art.
No GUI or network code - data in, argument list out.

Metadata is a plain JSON-serialisable dict (it is stored in the job manifest
so a resumed job tags its files identically):

    {
      "album":  {"artist", "album", "album_artist", "date", "genre"},
      "track_artists": {"3": "Artist feat. Guest"},   # chapter index -> artist override
      "cover":  "C:/.../cover.jpg",                   # optional local image
      "cover_mode": "both"                            # "both" | "embed" | "folder"
    }

Tags and covers go into FLAC files. MKV exports carry only each song's title;
there the metadata is used for file names (the artist) alone.
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
    """The cover to embed in each file, unless the user wants it only as a file in the folder."""
    if (metadata or {}).get("cover_mode", "both") in ("both", "embed"):
        return cover_path(metadata)
    return None


def artist_for(metadata: Optional[dict], index: int) -> str:
    """Per-track artist if set, else the album artist."""
    metadata = metadata or {}
    album = metadata.get("album") or {}
    return _clean((metadata.get("track_artists") or {}).get(str(index)) or album.get("artist"))


def flac_tag_args(metadata: Optional[dict], index: int, total: int, title: str, *,
                  track_number: Optional[int] = None) -> list[str]:
    """ffmpeg output options that tag one chapter's FLAC file (placed before the output path)."""
    if not metadata and track_number is None:
        return []
    metadata = metadata or {}
    album = metadata.get("album") or {}
    number = index if track_number is None else track_number
    tags = [
        ("title", title),
        ("track", f"{number}/{total}" if total else number),
        ("artist", artist_for(metadata, index)),
        ("album_artist", album.get("album_artist") or album.get("artist")),
        ("album", album.get("album")),
        ("date", album.get("date")),
        ("genre", album.get("genre")),
    ]
    args: list[str] = []
    for key, value in tags:
        value = _clean(value)
        if value:
            args.extend(["-metadata", f"{key}={value}"])
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
