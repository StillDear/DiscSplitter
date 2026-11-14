"""Track names from text: sidecar files, pasted lists, and aligning them with chapters."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import Chapter


_LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[\.\)\-]?\s*")


def strip_leading_number(line: str) -> str:
    """Strip a leading '1.', '01 -', '1)' etc from a pasted or imported tracklist line."""
    return _LEADING_NUMBER_RE.sub("", line).strip()


# ---------------------------------------------------------------------------
# Track-name discovery: disc-local sidecar files and user-imported tracklists
# ---------------------------------------------------------------------------

@dataclass
class TracklistEntry:
    name: str
    index: Optional[int] = None
    start_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None


EXPORTED_TRACKLIST_FORMAT = "DiscSplitter.chapter-titles.v1"


def parse_exported_tracklist(text: str) -> Optional[list[TracklistEntry]]:
    """Read a saved chapter mapping, or return None for another input format."""
    text = text.lstrip("\ufeff \t\r\n")
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        if EXPORTED_TRACKLIST_FORMAT in text:
            raise ValueError("Invalid chapter mapping") from exc
        return None
    if data.get("format") != EXPORTED_TRACKLIST_FORMAT:
        return None
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("Invalid chapter mapping")
    entries = []
    seen = set()
    for item in chapters:
        if not isinstance(item, dict):
            raise ValueError("Invalid chapter mapping")
        index, title = item.get("chapter"), item.get("title")
        if type(index) is not int or index < 1 or index in seen or not isinstance(title, str) or not title.strip():
            raise ValueError("Invalid chapter mapping")
        seen.add(index)
        entries.append(TracklistEntry(name=title, index=index))
    return entries


def export_chapter_tracklist(titles: dict[int, str]) -> str:
    return json.dumps({
        "format": EXPORTED_TRACKLIST_FORMAT,
        "chapters": [{"chapter": index, "title": title} for index, title in sorted(titles.items())],
    }, ensure_ascii=False, indent=2) + "\n"


def find_sidecar_tracklist_files(disc_folder: Path) -> list[Path]:
    """
    Look for disc-local files that might carry track names: a plain text
    or NFO tracklist dropped next to the disc, a CUE sheet, a previously
    saved project mapping (*.tracklist.json), or (best-effort) BDMV disc
    metadata. Only the top level of disc_folder is searched for the
    common formats - not recursively - since a deep search of the whole
    BDMV structure would surface a lot of files that have nothing to do
    with track names.

    Never applied automatically - this only finds candidates. Parsing
    happens via load_sidecar_tracklist(), and the result still has to go
    through match_tracklist_to_chapters() and user confirmation before it
    touches any naming field.
    """
    candidates: list[Path] = []
    for pattern in ("*.nfo", "*.cue", "*.txt", "*.tracklist.json"):
        candidates.extend(sorted(disc_folder.glob(pattern)))

    meta_dl = disc_folder / "BDMV" / "META" / "DL"
    if meta_dl.is_dir():
        candidates.extend(sorted(meta_dl.glob("*.xml")))

    return candidates


def parse_plain_text_tracklist(text: str) -> list[TracklistEntry]:
    """One track name per line - the common shape for a .txt/.nfo tracklist or a pasted list."""
    entries: list[TracklistEntry] = []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        entries.append(TracklistEntry(index=i, name=strip_leading_number(line)))
    return entries


_CUE_TRACK_RE = re.compile(r'^\s*TRACK\s+(\d+)\s+AUDIO', re.IGNORECASE)
_CUE_TITLE_RE = re.compile(r'^\s*TITLE\s+"(.*)"', re.IGNORECASE)
_CUE_INDEX01_RE = re.compile(r'^\s*INDEX\s+01\s+(\d+):(\d+):(\d+)', re.IGNORECASE)


def parse_cue_tracklist(text: str) -> list[TracklistEntry]:
    """
    Parse a CUE sheet's TRACK/TITLE/INDEX 01 entries. INDEX 01 timestamps
    are mm:ss:ff (ff = frames, 75 frames/second in the Red Book standard
    CUE sheets use), which gives each track a real start time - unlike a
    plain text list, this lets match_tracklist_to_chapters() align by
    actual position instead of assuming track order matches chapter order.
    """
    entries: list[TracklistEntry] = []
    current_index: Optional[int] = None
    current_title = ""
    current_start: Optional[float] = None

    def flush() -> None:
        if current_index is not None and current_title:
            entries.append(
                TracklistEntry(index=current_index, name=current_title, start_seconds=current_start)
            )

    for line in text.splitlines():
        m = _CUE_TRACK_RE.match(line)
        if m:
            flush()
            current_index = int(m.group(1))
            current_title = ""
            current_start = None
            continue

        # Only a TITLE line *after* a TRACK line is a song title - a
        # TITLE line before the first TRACK is the album title.
        m = _CUE_TITLE_RE.match(line)
        if m and current_index is not None:
            current_title = m.group(1).strip()
            continue

        m = _CUE_INDEX01_RE.match(line)
        if m and current_index is not None:
            mm, ss, ff = m.groups()
            current_start = int(mm) * 60 + int(ss) + int(ff) / 75.0
            continue

    flush()

    for i, entry in enumerate(entries):
        if (
            i + 1 < len(entries)
            and entry.start_seconds is not None
            and entries[i + 1].start_seconds is not None
        ):
            entry.duration_seconds = entries[i + 1].start_seconds - entry.start_seconds

    return entries


def parse_json_tracklist(text: str) -> list[TracklistEntry]:
    """
    Supports a few JSON shapes:
      - a list of plain strings: ["Song One", "Song Two"]
      - a list of objects: [{"name": "...", "start_seconds": ..., "duration_seconds": ...}, ...]
      - a dict mapping chapter index -> name: {"1": "Song One", "2": "Song Two"}
        (the shape a previously saved project mapping would use)
    """
    data = json.loads(text)
    entries: list[TracklistEntry] = []

    if isinstance(data, list):
        for i, item in enumerate(data, start=1):
            if isinstance(item, str):
                if item.strip():
                    entries.append(TracklistEntry(index=i, name=item.strip()))
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or "").strip()
                if not name:
                    continue
                entries.append(
                    TracklistEntry(
                        index=item.get("index", i),
                        name=name,
                        start_seconds=item.get("start_seconds"),
                        duration_seconds=item.get("duration_seconds"),
                    )
                )
    elif isinstance(data, dict):
        for k, v in data.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            if isinstance(v, str) and v.strip():
                entries.append(TracklistEntry(index=idx, name=v.strip()))
        entries.sort(key=lambda e: e.index if e.index is not None else 0)

    return entries


def parse_disc_meta_tracklist(text: str) -> list[TracklistEntry]:
    """
    Best-effort parse of a BDMV/META/DL/*.xml disc metadata file. These
    aren't a standardised song-tracklist format - they're disc/menu
    metadata (title, thumbnails; a chapter/mark title list only shows up
    depending on the authoring tool) - so this only looks for a handful
    of common tag shapes (<chapter>/<track>/<item> with a <title> or
    <name> child) and returns an empty list if none match, rather than
    guessing at a schema that may not apply. A result from here goes
    through the same match/review step as every other source either way.
    """
    try:
        root = ET.fromstring(text.lstrip("\ufeff"))
    except ET.ParseError:
        return []

    entries: list[TracklistEntry] = []
    for tag in ("chapter", "Chapter", "track", "Track", "item", "Item"):
        for i, el in enumerate(root.iter(tag), start=1):
            title_el = (
                el.find("title") or el.find("Title") or el.find("name") or el.find("Name")
            )
            name = (title_el.text or "").strip() if title_el is not None else ""
            if name:
                entries.append(TracklistEntry(index=i, name=name))
        if entries:
            break

    return entries


def load_sidecar_tracklist(path: Path) -> list[TracklistEntry]:
    """
    Parse a sidecar tracklist file based on its extension. Raises
    ValueError with a clear, file-specific message on anything
    unparseable or empty - this is user-supplied data (someone's own
    .nfo/.cue/.txt/.json file), so a bad or unexpected file is expected
    occasionally and should read as a normal, specific error rather than
    a raw parser traceback.
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise ValueError(f"Could not read {path.name}: {exc}") from exc

    suffix = path.suffix.lower()
    try:
        if suffix == ".cue":
            entries = parse_cue_tracklist(text)
        elif suffix == ".json" or path.name.lower().endswith(".tracklist.json"):
            entries = parse_json_tracklist(text)
        elif suffix == ".xml":
            entries = parse_disc_meta_tracklist(text)
        else:
            # .nfo, .txt, and anything unrecognised - treat as plain text.
            entries = parse_plain_text_tracklist(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse {path.name} as JSON: {exc}") from exc

    if not entries:
        raise ValueError(f"{path.name} didn't contain anything recognisable as track names.")

    return entries


@dataclass
class ChapterMatch:
    chapter_index: int
    name: str = ""
    confidence: str = "no_match"   # "matched" | "duration_mismatch" | "no_match"
    detail: str = ""
    entry_index: Optional[int] = None  # which tracklist entry was used (None = none)


@dataclass
class TracklistMatchResult:
    matches: list[ChapterMatch]
    matched_count: int
    total_chapters: int
    summary: str


def can_align_by_duration(chapters: list[Chapter], entries: list[TracklistEntry]) -> bool:
    """Duration alignment needs lengths for (nearly) every entry and chapter.

    The last chapter of a playlist often has no end time (it "runs to the end
    of the file"), so a few chapters of unknown length are tolerated; they are
    simply never paired by length.
    """
    if not entries or not chapters:
        return False
    known_entries = sum(1 for e in entries if e.duration_seconds)
    known_chapters = sum(1 for ch in chapters if ch.end_seconds is not None)
    return (known_entries >= max(1, int(len(entries) * 0.8))
            and known_chapters >= max(1, int(len(chapters) * 0.8)))


def _align_by_duration(
    chapters: list[Chapter], entries: list[TracklistEntry], tolerance: float = 20.0, window: float = 45.0,
    skip_entry_cost: float = 0.3,
) -> TracklistMatchResult:
    """
    Order-preserving alignment of tracklist entries onto chapters by length.

    Concert discs usually have more chapters than the album has songs (intro,
    MC talk, encore calls...), and albums sometimes carry songs the disc does
    not. Both sides may therefore be skipped; a pair is only allowed when the
    lengths are within `window` seconds, and closer pairs score higher. A
    classic dynamic-programming sequence alignment picks the best monotonic
    pairing, so the order of the songs is never shuffled.

    Skipping a chapter is free (talk / MC chapters are common), but skipping a
    tracklist song costs a little: a live album's songs are nearly all on the
    disc, so the alignment should not leap ahead past several songs just
    because a later one happens to be a few seconds closer.
    """
    n, m = len(chapters), len(entries)
    length = [ch.end_seconds - ch.start_seconds if ch.end_seconds is not None else None for ch in chapters]

    def pair(i: int, j: int) -> Optional[float]:
        d = entries[j].duration_seconds
        if not d or length[i] is None:
            return None
        diff = abs(length[i] - d)
        return 1.0 - diff / window if diff < window else None

    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    step = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        step[i][0] = "c"
    for j in range(1, m + 1):
        step[0][j] = "e"
        best[0][j] = -skip_entry_cost * j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            options = [(best[i - 1][j], "c"), (best[i][j - 1] - skip_entry_cost, "e")]
            score = pair(i - 1, j - 1)
            if score is not None:
                options.append((best[i - 1][j - 1] + score, "m"))
            # Prefer a match on ties so equal-length runs pair up rather than skip.
            best[i][j], step[i][j] = max(options, key=lambda o: (o[0], o[1] == "m"))

    # Songs after the last matched one are simply not on this part of the disc:
    # leaving them out is free, so only gaps *between* matched songs cost.
    end_j = max(range(m + 1), key=lambda k: (best[n][k] + skip_entry_cost * (m - k), k))
    chosen: dict[int, int] = {}
    i, j = n, end_j
    while i > 0 or j > 0:
        move = step[i][j]
        if move == "m":
            chosen[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif move == "c":
            i -= 1
        else:
            j -= 1

    matches: list[ChapterMatch] = []
    for index, ch in enumerate(chapters):
        if index not in chosen:
            matches.append(ChapterMatch(chapter_index=ch.index, confidence="no_match"))
            continue
        entry_i = chosen[index]
        diff = abs(length[index] - entries[entry_i].duration_seconds)
        confidence, detail = "matched", ""
        if diff > tolerance:
            confidence = "duration_mismatch"
            detail = f"Track {ch.index} differs by {diff:.0f} seconds"
        matches.append(ChapterMatch(chapter_index=ch.index, name=entries[entry_i].name, confidence=confidence,
                                    detail=detail, entry_index=entry_i))
    matched = sum(1 for x in matches if x.confidence != "no_match")
    return TracklistMatchResult(matches=matches, matched_count=matched, total_chapters=n,
                                summary=f"{matched} of {n} chapter(s) aligned by duration")


def match_tracklist_to_chapters(
    chapters: list[Chapter],
    entries: list[TracklistEntry],
    start_tolerance_seconds: float = 8.0,
    duration_tolerance_seconds: float = 20.0,
    mode: str = "auto",
) -> TracklistMatchResult:
    """
    Propose a mapping from an imported tracklist onto actual chapters.
    Never applied automatically - this only produces per-chapter
    confidence for the caller (GUI) to show and let the user accept,
    adjust, or reject before it touches any naming field.

    Two alignment strategies, chosen by what the tracklist provides:

    - If every entry has a start_seconds (from a CUE sheet's INDEX 01
      timestamps), align each chapter to whichever unused entry's start
      time is closest, within start_tolerance_seconds. This tolerates
      chapters the tracklist doesn't cover and tracklist entries that
      don't correspond to any chapter - intros, encores, spoken
      sections, bonus features - rather than assuming a strict 1:1
      position match.

    - Otherwise (plain text/NFO/JSON names with no timing), align
      positionally: tracklist entry i -> chapter i. There's no timing
      information to align by in that case, and straight position order
      is what a pasted "one song per line" list means.

    Where an entry does carry a duration_seconds (from a CUE sheet), a
    matched chapter whose actual duration differs by more than
    duration_tolerance_seconds is flagged "duration_mismatch" rather than
    a plain match, since that usually means the tracklist is for a
    different edition/cut even though the position lined up.
    """
    matches: list[ChapterMatch] = []
    if mode == "chapter":
        indexed = {entry.index: (i, entry.name) for i, entry in enumerate(entries)}
        for ch in chapters:
            match = indexed.get(ch.index)
            if match is None:
                matches.append(ChapterMatch(chapter_index=ch.index))
            else:
                position, name = match
                matches.append(ChapterMatch(ch.index, name, "matched", entry_index=position))
        matched_count = sum(match.entry_index is not None for match in matches)
        return TracklistMatchResult(matches, matched_count, len(chapters),
                                    f"{matched_count} of {len(chapters)} chapter(s) matched")
    has_timing = bool(entries) and all(e.start_seconds is not None for e in entries)
    if not has_timing and mode != "order" and can_align_by_duration(chapters, entries):
        return _align_by_duration(chapters, entries, duration_tolerance_seconds,
                                  window=max(45.0, duration_tolerance_seconds + 25.0))

    if has_timing:
        used: set[int] = set()
        for ch in chapters:
            best_i, best_diff = None, None
            for i, entry in enumerate(entries):
                if i in used:
                    continue
                diff = abs(entry.start_seconds - ch.start_seconds)
                if best_diff is None or diff < best_diff:
                    best_i, best_diff = i, diff

            if best_i is not None and best_diff is not None and best_diff <= start_tolerance_seconds:
                entry = entries[best_i]
                used.add(best_i)
                confidence, detail = "matched", ""
                if entry.duration_seconds is not None and ch.end_seconds is not None:
                    actual_duration = ch.end_seconds - ch.start_seconds
                    duration_diff = abs(actual_duration - entry.duration_seconds)
                    if duration_diff > duration_tolerance_seconds:
                        confidence = "duration_mismatch"
                        detail = f"Track {ch.index} differs by {duration_diff:.0f} seconds"
                matches.append(
                    ChapterMatch(chapter_index=ch.index, name=entry.name, confidence=confidence, detail=detail,
                                 entry_index=best_i)
                )
            else:
                matches.append(ChapterMatch(chapter_index=ch.index, confidence="no_match"))
    else:
        for i, ch in enumerate(chapters):
            if i < len(entries) and entries[i].name:
                confidence, detail = "matched", ""
                if entries[i].duration_seconds and ch.end_seconds is not None:
                    diff = abs((ch.end_seconds - ch.start_seconds) - entries[i].duration_seconds)
                    if diff > duration_tolerance_seconds:
                        confidence, detail = "duration_mismatch", f"Track {ch.index} differs by {diff:.0f} seconds"
                matches.append(ChapterMatch(chapter_index=ch.index, name=entries[i].name, confidence=confidence,
                                            detail=detail, entry_index=i))
            else:
                matches.append(ChapterMatch(chapter_index=ch.index, confidence="no_match"))

    matched_count = sum(1 for m in matches if m.confidence in ("matched", "duration_mismatch"))
    summary = f"{matched_count} of {len(chapters)} chapter(s) matched"

    # A large gap between tracklist length and chapter count - well beyond
    # what a few bonus tracks/intros would explain - is a sign this
    # tracklist may belong to a different edition of the release entirely,
    # not just a partial match. This is a hint, not a hard rule.
    if entries and abs(len(entries) - len(chapters)) >= max(2, len(chapters) // 3):
        summary += " - candidate may be a different live edition (track counts differ significantly)"

    return TracklistMatchResult(
        matches=matches, matched_count=matched_count, total_chapters=len(chapters), summary=summary
    )
