"""Song titles from every source (pasted text, screenshots, web pages, files, the disc, MusicBrainz),
reviewed against the chapters before they are applied."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QUrl, Slot
from PySide6.QtGui import QGuiApplication

import extractor
import metadata_sources
import tagging
import ocr
import preview
import setlist
import webpage
from .. import logic
from core import naming
from ..models import Rows
from .base import Controller


class NamesController(Controller):
    """Song titles from every source (pasted text, screenshots, web pages, files, the disc, MusicBrainz),
    reviewed against the chapters before they are applied."""

    def __init__(self, app):
        super().__init__(
            app, pasteDraft='',
            pastePreview=dict(exported=False, rows=[], discs=[], disc=0, start=1, end=0, free=0, mode='order', canDuration=False,
                              songs=0, extras=0, used=0, chapters=0, overflow=0, valid=False, columns=[],
                              column=-1, strip=[], byWave=False, skip='auto', skippedCount=0),
            pasteOcr=dict(state='idle', text='', language='', languages=[], error='', image='', path='', serial=0,
                          again=False),
            pasteWeb=dict(state='idle', candidates=[], chosen=0, error='', url='', serial=0),
            reviewSource='online', reviewSourceName='', reviewCount=0, reviewChecked=0, reviewPool=[],
            reviewCanAlign=False, reviewMode='auto', reviewStrippable=False, reviewRemoved=0, reviewTolerance=20.0,
            reviewCounts=dict(all=0, matched=0, check=0, unmatched=0, removed=0),
            mb='idle', mbError='', mbRelease='', mbArtist='', mbAlbum='',
            titleSource=app.cfg.get('meta_source', 'musicbrainz'))
        self.entries_source = 'edited'
        self.review_model = Rows(['number', 'current', 'proposed', 'duration', 'confidence', 'detail', 'checked',
                                  'entry', 'entryLabel', 'entryDuration', 'entrySeconds', 'seconds', 'kind'], self)
        # Chapters taken out of naming (talk, films, unwanted): matching passes over them and they
        # keep their titles. Remembered per chapter list, so another disc starts with none.
        self.removed: set[int] = set()
        self.removed_for = None
        self.review_pool = []   # the tracklist being reviewed, for manual assignment
        self.release_model = Rows(['label', 'detail', 'tracks', 'chapters', 'fit', 'chosen', 'thumb'], self)
        self.candidates = []
        self.disc_number = None

    def removed_chapters(self) -> set[int]:
        key = (self.state['source'], tuple(c.index for c in self.disc.chapters))
        if key != self.removed_for:
            self.removed, self.removed_for = set(), key
        return self.removed

    def naming_chapters(self):
        removed = self.removed_chapters()
        return [c for c in self.disc.chapters if c.index not in removed]

    def naming_count(self):
        return len(self.naming_chapters()) or len(self.disc.chapters)

    def kinds_by_number(self):
        kinds, _ = self.chapter_kinds()
        return kinds

    def removed_row(self, number, current, lengths, kinds):
        return dict(number=number, current=current[number]['title'], proposed='', duration=current[number]['duration'],
                    confidence='removed', detail='', checked=False, seconds=lengths.get(number) or 0,
                    kind=kinds.get(number, ''), **self.entry_fields(None))

    def review_entries(self, entries, origin='edited', mode='auto', show=True):
        if not entries or not self.disc.chapters:
            self.notify(self.tr('noNames'))
            return
        if mode == 'chapter' and not {entry.index for entry in entries}.issubset(c.index for c in self.disc.chapters):
            self.notify(self.tr('tracklistChapterMismatch'))
            return
        chapters = self.naming_chapters()
        removed = self.removed_chapters()
        # Exported tracklists name chapters by number: names of removed chapters are left out
        matched_entries = [e for e in entries if e.index not in removed] if mode == 'chapter' else entries
        result = extractor.match_tracklist_to_chapters(chapters, matched_entries, mode=mode,
                                                       duration_tolerance_seconds=self.app.exporter.tolerance()) \
            if chapters and matched_entries else None
        current = {r['number']: r for r in self.disc.chapter_model.rows}
        lengths = {c.index: (c.end_seconds - c.start_seconds) if c.end_seconds is not None else None for c in self.disc.chapters}
        kinds = self.kinds_by_number()
        self.entries_source = origin
        self.review_pool = list(entries)
        self.put(reviewCount=len(self.review_pool))
        rows = []
        for m in (result.matches if result else []):
            # Exported tracklists keep their numbering: point at the entry by position in the pool
            entry_index = m.entry_index
            if entry_index is not None and matched_entries is not entries:
                entry_index = entries.index(matched_entries[entry_index])
            row = dict(number=m.chapter_index, current=current[m.chapter_index]['title'], proposed=m.name,
                       duration=current[m.chapter_index]['duration'], confidence=m.confidence, detail=m.detail,
                       checked=m.confidence == 'matched' and bool(m.name), seconds=lengths.get(m.chapter_index) or 0,
                       kind=kinds.get(m.chapter_index, ''))
            row.update(self.entry_fields(entry_index))
            rows.append(row)
        rows += [self.removed_row(n, current, lengths, kinds) for n in removed if n in current]
        rows.sort(key=lambda r: r['number'])
        (self.review_model.refresh if getattr(self, 'in_place', False) else self.review_model.replace)(rows)
        self.publish_counts()
        can_align = mode != 'chapter' and bool(chapters) and extractor.can_align_by_duration(chapters, entries) and not any(
            e.start_seconds is not None for e in entries)
        self.put(**({'page': 'review'} if show else {}), reviewChecked=self.count_checked(), reviewCanAlign=can_align,
                 reviewRemoved=len(removed), reviewTolerance=self.app.exporter.tolerance(),
                 reviewMode=('chapter' if mode == 'chapter' else 'duration' if can_align and mode != 'order' else 'order'))
        self.publish_pool()

    def show_waiting_rows(self):
        """
        Before a release (or list) is chosen the table still shows the chapters, with their
        lengths and current titles, so versions can be compared against them.
        """
        lengths = {c.index: (c.end_seconds - c.start_seconds) if c.end_seconds is not None else 0 for c in self.disc.chapters}
        removed, kinds = self.removed_chapters(), self.kinds_by_number()
        (self.review_model.refresh if getattr(self, 'in_place', False) else self.review_model.replace)(
            [dict(number=r['number'], current=r['title'], proposed='', duration=r['duration'],
                                        confidence='removed' if r['number'] in removed else 'waiting', detail='',
                                        checked=False, seconds=lengths.get(r['number']) or 0,
                                        kind=kinds.get(r['number'], ''), **self.entry_fields(None))
                                   for r in self.disc.chapter_model.rows])
        self.publish_counts()
        self.review_pool = []
        self.put(reviewChecked=0, reviewCount=0, reviewPool=[], reviewStrippable=False, reviewRemoved=len(removed),
                 reviewTolerance=self.app.exporter.tolerance())

    def entry_fields(self, index):
        if index is None or not 0 <= index < len(self.review_pool):
            return dict(entry=-1, entryLabel='', entryDuration='', entrySeconds=0.0)
        entry = self.review_pool[index]
        return dict(entry=index, entryLabel=f'{index + 1:02d}',
                    entryDuration=logic.format_time(entry.duration_seconds) if entry.duration_seconds else '',
                    entrySeconds=float(entry.duration_seconds or 0))

    def publish_pool(self):
        used = {r['entry'] for r in self.review_model.rows if r['entry'] >= 0}
        self.put(reviewStrippable=bool(self.shared_notes()), reviewPool=[dict(index=i, number=f'{i + 1:02d}', name=e.name,
                                  duration=logic.format_time(e.duration_seconds) if e.duration_seconds else '',
                                  used=i in used) for i, e in enumerate(self.review_pool)])

    @Slot(str)
    def realignReview(self, mode):
        """Re-run matching on the same tracklist: "duration" (skip talk/MC chapters) or "order" (1:1 by position)."""
        if self.review_pool and self.state['reviewMode'] != 'chapter' and mode in ('duration', 'order'):
            self.review_entries(self.review_pool, self.entries_source, 'order' if mode == 'order' else 'auto')

    @Slot(int, int)
    def assignReview(self, row, index):
        """Put tracklist entry `index` on review row `row` (-1 clears it)."""
        if not 0 <= row < len(self.review_model.rows):
            return
        fields = self.entry_fields(index if index >= 0 else None)
        if fields['entry'] < 0:
            self.review_model.change(row, proposed='', confidence='no_match', detail='', checked=False, **fields)
        else:
            self.review_model.change(row, proposed=self.review_pool[index].name, confidence='manual', detail='',
                                     checked=True, **fields)
        self.publish_counts()
        self.put(reviewChecked=self.count_checked())
        self.publish_pool()

    def publish_counts(self):
        """How many rows each filter of the review table holds."""
        counts = dict(all=0, matched=0, check=0, unmatched=0, removed=0, talk=0)
        for r in self.review_model.rows:
            counts['all'] += 1
            if r.get('kind') in setlist.NON_SONGS and r['confidence'] != 'removed':
                counts['talk'] += 1          # non-song chapters still taking part
            c = r['confidence']
            group = ('matched' if c in ('matched', 'manual') else 'removed' if c == 'removed'
                     else 'unmatched' if c == 'no_match' else None if c == 'waiting' else 'check')
            if group:
                counts[group] += 1
        self.put(reviewCounts=counts)

    def count_checked(self):
        return sum(bool(r['checked'] and r['proposed'].strip()) for r in self.review_model.rows)

    @Slot()
    def reviewEmbedded(self):
        self.put(mbRelease=self.tr('srcDiscBadge'), reviewSource='disc', reviewSourceName='')
        self.review_entries([extractor.TracklistEntry(c.embedded_name or c.name) for c in self.naming_chapters()], 'disc')

    @Slot(str)
    def reviewPaste(self, text):
        self.applyPaste(text, {})

    # ------------------------------------------------------------ pasted set lists
    PASTE_DEFAULTS = dict(disc=0, start=1, end=0, mode='auto', extras=True, halfwidth=False, suffixes=False,
                          original=False, column=-1, overrides={}, skip='auto', chapters={}, excluded=[])

    def paste_options(self, options):
        merged = dict(self.PASTE_DEFAULTS)
        merged.update({k: v for k, v in dict(options or {}).items() if k in merged and v is not None})
        merged['disc'], merged['start'], merged['column'] = int(merged['disc']), int(merged['start']), int(merged['column'])
        merged['end'] = int(merged['end'])
        merged['overrides'] = {str(k): str(v) for k, v in dict(merged['overrides'] or {}).items()}
        merged['chapters'] = {int(k): str(v) for k, v in dict(merged['chapters'] or {}).items()}
        merged['excluded'] = frozenset(str(k) for k in (merged['excluded'] or []))
        if merged['skip'] not in ('none', 'auto', 'lines'):
            merged['skip'] = 'auto'
        return merged

    def chapter_kinds(self):
        peaks = self.app.preview.waveform if self.state['waveState'] == 'ready' else []
        kinds = setlist.chapter_kinds(self.disc.chapters, peaks, preview.DISC_PER_SECOND,
                                      self.app.preview.ripple if peaks else None)
        return self.disc.with_manual_kinds(kinds), bool(peaks)

    def skipped_chapters(self, o, kinds):
        """Chapters songs pass over: detected non-songs (in "auto"), changed by hand either way."""
        # "auto" (the default): detected talk and interludes are passed over; "none": every chapter takes a song
        skip = {n for n, kind in kinds.items() if kind in setlist.NON_SONGS} if o['skip'] == 'auto' else set()
        skip |= self.removed_chapters()          # taken out of naming on the review page
        for number, choice in o['chapters'].items():
            if choice == 'skip':
                skip.add(number)
            elif choice == 'use':
                skip.discard(number)
        return frozenset(skip)

    def paste_plan(self, text, options):
        o = self.paste_options(options)
        parsed = setlist.parse(text, halfwidth=bool(o['halfwidth']), suffixes=bool(o['suffixes']),
                               original=bool(o['original']), column=o['column'], overrides=o['overrides'])
        disc = o['disc']
        if disc not in parsed.discs:
            disc = setlist.guess_disc(Path(self.state['source'] or '').name, parsed.discs) or 0
        count = len(self.disc.chapters) or 1
        start = max(1, min(o['start'], count))
        o['end'] = max(start, min(o['end'], count)) if o['end'] > 0 else count
        kinds, _ = self.chapter_kinds()
        skip = self.skipped_chapters(o, kinds)
        o['extras'] = o['skip'] == 'lines'       # detected chapters already stand for MC / encore lines
        plan = setlist.plan(parsed, self.disc.chapters, disc=disc or None, start=start, mode=o['mode'],
                            extras_take_chapter=o['extras'], tolerance=self.app.exporter.tolerance(), skip_chapters=skip,
                            end=o['end'])
        o['skipped'] = skip
        return parsed, disc, start, plan, o

    @Slot(str)
    def rememberPaste(self, text):
        self.put(pasteDraft=text)

    @Slot(str, 'QVariantMap')
    def previewPaste(self, text, options):
        """What a paste will do, line by line, while the user is still editing it."""
        self.put(pasteDraft=text)
        try:
            exported = extractor.parse_exported_tracklist(text)
        except ValueError:
            exported = []
        if exported is not None:
            self.put(pastePreview=dict(exported=True, rows=[], discs=[], disc=0, start=1, end=len(self.disc.chapters),
                                       free=0, mode='chapter',
                                       canDuration=False, songs=len(exported), extras=0, used=len(exported),
                                       chapters=len(self.disc.chapters), overflow=0, valid=bool(exported),
                                       columns=[], column=-1, strip=[], byWave=False, skip='auto', skippedCount=0))
            return
        parsed, disc, start, plan, o = self.paste_plan(text, options)
        placed = {p.line: p.chapter for p in plan.placements}
        lengths = {c.index: (c.end_seconds - c.start_seconds) if c.end_seconds is not None else None for c in self.disc.chapters}
        rows = []
        for i, line in enumerate(parsed.lines):
            if line.kind == setlist.BLANK:
                continue
            state = line.kind
            if line.kind in (setlist.SONG, setlist.EXTRA, setlist.SKIP):
                if parsed.discs and line.disc != disc:
                    state = 'otherDisc'
                elif line.kind == setlist.EXTRA and not o['extras']:
                    state = 'ignored'
                elif i not in placed:
                    state = 'unplaced'
                elif placed[i] is None:
                    state = 'unplaced' if plan.mode == 'duration' else 'overflow'
            chapter = placed.get(i)
            rows.append(dict(kind=line.kind, state=state, raw=line.raw.strip(), key=line.key, auto=line.auto,
                             manual=line.key in o['overrides'], excluded=line.key in o['excluded'],
                             title=line.title if line.kind in (setlist.SONG, setlist.EXTRA, setlist.MERGED, setlist.OFF)
                             and line.title else line.raw.strip(),
                             time=logic.format_length(line.seconds) if line.seconds else '',
                             chapter=f'{chapter:02d}' if chapter else '',
                             chapterTime=logic.format_length(lengths[chapter]) if chapter and lengths.get(chapter) else '',
                             disc=line.disc))
        table = parsed.table
        columns = [] if table is None else [dict(key=str(c), label=(label or '—')[:24])
                                            for c, (label, kind) in enumerate(zip(table.columns, table.kinds)) if kind == 'text']
        used = sum(1 for p in plan.placements if p.chapter is not None)
        kept = sum(1 for p in plan.placements if p.chapter is not None and parsed.lines[p.line].key not in o['excluded'])
        kinds, by_wave = self.chapter_kinds()
        song_at = {placed[i]: parsed.lines[i].title for i in placed
                   if placed[i] is not None and parsed.lines[i].key not in o['excluded']}
        strip = [dict(n=f'{c.index:02d}', number=c.index, row=row, kind=kinds.get(c.index, ''),
                      skipped=c.index in o['skipped'], manual=c.index in o['chapters'],
                      title=song_at.get(c.index, ''), before=c.index < start or c.index > o['end'],
                      length=logic.format_length(lengths[c.index]) if lengths.get(c.index) else '')
                 for row, c in enumerate(self.disc.chapters)]
        slots = sum(1 for c in self.disc.chapters if start <= c.index <= o['end'] and c.index not in o['skipped'])
        self.put(pastePreview=dict(exported=False, rows=rows, strip=strip, byWave=by_wave, skip=o['skip'],
                                   skippedCount=len(o['skipped']), discs=parsed.discs, disc=disc, start=start, end=o['end'],
                                   free=max(0, slots - used), kept=kept, mode=plan.mode,
                                   canDuration=plan.can_duration, songs=plan.songs, extras=plan.extras, used=used,
                                   chapters=len(self.disc.chapters), overflow=sum(1 for p in plan.placements if p.chapter is None),
                                   valid=plan.songs > 0, columns=columns, column=table.title if table else -1))

    @Slot(str, 'QVariantMap')
    def applyPaste(self, text, options):
        self.last_paste_options = dict(options or {})
        self.put(mbRelease=self.tr('srcPasteBadge'), reviewSource='paste', reviewSourceName='', pasteDraft=text)
        try:
            entries = extractor.parse_exported_tracklist(text)
        except ValueError:
            self.notify(self.tr('invalidChapterTracklist'))
            return
        if entries is not None:
            self.review_entries(entries, mode='chapter')
            return
        parsed, disc, start, plan, o = self.paste_plan(text, options)
        if not plan.entries:
            self.notify(self.tr('noNames'))
            return
        self.review_entries(plan.entries, mode=plan.entry_mode)
        left_out = {p.chapter for p in plan.placements
                    if p.chapter is not None and parsed.lines[p.line].key in o['excluded']}
        if left_out:
            for row, item in enumerate(self.review_model.rows):
                if item['number'] in left_out:
                    self.review_model.change(row, checked=False)
            self.put(reviewChecked=self.count_checked())
        if plan.mode == 'order':
            # Non-song chapters (MC, encore film...) keep their label but stay unticked.
            for row, item in enumerate(self.review_model.rows):
                if item['number'] in self.removed_chapters():
                    self.review_model.change(row, confidence='removed', proposed='', checked=False)
                elif item['number'] in plan.extra_chapters or item['number'] in o['skipped']:
                    self.review_model.change(row, confidence='extra', checked=False)
            # Songs past the last chapter stay available for picking by hand.
            placed = {p.line for p in plan.placements if p.chapter is not None}
            spare = [extractor.TracklistEntry(l.title) for i, l in enumerate(parsed.lines)
                     if l.kind == setlist.SONG and (not parsed.discs or l.disc == disc) and i not in placed]
            if spare:
                self.review_pool.extend(spare)
                self.put(reviewCount=len(self.review_pool))
                self.publish_pool()
            self.publish_counts()
            self.put(reviewChecked=self.count_checked())

    # ------------------------------------------------------------ set lists from screenshots and web pages
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
        path = Path(QUrl(location).toLocalFile() if location.startswith('file:') else location)
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
        def work(progress):
            text, used = ocr.recognize(path, language)
            return text, used, ocr.languages()[0]

        def done(result):
            text, used, available = result
            self.put(pasteOcr=dict(self.state['pasteOcr'], state='done', text=text, language=used,
                                   languages=available, again=again,
                                   serial=self.state['pasteOcr'].get('serial', 0) + 1))

        def failed(exc):
            message = self.tr('ocrUnavailable') if isinstance(exc, ocr.OcrUnavailable) else str(exc)
            self.put(pasteOcr=dict(self.state['pasteOcr'], state='failed', error=message))
        self.task(work, done, failed, label='ocrRunning',
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
            message = self.tr('webBadAddress') if isinstance(exc, ValueError) else str(exc)
            self.put(pasteWeb=dict(self.state['pasteWeb'], state='failed', error=message))
        self.task(work, done, failed, label='webFetching',
                  begin=dict(pasteWeb=dict(self.state['pasteWeb'], state='running', error='', url=address)))

    @Slot(str)
    def importFile(self, path):
        if path.startswith('file:'):
            path = QUrl(path).toLocalFile()
        source = Path(path)
        def work(progress):
            if source.suffix.lower() == '.json':
                entries = extractor.parse_exported_tracklist(source.read_text(encoding='utf-8-sig', errors='replace'))
                if entries is not None:
                    return entries, 'chapter'
            return extractor.load_sidecar_tracklist(source), 'auto'
        def done(result):
            entries, mode = result
            # From the workspace the file's matching titles go straight onto the chapters (the same rows the
            # review would have ticked); "Get titles" reopens the list for adjusting. On the review page it shows there.
            here = self.state['page'] == 'review'
            self.put(mbRelease=Path(path).name, reviewSource='import', reviewSourceName=Path(path).name)
            self.review_entries(entries, mode=mode, show=here)
            if not here and self.review_model.rows:
                self.applyReview()
        self.task(work, done)

    def refresh_removed(self):
        """Match again without (or with) the chapters just taken out (or put back). Rows are updated
        in place, so the table stays where it was scrolled to."""
        self.in_place = True
        try:
            self.redo_matching()
        finally:
            self.in_place = False

    def redo_matching(self):
        self.put(reviewRemoved=len(self.removed_chapters()))
        if self.state['reviewCount'] == 0:
            self.show_waiting_rows()
        elif self.state['reviewSource'] == 'paste' and self.state['pasteDraft'] and self.review_model.rows and self.state['reviewMode'] == 'chapter':
            # A pasted list is laid out over the chapters again, passing over the removed ones
            self.applyPaste(self.state['pasteDraft'], getattr(self, 'last_paste_options', {}))
            self.put(reviewRemoved=len(self.removed_chapters()))
        elif self.entries_source == 'disc':
            self.review_entries([extractor.TracklistEntry(c.embedded_name or c.name) for c in self.naming_chapters()],
                                'disc', show=False)
        else:
            mode = self.state['reviewMode']
            self.review_entries(self.review_pool, self.entries_source,
                                'chapter' if mode == 'chapter' else 'order' if mode == 'order' else 'auto', show=False)
        self.refresh_release_fits()

    def refresh_release_fits(self):
        """Releases compare their track count with the chapters still being named."""
        chapters = self.naming_count()
        for i, row in enumerate(self.release_model.rows):
            if row['fit'] == 'unknown':
                self.release_model.change(i, chapters=chapters)
                continue
            diff = abs(row['tracks'] - chapters)
            self.release_model.change(i, chapters=chapters, fit='exact' if diff == 0 else 'close' if diff <= 2 else 'far')

    @Slot(int, bool)
    def removeChapter(self, number, removed):
        """Take a chapter out of naming (it keeps its title), or put it back."""
        chapters = self.removed_chapters()
        if removed and len(chapters) + 1 >= len(self.disc.chapters):
            return                          # at least one chapter stays to be named
        (chapters.add if removed else chapters.discard)(number)
        self.refresh_removed()

    @Slot()
    def removeNonSongs(self):
        """Take out every chapter the loudness outline says is talk (MC, films, credits)."""
        talk = {n for n, kind in self.kinds_by_number().items() if kind in setlist.NON_SONGS}
        if talk and len(talk) < len(self.disc.chapters):
            self.removed_chapters().update(talk)
            self.refresh_removed()

    @Slot()
    def restoreRemoved(self):
        self.removed_chapters().clear()
        self.refresh_removed()

    @Slot(int, str, result=str)
    def fileNamePreview(self, number, title):
        """The file this chapter would be exported as, with the current naming settings."""
        try:
            template = self.app.exporter.filename_template()
            included = [r['number'] for r in self.disc.chapter_model.rows if r.get('included')]
            position = included.index(number) + 1 if number in included else number
            base = naming.sanitize_filename(title.strip() or f'Track {number:02d}')
            if template != 'title':
                metadata = self.app.metadata.export_metadata() if self.disc.state['outputFormat'] == 'flac' else None
                base = naming.sanitize_filename(naming.render_filename(template, position, base,
                                                                       tagging.artist_for(metadata, number)))
            return base + ('.flac' if self.disc.state['outputFormat'] == 'flac' else '.mkv')
        except Exception:      # a preview only: never break the table
            return ''

    @Slot(int, bool)
    def checkReview(self, row, checked):
        self.review_model.change(row, checked=checked)
        self.put(reviewChecked=self.count_checked())

    @Slot(bool)
    def checkAllReview(self, checked):
        for i, row in enumerate(self.review_model.rows):
            self.review_model.change(i, checked=checked and bool(row['proposed'].strip()) and row['confidence'] != 'removed')
        self.put(reviewChecked=self.count_checked())

    @Slot(int, str)
    def editReview(self, row, title):
        # Typing a title is a clear intent to use it.
        self.review_model.change(row, proposed=title, checked=bool(title.strip()))
        self.put(reviewChecked=self.count_checked(), reviewStrippable=bool(self.shared_notes()))

    def shared_notes(self):
        """The bracketed notes most candidate titles share (from the tracklist, else the rows)."""
        titles = [e.name for e in self.review_pool] or [r['proposed'] for r in self.review_model.rows]
        shared = setlist.shared_suffixes(titles)
        # Only worth a button while some candidate still carries one.
        if any(setlist.drop_suffix_notes(r['proposed'], shared) != r['proposed'] for r in self.review_model.rows):
            return shared
        return set()

    @Slot()
    def stripReviewBrackets(self):
        """
        One click: drop the bracketed note most candidate titles share (an album-wide
        "(Live on …)"), keeping notes that belong to one song. Searching again restores them.
        """
        shared = self.shared_notes()
        if not shared:
            return
        self.review_pool = [replace(e, name=setlist.drop_suffix_notes(e.name, shared)) for e in self.review_pool]
        for i, row in enumerate(self.review_model.rows):
            title = setlist.drop_suffix_notes(row['proposed'], shared)
            if title != row['proposed']:
                self.review_model.change(i, proposed=title)
        self.publish_pool()

    @Slot()
    def applyReview(self):
        current = {r['number']: i for i, r in enumerate(self.disc.chapter_model.rows)}
        for row in self.review_model.rows:
            if row['checked'] and row['proposed'].strip():
                title = row['proposed'] if self.state['reviewMode'] == 'chapter' else row['proposed'].strip()
                self.disc.chapter_model.change(current[row['number']], title=title, origin=self.entries_source)
                if self.entries_source == 'disc':
                    self.disc.disc_baselines[row['number']] = row['proposed'].strip()
        self.put(page='main')

    @Slot()
    def openTitles(self):
        """The workspace's single "get titles" entry: reopen whichever source was used last."""
        if self.state['busy']:
            return
        source = self.state['reviewSource']
        if source == 'disc' and self.disc.chapters:
            self.reviewEmbedded()
        elif source == 'import' and self.review_pool:
            # A file imported from the workspace was applied directly: reopen it, matched against the current titles.
            self.review_entries(self.review_pool, origin=self.entries_source,
                                mode='chapter' if self.state['reviewMode'] == 'chapter' else 'auto')
        elif source in ('paste', 'import'):
            # Nothing to re-run without the text/file: show that tab with a prompt.
            self.review_pool = []
            self.show_waiting_rows()
            self.put(page='review', reviewChecked=0, reviewCount=0, mbRelease='', reviewSourceName='', reviewCanAlign=False)
        else:
            self.openOnline()

    @Slot()
    def openOnline(self):
        """Enter the MusicBrainz review: start from a clean table, search right away when there is a query."""
        if self.state['busy']:
            return
        self.show_waiting_rows()
        chosen = next((i for i, r in enumerate(self.release_model.rows) if r['chosen']), None)
        self.put(page='review', reviewChecked=0, mbRelease='', reviewSource='online', reviewSourceName='', reviewCanAlign=False)
        if chosen is not None:
            self.selectRelease(chosen)
        elif not self.candidates and (self.state['mbArtist'].strip() or self.state['mbAlbum'].strip()):
            self.search(self.state['mbArtist'], self.state['mbAlbum'], '')

    def start_over(self, artist, album):
        """A new source: forget the releases found for the last one. Returns the album name to search for."""
        album, self.disc_number = extractor.split_disc_tag(album)
        self.candidates = []
        self.release_model.replace([])
        self.put(mb='idle', mbError='', mbRelease='', mbArtist=artist, mbAlbum=album)
        return album

    def mb_error(self, exc):
        return self.tr('mbBusy') if isinstance(exc, extractor.MusicBrainzBusy) else str(exc)

    def release_fit(self, candidate):
        """Track count of the disc that would be used, and how well it fits the chapter count."""
        counts = candidate.medium_track_counts or ([candidate.track_count] if candidate.track_count else [])
        if not counts:
            return 0, 'unknown'
        tracks = counts[extractor.pick_medium(counts, self.naming_count(), self.disc_number)]
        diff = abs(tracks - self.naming_count())
        return tracks, 'exact' if diff == 0 else 'close' if diff <= 2 else 'far'

    @Slot(str, str, str)
    def search(self, artist, album, barcode):
        if self.state['busy']:
            return
        self.put(mbArtist=artist, mbAlbum=album)
        if not (artist.strip() or album.strip() or barcode.strip()):
            self.put(mb='error', mbError=self.tr('mbNeedQuery'))
            return
        if self.state['titleSource'] != 'musicbrainz':
            self.search_other(self.state['titleSource'], artist, album, barcode)
            return
        def work(p):
            return (extractor.search_musicbrainz_releases_by_barcode(barcode) if barcode.strip()
                    else extractor.search_musicbrainz_releases(artist, album))
        def done(candidates):
            order = {'exact': 0, 'close': 1, 'unknown': 2, 'far': 3}
            fits = {id(c): self.release_fit(c) for c in candidates}
            candidates = sorted(candidates, key=lambda c: (order[fits[id(c)][1]], -c.score))
            self.candidates = candidates
            self.release_model.replace([dict(label=f'{c.artist} — {c.title}' if c.artist else c.title,
                detail=' · '.join(x for x in (c.format_hint, c.date,
                    self.tr('mbDiscs').format(n=len(c.medium_track_counts)) if len(c.medium_track_counts) > 1 else '') if x),
                tracks=fits[id(c)][0], chapters=self.naming_count(), fit=fits[id(c)][1], chosen=False, thumb='') for c in candidates])
            self.put(mb='results' if candidates else 'empty', mbError='')
            # Preview the best fit straight away; nothing is applied until the user confirms.
            if candidates and fits[id(candidates[0])][1] == 'exact':
                self.selectRelease(0)
        def failed(exc):
            self.put(mb='error', mbError=self.mb_error(exc))
        self.task(work, done, failed, begin=dict(mb='searching', mbError=''))

    @Slot(int)
    def selectRelease(self, row):
        if self.state['busy'] or not 0 <= row < len(self.candidates):
            return
        release = self.candidates[row]
        for i in range(len(self.release_model.rows)):
            self.release_model.change(i, chosen=i == row)
        if isinstance(release, metadata_sources.Candidate):
            self.select_other(release, self.release_model.rows[row]['label'])
            return
        chapters, disc = self.naming_count(), self.disc_number
        label = self.release_model.rows[row]['label']
        def done(entries):
            self.put(mb='results')
            if not entries:
                self.show_waiting_rows()
                self.put(mbRelease='', reviewChecked=0, mb='error', mbError=self.tr('mbNoTracks'))
                return
            self.put(mbRelease=label, reviewSource='online')
            self.review_entries(entries)
        def failed(exc):
            self.put(mb='error', mbError=self.mb_error(exc))
        self.task(lambda p: extractor.fetch_musicbrainz_tracklist(release.release_id, chapters, disc), done, failed,
                  begin=dict(mb='loading', mbError=''))

    @Slot(str)
    def setTitleSource(self, source):
        if source not in metadata_sources.SOURCES or self.state['busy'] or source == self.state['titleSource']:
            return
        self.candidates = []
        self.release_model.replace([])
        self.put(titleSource=source, mb='idle', mbError='')

    def search_other(self, source, artist, album, barcode):
        chapters = self.naming_count()
        def fit(count):
            if not count:
                return 'unknown'
            diff = abs(count - chapters)
            return 'exact' if diff == 0 else 'close' if diff <= 2 else 'far'
        def done(found):
            order = {'exact': 0, 'close': 1, 'unknown': 2, 'far': 3}
            found = sorted(found, key=lambda c: order[fit(c.track_count)])
            self.candidates = found
            self.release_model.replace([dict(label=f'{c.artist} \u2014 {c.title}' if c.artist else c.title,
                detail=c.detail, tracks=c.track_count, chapters=chapters, fit=fit(c.track_count),
                chosen=False, thumb=c.thumb) for c in found])
            self.put(mb='results' if found else 'empty', mbError='')
        def failed(exc):
            self.put(mb='error', mbError=self.app.metadata.source_error(exc))
        self.task(lambda p: metadata_sources.search(source, artist, album, barcode), done, failed,
                  begin=dict(mb='searching', mbError=''))

    def select_other(self, candidate, label):
        def work(p):
            return metadata_sources.fetch(candidate.source, candidate.id)
        def done(info):
            self.put(mb='results')
            if not info.tracks:
                self.show_waiting_rows()
                self.put(mbRelease='', reviewChecked=0, mb='error', mbError=self.tr('mbNoTracks'))
                return
            self.put(mbRelease=label, reviewSource='online')
            self.review_entries([extractor.TracklistEntry(t.title, index=i + 1, duration_seconds=t.seconds)
                                 for i, t in enumerate(info.tracks)])
        def failed(exc):
            self.put(mb='error', mbError=self.app.metadata.source_error(exc))
        self.task(work, done, failed, begin=dict(mb='loading', mbError=''))
