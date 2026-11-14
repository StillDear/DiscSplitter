"""
Fetch a web page (official site, Wikipedia, a shop or fan page) and pull out
the parts that look like a set list: tables, numbered or bulleted lists, and
runs of numbered lines in ordinary text. Each becomes a candidate the user can
switch between; the text then goes through the normal paste parser.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional

import setlist

# A plain browser identity: some sites refuse unknown clients.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAX_BYTES = 6 * 1024 * 1024

_BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "aside", "h1", "h2", "h3", "h4", "h5", "h6",
          "dl", "dt", "dd", "blockquote", "pre", "figure", "figcaption", "center", "address", "hr", "form", "fieldset"}
_SKIP = {"script", "style", "noscript", "template", "svg", "head", "button", "select", "option", "textarea"}
# Whole class names only ("vector-toc-landmark" wraps the entire page on Wikipedia)
_NOISE_CLASSES = {"reference", "references", "reflist", "mw-editsection", "noprint", "navbox", "sidebar", "toc",
                  "mw-references-wrap", "sr-only", "visually-hidden", "breadcrumb", "catlinks", "mw-cite-backlink",
                  "interlanguage-link", "mw-list-item", "infobox", "vector-menu", "mw-jump-link", "hatnote",
                  "navigation-not-searchable", "mw-portlet", "thumb", "gallery"}
_GOOD_HEADINGS = re.compile(r"収録|曲目|セットリスト|セトリ|set ?list|track ?list|track listing|songs|曲順|演奏曲|blu-?ray|dvd|disc|本編|本篇|曲目单|歌单", re.IGNORECASE)


@dataclass
class Candidate:
    kind: str          # "table" | "list" | "text"
    text: str
    songs: int
    heading: str = ""
    tracklist: bool = False        # a table marked up as a track listing (Wikipedia)


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.stack: list[tuple[str, bool]] = []      # (tag, noisy)
        self.lines: list[str] = [""]                 # the page as text, one line per block / <br>
        self.tables: list[list[list[str]]] = []
        self.lists: list[list[str]] = []
        self.table_stack: list[list[list[str]]] = []
        self.list_stack: list[list[str]] = []
        self.cell: Optional[list[str]] = None
        self.item: Optional[list[str]] = None
        self.item_depth = 0
        self.heading = ""
        self.in_heading = False
        self.headings: dict[int, tuple[str, str]] = {}   # table/list id -> (nearest heading above, class)
        self.sup = 0

    # text sinks -------------------------------------------------------
    def _newline(self):
        if self.lines[-1].strip():
            self.lines.append("")

    def _emit(self, text: str):
        if self.cell is not None:
            self.cell.append(text)
        if self.item is not None:
            self.item.append(text)
        if not self.table_stack and not self.list_stack:     # tables and lists are candidates of their own
            self.lines[-1] += text
        if self.in_heading:
            self.heading += text

    # parser hooks -----------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        noisy = bool(_NOISE_CLASSES.intersection((attrs.get("class") or "").split()))
        if tag in _SKIP or self.skip or noisy:
            if tag not in ("br", "hr", "img", "input", "meta", "link"):
                self.skip += 1
                self.stack.append((tag, True))
            return
        self.stack.append((tag, False))
        if tag == "br":
            self.stack.pop()
            if self.cell is not None:
                self.cell.append(" / ")
            if self.item is not None:
                self.item.append("\n")
            self.lines.append("")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading, self.heading = True, ""
        if tag in _BLOCK or tag in ("li", "tr", "table", "ul", "ol"):
            self._newline()
        if tag == "table":
            self.table_stack.append([])
            self.headings[id(self.table_stack[-1])] = (self.heading.strip(), attrs.get("class") or "")
        elif tag == "tr" and self.table_stack:
            self.table_stack[-1].append([])
        elif tag in ("td", "th") and self.table_stack and self.table_stack[-1]:
            self.cell = []
        elif tag in ("ul", "ol"):
            self.list_stack.append([])
            self.headings[id(self.list_stack[-1])] = (self.heading.strip(), attrs.get("class") or "")
        elif tag == "li" and self.list_stack and self.item is None:
            self.item, self.item_depth = [], len(self.list_stack)
        elif tag in ("td", "th"):
            self.lines[-1] += "\t"

    def handle_endtag(self, tag):
        # Close up to the matching tag (HTML in the wild leaves tags open)
        if not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            open_tag, noisy = self.stack.pop()
            if noisy:
                self.skip -= 1
            else:
                self._close(open_tag)
            if open_tag == tag:
                break

    def _close(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading = False
        if tag in ("td", "th") and self.cell is not None and self.table_stack and self.table_stack[-1]:
            self.table_stack[-1][-1].append(_clean("".join(self.cell)))
            self.cell = None
            self.lines[-1] += "\t"
        elif tag == "table" and self.table_stack:
            self.tables.append(self.table_stack.pop())
        elif tag == "li" and self.item is not None and len(self.list_stack) == self.item_depth:
            self.list_stack[-1].append(_clean("".join(self.item).split("\n")[0]))
            self.item = None
        elif tag in ("ul", "ol") and self.list_stack:
            self.lists.append(self.list_stack.pop())
        if tag in _BLOCK or tag in ("li", "tr", "table", "ul", "ol"):
            self._newline()

    def handle_data(self, data):
        if self.skip:
            return
        self._emit(re.sub(r"\s+", " ", data))


def _clean(text: str) -> str:
    text = re.sub(r"\[\s*(?:\d+|[a-z]|注\s*\d+|edit|編集)\s*\]", "", text)    # [1], [a], [edit] reference marks
    return re.sub(r"[ \t　]+", " ", text).strip()


def _songs(text: str) -> int:
    return sum(1 for l in setlist.parse(text).lines if l.kind == setlist.SONG)


def _decode(data: bytes, header_charset: Optional[str]) -> str:
    charsets = []
    if header_charset:
        charsets.append(header_charset)
    m = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", data[:4096], re.IGNORECASE)
    if m:
        charsets.append(m.group(1).decode("ascii", "ignore"))
    charsets += ["utf-8", "cp932", "euc-jp", "gb18030", "big5"]
    for name in charsets:
        try:
            return data.decode(_charset_alias(name))
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


def _charset_alias(name: str) -> str:
    name = name.lower().strip()
    return {"shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932", "gb2312": "gb18030",
            "gbk": "gb18030"}.get(name, name)


def fetch(url: str, timeout: float = 15.0) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parts = urllib.parse.urlsplit(url)
    if not parts.netloc or "." not in parts.netloc:
        raise ValueError("Not a web address")
    # Addresses copied from the browser bar may hold Japanese/Chinese characters
    host = parts.netloc.encode("idna").decode("ascii") if not parts.netloc.isascii() else parts.netloc
    url = urllib.parse.urlunsplit((parts.scheme, host,
                                   urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=~"),
                                   urllib.parse.quote(parts.query, safe="=&%/:+,;@!$'()*~?"),
                                   ""))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8",
                                                   "Accept-Language": "ja,zh-CN;q=0.9,en;q=0.8"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_BYTES)
            charset = response.headers.get_content_charset()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{parts.netloc} returned an error ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {parts.netloc}: {exc.reason}") from exc
    return _decode(data, charset)


def candidates(html: str) -> list[Candidate]:
    """Parts of the page that look like a set list, most likely first."""
    collector = _Collector()
    collector.feed(html)
    collector.close()
    found: list[Candidate] = []
    seen: set[str] = set()

    def add(kind, text, about=("", "")):
        text = text.strip()
        if not text or text in seen:
            return
        songs = _songs(text)
        if songs >= 3:
            seen.add(text)
            heading, classes = about
            found.append(Candidate(kind, text, songs, heading, "tracklist" in classes.split()))

    for table in collector.tables:
        rows = [r for r in table if any(c for c in r)]
        if len(rows) >= 3:
            add("table", "\n".join("\t".join(r) for r in rows), collector.headings.get(id(table), ("", "")))
    for raw_items in collector.lists:
        items = [i for i in raw_items if i]
        if len(items) >= 3 and sum(len(i) for i in items) / len(items) < 120:
            add("list", "\n".join(items), collector.headings.get(id(raw_items), ("", "")))
    # Runs of numbered lines in ordinary text (official sites often use <br>)
    lines = [_clean(l) for l in "\n".join(collector.lines).split("\n")]
    run: list[str] = []
    numbered = re.compile(r"^\s*(?:(?:m|en|ec)\s*-?\s*\d{1,3}|#?\d{1,3}[.)．]|[①-⑳])", re.IGNORECASE)

    def flush():
        while run and not numbered.match(run[-1]):     # short lines after the list are page furniture
            run.pop()
        if sum(1 for l in run if numbered.match(l)) >= 3:
            add("text", "\n".join(run))
        run.clear()

    gap = 0
    for line in lines:
        if not line:
            continue
        if numbered.match(line) or (run and len(line) < 60 and gap < 3):
            run.append(line)
            gap = 0 if numbered.match(line) else gap + 1
        else:
            flush()
            gap = 0
    flush()

    def score(c: Candidate):
        items = setlist.parse(c.text).items()
        titles = [l.title for l in items] or [""]
        timed = sum(1 for l in items if l.seconds) / max(1, len(items))
        dated = sum(1 for t in titles if re.search(r"(19|20)\d\d|年|月|日", t)) / len(titles)
        long = sum(1 for t in titles if len(t) > 50) / len(titles)
        size = min(c.songs, 30) * 0.5 - max(0, c.songs - 60) * 0.5     # most set lists have 8-40 songs
        return (size + timed * 15 + (12 if c.tracklist else 0) + (8 if _GOOD_HEADINGS.search(c.heading) else 0)
                - dated * 15 - long * 12 + {"table": 2, "list": 1, "text": 0}[c.kind])

    return sorted(found, key=score, reverse=True)
