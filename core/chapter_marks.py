"""Chapter markers: reading them from a source, and editing them (merge, split, move)."""

from __future__ import annotations

import dataclasses
import re
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from . import dvd
from . import tools
from .jobs import Failure, tool_failed
from .models import Chapter
from .tools import TOOL_PATHS


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r"(\d+):(\d+):(\d+(?:\.\d+)?)")


def _timecode_to_seconds(tc: str) -> float:
    m = _TIME_RE.match(tc)
    if not m:
        raise ValueError(f"Unrecognised timecode: {tc}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def read_chapters(mkv_path: Path, preferred_language: str = "eng") -> list[Chapter]:
    """
    Extract chapter markers from a real Matroska (.mkv) file via
    `mkvextract chapters -`.

    IMPORTANT: mkvextract can only read chapters from an actual Matroska
    container. It cannot read a Blu-ray .mpls playlist directly - handing
    it one fails with "Not a valid Matroska file (no EBML head found)",
    even though mkvmerge reads the same .mpls fine for scanning/
    extraction. For a .mpls (or anything else that isn't already a
    .mkv), use read_chapters_from_source() instead, which handles that
    conversion.

    Also reads each chapter's embedded name, if the source has one: a
    ChapterAtom can carry multiple <ChapterDisplay> blocks (one per
    language) via <ChapterString>/<ChapterLanguage> - when there's more
    than one, the one matching preferred_language is used, falling back
    to the first display block present.
    """
    result = tools.run([TOOL_PATHS["mkvextract"], str(mkv_path), "chapters", "-"], timeout=60)
    if result.returncode != 0:
        # mkvextract doesn't consistently write its error to stderr - some
        # failure modes (e.g. "not a valid Matroska file") land on stdout
        # instead, which used to leave the caller with an empty, useless
        # error message ("mkvextract failed:" and nothing after it).
        # Including both means the real reason always makes it to the user.
        detail = result.stderr.strip() or result.stdout.strip() or "(no output from mkvextract)"
        raise tool_failed("mkvextract", detail)

    xml_text = result.stdout
    # Defensive cleanup: strip a UTF-8 BOM (now correctly decoded thanks to
    # explicit encoding="utf-8" in run) and drop anything before the
    # opening "<" in case a tool ever emits stray leading bytes/whitespace.
    xml_text = xml_text.lstrip("\ufeff").strip()
    lt_index = xml_text.find("<")
    if lt_index > 0:
        xml_text = xml_text[lt_index:]
    root = ET.fromstring(xml_text)

    chapters: list[Chapter] = []
    for i, atom in enumerate(root.iter("ChapterAtom"), start=1):
        start_el = atom.find("ChapterTimeStart")
        if start_el is None or start_el.text is None:
            continue

        embedded_name, language = _pick_chapter_display(atom, preferred_language)

        chapters.append(
            Chapter(
                index=i,
                start_seconds=_timecode_to_seconds(start_el.text),
                embedded_name=embedded_name,
                language=language,
            )
        )

    # Fill in end times from the next chapter's start.
    for i, ch in enumerate(chapters):
        if i + 1 < len(chapters):
            ch.end_seconds = chapters[i + 1].start_seconds
        else:
            ch.end_seconds = None  # last chapter runs to end of file

    return chapters


def read_chapters_from_source(
    source_path: Path, preferred_language: str = "eng"
) -> list[Chapter]:
    """
    Read chapters from any mkvmerge-readable source, including a Blu-ray
    .mpls playlist - unlike read_chapters(), which only works on an
    actual .mkv file (see its docstring for why).

    For a .mpls (or anything else that isn't already a .mkv), this asks
    mkvmerge to remux just the chapter data into a small temporary .mkv
    in the system temp folder - no video, audio, or subtitle tracks are
    copied, so this is fast even though the source is a full disc rip -
    then reads chapters from that via read_chapters(). The temp file is
    always cleaned up afterwards, whether or not reading succeeds.
    """
    if source_path.suffix.lower() == ".mkv":
        return read_chapters(source_path, preferred_language=preferred_language)
    if dvd.is_title(source_path):
        return dvd.read_chapters(source_path)

    tmp_path = Path(tempfile.gettempdir()) / f"_chapters_only_{uuid.uuid4().hex}.mkv"
    args = [
        TOOL_PATHS["mkvmerge"], "-o", str(tmp_path),
        "--no-video", "--no-audio", "--no-subtitles",
        str(source_path),
    ]
    result = tools.run(args, timeout=120)
    if result.returncode >= 2 or not tmp_path.is_file():
        detail = result.stderr.strip() or result.stdout.strip() or "(no output from mkvmerge)"
        raise Failure("tool_failed", f"mkvmerge could not read chapter data from {source_path.name}:\n{detail}",
                      detail=detail, tool="mkvmerge")
    try:
        return read_chapters(tmp_path, preferred_language=preferred_language)
    finally:
        tmp_path.unlink(missing_ok=True)


_LANGUAGE_ALIASES = (
    {"eng", "en"}, {"jpn", "ja"}, {"zho", "chi", "zh"}, {"kor", "ko"},
    {"fre", "fra", "fr"}, {"ger", "deu", "de"}, {"spa", "es"},
)


def _language_aliases(code: str) -> set[str]:
    """All spellings of one language (ISO 639-2 B/T and 639-1). "" or "first" means no preference."""
    code = (code or "").strip().lower()
    if not code or code == "first":
        return set()
    return next((group for group in _LANGUAGE_ALIASES if code in group), {code})


def _display_ietf(display: ET.Element) -> str:
    element = display.find("ChapLanguageIETF")
    return (element.text or "").strip() if element is not None else ""


def _pick_chapter_display(atom: ET.Element, preferred_language: str) -> tuple[str, str]:
    """
    A ChapterAtom can have several <ChapterDisplay> blocks (e.g. one per
    language track on the disc). Prefer the one whose <ChapterLanguage>
    matches preferred_language; otherwise use the first display block
    present. Returns (name, language), both "" if there's no display
    block or no <ChapterString> text at all.
    """
    displays = atom.findall("ChapterDisplay")
    if not displays:
        return "", ""

    def display_name_lang(display: ET.Element) -> tuple[str, str]:
        string_el = display.find("ChapterString")
        lang_el = display.find("ChapterLanguage")
        name = (string_el.text or "").strip() if string_el is not None else ""
        language = (lang_el.text or "").strip() if lang_el is not None else ""
        return name, language

    wanted = _language_aliases(preferred_language)
    for display in displays:
        name, language = display_name_lang(display)
        if name and wanted and (language.lower() in wanted
                                or _display_ietf(display).split("-", 1)[0].lower() in wanted):
            return name, language

    # No match for preferred_language (or none of them had a name) - fall
    # back to the first display block that actually has a name.
    for display in displays:
        name, language = display_name_lang(display)
        if name:
            return name, language

    return "", ""


# ---------------------------------------------------------------------------
# Chapter editing: merge neighbours, split one in two, move a boundary.
#
# An edited chapter list is described by its start times only (a "layout"):
# chapter N runs from layout[N-1] to layout[N], the last one to the source's
# end. The layout is what a job manifest stores, so a resumed export rebuilds
# exactly the same songs from the source's own chapters.
# ---------------------------------------------------------------------------

MIN_CHAPTER_SECONDS = 1.0
_SAME_TIME = 0.0005


def chapter_layout(chapters: list[Chapter]) -> list[float]:
    return [ch.start_seconds for ch in chapters]


def apply_chapter_layout(source: list[Chapter], layout: list[float]) -> list[Chapter]:
    """
    Rebuild chapters (numbered 1..N) from start times. Each keeps the disc's
    embedded name of the source chapter that starts at the same moment; the
    last one ends where the source's last chapter ends.
    """
    if not source:
        return []
    starts = sorted(float(s) for s in layout)
    if not starts:
        return [dataclasses.replace(ch) for ch in source]
    end = source[-1].end_seconds
    result = []
    for number, start in enumerate(starts, start=1):
        stop = starts[number] if number < len(starts) else end
        twin = next((ch for ch in source if abs(ch.start_seconds - start) < _SAME_TIME), None)
        result.append(Chapter(number, start, stop, embedded_name=twin.embedded_name if twin else "",
                              language=twin.language if twin else ""))
    return result


def same_layout(a: list[Chapter], b: list[Chapter]) -> bool:
    return len(a) == len(b) and all(abs(x.start_seconds - y.start_seconds) < _SAME_TIME for x, y in zip(a, b))


def _renumbered(chapters: list[Chapter]) -> list[Chapter]:
    return [dataclasses.replace(ch, index=number) for number, ch in enumerate(chapters, start=1)]


def merge_chapters(chapters: list[Chapter], position: int) -> list[Chapter]:
    """Join chapters[position] with the one after it (0-based positions)."""
    if not 0 <= position < len(chapters) - 1:
        raise ValueError("There is no next chapter to merge with.")
    first, second = chapters[position], chapters[position + 1]
    merged = dataclasses.replace(first, end_seconds=second.end_seconds, name=first.name or second.name,
                                 embedded_name=first.embedded_name or second.embedded_name)
    return _renumbered(chapters[:position] + [merged] + chapters[position + 2:])


def split_chapter(chapters: list[Chapter], position: int, at_seconds: float) -> list[Chapter]:
    """Cut chapters[position] in two at an absolute time; the second half starts unnamed."""
    if not 0 <= position < len(chapters):
        raise ValueError("No such chapter.")
    ch = chapters[position]
    at_seconds = float(at_seconds)
    if at_seconds < ch.start_seconds + MIN_CHAPTER_SECONDS or (
            ch.end_seconds is not None and at_seconds > ch.end_seconds - MIN_CHAPTER_SECONDS):
        raise ValueError("The split point is too close to the chapter's start or end.")
    left = dataclasses.replace(ch, end_seconds=at_seconds)
    right = Chapter(ch.index + 1, at_seconds, ch.end_seconds)
    return _renumbered(chapters[:position] + [left, right] + chapters[position + 1:])


def move_chapter_start(chapters: list[Chapter], position: int, new_start: float) -> list[Chapter]:
    """
    Move the boundary between chapters[position - 1] and chapters[position].
    The time is clamped so neither chapter becomes shorter than MIN_CHAPTER_SECONDS.
    """
    if not 1 <= position < len(chapters):
        raise ValueError("The first chapter's start cannot be moved.")
    before, ch = chapters[position - 1], chapters[position]
    low = before.start_seconds + MIN_CHAPTER_SECONDS
    high = ch.end_seconds - MIN_CHAPTER_SECONDS if ch.end_seconds is not None else float("inf")
    if low > high:
        raise ValueError("The chapters are too short to move this boundary.")
    start = min(max(float(new_start), low), high)
    result = list(chapters)
    result[position - 1] = dataclasses.replace(before, end_seconds=start)
    result[position] = dataclasses.replace(ch, start_seconds=start)
    return result
