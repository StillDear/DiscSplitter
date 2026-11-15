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


# ---------------------------------------------------------------------------
# The title of a Matroska file, set in place (as mkvpropedit does)
# ---------------------------------------------------------------------------
# The engine writes one title for every part of a split. It is given a placeholder of TITLE_ROOM bytes; each part's
# own title is then written over it, the bytes left over becoming a Void element, so nothing in the file moves. The
# segment info carries a CRC-32, which is written again.

TITLE_ROOM = 512
TITLE_PLACEHOLDER = "DiscSplitter-title-" + "." * (TITLE_ROOM - 19)
_INFO_ID = b"\x15\x49\xa9\x66"
_TITLE_ID = b"\x7b\xa9"
_SEGMENT_ID = b"\x18\x53\x80\x67"


def _read_size(data: bytes, pos: int) -> tuple[int, int]:
    """An EBML size at pos: (value, width)."""
    first = data[pos]
    width = 1
    while width <= 8 and not first & (0x80 >> (width - 1)):
        width += 1
    if width > 8:
        raise ValueError("not an EBML size")
    value = first & (0xFF >> width)
    for byte in data[pos + 1:pos + width]:
        value = (value << 8) | byte
    return value, width


def _size(value: int, width: int) -> bytes:
    if value >= (1 << (7 * width)) - 1:
        raise ValueError("size does not fit")
    return ((1 << (7 * width)) | value).to_bytes(width, "big")


def _void(length: int) -> bytes:
    """A Void element of exactly `length` bytes (at least 2)."""
    if length - 2 < 127:
        return b"\xec" + _size(length - 2, 1) + bytes(length - 2)
    return b"\xec" + _size(length - 9, 8) + bytes(length - 9)


def _element_id(data: bytes, pos: int) -> tuple[bytes, int]:
    first = data[pos]
    width = 1
    while width <= 4 and not first & (0x80 >> (width - 1)):
        width += 1
    if width > 4:
        raise ValueError("not an EBML ID")
    return bytes(data[pos:pos + width]), width


def _segment_info(head: bytes, path: Path) -> tuple[int, int]:
    """(where the body of the segment info starts, its size), walking the file's top-level elements."""
    pos = 0
    ident, width = _element_id(head, pos)                # the EBML header
    size, size_width = _read_size(head, pos + width)
    pos += width + size_width + size
    ident, width = _element_id(head, pos)                # the segment
    if ident != _SEGMENT_ID:
        raise ValueError(f"{path.name}: not a Matroska file")
    pos += width + _read_size(head, pos + width)[1]
    while pos < len(head) - 12:
        ident, width = _element_id(head, pos)
        size, size_width = _read_size(head, pos + width)
        if ident == _INFO_ID:
            if pos + width + size_width + size > len(head):
                break
            return pos + width + size_width, size
        pos += width + size_width + size
    raise ValueError(f"{path.name}: no segment info near the start")


def set_matroska_title(path: Path, title: str, placeholder: str = TITLE_PLACEHOLDER) -> None:
    """Write `title` over the placeholder title of a Matroska file, in place."""
    import zlib
    with open(path, "r+b") as f:
        head = f.read(1 << 16)
        start, size = _segment_info(head, path)
        body = bytearray(head[start:start + size])
        key = placeholder.encode("utf-8")
        place = body.find(key)
        if place < 0:
            raise ValueError(f"{path.name}: the title to replace is not there")
        for w in range(1, 9):     # the title element's own size, just before its text
            if place - w - 2 >= 0 and body[place - w - 2:place - w] == _TITLE_ID and \
                    _read_size(body, place - w) == (len(key), w):
                break
        else:
            raise ValueError(f"{path.name}: the title element is not as expected")
        text = title.encode("utf-8")
        while len(text) > len(key):                     # cut at a whole character
            text = text[:-1]
            while text and (text[-1] & 0xC0) == 0x80:
                text = text[:-1]
            text = text[:-1] if text and text[-1] >= 0xC0 else text
        if len(key) - len(text) == 1:                   # no Void element is one byte long
            text += b" "
        rest = len(key) - len(text)
        body[place - w:place + len(key)] = _size(len(text), w) + text + (_void(rest) if rest else b"")
        if body[:2] == b"\xbf\x84":                     # CRC-32 of everything after it
            body[2:6] = (zlib.crc32(bytes(body[6:])) & 0xFFFFFFFF).to_bytes(4, "little")
        f.seek(start)
        f.write(body)


_SEEKHEAD_ID = b"\x11\x4d\x9b\x74"
_SEEK_ID = b"\x4d\xbb"
_SEEK_ID_ID = b"\x53\xab"
CHAPTERS_ID = b"\x10\x43\xa7\x70"
ATTACHMENTS_ID = b"\x19\x41\xa4\x69"


def _top_level(f, file_size: int) -> list[tuple[bytes, int, int]]:
    """(ID, position, whole length) of the segment's top-level elements, read header by header."""
    f.seek(0)
    head = f.read(64)
    ident, width = _element_id(head, 0)
    size, size_width = _read_size(head, width)
    pos = width + size_width + size                     # past the EBML header
    f.seek(pos)
    head = f.read(16)
    ident, width = _element_id(head, 0)
    if ident != _SEGMENT_ID:
        raise ValueError("not a Matroska file")
    pos += width + _read_size(head, width)[1]
    found = []
    while pos < file_size:
        f.seek(pos)
        head = f.read(16)
        if len(head) < 2:
            break
        ident, width = _element_id(head, 0)
        size, size_width = _read_size(head, width)
        found.append((ident, pos, width + size_width + size))
        pos += width + size_width + size
    return found


def blank_matroska_elements(path: Path, ids: tuple[bytes, ...] = (CHAPTERS_ID, ATTACHMENTS_ID)) -> None:
    """
    Turn top-level elements of a Matroska file (by default its chapters and attachments) into Void elements of the
    same length, in place, and their entries in the SeekHead too (whose CRC-32 is written again).
    """
    import zlib
    with open(path, "r+b") as f:
        elements = _top_level(f, path.stat().st_size)
        blanked = False
        for ident, pos, length in elements:
            if ident in ids:
                f.seek(pos)
                f.write(_void(length))
                blanked = True
        if not blanked:
            return
        for ident, pos, length in elements:
            if ident != _SEEKHEAD_ID:
                continue
            f.seek(pos)
            whole = bytearray(f.read(length))
            width = len(ident)
            size, size_width = _read_size(whole, width)
            start = width + size_width
            at = start
            while at < start + size:
                child, child_width = _element_id(whole, at)
                child_size, child_size_width = _read_size(whole, at + child_width)
                end = at + child_width + child_size_width + child_size
                if child == _SEEK_ID:
                    inner = bytes(whole[at + child_width + child_size_width:end])
                    marker = inner.find(_SEEK_ID_ID)
                    if marker >= 0:
                        id_size, id_width = _read_size(inner, marker + 2)
                        target = inner[marker + 2 + id_width:marker + 2 + id_width + id_size]
                        if target in ids:
                            whole[at:end] = _void(end - at)
                at = end
            if whole[start:start + 2] == b"\xbf\x84":
                whole[start + 2:start + 6] = (zlib.crc32(bytes(whole[start + 6:start + size])) & 0xFFFFFFFF) \
                    .to_bytes(4, "little")
            f.seek(pos)
            f.write(whole)
