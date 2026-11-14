"""
Pasted set lists, as copied from an official site, Wikipedia, a shop page or
a forum post: numbering in many styles, durations, disc sections, headings,
and lines that are not songs (MC, encore, opening film, credits).

parse() classifies every line; plan() lays the result over the disc's
chapters, either by order (from a chosen start chapter) or by duration.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import extractor

SONG, EXTRA, SKIP, HEADER, DISC, BLANK = "song", "extra", "skip", "header", "disc", "blank"
NOTE, OFF, MERGED = "note", "off", "merged"      # credits / remarks; switched off by hand; joined to the line above

_DISC_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_DISC_RE = re.compile(
    r"^[\s\[\(<【〈＜《■□◆◇●○*#=\-–—]*"
    r"(?:blu-?ray\s*|bd\s*|dvd\s*)?(?:disc|disk|cd|dvd|blu-?ray|bd|ディスク)\s*[-.#:：]?\s*"
    r"(\d{1,2}|one|two|three|four|five)\b(.*)$", re.IGNORECASE)
_HEADER_WORDS = (
    "収録", "収録内容", "収録曲", "収録楽曲", "収録曲目", "セットリスト", "セトリ", "曲目", "曲目列表", "曲目表", "曲目单", "本編",
    "setlist", "set list", "tracklist", "track list", "tracklisting", "track listing", "contents", "songs",
    "特典映像", "特典", "bonus", "bonus video", "bonus feature", "bonus features", "映像特典", "本篇", "演出曲目",
    "blu-ray", "bluray", "dvd", "bd", "cd", "live", "live blu-ray", "live dvd",
)
_DECOR = "-－—–~～〜_=*・•●○◆◇■□▶►▼▽★☆<>＜＞〈〉《》«»()（）[]【】〔〕「」『』:：/／|｜ \t　"
_EXTRA_WORDS = (
    "mc", "m.c.", "talk", "トーク", "opening", "op", "overture", "intro", "introduction", "prologue", "epilogue",
    "ending", "ed", "endroll", "end roll", "ending movie", "ending roll", "credit", "credits", "staff roll", "staffroll",
    "エンドロール", "オープニング", "エンディング", "オープニング映像", "エンディング映像", "オープニングムービー",
    "encore", "en", "アンコール", "ダブルアンコール", "wアンコール", "w encore", "double encore", "encore mc",
    "アンコールmc", "opening movie", "opening se", "opening video", "interlude", "幕間", "幕間映像", "映像", "vtr",
    "se", "band solo", "band session", "メンバー紹介", "member introduction", "member intro", "開場", "影像",
    "开场", "开场影像", "返场", "安可", "谢幕", "片尾", "片头", "串场", "主持", "主持人",
)
_SKIP_WORDS = ("-", "—", "–", "－", "x", "×", "skip", "(skip)", "跳过", "スキップ", "略")
# Numbering that can never be part of a title: M1 / M-01 / EN1 / #1 / Track 1 / Tr.1 / ①
_SURE_NUMBER_RE = re.compile(
    r"^\s*(?:[・•●○◆◇■□▶►*]\s*)?(?:(?:m|w-?en|en|ec)\s*-?\s*\d{1,3}\b[.):．：]?|#\s*\d{1,3}[.):．：]?|tr(?:ack)?\.?\s*\d{1,3}[.):．：]?|"
    r"[①-⑳])\s*", re.IGNORECASE)
# Numbering that might be a title ("1/3の純情な感情", "99 Luftballons"): stripped when most lines carry it
_MAYBE_NUMBER_RE = re.compile(r"^\s*(?:[・•●○◆◇■□▶►*]\s*)?[(（]?\d{1,3}(?:[.)．、:：）]\s*|\s+|\t)")
_BULLET_RE = re.compile(r"^\s*[・•●○◆◇■□▶►*]\s*")
_DURATION_RE = re.compile(r'[\s\t]*[(（\[［]?\s*(\d{1,2})[:\'’′]([0-5]\d)(?::([0-5]\d))?["”″]?\s*[)）\]］]?\s*$')
_CELL_DURATION_RE = re.compile(r"^\s*\d{1,2}[:'’′][0-5]\d(?::[0-5]\d)?[\"”″]?\s*$")
_CELL_NUMBER_RE = re.compile(r"^\s*(?:m|en|ec|#|tr\.?|track)?\s*-?\s*\d{1,3}[.)．]?\s*$|^\s*[①-⑳]\s*$", re.IGNORECASE)
_TRAILING_DASH_RE = re.compile(r"\s*[-–—/／|｜]\s*$")
_SUFFIX_RE = re.compile(r"\s*[(（\[［【〔〈<＜][^()（）\[\]［］【】〔〕〈〉<>＜＞]*[)）\]］】〕〉>＞]\s*$")
# Credits and remarks: "作詞：…", "Music: …", "※ …"
_CREDIT_RE = re.compile(
    r"^\s*[(（]?\s*(?:作詞|作曲|編曲|作词|编曲|作詞・作曲|作詞作曲|作詞/作曲|詞|lyrics?|music|words|arr(?:anged)?\.?|"
    r"composed|written|vocals?|vo\.)\s*(?:by)?\s*[:：/／]", re.IGNORECASE)
_NOTE_RE = re.compile(r"^\s*(?:※|注[:：]|備考[:：]|note[:：]|total(?:\s+length)?\s*[:：]?|合計|総時間|总时长|收录时间)",
                      re.IGNORECASE)
_TRAILING_CREDIT_RE = re.compile(r"\s*[(（\[]?\s*(?:作詞|作曲|編曲|作词|lyrics?|music|words)\s*[:：].*$", re.IGNORECASE)
_QUOTES = (("「", "」"), ("『", "』"), ('"', '"'), ("“", "”"), ("‘", "’"), ("《", "》"))
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿豈-﫿가-힯]")
# "1. A 2. B 3. C" squeezed onto one line
_MARKER_RE = re.compile(r"(?:(?<=\s)|^)(?:(m|en|ec)\s*-?\s*)?(\d{1,3})[.)．]\s+|[①-⑳]\s*", re.IGNORECASE)
_LIST_SEP_RE = re.compile(r"\s*(?:／|\s/\s|｜|\s\|\s|、|,\s)\s*")
_TABLE_HEAD = {
    "no", "no.", "#", "m", "tr", "track", "曲名", "タイトル", "title", "song", "song title", "track title", "曲目", "楽曲", "曲",
    "歌曲", "作詞", "作曲", "編曲", "作词", "lyrics", "music", "writer", "writers", "writer(s)", "time", "length", "duration",
    "時間", "長さ", "时长", "artist", "歌手", "アーティスト", "備考", "notes", "note", "original artist", "曲順",
}
_TITLE_HEAD = {"曲名", "タイトル", "title", "song", "song title", "track title", "曲目", "楽曲", "曲", "歌曲"}


def _bare(text: str) -> str:
    return text.strip(_DECOR).lower()


def to_halfwidth(text: str) -> str:
    """Full-width letters, digits and punctuation (Ａ１！) to plain ASCII; kana and CJK untouched."""
    return "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else " " if c == "　" else c
                   for c in text)


def drop_suffixes(title: str) -> str:
    """Remove trailing bracketed notes: "Song (Live)" / "Song【Encore】" -> "Song"."""
    previous = None
    while previous != title:
        previous = title
        stripped = _SUFFIX_RE.sub("", title)
        title = stripped if stripped.strip() else title
    return title.strip()


def _peel_suffixes(title: str) -> tuple[str, list[str]]:
    """"Song (A) [B]" -> ("Song", ["(A)", "[B]"]); the title itself is never peeled away."""
    groups = []
    while True:
        m = _SUFFIX_RE.search(title)
        if not m or not title[:m.start()].strip():
            return title.strip(), groups
        groups.insert(0, m.group(0).strip())
        title = title[:m.start()]


def _suffix_key(group: str) -> str:
    return " ".join(to_halfwidth(group[1:-1]).casefold().split())


def shared_suffixes(titles: list[str]) -> set[str]:
    """The trailing bracketed notes that at least half the titles (and two or more) carry."""
    counts = {}
    named = 0
    for title in titles:
        base, groups = _peel_suffixes(title)
        if base:
            named += 1
            for key in {_suffix_key(g) for g in groups}:
                counts[key] = counts.get(key, 0) + 1
    return {key for key, n in counts.items() if n >= max(2, (named + 1) // 2)}


def drop_suffix_notes(title: str, shared: set[str]) -> str:
    """Remove the given trailing notes from one title; its other notes stay in place."""
    base, groups = _peel_suffixes(title)
    if not base or not any(_suffix_key(g) in shared for g in groups):
        return title
    return " ".join([base] + [g for g in groups if _suffix_key(g) not in shared])


def drop_shared_suffixes(titles: list[str]) -> list[str]:
    """
    Remove the trailing bracketed notes that most titles carry (an album-wide
    "(Live on …)" or "[Remastered]"), keeping notes that belong to one song:
    "A (Acoustic Ver.) (Live on X)", "B (Live on X)" -> "A (Acoustic Ver.)", "B".
    """
    shared = shared_suffixes(titles)
    return [drop_suffix_notes(t, shared) for t in titles]


def unquote(title: str) -> str:
    """「Song」 / "Song" (Original) -> Song / Song (Original); 「A」のB stays as it is."""
    t = title.strip()
    for opening, closing in _QUOTES:
        if t.startswith(opening):
            end = t.find(closing, len(opening))
            if end > len(opening):
                inner, rest = t[len(opening):end].strip(), t[end + len(closing):].strip()
                if not rest:
                    return inner
                if rest[0] in "(（[［/／-–—":
                    return f"{inner} {rest}"
    return t


def prefer_original(title: str) -> str:
    """"Aitakute (会いたくて)" or "会いたくて / Aitakute" -> the side written in Japanese/Chinese/Korean."""
    for pattern in (r"^(.*?)\s*[(（](.+?)[)）]\s*$", r"^(.+?)\s+[/／]\s+(.+)$"):
        m = re.match(pattern, title)
        if m:
            a, b = m.group(1).strip(), m.group(2).strip()
            if a and b and _CJK_RE.search(b) and not _CJK_RE.search(a):
                return b
            if a and b and _CJK_RE.search(a) and not _CJK_RE.search(b):
                return a
    return title


@dataclass
class Line:
    raw: str
    kind: str
    title: str = ""
    seconds: Optional[float] = None
    disc: int = 0
    key: str = ""                 # what a manual override is filed under (survives edits elsewhere in the text)
    auto: str = ""                # the kind before any manual override


@dataclass
class Table:
    columns: list[str]            # a label per column (header text, or a sample cell)
    kinds: list[str]              # "number" | "duration" | "text" per column
    title: int                    # column used for titles
    rows: int


@dataclass
class Setlist:
    lines: list[Line]
    discs: list[int] = field(default_factory=list)
    table: Optional[Table] = None

    def items(self, disc: Optional[int] = None) -> list[Line]:
        """Lines that take a chapter (songs, extras, placeholders), optionally from one disc only."""
        return [l for l in self.lines if l.kind in (SONG, EXTRA, SKIP) and (disc is None or l.disc == disc)]


def _disc_number(line: str) -> Optional[int]:
    m = _DISC_RE.match(line)
    if not m:
        return None
    rest = m.group(2).strip(_DECOR)
    if len(rest) > 24:            # "Blu-ray Disc 1 contains the full concert" is prose, not a heading
        return None
    word = m.group(1).lower()
    return _DISC_WORDS.get(word) or int(word)


def _is_header(line: str) -> bool:
    bare = _bare(line)
    if not bare:
        return len(line.strip()) >= 2      # pure decoration ("-----"); a lone "-" is a placeholder
    return bare in _HEADER_WORDS


def split_squeezed(line: str) -> list[str]:
    """"M1. A M2. B M3. C" (line breaks lost when copying) -> one piece per song."""
    marks = list(_MARKER_RE.finditer(line))
    if len(marks) < 2:
        return [line]
    chain, last = [], None
    for m in marks:
        circled = m.group(2) is None
        prefix = "circled" if circled else (m.group(1) or "").lower()
        number = ord(m.group(0).strip()[0]) - 0x245F if circled else int(m.group(2))
        if last is None:
            if line[:m.start()].strip():
                return [line]
            chain.append(m)
            last = (prefix, number)
        elif (prefix == last[0] and number == last[1] + 1) or (prefix != last[0] and number == 1):
            chain.append(m)
            last = (prefix, number)
    # Two bare numbers could be part of a title ("1. Vol. 2. Song"); prefixed or circled ones cannot
    plain = all(m.group(2) is not None and not m.group(1) for m in chain)
    if len(chain) < (3 if plain else 2):
        return [line]
    cuts = [m.start() for m in chain] + [len(line)]
    return [line[cuts[i]:cuts[i + 1]].strip() for i in range(len(chain)) if line[cuts[i]:cuts[i + 1]].strip()]


def _read_table(work: list[str], column: int) -> Optional[tuple[Table, dict[int, str], set[int]]]:
    """Rows copied from a web table arrive tab-separated: pick the title (and length) column."""
    nonblank = [i for i, w in enumerate(work) if w.strip()]
    tabbed = [i for i in nonblank if "\t" in w_strip(work[i])]
    if len(tabbed) < 3 or len(tabbed) < len(nonblank) * 0.5:
        return None
    cells = {i: [c.strip() for c in work[i].split("\t")] for i in tabbed}
    width = max(len(c) for c in cells.values())
    head_row = None
    for i in tabbed[:3]:
        filled = [c.lower() for c in cells[i] if c]
        if filled and sum(c in _TABLE_HEAD for c in filled) >= max(1, len(filled) / 2):
            head_row = i
            break
    data = [i for i in tabbed if i != head_row]
    if not data:
        return None
    kinds, labels = [], []
    for col in range(width):
        values = [cells[i][col] if col < len(cells[i]) else "" for i in data]
        filled = [v for v in values if v]
        if filled and sum(bool(_CELL_DURATION_RE.match(v)) for v in filled) >= len(filled) * 0.6:
            kinds.append("duration")
        elif not filled or sum(bool(_CELL_NUMBER_RE.match(v)) for v in filled) >= len(filled) * 0.6:
            kinds.append("number")
        else:
            kinds.append("text")
        head = cells[head_row][col] if head_row is not None and col < len(cells[head_row]) else ""
        labels.append(head or next((v for v in filled), ""))
    texts = [c for c in range(width) if kinds[c] == "text"]
    if not texts:
        return None
    if column in texts:
        title = column
    else:
        named = [c for c in texts if head_row is not None and labels[c].lower() in _TITLE_HEAD]
        title = named[0] if named else texts[0]
    duration = next((c for c in range(width) if kinds[c] == "duration"), None)
    rewritten = {}
    for i in data:
        row = cells[i]
        name = row[title] if title < len(row) else ""
        if not name:     # a row read off a screenshot may have its title drift into a neighbouring column
            name = " ".join(c for n, c in enumerate(row) if c and n != duration)
        length = row[duration] if duration is not None and duration < len(row) else ""
        rewritten[i] = f"{name}  {length}".strip() if length else name
    return Table(labels, kinds, title, len(data)), rewritten, ({head_row} if head_row is not None else set())


def w_strip(text: str) -> str:
    return text.strip(" 　")


def _duration(title: str) -> tuple[str, Optional[float]]:
    m = _DURATION_RE.search(title)
    if m and title[:m.start()].strip():
        a, b, c = m.group(1), m.group(2), m.group(3)
        seconds = (int(a) * 3600 + int(b) * 60 + int(c)) if c else int(a) * 60 + int(b)
        return _TRAILING_DASH_RE.sub("", title[:m.start()]).strip(), seconds
    return title, None


def parse(text: str, halfwidth: bool = False, suffixes: bool = False, original: bool = False,
          column: int = -1, overrides: Optional[dict] = None) -> Setlist:
    """
    Classify every line of a pasted set list. `column` picks the title column of
    a pasted table (-1: guess); `overrides` maps a line key to "song", "extra",
    "off" or "merged" (join to the line above), set by hand in the preview.
    """
    overrides = overrides or {}
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    work = [to_halfwidth(r) if halfwidth else r for r in raw_lines]
    table = _read_table(work, column)
    table_rows: dict[int, str] = {}
    head_rows: set[int] = set()
    if table:
        table, table_rows, head_rows = table

    # One entry per piece: (raw line, key, working text, from a table)
    pieces: list[tuple[str, str, str, bool]] = []
    nonblank = [w for w in work if w.strip()]
    for i, (raw, line) in enumerate(zip(raw_lines, work)):
        key = raw.strip()
        if i in head_rows:
            pieces.append((raw, key, "", True))
            continue
        if i in table_rows:
            pieces.append((raw, key, table_rows[i], True))
            continue
        parts = split_squeezed(line)
        if len(parts) == 1 and len(nonblank) <= 2 and line.strip():
            listed = [p for p in _LIST_SEP_RE.split(line.strip()) if p.strip()]
            parts = listed if len(listed) >= 3 else parts
        if len(parts) > 1:
            pieces.extend((raw, f"{key}#{n}", part, False) for n, part in enumerate(parts))
        else:
            pieces.append((raw, key, line, False))

    # Does this list number its lines? Only then strip a bare leading number.
    candidates = [w for _, _, w, t in pieces if w.strip() and not t and _disc_number(w) is None and not _is_header(w)]
    numbered = sum(1 for w in candidates if _MAYBE_NUMBER_RE.match(w) or _SURE_NUMBER_RE.match(w))
    strip_plain = bool(candidates) and numbered >= len(candidates) * 0.5 and (numbered >= 2 or len(candidates) == 1)

    lines: list[Line] = []
    disc = 0
    for raw, key, line, from_table in pieces:
        if from_table and not line:
            lines.append(Line(raw, HEADER, disc=disc, key=key, auto=HEADER))
            continue
        if not line.strip():
            lines.append(Line(raw, BLANK, disc=disc, key=key))
            continue
        number = _disc_number(line)
        if number is not None and not from_table:
            disc = number
            lines.append(Line(raw, DISC, disc=number, key=key, auto=DISC))
            continue
        title = line.strip()
        if from_table:
            title = _SURE_NUMBER_RE.sub("", title, count=1).strip() or title
        else:
            stripped = _SURE_NUMBER_RE.sub("", title, count=1)
            if stripped == title and strip_plain:
                stripped = _MAYBE_NUMBER_RE.sub("", title, count=1)
            title = _BULLET_RE.sub("", stripped).strip() or title
        title, seconds = _duration(title)
        if _CREDIT_RE.match(title) or _NOTE_RE.match(title) or (from_table and _CELL_DURATION_RE.match(title)):
            kind = NOTE
        elif _is_header(line):
            kind = HEADER
        else:
            kind = SONG
            trimmed = _TRAILING_CREDIT_RE.sub("", title).strip()
            title = unquote(trimmed or title)
            bare = _bare(title)
            if title.strip() in _SKIP_WORDS or bare in _SKIP_WORDS:
                kind, title = SKIP, ""
            elif re.sub(r"[\s\d①-⑳]+$", "", bare).strip() in _EXTRA_WORDS or bare in _EXTRA_WORDS:
                kind, title = EXTRA, title.strip(_DECOR) or title
            else:
                if original:
                    title = prefer_original(title)
                if suffixes:
                    title = drop_suffixes(title)
        auto = kind
        wanted = overrides.get(key)
        if wanted in (SONG, EXTRA, OFF, MERGED) and kind not in (SKIP,):
            kind = wanted
            if not title:
                title = line.strip()
        lines.append(Line(raw, kind, title, seconds, disc, key, auto))

    # Wrapped titles joined back onto the line above
    for n, l in enumerate(lines):
        if l.kind != MERGED:
            continue
        above = next((lines[k] for k in range(n - 1, -1, -1) if lines[k].kind in (SONG, EXTRA)), None)
        if above is None:
            l.kind = l.auto
            continue
        above.title = f"{above.title} {l.title}".strip()
        above.seconds = above.seconds or l.seconds

    discs = sorted({l.disc for l in lines if l.kind == DISC})
    if discs:
        # Songs listed before the first heading belong to the disc before it ("...", "Disc 2", ...)
        implicit = discs[0] - 1 if discs[0] > 1 else 0
        for l in lines:
            if l.kind == DISC:
                break
            l.disc = implicit
        if implicit and any(l.kind == SONG and l.disc == implicit for l in lines):
            discs.insert(0, implicit)
    return Setlist(lines, discs, table)


def guess_disc(source_name: str, discs: list[int]) -> Optional[int]:
    """"... DISC 2.iso" -> 2 when the paste has a Disc 2 section."""
    if not discs:
        return None
    m = re.search(r"(?:disc|disk|cd|bd|ディスク)\s*[-_.#]?\s*(\d{1,2})", source_name, re.IGNORECASE)
    if m and int(m.group(1)) in discs:
        return int(m.group(1))
    return discs[0]


@dataclass
class Placement:
    line: int                     # index into Setlist.lines
    chapter: Optional[int]        # chapter number it lands on (None: past the last chapter / not placed)


@dataclass
class Plan:
    mode: str                     # "order" | "duration"
    placements: list[Placement]
    songs: int
    extras: int
    chapters: int
    can_duration: bool
    entries: list[extractor.TracklistEntry]   # what the review page gets
    extra_chapters: dict[int, str]            # chapter -> label of a non-song line on it
    entry_mode: str                           # match mode for the review page


def plan(setlist: Setlist, chapters: list[extractor.Chapter], disc: Optional[int] = None, start: int = 1,
         mode: str = "auto", extras_take_chapter: bool = True, tolerance: float = 20.0,
         skip_chapters: frozenset = frozenset(), end: int = 0) -> Plan:
    """skip_chapters: chapters that are not songs (talk, opening film): order alignment passes over them.
    start / end (1-based, end 0 = the last chapter): the range order alignment fills; chapters outside stay as they are."""
    picked = [(i, l) for i, l in enumerate(setlist.lines)
              if l.kind in (SONG, EXTRA, SKIP) and (disc is None or not setlist.discs or l.disc == disc)]
    if not extras_take_chapter:
        picked = [(i, l) for i, l in picked if l.kind != EXTRA]
    songs = [(i, l) for i, l in picked if l.kind == SONG]
    song_entries = [extractor.TracklistEntry(l.title, index=n + 1, duration_seconds=l.seconds)
                    for n, (_, l) in enumerate(songs)]
    can_duration = bool(songs) and extractor.can_align_by_duration(chapters, song_entries)
    use_duration = can_duration and mode != "order"
    numbers = [c.index for c in chapters]
    placements: list[Placement] = []
    extra_chapters: dict[int, str] = {}

    if use_duration:
        result = extractor.match_tracklist_to_chapters(chapters, song_entries, duration_tolerance_seconds=tolerance)
        where = {m.entry_index: m.chapter_index for m in result.matches if m.entry_index is not None}
        for n, (i, _) in enumerate(songs):
            placements.append(Placement(i, where.get(n)))
        # Lengths that mostly disagree (another edition, a different cut): plain order is the better guess
        if mode == "auto" and sum(1 for p in placements if p.chapter is not None) < len(songs) / 2:
            return plan(setlist, chapters, disc, start, "order", extras_take_chapter, tolerance, skip_chapters, end)
        return Plan("duration", placements, len(songs), len(picked) - len(songs), len(chapters), True,
                    song_entries, extra_chapters, "auto")

    slots = [n for n in numbers[max(0, start - 1):end if end > 0 else None] if n not in skip_chapters]
    entries: list[extractor.TracklistEntry] = []
    for n, (i, l) in enumerate(picked):
        chapter = slots[n] if n < len(slots) else None
        placements.append(Placement(i, chapter))
        if chapter is None:
            continue
        if l.kind == SONG:
            entries.append(extractor.TracklistEntry(l.title, index=chapter, duration_seconds=l.seconds))
        elif l.kind == EXTRA:
            extra_chapters[chapter] = l.title
            entries.append(extractor.TracklistEntry(l.title, index=chapter, duration_seconds=l.seconds))
    return Plan("order", placements, len(songs), len(picked) - len(songs), len(chapters), can_duration,
                entries, extra_chapters, "chapter")


MUSIC, TALK, UNSURE = "music", "talk", "unsure"
INTERLUDE = "interlude"      # music that is not a song: overture, costume-change BGM, film score, credits
NON_SONGS = frozenset({TALK, INTERLUDE})


def chapter_kinds(chapters: list[extractor.Chapter], peaks: list[float], per_second: float,
                  ripple: Optional[list[float]] = None) -> dict[int, str]:
    """
    Music, interlude, talk or unsure per chapter, from the programme's outline. A guess,
    tuned on a real concert disc; the UI says so and lets every chapter be set by hand.

    - Loud chapters (median level near the disc's) are songs.
    - Quiet ones are told apart by `ripple`, how much the level swings within each half
      second: speech rises and drops with syllables and pauses (high), music holds its
      level (low). Quiet and steady: an interlude (overture, costume-change BGM, film
      score); quiet and choppy: talk; in between: unsure.
    - Middling ones are songs unless short or mostly soft, which makes them interludes.
    Without a ripple series (older outlines) quiet chapters can only be "talk"; without
    an outline, only very short chapters are taken for non-songs.
    """
    kinds: dict[int, str] = {}
    usable = [p if p is not None else 0.0 for p in peaks] if peaks else []
    swings = list(ripple) if ripple and len(ripple) == len(usable) else []
    # Reference: how loud the band gets (the loudest tenth of the disc is always music), so a
    # disc with a lot of talk does not move the scale
    level = sorted(usable)[int(len(usable) * 0.9)] if usable else 0.0
    for c in chapters:
        end = c.end_seconds if c.end_seconds is not None else (len(usable) / per_second if usable else None)
        length = (end - c.start_seconds) if end is not None else None
        lo, hi = int(c.start_seconds * per_second), int(end * per_second) if end else 0
        part = usable[lo:hi] if usable and end else []
        if not part or level <= 0:
            kinds[c.index] = TALK if length is not None and length < 45 else MUSIC
            continue
        typical = sorted(part)[len(part) // 2] / level          # 1.0: as loud as the band at full tilt
        loud = sum(1 for p in part if p > level * 0.45) / len(part)
        if typical >= 0.5:
            kinds[c.index] = MUSIC
            continue
        if typical >= 0.25:                                     # middling: a soft song or an interlude
            if length is not None and length < 100:
                kinds[c.index] = INTERLUDE
            else:
                kinds[c.index] = MUSIC if loud >= 0.25 else UNSURE
            continue
        swing = [r for p, r in zip(part, swings[lo:hi]) if r > 0]
        if len(swing) < 10:                                     # no ripple to go by: the old rule
            kinds[c.index] = MUSIC if loud >= 0.25 else TALK if loud < 0.12 else UNSURE
            continue
        choppy = sorted(swing)[int(len(swing) * 0.75)]
        kinds[c.index] = TALK if choppy >= 0.42 else INTERLUDE if choppy <= 0.36 else UNSURE
    return kinds
