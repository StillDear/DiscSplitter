"""The disc being worked on: source and destination, the chosen playlist, its tracks and
chapters (with edits), and the track details sheet."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import QUrl, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from core import bluray_iso, chapter_marks, dvd, engine, models, naming, preview, setlist, sources, space, tracklist
from .. import logic, track_info
from ..background import SideJob
from ..i18n import localize_reason
from ..models import Rows, SelectedChapters
from .base import Controller, local_path


class DiscController(Controller):
    """The disc being worked on: source and destination, the chosen playlist, its tracks and
    chapters (with edits), and the track details sheet."""

    FORMATS = ('mkv', 'm2ts', 'flac')

    def __init__(self, app):
        cfg = app.cfg
        super().__init__(
            app, source=cfg.get('last_source_folder', ''), output=cfg.get('last_output_folder', ''),
            sidecars=[], album='', artist='',
            chapterSelected=0, longClock=False, timelineSeconds=0, timelineChapters=[], audioSelected=0, audioRecommended=-1, subtitleSelected=0, unnamedRows=[], originsMixed=False, chaptersEdited=False,
            hasVideo=False, keepVideo=False, videoSummary='', videoExtra='', exportEstimate={}, sourceSummary='', chapterKinds={}, chapterKindsManual=[],
            outputFormat=cfg.get('output_container') if cfg.get('output_container') in self.FORMATS else 'mkv',
            canM2ts=False,
            trackInfo=dict(title='', heading='', sections=[], probing=False, error=''))
        self.playlists = []
        self.playlist = None
        self.audio = None
        self.chapters = []
        self.source_chapters = None     # the source's own chapters, kept while the list is being edited
        self.source_size = None         # bytes behind the chosen playlist, for the disk space check
        self.disc_baselines = {}
        self.scanned_source = None      # the disc the chapter table belongs to
        self.playlist_model = Rows(['label', 'detail', 'tracks', 'headline', 'reasons', 'chosen'], self)
        self.audio_model = Rows(['label', 'codec', 'details', 'chosen', 'title', 'chips', 'extra'], self)
        self.subtitle_model = Rows(['label', 'chosen', 'title', 'chips', 'extra'], self)
        self.chapter_model = Rows(['number', 'title', 'origin', 'duration', 'seconds', 'start', 'status', 'file',
                                   'artist', 'included', 'begin', 'verify', 'verifyText'], self)
        self.export_model = SelectedChapters(self.chapter_model, self)
        # Any change to chapter titles refreshes which rows still need a name (timeline highlight).
        self.chapter_model.modelReset.connect(self.update_unnamed)
        self.chapter_model.dataChanged.connect(lambda *args: self.update_unnamed())
        self.info_target = None
        # Stream details read in the background: the card's video line, and the details sheet.
        self.video_probe = SideJob(self, self.video_probed)
        self.info_probe = SideJob(self, self.info_done, self.info_failed)
        self._kind_key, self._kind_overrides = None, {}     # music / talk set by hand, per playlist

    @Slot(str)
    def setSource(self, source):
        if self.working:
            return
        source = local_path(source).strip('"')
        self.put(source=source)
        self.app.exporter.refresh_resume()
        path = Path(source)
        if source and (path.is_dir() or sources.is_mkv_source(path) or bluray_iso.is_iso(path)
                       or sources.is_bluray_file(path)):
            self.scan()

    @Slot(str)
    def setOutput(self, output):
        if self.state['busy']:
            return
        output = local_path(output)
        self.app.set_config(last_output_folder=output)
        self.put(output=output)
        self.app.exporter.refresh_resume()
        self.refresh_insights()

    @Slot()
    def scan(self):
        if self.working or not self.state['source']:
            return
        source = Path(self.state['source'])
        self.app.preview.stopPreview()
        self.app.preview.stop_waveform()
        self.playlists = []
        self.playlist = self.audio = None
        self.audio_model.replace([])
        self.subtitle_model.replace([])
        self.playlist_model.replace([])
        if str(source) != self.scanned_source:
            # Another disc: none of the old chapter titles belong to it. (A rescan of the
            # same disc keeps them, as switching between its playlists does.)
            self.forget_chapters()
        self.show('main')
        self.put(audioSelected=0, audioRecommended=-1, subtitleSelected=0, chapterSelected=0, hasVideo=False, keepVideo=False, canM2ts=False)
        keeper = self.app.preview_mounts
        def work(progress):
            keeper.close()
            sidecar_folder = (source.parent if sources.is_mkv_source(source) or bluray_iso.is_iso(source)
                              or sources.is_bluray_file(source)
                              else dvd.disc_folder(source) or source)
            return (sources.score_playlists(sources.scan_source(source)),
                    tracklist.find_sidecar_tracklist_files(sidecar_folder),
                    naming.guess_artist_album_year(sources.source_name_path(source)))
        def done(result):
            scores, sidecars, guessed = result
            self.playlists = scores
            self.scanned_source = str(source)
            self.app.set_config(last_source_folder=str(source))
            mb_album = self.app.names.start_over(guessed[0], guessed[1])
            self.put(sidecars=[str(p) for p in sidecars], artist=guessed[0], album=guessed[1])
            self.playlist_model.replace([self.playlist_card(s) for s in scores])
            self.app.metadata.for_source(str(source), guessed[0], mb_album, guessed[2])
            if scores:
                self.selectPlaylist(0)
            else:
                self.chapter_model.replace([])
                self.show('start')          # nothing to work on: back where the disc was chosen
                self.notify(self.tr('noPlaylists'))
        def failed(exc):
            self.chapters = []
            self.chapter_model.replace([])
            self.put(sidecars=[], artist='', album='')
            self.show('start')
            self.report(exc)
        self.task(work, done, failed, label='scanning')

    def playlist_card(self, score):
        return dict(label=self.playlist_label(score.playlist), chosen=False,
                    **self.card_texts(score, self.cfg.get('language', 'zh')))

    def forget_chapters(self):
        self.chapters = []
        self.source_chapters = None
        self.source_size = None
        self.disc_baselines = {}
        self.chapter_model.replace([])
        self.put(chaptersEdited=False)

    def card_texts(self, score, language):
        """Everything on a playlist card that depends on the interface language."""
        playlist = score.playlist
        return dict(detail=f"{logic.format_length(playlist.duration_seconds)} · {self.tr('chapterShort').replace('{n}', str(playlist.chapter_count))}",
                    tracks=self.track_summary(playlist), **self.reason_fields(score.reasons, language))

    @staticmethod
    def reason_fields(reasons, language):
        """One line for the card, the full list for its tooltip."""
        headline = logic.headline_reason(reasons)
        return dict(headline=localize_reason(headline, language) if headline else '',
                    reasons='\n'.join(localize_reason(r, language) for r in reasons))

    def track_summary(self, playlist):
        """What a candidate holds, for comparing them side by side: "TrueHD Atmos 7.1 / LPCM 2.0 · 1920×1080 · 2 subtitles"."""
        audio = list(dict.fromkeys(' '.join(x for x in (t.codec, t.channel_layout) if x) for t in playlist.audio_tracks))
        audio_text = ' / '.join(audio[:2]) + (f' +{len(audio) - 2}' if len(audio) > 2 else '') if audio else self.tr('plNoAudio')
        video = playlist.video_track
        size = track_info.resolution(video, {}) if video is not None else None
        video_text = (f'{size[0]}×{size[1]}' if size else video.codec) if video is not None else self.tr('plNoVideo')
        subtitles = len(playlist.subtitle_tracks)
        subtitle_text = self.tr('plSubs').replace('{n}', str(subtitles)) if subtitles else self.tr('plNoSubs')
        # A no-break space keeps each "·" with the item before it, so a wrapped line never starts with one
        return ' · '.join((audio_text, video_text, subtitle_text))

    def playlist_label(self, playlist):
        title = dvd.title_of(playlist.path)
        return f"DVD · {self.tr('dvdTitle')} {title[1]:02d}" if title else playlist.path.name

    # ------------------------------------------------------------ track details
    def info_tracks(self, kind):
        if self.playlist is None:
            return []
        if kind == 'video':
            return [self.playlist.video_track] if self.playlist.video_track is not None else []
        return self.playlist.audio_tracks if kind == 'audio' else self.playlist.subtitle_tracks

    def info_track(self, kind, row):
        tracks = self.info_tracks(kind)
        return tracks[row] if 0 <= row < len(tracks) else None

    def publish_info(self, probe=None, probing=False, error=''):
        kind, row = self.info_target
        track = self.info_track(kind, row)
        if track is None:
            return
        lang = self.cfg.get('language', 'zh')
        length = self.playlist.duration_seconds or max((c.end_seconds or 0 for c in self.chapters), default=0)
        probe = dict(probe or {})
        sampled = probe.pop('sampled_kbps', None)
        sheet = track_info.sections(track, kind, length, probe, self.tr, lang, sampled_kbps=sampled)
        title = self.tr({'audio': 'tiTitle', 'video': 'tiVideoTitle'}.get(kind, 'tiSubtitleTitle'))
        heading = (track.display_label if kind == 'audio' else
                   track_info.video_summary(track, probe) if kind == 'video' else track.codec)
        self.put(trackInfo=dict(title=title, heading=heading, sections=sheet, probing=probing, error=error,
                                text=track_info.as_text(title, heading, sheet)))
        if kind == 'video' and probe:
            self.put(videoSummary=track_info.video_summary(track, probe))

    VIDEO_SAMPLE_AT = 300       # measure the video bitrate this far in (openings are often dark and cheap)

    def probe_video(self, path, playlist, track, with_bitrate):
        """ffprobe's view of the video stream, plus a measured bitrate when asked."""
        probe = preview.probe_stream(path, track, 0, 'video')
        if with_bitrate and probe:
            try:
                start = float(probe.get('start_time') or 0)
            except ValueError:
                start = 0.0
            length = playlist.duration_seconds or 0
            at = min(self.VIDEO_SAMPLE_AT, length / 3) if length else 0
            if sources.is_mkv_source(path) or dvd.is_title(path):
                start = 0.0          # these seek on their own timeline; m2ts clocks start elsewhere
            probe['sampled_kbps'] = preview.sample_bitrate(path, track, 0, 'video', at=start + at,
                                                           share=at / length if length else 0.0)
        return probe

    def refresh_video_summary(self):
        """Card line for the video stream; frame rate, scan type and HDR follow from a quick probe."""
        playlist = self.playlist
        track = playlist.video_track if playlist is not None else None
        self.put(videoSummary=track_info.video_summary(track, None) if track is not None else '')
        if track is None or self.smoke or self.state['busy']:
            return
        keeper = self.app.preview_mounts

        def probe(cancel, progress):
            with keeper.use(playlist.path, playlist.iso_image) as path:
                return playlist, self.probe_video(path, playlist, track, False)
        self.video_probe.start(probe)

    def video_probed(self, result):
        playlist, probe = result
        if playlist is self.playlist and playlist.video_track is not None and probe:
            self.put(videoSummary=track_info.video_summary(playlist.video_track, probe))

    @Slot(str, int)
    def showTrackInfo(self, kind, row):
        """Fill the details sheet now from mkvmerge; ffprobe's decoder details follow in the background."""
        if kind not in ('audio', 'subtitle', 'video') or self.info_track(kind, row) is None:
            return
        self.info_target = (kind, row)
        self.info_probe.cancel()
        if self.state['busy'] or self.smoke:
            self.publish_info()             # don't touch the disc while a job runs (or in the offline smoke run)
            return
        self.publish_info(probing=True)
        playlist, track, keeper = self.playlist, self.info_track(kind, row), self.app.preview_mounts
        index = self.info_tracks(kind).index(track)

        def probe(cancel, progress):
            with keeper.use(playlist.path, playlist.iso_image) as path:
                if kind == 'video':
                    return self.probe_video(path, playlist, track, True)
                return preview.probe_stream(path, track, index, kind)
        self.info_probe.start(probe)

    def info_done(self, probe):
        if self.info_target is not None:
            self.publish_info(probe)

    def info_failed(self, exc):
        text = str(exc).strip()
        if self.info_target is not None:
            self.publish_info(error=text.splitlines()[-1] if text else '')

    @Slot(result=bool)
    def copyTrackInfo(self):
        text = self.state['trackInfo'].get('text', '')
        if text:
            QGuiApplication.clipboard().setText(text)
        return bool(text)

    @Slot(int)
    def selectPlaylist(self, index):
        if self.working or not 0 <= index < len(self.playlists):
            return
        preserved = {r['number']: (r['title'], r['origin']) for r in self.chapter_model.rows if r['title'].strip()}
        self.app.preview.stopPreview()
        self.app.preview.stop_waveform()
        self.playlist = self.playlists[index].playlist
        for i in range(len(self.playlist_model.rows)):
            self.playlist_model.change(i, chosen=i == index)
        self.put(canM2ts=self.m2ts_possible())
        if self.state['outputFormat'] == 'm2ts' and not self.state['canM2ts']:
            self.put(outputFormat='mkv')        # this source cannot be copied as M2TS; the setting stays as it is
        self.audio = self.default_audio()
        if self.state['outputFormat'] == 'm2ts':
            # A copy of the disc keeps every sound and subtitle track unless some are taken out.
            self.populate_tracks([t.track_id for t in self.playlist.audio_tracks],
                                 [t.track_id for t in self.playlist.subtitle_tracks])
        else:
            self.populate_tracks([self.audio.track_id] if self.audio else [], [])
        self.chapters = [models.Chapter(i, 0) for i in range(1, self.playlist.chapter_count + 1)]
        self.source_chapters = None
        self.put(chaptersEdited=False)
        self.rebuild_chapters({i: value[0] for i, value in preserved.items()})
        for i, row in enumerate(self.chapter_model.rows):
            if row['number'] in preserved:
                self.chapter_model.change(i, origin=preserved[row['number']][1])
        playlist = self.playlist
        language = self.cfg.get('chapter_language') or 'eng'
        self.source_size = None
        def work(progress):
            with self.app.preview_mounts.use(playlist.path, playlist.iso_image, direct=playlist.by_engine) as path:
                # The engine's scan brought the marks along: nothing to read for them.
                return (chapter_marks.playlist_chapters(playlist) if playlist.by_engine and playlist.marks
                        else chapter_marks.read_chapters_from_source(path, preferred_language=language),
                        space.source_size_bytes(path),
                        # Measured for the chosen playlist only (a scan reads hundreds of them).
                        sources.audio_bitrates(playlist, path) if not playlist.measured else {})
        def done(result):
            chapters, self.source_size, rates = result
            sources.apply_bitrates(playlist, rates)
            playlist.measured = True
            self.refresh_stream_texts()
            self.chapters = chapters or self.chapters
            # The last chapter "runs to the end of the file"; give it a real length for display and matching.
            if self.chapters and self.chapters[-1].end_seconds is None and playlist.duration_seconds:
                last = self.chapters[-1]
                if playlist.duration_seconds > last.start_seconds:
                    last.end_seconds = playlist.duration_seconds
            self.source_chapters = [replace(c) for c in self.chapters]
            self.rebuild_chapters({i: value[0] for i, value in preserved.items()})
            for i, row in enumerate(self.chapter_model.rows):
                if row['number'] in preserved:
                    self.chapter_model.change(i, origin=preserved[row['number']][1])
            self.app.preview.start_waveform()
            self.app.metadata.search_when_due()
            if any(c.embedded_name for c in chapters):
                # The disc has its own chapter names: "Get titles" starts there, but nothing opens by itself.
                self.app.names.offer_disc_titles()
        self.task(work, done, label='reading')

    # ------------------------------------------------------------ what is chosen (the export reads these)
    def titles(self) -> dict[int, str]:
        """Chapter number -> title, for the chapters that have one."""
        return {r['number']: r['title'] for r in self.chapter_model.rows if r['title'].strip()}

    def included_numbers(self) -> list[int]:
        """The chapters ticked for export, in order."""
        return [r['number'] for r in self.chapter_model.rows if r['included']]

    def selected_ids(self, kind) -> list[int]:
        """Track IDs of the ticked audio ("audio") or subtitle tracks."""
        return [t.track_id for t in self.selected_tracks(kind)]

    def restore_job(self, playlist, audio, source_size, manifest):
        """Put a checkpointed export back on screen: its playlist, tracks, chapters, titles and ticks."""
        self.playlist, self.audio, self.source_size = playlist, audio, source_size
        # The playlist cards and the scanned disc follow the job, so picking another playlist or
        # rescanning afterwards behaves as after a scan of this disc.
        key = (str(playlist.path), str(playlist.iso_image or ''))
        index = next((i for i, s in enumerate(self.playlists)
                      if (str(s.playlist.path), str(s.playlist.iso_image or '')) == key), None)
        if index is None:
            self.playlists = sources.score_playlists([playlist])
            self.playlist_model.replace([self.playlist_card(s) for s in self.playlists])
            index = 0
        else:
            self.playlists[index] = replace(self.playlists[index], playlist=playlist)
        for i in range(len(self.playlist_model.rows)):
            self.playlist_model.change(i, chosen=i == index)
        self.scanned_source = str(Path(self.state['source'])) if self.state['source'] else None
        self.put(outputFormat=manifest.container, canM2ts=self.m2ts_possible())
        self.populate_tracks(manifest.audio_track_ids or [manifest.audio_track_id], manifest.subtitle_track_ids,
                             keep_video=manifest.video_track_id is not None)
        fields = {'index', 'start_seconds', 'end_seconds', 'name'}
        self.chapters = ([models.Chapter(**{k: v for k, v in row.items() if k in fields}) for row in manifest.chapters]
                         or [models.Chapter(i, 0) for i in range(1, playlist.chapter_count + 1)])
        self.source_chapters = None
        self.put(chaptersEdited=False)
        self.rebuild_chapters({int(k): v for k, v in manifest.track_names.items()}, manifest.chapter_indices)

    # ------------------------------------------------------------ chapter editing
    def edited_layout(self):
        """Edited chapter start times for the export, or None when the source's chapters are used as they are."""
        if self.source_chapters is None or chapter_marks.same_layout(self.chapters, self.source_chapters):
            return None
        return chapter_marks.chapter_layout(self.chapters)

    def carried_rows(self):
        return [dict(title=r['title'], origin=r['origin'], included=r['included'], artist=r['artist'])
                for r in self.chapter_model.rows]

    def edit_chapters(self, chapters, rows):
        """Swap in an edited chapter list; rows holds the title / origin / tick / artist for each new chapter."""
        self.app.preview.stopPreview()
        if self.source_chapters is None:
            self.source_chapters = [replace(c) for c in self.chapters]
        self.chapters = chapters
        self.app.metadata.set_track_artists({c.index: r['artist'] for c, r in zip(chapters, rows)})
        self.rebuild_chapters({c.index: r['title'] for c, r in zip(chapters, rows) if r['title'].strip()},
                              [c.index for c, r in zip(chapters, rows) if r['included']])
        for i, r in enumerate(rows):
            if r['origin']:
                self.chapter_model.change(i, origin=r['origin'])
        self.put(chaptersEdited=self.edited_layout() is not None)
        self.app.metadata.publish_metadata()

    def can_edit(self, row, need_next=False):
        if self.state['busy'] or not 0 <= row < len(self.chapters) or len(self.chapters) != len(self.chapter_model.rows):
            return False
        return not need_next or row + 1 < len(self.chapters)

    @Slot(int)
    def mergeChapterWithNext(self, row):
        """Join a chapter and the one after it into one song (keeps the first title, else the second)."""
        if not self.can_edit(row, need_next=True):
            return
        rows = self.carried_rows()
        a, b = rows[row], rows[row + 1]
        named = a if a['title'].strip() else b
        merged = dict(title=named['title'], origin=named['origin'], included=a['included'] or b['included'],
                      artist=a['artist'] or b['artist'])
        self.edit_chapters(chapter_marks.merge_chapters(self.chapters, row), rows[:row] + [merged] + rows[row + 2:])

    @Slot(int, float)
    def splitChapter(self, row, offset):
        """Cut a chapter in two, offset seconds after its start; the second part starts unnamed."""
        if not self.can_edit(row):
            return
        try:
            chapters = chapter_marks.split_chapter(self.chapters, row, self.chapters[row].start_seconds + offset)
        except ValueError:
            self.notify(self.tr('splitTooClose'), 'chapterEdit')
            return
        rows = self.carried_rows()
        second = dict(title='', origin='', included=rows[row]['included'], artist='')
        self.edit_chapters(chapters, rows[:row + 1] + [second] + rows[row + 1:])

    @Slot(int, float)
    def nudgeChapterStart(self, row, delta):
        """Move the boundary before a chapter by delta seconds (the previous chapter's end moves with it)."""
        if not self.can_edit(row) or row == 0:
            return
        try:
            chapters = chapter_marks.move_chapter_start(self.chapters, row, self.chapters[row].start_seconds + delta)
        except ValueError:
            self.notify(self.tr('splitTooClose'), 'chapterEdit')
            return
        self.edit_chapters(chapters, self.carried_rows())

    @Slot()
    def restoreChapters(self):
        """Back to the source's own chapters; titles stay on chapters that start at the same moment."""
        if self.state['busy'] or self.source_chapters is None:
            return
        current = {round(c.start_seconds, 3): r for c, r in zip(self.chapters, self.carried_rows())}
        blank = dict(title='', origin='', included=False, artist='')
        source = [replace(c) for c in self.source_chapters]
        self.edit_chapters(source, [current.get(round(c.start_seconds, 3), blank) for c in source])

    def update_unnamed(self):
        rows = [i for i, r in enumerate(self.chapter_model.rows) if not str(r.get('title') or '').strip()]
        if rows != self.state.get('unnamedRows'):
            self.put(unnamedRows=rows)
        # The title-source column only says something when the titles come from more than one place.
        mixed = len({r.get('origin') for r in self.chapter_model.rows if r.get('origin')}) > 1
        if mixed != self.state.get('originsMixed'):
            self.put(originsMixed=mixed)

    def rebuild_chapters(self, names=None, chapter_indices=None):
        names = names or {}
        selected = set(chapter_indices) if chapter_indices is not None else None
        total = max([self.playlist.duration_seconds or 0 if self.playlist else 0]
                    + [c.end_seconds or c.start_seconds for c in self.chapters])
        long = total >= 3600
        # The timeline's scale, and each chapter's [start, length] as the chapter list shows them
        self.put(longClock=long, timelineSeconds=total,
                 timelineChapters=[[c.start_seconds, max(1, c.duration or 1)] for c in self.chapters])
        self.chapter_model.replace([dict(number=c.index, title=names.get(c.index, ''), origin='',
            duration=logic.format_time(c.duration), seconds=max(1, c.duration or 1),
            start=logic.format_clock(c.start_seconds, long), begin=c.start_seconds, status='pending', file='',
            included=selected is not None and c.index in selected, verify='', verifyText='',
            artist=self.app.metadata.track_artist(c.index)) for c in self.chapters])
        self.update_chapter_selection()

    def populate_tracks(self, audio_ids, subtitle_ids, keep_video=True):
        lang = self.cfg.get('language', 'zh')
        self.audio_model.replace([dict(label=t.display_label, codec=t.codec,
            details=t.display_label.removeprefix(t.codec).lstrip(' -'), chosen=t.track_id in audio_ids,
            **track_info.audio_card(t, lang, self.tr)) for t in self.playlist.audio_tracks])
        self.subtitle_model.replace([dict(label=' · '.join(filter(None, (t.codec, t.language, t.title))),
            chosen=t.track_id in subtitle_ids, **track_info.subtitle_card(t, lang, self.tr))
            for t in self.playlist.subtitle_tracks])
        has_video = self.playlist.video_track is not None
        self.put(hasVideo=has_video, keepVideo=has_video and keep_video)
        self.update_recommended_audio()
        self.refresh_video_summary()
        self.update_track_selection()

    def update_track_selection(self):
        self.put(audioSelected=sum(r['chosen'] for r in self.audio_model.rows),
                 subtitleSelected=sum(r['chosen'] for r in self.subtitle_model.rows))
        self.refresh_insights()

    def m2ts_possible(self) -> bool:
        """M2TS copies a Blu-ray as the disc has it: only a Blu-ray read by the built-in engine."""
        playlist = self.playlist
        return playlist is not None and playlist.by_engine and not dvd.is_title(playlist.path)

    @Slot(str)
    def setOutputFormat(self, output_format):
        if self.state['busy'] or output_format not in self.FORMATS:
            return
        if output_format == 'm2ts' and self.playlist is not None and not self.m2ts_possible():
            return
        self.app.set_config(output_container=output_format)
        previous = self.state['outputFormat']
        self.put(outputFormat=output_format)
        if output_format != 'flac':         # video mode always carries the picture when the disc has one
            self.put(keepVideo=self.state['hasVideo'])
        if output_format == 'm2ts' and previous != 'm2ts' and self.playlist is not None:
            for i in range(len(self.audio_model.rows)):
                self.audio_model.change(i, chosen=True)
            for i in range(len(self.subtitle_model.rows)):
                self.subtitle_model.change(i, chosen=True)
            self.update_track_selection()
        self.refresh_insights()
        self.app.preview.restart_preview()
        self.update_recommended_audio()
        if output_format == 'flac' and previous != 'flac' and self.playlist is not None:
            # Sound only starts from the same track as when the playlist is picked in FLAC mode, not from
            # whichever track was ticked last in a video mode.
            default = self.default_audio()
            if default is not None:
                self.selectAudio(self.playlist.audio_tracks.index(default))

    def default_audio(self):
        """The audio track ticked to begin with: the lossless stereo mix for FLAC, else the best track."""
        if self.playlist is None:
            return None
        if self.state['outputFormat'] == 'flac':
            return self.playlist.best_music_track()
        return self.playlist.best_default_audio_track()

    def update_recommended_audio(self):
        """The track card marked "Recommended" is the one the current format starts from."""
        default = self.default_audio()
        self.put(audioRecommended=self.playlist.audio_tracks.index(default) if default is not None else -1)

    @Slot(bool)
    def setKeepVideo(self, enabled):
        if not self.state['busy'] and self.state['hasVideo']:
            self.put(keepVideo=enabled)
            self.app.preview.restart_preview()
            self.refresh_insights()

    def update_chapter_selection(self):
        self.put(chapterSelected=sum(r['included'] for r in self.chapter_model.rows))
        self.refresh_insights()

    @Slot(int, bool)
    def setChapterIncluded(self, row, checked):
        if not self.state['busy']:
            self.chapter_model.change(row, included=checked)
            self.update_chapter_selection()

    @Slot(bool)
    def setAllChapters(self, checked):
        if not self.state['busy']:
            for i in range(len(self.chapter_model.rows)):
                self.chapter_model.change(i, included=checked)
            self.update_chapter_selection()

    @Slot()
    def selectRenamedChapters(self):
        """Select exactly the chapters given a title (typed or applied), not plain disc names."""
        if not self.state['busy']:
            for i, row in enumerate(self.chapter_model.rows):
                renamed = bool(row['title'].strip()) and row['origin'] != 'disc'
                self.chapter_model.change(i, included=renamed)
            self.update_chapter_selection()

    @Slot()
    def unselectUnnamedChapters(self):
        if not self.state['busy']:
            for i in self.state['unnamedRows']:
                self.chapter_model.change(i, included=False)
            self.update_chapter_selection()

    @Slot(int)
    def selectAudio(self, row):
        if self.state['busy'] or self.playlist is None or not 0 <= row < len(self.audio_model.rows):
            return
        single = self.state['outputFormat'] == 'flac'
        chosen = single or not self.audio_model.rows[row]['chosen']
        if single:
            for i in range(len(self.audio_model.rows)):
                self.audio_model.change(i, chosen=i == row)
        else:
            self.audio_model.change(row, chosen=chosen)
        tracks = self.playlist.audio_tracks
        self.audio = tracks[row] if chosen else next(
            (t for t, r in zip(tracks, self.audio_model.rows) if r['chosen']), None)
        self.update_track_selection()

    @Slot(int)
    def selectSubtitle(self, row):
        if not self.state['busy'] and 0 <= row < len(self.subtitle_model.rows):
            self.subtitle_model.change(row, chosen=not self.subtitle_model.rows[row]['chosen'])
            self.update_track_selection()

    def refresh_insights(self):
        """The workspace's side information: export estimate, disc overview, music / talk per chapter."""
        self.put(exportEstimate=self.export_estimate(), sourceSummary=self.source_summary(),
                 chapterKinds=self.chapter_kind_map(), chapterKindsManual=sorted(self.manual_kinds()),
                 videoExtra=track_info.video_extra(self.playlist, self.source_size, self.tr)
                 if self.playlist is not None and self.playlist.video_track is not None else '')

    def refresh_stream_texts(self):
        """Card texts name languages, so they follow the interface language."""
        if self.playlist is None:
            return
        lang = self.cfg.get('language', 'zh')
        for i, t in enumerate(self.playlist.audio_tracks[:len(self.audio_model.rows)]):
            self.audio_model.change(i, label=t.display_label, details=t.display_label.removeprefix(t.codec).lstrip(' -'),
                                    **track_info.audio_card(t, lang, self.tr))
        for i, t in enumerate(self.playlist.subtitle_tracks[:len(self.subtitle_model.rows)]):
            self.subtitle_model.change(i, **track_info.subtitle_card(t, lang, self.tr))
        self.refresh_insights()

    def selected_tracks(self, kind):
        if self.playlist is None:
            return []
        tracks, model = ((self.playlist.audio_tracks, self.audio_model) if kind == 'audio'
                         else (self.playlist.subtitle_tracks, self.subtitle_model))
        return [t for t, row in zip(tracks, model.rows) if row['chosen']]

    def export_estimate(self):
        playlist = self.playlist
        if playlist is None or not self.chapters:
            return {}
        included = {r['number'] for r in self.chapter_model.rows if r['included']}
        chapters = [c for c in self.chapters if c.index in included]
        # Until the disc's chapter times are read every chapter is a placeholder at 0:00 with no end.
        timed = len(self.chapters) < 2 or any(c.start_seconds > 0 for c in self.chapters)
        end = lambda c: c.end_seconds if c.end_seconds is not None else playlist.duration_seconds or c.start_seconds
        seconds = sum(max(0.0, end(c) - c.start_seconds) for c in chapters)
        container = self.state['outputFormat']
        audio = self.selected_tracks('audio')
        if container == 'flac':
            audio = audio[:1]
        keep_video = container != 'flac' and self.state['keepVideo']
        size = need = None
        if timed:
            size = space.estimate_output_bytes(playlist, chapters, audio_tracks=audio, keep_video=keep_video,
                                                   container=container, source_size=self.source_size)
            need = space.estimate_export_bytes(playlist, chapters, audio_track_ids=[t.track_id for t in audio],
                                                   keep_video=keep_video, container=container,
                                                   source_size=self.source_size)
            if need is None and size and dvd.is_title(playlist.path) and self.source_size:
                need = size + self.source_size      # the title is remuxed whole before it is cut
        folder = (logic.album_output(self.state['source'], self.state['output'])
                  if self.state['source'] and self.state['output'] else None)
        free = space.free_space_bytes(folder) if folder else None
        return dict(files=len(chapters), duration=logic.format_length(seconds) if chapters and timed else '',
                    size=logic.format_bytes(size) if size else '', free=logic.format_bytes(free) if free is not None else '',
                    drive=(folder.drive or folder.anchor) if folder else '',
                    enough=None if not chapters or need is None or free is None else need <= free,
                    folder=str(folder) if folder else '')

    def source_summary(self):
        """What the source is and how big, e.g. "Blu-ray ISO · 34.5 GB"; the rest of the playlist is on screen already."""
        playlist = self.playlist
        if playlist is None:
            return ''
        source = Path(self.state['source'] or '.')
        dvd_title = dvd.title_of(playlist.path)
        is_image = bluray_iso.is_iso(source)
        if dvd_title is not None:
            kind = 'ovDvdIso' if is_image else 'ovDvdFolder'
        elif playlist.iso_image is not None or is_image:
            kind = 'ovBdIso'
        elif playlist.path.suffix.lower() == '.mpls':
            kind = 'ovBdFolder'
        elif playlist.path.suffix.lower() in engine.TS_SUFFIXES:
            kind = 'ovM2ts'
        else:
            kind = 'ovMkv'
        size = None
        try:
            size = source.stat().st_size if source.is_file() else self.source_size
        except OSError:
            pass
        return self.tr(kind) + (f' · {logic.format_bytes(size)}' if size else '')

    # ------------------------------------------------------------ music / talk, set by hand
    # Overrides are filed under the chapter's start time, so they stay with the right chapter when
    # others are split or merged; another disc or playlist starts with none.
    def kind_overrides(self) -> dict:
        key = (self.state['source'], str(self.playlist.path) if self.playlist is not None else None)
        if self._kind_key != key:
            self._kind_key, self._kind_overrides = key, {}
        return self._kind_overrides

    def manual_kinds(self) -> dict[int, str]:
        """Chapter number -> kind chosen by hand."""
        overrides = self.kind_overrides()
        return {c.index: overrides[round(c.start_seconds, 2)] for c in self.chapters
                if round(c.start_seconds, 2) in overrides}

    def with_manual_kinds(self, kinds: dict) -> dict:
        """Detected kinds (chapter number -> kind) with the hand-set ones on top."""
        return {**kinds, **self.manual_kinds()}

    def chapter_kind_map(self):
        if not self.chapters:
            return {}
        kinds = {}
        if self.state['waveState'] == 'ready' and self.app.preview.waveform:
            kinds = setlist.chapter_kinds(self.chapters, self.app.preview.waveform, preview.DISC_PER_SECOND,
                                          self.app.preview.ripple)
        return {str(number): kind for number, kind in self.with_manual_kinds(kinds).items()}

    @Slot(int, str)
    def setChapterKind(self, row, kind):
        """Mark a chapter as music or talk by hand ("" goes back to what the outline says)."""
        if not 0 <= row < len(self.chapters):
            return
        start = round(self.chapters[row].start_seconds, 2)
        if kind in ('music', 'interlude', 'talk'):
            self.kind_overrides()[start] = kind
        else:
            self.kind_overrides().pop(start, None)
        self.put(chapterKinds=self.chapter_kind_map(), chapterKindsManual=sorted(self.manual_kinds()))

    @Slot(int)
    def openRecent(self, row):
        rows = self.state['recentExports']
        if 0 <= row < len(rows) and Path(rows[row]['folder']).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(rows[row]['folder']))
        elif 0 <= row < len(rows):
            self.notify(self.tr('recentGone'))

    @Slot(int)
    def reloadRecent(self, row):
        rows = self.state['recentExports']
        if 0 <= row < len(rows) and rows[row]['canReload'] and not self.working:
            self.setSource(rows[row]['source'])

    @Slot(str, bool)
    def setAllTracks(self, kind, checked):
        if (self.state['busy'] or self.state['outputFormat'] == 'flac'
                or not self.playlist or kind not in ('audio', 'subtitle')):
            return
        model = self.audio_model if kind == 'audio' else self.subtitle_model
        for i in range(len(model.rows)):
            model.change(i, chosen=checked)
        if kind == 'audio':
            self.audio = self.playlist.best_default_audio_track() if checked else None
        self.update_track_selection()

    @Slot(int, str)
    def editTitle(self, row, title):
        if not self.state['busy']:
            number = self.chapter_model.rows[row]['number'] if 0 <= row < len(self.chapter_model.rows) else None
            origin = 'disc' if title and self.disc_baselines.get(number) == title else 'edited'
            self.chapter_model.change(row, title=title, origin=origin)

    @Slot(int, str, str)
    def restoreTitle(self, row, title, origin):
        """Esc in a title field: put back the title (and where it came from) as it was before editing."""
        if not self.state['busy'] and 0 <= row < len(self.chapter_model.rows):
            self.chapter_model.change(row, title=title, origin=origin)
