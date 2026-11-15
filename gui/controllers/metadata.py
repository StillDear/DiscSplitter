"""Album and track tags and the cover: looked up online, edited, and handed to the export."""
from __future__ import annotations

import copy
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QTimer, QUrl, Slot

from core import metadata_sources, musicbrainz, tagging
from .. import settings
from .. import cover_crop, logic
from ..models import Rows
from .base import Controller, local_path


class MetadataController(Controller):
    """Album and track tags and the cover: looked up online, edited, and handed to the export."""

    def __init__(self, app):
        super().__init__(app, meta=tagging.empty_metadata(), metaStatus='idle', metaError='', metaChosen=-1,
                         canRestoreCover=False, coverCache='')
        self.meta = tagging.empty_metadata()
        self.meta_model = Rows(['source', 'label', 'detail', 'thumb', 'chosen'], self)
        self.original_cover = ''
        self.cover_crop_margins = {}
        self.meta_owner = None          # source path the metadata belongs to
        self.meta_candidates = []
        self.auto_meta_pending = False

    COVER_CACHE = settings.SETTINGS_PATH.parent / 'covers'

    def publish_metadata(self):
        self.put(meta=copy.deepcopy(self.meta), canRestoreCover=bool(self.original_cover))

    def reset_metadata(self, owner, artist='', album='', year=None):
        self.meta = tagging.empty_metadata()
        self.original_cover = ''
        self.cover_crop_margins = {}
        self.meta['album'].update(artist=artist or '', album=album or '', album_artist=artist or '',
                                  date=str(year) if year else '')
        self.meta_owner = owner
        self.auto_meta_pending = bool(self.cfg.get('meta_auto_search')) and bool(artist or album) and not self.smoke
        self.meta_candidates = []
        self.meta_model.replace([])
        for i in range(len(self.disc.chapter_model.rows)):
            self.disc.chapter_model.change(i, artist='')
        self.put(metaStatus='idle', metaError='', metaChosen=-1)
        self.publish_metadata()

    def for_source(self, owner, artist='', album='', year=None):
        """A source was scanned: fresh tags for a new one; the same source scanned again keeps its edits."""
        if self.meta_owner != owner:
            self.reset_metadata(owner, artist, album, year)

    def search_when_due(self):
        """The new source's first playlist is read: run the automatic tag search once, if it is switched on."""
        if not self.auto_meta_pending:
            return
        self.auto_meta_pending = False
        album = self.meta['album']
        QTimer.singleShot(0, lambda: self.metaSearch(self.cfg.get('meta_source', 'musicbrainz'),
                                                     album['artist'], album['album'], ''))

    def track_artist(self, index):
        return self.meta['track_artists'].get(str(index), '')

    def set_track_artists(self, artists):
        """Per-song artists by chapter index (after the chapters were edited); blank ones are dropped."""
        self.meta['track_artists'] = {str(index): artist for index, artist in artists.items() if artist.strip()}

    def export_metadata(self):
        meta = copy.deepcopy(self.meta)
        meta['track_artists'] = {k: v for k, v in meta['track_artists'].items() if v.strip()}
        meta['cover_mode'] = self.cfg.get('cover_target', 'both')
        if self.cover_crop_margins:
            meta['replace_folder_cover'] = True
        return meta

    @Slot(str, str)
    def setMeta(self, key, value):
        """key is "album.<field>"."""
        group, _, name = key.partition('.')
        if group != 'album' or name not in tagging.ALBUM_FIELDS:
            return
        self.meta['album'][name] = value
        self.publish_metadata()

    @Slot(int, str)
    def setTrackArtist(self, row, artist):
        if not 0 <= row < len(self.disc.chapter_model.rows):
            return
        number = str(self.disc.chapter_model.rows[row]['number'])
        self.meta['track_artists'][number] = artist
        self.disc.chapter_model.change(row, artist=artist)
        self.publish_metadata()

    @Slot(str)
    def chooseCover(self, url):
        path = Path(local_path(url))
        if path.suffix.lower() not in tagging.COVER_TYPES or not path.is_file():
            self.notify(self.tr('coverInvalid'))
            return
        self.use_cover(path)
        self.publish_metadata()

    def use_cover(self, path):
        self.meta['cover'] = str(path)
        self.original_cover = ''
        self.cover_crop_margins = {}
        approved = cover_crop.approved_crop(path, self.COVER_CACHE)
        if approved:
            target, self.cover_crop_margins = approved
            self.meta['cover'] = str(target)
            self.original_cover = str(path)

    @Slot()
    def clearCover(self):
        self.meta['cover'] = ''
        self.original_cover = ''
        self.cover_crop_margins = {}
        self.publish_metadata()

    @Slot(result='QVariantMap')
    def coverCropInfo(self):
        source = self.original_cover or self.meta['cover']
        image = cover_crop.read_cover(source) if source else None
        if image is None or image.isNull():
            self.notify(self.tr('coverInvalid'))
            return {}
        margins = self.cover_crop_margins if self.original_cover else cover_crop.suggest_crop(image)
        return dict(url=QUrl.fromLocalFile(source).toString(), width=image.width(), height=image.height(),
                    **margins)

    @Slot(int, int, int, int, result=bool)
    def applyCoverCrop(self, left, right, top, bottom):
        if self.state['busy'] or not self.meta['cover']:
            return False
        source = self.original_cover or self.meta['cover']
        image = cover_crop.read_cover(source)
        suffix = '.png' if Path(source).suffix.lower() == '.png' else '.jpg'
        target = self.COVER_CACHE / f'crop-{uuid4().hex}{suffix}'
        margins = dict(left=left, right=right, top=top, bottom=bottom)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if image.isNull() or not cover_crop.save_crop(image, target, left, right, top, bottom):
                self.notify(self.tr('coverCropFailed'))
                return False
            cover_crop.remember_crop(Path(source), target, margins)
        except OSError:
            self.notify(self.tr('coverCropFailed'))
            return False
        self.original_cover = source
        self.cover_crop_margins = margins
        self.meta['cover'] = str(target)
        self.publish_metadata()
        return True

    @Slot()
    def restoreCover(self):
        if self.original_cover and not self.state['busy']:
            try:
                cover_crop.approval_path(Path(self.original_cover), self.COVER_CACHE).unlink(missing_ok=True)
            except OSError:
                self.notify(self.tr('coverRestoreFailed'))
                return
            self.meta['cover'], self.original_cover = self.original_cover, ''
            self.publish_metadata()

    @Slot(str, str, str, str)
    def metaSearch(self, source, artist, album, barcode):
        if source not in metadata_sources.SOURCES:
            return
        def done(found):
            self.meta_candidates = found
            self.meta_model.replace([dict(
                source=c.source, label=f'{c.artist} \u2014 {c.title}',
                detail=' \u00b7 '.join(x for x in (c.detail, self.tr('trackCount').replace('{n}', str(c.track_count)) if c.track_count else '') if x),
                thumb=c.thumb, chosen=False) for c in found])
            self.put(metaStatus='results' if found else 'empty', metaChosen=-1)
        def failed(exc):
            self.put(metaStatus='error', metaError=self.source_error(exc))
        self.task(lambda p: metadata_sources.search(source, artist, album, barcode), done, failed,
                  begin=dict(metaStatus='loading', metaError=''), blocking=False)

    def source_error(self, exc):
        """A catalogue's failure in the user's words."""
        if isinstance(exc, musicbrainz.MusicBrainzBusy):
            return self.tr('mbBusy')
        return self.app.error_text(exc)

    @Slot(int)
    def metaChoose(self, row):
        if 0 <= row < len(self.meta_candidates):
            for i in range(len(self.meta_model.rows)):
                self.meta_model.change(i, chosen=i == row)
            self.put(metaChosen=row)

    @Slot(bool, bool, bool, bool)
    def metaApply(self, album, cover, artists, titles):
        """Fetch the chosen release and apply the parts the user ticked."""
        row = self.state['metaChosen']
        if self.working or not 0 <= row < len(self.meta_candidates):
            return
        candidate = self.meta_candidates[row]
        def work(progress):
            info = metadata_sources.fetch(candidate.source, candidate.id)
            cover_file, cover_error = None, ''
            if cover and info.cover_url:
                try:
                    cover_file = metadata_sources.download_cover(info.cover_url, self.COVER_CACHE,
                                                                 f'{candidate.source}:{candidate.id}')
                except RuntimeError as exc:
                    cover_error = self.app.error_text(exc)
            return info, cover_file, cover_error
        def done(result):
            info, cover_file, cover_error = result
            if album:
                for name in tagging.ALBUM_FIELDS:
                    value = getattr(info, name, '')
                    if value:
                        self.meta['album'][name] = value
            if cover_file:
                self.use_cover(cover_file)
            # A multi-disc release: only the disc this playlist holds.
            tracks = info.disc_tracks(self.app.names.naming_count(), self.app.names.disc_number)
            if artists:
                album_artist = self.meta['album']['album_artist'] or self.meta['album']['artist']
                for i, track in enumerate(tracks[:len(self.disc.chapter_model.rows)]):
                    value = track.artist if track.artist and track.artist != album_artist else ''
                    self.meta['track_artists'][str(self.disc.chapter_model.rows[i]['number'])] = value
                    self.disc.chapter_model.change(i, artist=value)
            self.publish_metadata()
            self.put(metaStatus='applied', metaError=cover_error)
            if titles and tracks:
                self.app.names.review_online(f'{info.artist} \u2014 {info.album}'.strip(' \u2014'),
                                             metadata_sources.tracklist_entries(tracks))
        def failed(exc):
            self.put(metaStatus='error', metaError=self.source_error(exc))
        self.task(work, done, failed, begin=dict(metaStatus='loading', metaError=''), blocking=False)

    def refresh_cover_cache(self):
        files = [p for p in self.COVER_CACHE.glob('*') if p.is_file()] if self.COVER_CACHE.is_dir() else []
        size = sum(p.stat().st_size for p in files)
        self.put(coverCache=logic.format_bytes(size) if files else '')

    @Slot()
    def clearCoverCache(self):
        keep = {Path(self.meta.get('cover') or ''), Path(self.original_cover)}
        if self.original_cover:
            try:
                keep.add(cover_crop.approval_path(Path(self.original_cover), self.COVER_CACHE))
            except OSError:
                pass
        if self.COVER_CACHE.is_dir():
            for path in self.COVER_CACHE.glob('*'):
                if path.is_file() and path not in keep:
                    path.unlink(missing_ok=True)
        self.refresh_cover_cache()
