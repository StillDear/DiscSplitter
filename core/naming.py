"""Output names: file name templates, the planned files of an export, album folder names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tagging

from .models import Chapter


# ---------------------------------------------------------------------------
# Splitting: extracted MKV + chapters -> individual named files
# ---------------------------------------------------------------------------

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserves these as device names - "CON.mkv" etc silently fails or
# hits the device instead of creating a file, even though the name looks
# fine on Linux/macOS where this tool is often developed/tested.
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(name: str) -> str:
    name = _INVALID_FILENAME_CHARS.sub("", name).strip()
    # Windows silently strips trailing dots/spaces from filenames, which
    # means "Track. " and "Track" collide without ever showing a warning -
    # strip them ourselves so what we display matches what actually lands
    # on disk.
    name = name.rstrip(" .")
    if not name:
        name = "Untitled"
    if name.upper() in _WINDOWS_RESERVED_NAMES:
        name = f"_{name}"
    return name


# Filename presets offered in the settings. "title" is the long-standing default.
FILENAME_TEMPLATES = {
    "title": "{title}",
    "nn_title": "{nn} - {title}",
    "nn_dot_title": "{nn}. {title}",
    "artist_title": "{artist} - {title}",
}


def render_filename(template: str, number: int, title: str, artist: str = "") -> str:
    """Fill a FILENAME_TEMPLATES preset; a missing artist just drops the "artist - " part."""
    pattern = FILENAME_TEMPLATES.get(template, "{title}")
    if "{artist}" in pattern and not artist.strip():
        pattern = "{title}"
    return pattern.format(nn=f"{number:02d}", n=number, title=title, artist=sanitize_filename(artist) if artist else "")


@dataclass
class PlannedOutput:
    chapter: "Chapter"
    path: Path
    exists: bool = False
    duplicate_name: bool = False  # another chapter sanitises to the same track name


def plan_output_files(
    chapters: list[Chapter],
    output_folder: Path,
    container: str = "mkv",
    *,
    number_filenames: bool = False,
    filename_template: str = "",
    metadata: Optional[dict] = None,
) -> list[PlannedOutput]:
    """
    Assign unique filenames before checking for existing files on disk.

    filename_template picks a FILENAME_TEMPLATES preset; numbers count the
    exported chapters (1, 2, 3...), like the track tags. Without it the
    legacy number_filenames switch applies (original chapter numbers).
    """
    stems: list[str] = []
    name_counts: dict[str, int] = {}
    for position, ch in enumerate(chapters, start=1):
        base = sanitize_filename(ch.name or f"Track {ch.index:02d}")
        if filename_template and filename_template != "title":
            stem = sanitize_filename(render_filename(filename_template, position, base,
                                                     tagging.artist_for(metadata, ch.index)))
        elif number_filenames:
            stem = f"{ch.index:02d} - {base}"
        else:
            stem = base
            if stem.split(".", 1)[0].rstrip().upper() in _WINDOWS_RESERVED_NAMES:
                stem = f"_{stem}"
        stems.append(stem)
        key = stem.casefold()
        name_counts[key] = name_counts.get(key, 0) + 1

    planned: list[PlannedOutput] = []
    used: set[str] = set()
    for ch, stem in zip(chapters, stems):
        candidate = stem
        if candidate.casefold() in used:
            suffix = 2
            while True:
                candidate = f"{stem} ({suffix})"
                if candidate.casefold() not in used and candidate.casefold() not in name_counts:
                    break
                suffix += 1
        used.add(candidate.casefold())
        path = output_folder / f"{candidate}.{container}"
        planned.append(
            PlannedOutput(
                chapter=ch,
                path=path,
                exists=path.exists(),
                duplicate_name=name_counts[stem.casefold()] > 1,
            )
        )

    return planned


def preflight_check(
    output_folder: Path,
    chapter_count: int,
    track_names: dict[int, str],
    container: str = "mkv",
    chapter_indices: Optional[list[int]] = None,
    *,
    number_filenames: bool = False,
    filename_template: str = "",
    metadata: Optional[dict] = None,
) -> list[PlannedOutput]:
    """
    Compute planned output filenames and existence collisions using just
    the chapter count and the names the user has already typed in -
    before the slow mkvmerge extraction step even starts. Chapter start
    times aren't known yet at this point and aren't needed for filename
    planning, so this uses placeholder timestamps.
    """
    indices = range(1, chapter_count + 1) if chapter_indices is None else chapter_indices
    fake_chapters = [
        Chapter(index=i, start_seconds=0.0, name=track_names.get(i, ""))
        for i in indices
    ]
    return plan_output_files(fake_chapters, output_folder, container=container, number_filenames=number_filenames,
                             filename_template=filename_template, metadata=metadata)


class OutputCollisionError(RuntimeError):
    """
    Raised when one or more planned output files already exist on disk and
    weren't explicitly approved for overwrite. Nothing is ever overwritten
    silently - the caller (GUI or CLI) must resolve this before splitting
    can proceed, typically via preflight_check() + user confirmation.
    """

    def __init__(self, colliding: list[PlannedOutput]):
        self.colliding = colliding
        names = ", ".join(p.path.name for p in colliding)
        super().__init__(
            f"{len(colliding)} output file(s) already exist and were not "
            f"approved for overwrite: {names}"
        )


_TRAILING_BRACKET_RE = re.compile(r"\s*[\[\(][^\[\]\(\)]*[\]\)]\s*$")


def derive_album_folder_name(source_folder: Path) -> str:
    """
    Turn a disc-rip folder name into a clean album folder name, e.g.
    "Fleetwood Mac - Fleetwood Mac (1975) [Blu-ray]" -> keeps the year,
    only strips a trailing "[Blu-ray]"-style disc/format tag.
    """
    name = source_folder.name
    # Repeatedly strip trailing bracketed tags if they look like disc/format
    # labels rather than a release year - years are 4 digits in parens and
    # should be kept (e.g. "(1975)"). Handles multiple stacked tags like
    # "Album (2020) [Blu-ray] [1080p]".
    while True:
        m = _TRAILING_BRACKET_RE.search(name)
        if not m or re.fullmatch(r"[\(]\d{4}[\)]", m.group(0).strip()):
            break
        name = name[: m.start()].strip()
    # A leading format tag such as "[DVD-ISO]" or "[BDMV]" is not part of the name either.
    name = re.sub(r"^(?:\[(?:[^\]]*\b(?:dvd|bd|bdmv|blu-?ray|iso|bdiso)\b[^\]]*)\]\s*)+", "", name,
                  flags=re.IGNORECASE).strip() or name
    return sanitize_filename(name) or source_folder.name


_YEAR_RE = re.compile(r"\((\d{4})\)")


def guess_artist_album_year(source_folder: Path) -> tuple[str, str, Optional[int]]:
    """
    Best-effort guess at artist/album/year from a disc-rip folder name,
    to prefill the MusicBrainz search form - e.g. "Fleetwood Mac -
    Fleetwood Mac (1975) [Blu-ray]" splits on the first " - " into
    artist/album and pulls the year out separately. Purely a starting
    point for a form the user reviews and can edit before anything is
    sent to MusicBrainz - if the folder name doesn't fit the pattern,
    this just returns an empty artist and the whole cleaned name as the
    album guess.
    """
    name = derive_album_folder_name(source_folder)
    year_match = _YEAR_RE.search(name)
    year = int(year_match.group(1)) if year_match else None
    if year_match:
        name = name[: year_match.start()].strip()

    if " - " in name:
        artist, _, album = name.partition(" - ")
        return artist.strip(), album.strip(), year
    return "", name.strip(), year
