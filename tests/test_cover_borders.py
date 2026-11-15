from PySide6.QtGui import QColor, QImage, QPainter

from gui import cover_crop


def picture(width, height, fill, art):
    """A cover of `fill` with a coloured block at `art` (x, y, w, h)."""
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(QColor(fill))
    with QPainter(image) as painter:
        painter.fillRect(*art, QColor('#C04878'))
    return image


def test_black_side_bars(qt_app):
    margins, colour = cover_crop.detect_borders(picture(320, 320, '#050505', (46, 0, 228, 320)))
    assert margins == dict(left=46, right=46, top=0, bottom=0) and colour == 'black'


def test_black_letterbox_top_and_bottom(qt_app):
    margins, colour = cover_crop.detect_borders(picture(400, 400, 'black', (0, 50, 400, 300)))
    assert margins == dict(left=0, right=0, top=50, bottom=50) and colour == 'black'


def test_white_still_found_and_named(qt_app):
    margins, colour = cover_crop.detect_borders(picture(320, 320, 'white', (46, 0, 228, 320)))
    assert margins['left'] == 46 and colour == 'white'


def test_white_sides_and_black_bars_at_once(qt_app):
    image = picture(400, 400, 'white', (40, 0, 320, 400))
    with QPainter(image) as painter:
        painter.fillRect(40, 0, 320, 40, QColor('black'))
        painter.fillRect(40, 360, 320, 40, QColor('black'))
    margins, colour = cover_crop.detect_borders(image)
    assert margins['left'] == 40 and margins['right'] == 40 and colour == 'white'   # sides only: top rows are not all black


def test_dark_art_is_not_mistaken_for_a_border(qt_app):
    # A dark cover whose edges carry detail: nothing to trim.
    image = picture(320, 320, '#101010', (0, 0, 0, 0))
    with QPainter(image) as painter:
        for x in range(0, 320, 16):
            painter.fillRect(x, 0, 6, 320, QColor('#E0B040'))
    assert not any(cover_crop.suggest_crop(image).values())
    image.fill(QColor('black'))                     # all black: no transition, nothing suggested
    assert cover_crop.detect_borders(image) == (dict(left=0, right=0, top=0, bottom=0), '')
