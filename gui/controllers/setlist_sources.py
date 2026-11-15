"""Set lists read from a screenshot (Windows OCR) or a web page: the text lands in the paste dialog."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QImage

from core import ocr, webpage
from .base import local_path


def prepared_for_ocr(path, max_side, scratch):
    """The screenshot at a size Windows OCR reads well: the file itself, or a resized copy in scratch."""
    image = QImage(str(path))
    if image.isNull():
        raise ValueError('Not an image')
    scale = ocr.scale_for(image.width(), image.height(), max_side)
    if scale == 1.0:
        return Path(path)
    image = image.scaled(int(image.width() * scale), int(image.height() * scale),
                         Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    target = Path(scratch) / f'ocr-{uuid4().hex[:8]}.png'
    if not image.save(str(target), 'PNG'):
        raise ValueError('Not an image')
    return target


class SetlistSources:
    """The part of NamesController that turns a screenshot or a web address into set-list text."""

    @Slot(result=bool)
    def clipboardHasImage(self):
        mime = QGuiApplication.clipboard().mimeData()
        return bool(mime and mime.hasImage() and not mime.hasText())

    @Slot()
    def ocrClipboard(self):
        image = QGuiApplication.clipboard().image()
        if image.isNull():
            self.put(pasteOcr=dict(self.state['pasteOcr'], state='failed', error=self.tr('ocrNoImage')))
            return
        target = self.app.preview_dir / f'screenshot-{uuid4().hex[:8]}.png'
        image.save(str(target), 'PNG')
        self.read_screenshot(target)

    @Slot(str)
    def ocrImage(self, location):
        path = Path(local_path(location))
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff') or not path.is_file():
            self.put(pasteOcr=dict(self.state['pasteOcr'], state='failed', error=self.tr('ocrNotImage')))
            return
        self.read_screenshot(path)

    @Slot(str)
    def ocrAgain(self, language):
        """Read the same screenshot again in another language."""
        path = self.state['pasteOcr'].get('path')
        if path and Path(path).is_file():
            self.read_screenshot(Path(path), language, again=True)

    def read_screenshot(self, path, language='auto', again=False):
        scratch = self.app.preview_dir

        def work(progress):
            available, max_side = ocr.languages()
            prepared = prepared_for_ocr(path, max_side, scratch)
            try:
                text, used = ocr.recognize(prepared, language)
            finally:
                if prepared != path:
                    prepared.unlink(missing_ok=True)
            return text, used, available

        def done(result):
            text, used, available = result
            self.put(pasteOcr=dict(self.state['pasteOcr'], state='done', text=text, language=used,
                                   languages=available, again=again,
                                   serial=self.state['pasteOcr'].get('serial', 0) + 1))

        def failed(exc):
            message = self.tr('ocrUnavailable') if isinstance(exc, ocr.OcrUnavailable) else self.app.error_text(exc)
            self.put(pasteOcr=dict(self.state['pasteOcr'], state='failed', error=message))
        self.task(work, done, failed, label='ocrRunning', blocking=False,
                  begin=dict(pasteOcr=dict(self.state['pasteOcr'], state='running', error='', path=str(path),
                                           image=QUrl.fromLocalFile(str(path)).toString())))

    @Slot(str)
    def fetchSetlist(self, address):
        address = address.strip()
        if not address:
            return
        timeout = float(self.cfg.get('net_timeout', '15') or 15)

        def work(progress):
            found = webpage.candidates(webpage.fetch(address, timeout))
            return [dict(kind=c.kind, text=c.text, songs=c.songs, heading=c.heading[:40]) for c in found[:8]]

        def done(found):
            serial = self.state['pasteWeb'].get('serial', 0) + 1
            if not found:
                self.put(pasteWeb=dict(self.state['pasteWeb'], state='failed', candidates=[],
                                       error=self.tr('webNothing')))
                return
            self.put(pasteWeb=dict(self.state['pasteWeb'], state='done', candidates=found, chosen=0, serial=serial))

        def failed(exc):
            message = self.tr('webBadAddress') if isinstance(exc, ValueError) else self.app.error_text(exc)
            self.put(pasteWeb=dict(self.state['pasteWeb'], state='failed', error=message))
        self.task(work, done, failed, label='webFetching', blocking=False,
                  begin=dict(pasteWeb=dict(self.state['pasteWeb'], state='running', error='', url=address)))
