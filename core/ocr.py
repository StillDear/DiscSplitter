"""
Read a screenshot of a set list with the OCR engine built into Windows 10/11
(Windows.Media.Ocr). It is reached through Windows PowerShell, so nothing
extra has to be installed or bundled; it uses whichever recognition languages
Windows has (Japanese, Chinese, English ... come with the language packs).

Words come back with their positions, so rows are rebuilt here: a wide gap
between words becomes a tab (a table column), and the spaces Windows puts
between Japanese/Chinese characters are removed.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Optional

from .tools import NO_WINDOW

_SCRIPT = r"""
param([string]$Path, [string]$Langs)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
if ($Path -eq '') {
    $tags = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
    ConvertTo-Json -Compress -InputObject @{ languages = $tags; max = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension }
    return
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$out = @{}
foreach ($tag in $Langs.Split(',')) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag))
    if ($null -eq $engine) { continue }
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $words = @()
    foreach ($line in $result.Lines) {
        foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            $words += ,@($w.Text, [math]::Round($r.X, 1), [math]::Round($r.Y, 1), [math]::Round($r.Width, 1), [math]::Round($r.Height, 1))
        }
    }
    $out[$tag] = $words
}
$stream.Dispose()
ConvertTo-Json -Compress -Depth 5 -InputObject $out
"""

_KANA_RE = re.compile(r"[぀-ヿ]")
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿豈-﫿가-힯！-｠　-〿]")


class OcrUnavailable(RuntimeError):
    pass


@dataclass
class Word:
    text: str
    x: float
    y: float
    w: float
    h: float


def _run(path: str, langs: str, timeout: float = 90) -> dict:
    script = Path(tempfile.gettempdir()) / "dts-ocr.ps1"
    if not script.is_file() or script.read_text(encoding="utf-8-sig") != _SCRIPT:
        script.write_text(_SCRIPT, encoding="utf-8-sig")       # BOM: Windows PowerShell reads it as UTF-8
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-Path", path, "-Langs", langs],
            capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
            creationflags=NO_WINDOW)
    except FileNotFoundError as exc:
        raise OcrUnavailable("Windows PowerShell was not found") from exc
    out = result.stdout.decode("utf-8", "replace").strip()
    if result.returncode != 0 or not out:
        error = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OcrUnavailable(error[0] if error else "Windows OCR is not available")
    return json.loads(out)


_languages: Optional[tuple[list[str], int]] = None


def languages() -> tuple[list[str], int]:
    """Recognition languages Windows has, and the largest image side it accepts."""
    global _languages
    if _languages is None:
        info = _run("", "", timeout=30)
        tags = info.get("languages") or []
        _languages = ([tags] if isinstance(tags, str) else list(tags), int(info.get("max") or 2600))
    return _languages


def _join(a: str, b: str, gap: float, unit: float) -> str:
    """Characters set tight together belong together; Japanese/Chinese need no space unless one was typeset."""
    if not a:
        return b
    if gap < unit * 0.3:
        return a + b
    if (_CJK_RE.match(a[-1]) or _CJK_RE.match(b[0])) and gap < unit * 0.6:
        return a + b
    return a + " " + b


def _tidy(text: str) -> str:
    text = re.sub(r"(\d)\s*([:：])\s*(\d)", r"\1:\3", text)          # "5 : 01"
    text = re.sub(r"(?<=[a-z])I(?=[a-z])", "l", text)                 # "DarIing": capital I read for l
    return text


def rebuild_rows(words: list[Word]) -> str:
    """
    Group words into rows by height and order them left to right. Rows split
    into pieces at wide gaps; pieces line up into columns by where they start,
    so a table comes out tab-separated with empty cells kept in place.
    """
    if not words:
        return ""
    unit = median(w.h for w in words) or 10
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda w: w.y + w.h / 2):
        centre = word.y + word.h / 2
        if rows:
            last = rows[-1]
            last_centre = median(w.y + w.h / 2 for w in last)
            if abs(centre - last_centre) <= max(unit, word.h) * 0.55:
                last.append(word)
                continue
        rows.append([word])
    pieces: list[list[tuple[float, str]]] = []      # per row: (left edge, text)
    for row in rows:
        row.sort(key=lambda w: w.x)
        parts, text, left, right = [], "", None, None
        for word in row:
            gap = 0.0 if right is None else word.x - right
            if right is not None and gap > unit * 2.0:
                parts.append((left, _tidy(text)))
                text, left = "", None
            if left is None:
                left = word.x
            text = _join(text, word.text, gap, unit)
            right = word.x + word.w
        parts.append((left, _tidy(text)))
        pieces.append(parts)
    # Column starts: left edges of pieces in multi-piece rows, clustered
    starts = sorted(x for parts in pieces if len(parts) > 1 for x, _ in parts)
    columns: list[float] = []
    for x in starts:
        if not columns or x - columns[-1] > unit * 1.5:
            columns.append(x)
    lines = []
    for parts in pieces:
        if len(parts) == 1 or len(columns) < 2:
            lines.append("\t".join(t for _, t in parts).strip())
            continue
        cells = [""] * len(columns)
        for x, t in parts:
            col = max((i for i, c in enumerate(columns) if c <= x + unit), default=0)
            cells[col] = f"{cells[col]} {t}".strip()
        lines.append("\t".join(cells).rstrip("\t"))
    return "\n".join(join_split_numbers(lines))


_SPLIT_NUMBER_RE = re.compile(r"^(\d)\s(\d)(?=[\s.．、)）:\t])")
_NUMBER_RE = re.compile(r"^(\d{1,3})(?=[\s.．、)）:\t])")


def join_split_numbers(lines: list[str]) -> list[str]:
    """
    Two-digit track numbers sometimes come back with their digits apart ("1 0 ONLYONE").
    They are joined only where that continues the numbering of the lines before
    (9 -> "1 0" -> "1 1"), so a title that really starts with "1 2" is left alone.
    """
    out, last = [], None
    for line in lines:
        m = _SPLIT_NUMBER_RE.match(line)
        if m and last is not None and int(m.group(1) + m.group(2)) == last + 1:
            line = m.group(1) + m.group(2) + line[m.end():]
        n = _NUMBER_RE.match(line)
        if n:
            last = int(n.group(1))
        out.append(line)
    return out


def _words(raw) -> list[Word]:
    if not raw:
        return []
    if raw and not isinstance(raw[0], list):        # a single word comes back unwrapped
        raw = [raw]
    return [Word(str(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in raw if len(r) >= 5]


def scale_for(width: int, height: int, max_side: int) -> float:
    """Shrink images Windows would refuse; enlarge small ones (small text reads badly). 1.0: use as is."""
    side = max(width, height)
    if side > max_side:
        return max_side / side
    if height < 1400 and side * 2 <= max_side:
        return 2.0
    return 1.0


def recognize(image_path: Path, language: str = "auto") -> tuple[str, str]:
    """
    Text of a set-list screenshot, one row per line; returns (text, language used).
    The image must already fit Windows' limit (see languages() and scale_for()).
    """
    available, _ = languages()
    if not available:
        raise OcrUnavailable("No OCR language is installed in Windows")
    if language != "auto":
        wanted = [language] if language in available else available[:1]
    else:
        prefer = [t for t in available if t.lower().startswith("ja")] + \
                 [t for t in available if t.lower().startswith("zh")] + \
                 [t for t in available if t.lower().startswith("ko")]
        wanted = prefer[:3] or available[:1]
    found = _run(str(image_path), ",".join(wanted))
    texts = {tag: rebuild_rows(_words(found.get(tag))) for tag in wanted}
    if language != "auto":
        return texts[wanted[0]], wanted[0]
    # Japanese lists nearly always contain kana; otherwise the Chinese reading is usually the better one.
    for tag in wanted:
        if tag.lower().startswith("ja") and _KANA_RE.search(texts[tag]):
            return texts[tag], tag
    for tag in wanted:
        if tag.lower().startswith("zh") and texts[tag].strip():
            return texts[tag], tag
    best = max(wanted, key=lambda t: len(texts[t]))
    return texts[best], best
