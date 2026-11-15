"""Suggest conservative white- or black-border crops for cover artwork."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader


def read_cover(path: str) -> QImage:
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    return reader.read()


# A border line is (almost) all one flat colour: near-white paper or near-black letterbox.
BORDER_TESTS = {
    'white': lambda low, high: low >= 242 and high - low <= 10,
    'black': lambda low, high: high <= 24 and high - low <= 12,
}


def detect_borders(image: QImage) -> tuple[dict[str, int], str]:
    """
    Paired, similarly sized white or black margins with a visible transition, and which colour
    they are ('white', 'black', or '' when none). Each axis is checked on its own, so a cover
    with black bars at the top and bottom and white ones at the sides is found too.
    """
    sample = image.scaled(320, 320, Qt.KeepAspectRatio, Qt.FastTransformation)

    def paired_margins(horizontal: bool, is_border) -> tuple[int, int]:
        length = sample.width() if horizontal else sample.height()
        cross = sample.height() if horizontal else sample.width()
        if length < 32 or cross < 32:
            return 0, 0

        def border_fraction(line: int) -> float:
            hits = 0
            for offset in range(0, cross, 2):
                pixel = sample.pixelColor(line, offset) if horizontal else sample.pixelColor(offset, line)
                low = min(pixel.red(), pixel.green(), pixel.blue())
                high = max(pixel.red(), pixel.green(), pixel.blue())
                hits += pixel.alpha() == 255 and is_border(low, high)
            return hits / ((cross + 1) // 2)

        def margin(reverse: bool) -> int:
            fractions = [border_fraction(length - 1 - i if reverse else i)
                         for i in range(length // 4 + 4)]
            end = next((i for i, value in enumerate(fractions) if value < 0.98), 0)
            if not max(3, length // 50) <= end <= length // 4:
                return 0
            return end if max(fractions[end + 1:end + 4]) <= 0.8 else 0

        first, last = margin(False), margin(True)
        if not first or not last or abs(first - last) > max(2, min(first, last) // 8):
            return 0, 0
        original = image.width() if horizontal else image.height()
        return round(first * original / length), round(last * original / length)

    margins, colours = dict(left=0, right=0, top=0, bottom=0), []
    for horizontal, edges in ((True, ('left', 'right')), (False, ('top', 'bottom'))):
        for colour, is_border in BORDER_TESTS.items():
            pair = paired_margins(horizontal, is_border)
            if any(pair):
                margins.update(zip(edges, pair))
                colours.append(colour)
                break
    colour = colours[0] if len(set(colours)) == 1 else 'mixed' if colours else ''
    return margins, colour


def suggest_crop(image: QImage) -> dict[str, int]:
    """Suggest only paired, similarly sized white or black margins with a visible transition."""
    return detect_borders(image)[0]


def describe(path: str) -> str:
    """'1400 × 1400 · JPEG · 512 KB' for the cover panel (reads only the image header)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid():
        return ''
    parts = [f'{size.width()} × {size.height()}', bytes(reader.format()).decode('ascii', 'replace').upper()]
    try:
        kib = Path(path).stat().st_size / 1024
        parts.append(f'{kib / 1024:.1f} MB' if kib >= 1024 else f'{kib:.0f} KB')
    except OSError:
        pass
    return ' · '.join(p for p in parts if p)


def save_crop(image: QImage, path: Path, left: int, right: int, top: int, bottom: int) -> bool:
    width = image.width() - left - right
    height = image.height() - top - bottom
    if min(left, right, top, bottom) < 0 or not any((left, right, top, bottom)) or min(width, height) < 1:
        return False
    return image.copy(left, top, width, height).save(str(path), quality=95 if path.suffix != '.png' else -1)


def approval_path(source: Path, cache: Path) -> Path:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return cache / f'crop-{digest}.json'


def remember_crop(source: Path, target: Path, margins: dict[str, int]) -> None:
    approval = approval_path(source, target.parent)
    pending = approval.with_suffix(f'.{uuid4().hex}.tmp')
    try:
        pending.write_text(json.dumps(dict(file=target.name, margins=margins)), encoding='utf-8')
        pending.replace(approval)
    finally:
        pending.unlink(missing_ok=True)


def approved_crop(source: Path, cache: Path) -> tuple[Path, dict[str, int]] | None:
    try:
        record = json.loads(approval_path(source, cache).read_text(encoding='utf-8'))
        target = cache / record['file']
        margins = record['margins']
        if (target.parent == cache and target.name.startswith('crop-') and target.is_file()
                and all(isinstance(margins[edge], int) and margins[edge] >= 0
                        for edge in ('left', 'right', 'top', 'bottom'))):
            return target, margins
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None
