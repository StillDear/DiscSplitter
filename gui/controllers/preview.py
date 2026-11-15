"""Listening to chapters (audio or video clips rendered on demand) and the loudness outlines
on the timeline and the preview bar."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading

from PySide6.QtCore import QObject, Property, QRunnable, QUrl, Signal, Slot

from core import jobs, models, preview
from .. import settings
from ..background import SideJob
from ..preview_session import PreviewSession, State as PreviewState
from .base import Controller


class PreviewSignals(QObject):
    done = Signal(int, str)
    failed = Signal(int, str)


class PreviewWorker(QRunnable):
    """Renders one chapter preview off the GUI thread; never marks the app busy."""
    def __init__(self, number, fn):
        super().__init__()
        self.number, self.fn = number, fn
        self.signals = PreviewSignals()

    def run(self):
        try:
            self.signals.done.emit(self.number, str(self.fn()))
        except jobs.JobCancelled:
            pass
        except Exception as exc:
            self.signals.failed.emit(self.number, str(exc))


class PreviewController(Controller):
    """Listening to chapters (audio or video clips rendered on demand) and the loudness outlines
    on the timeline and the preview bar."""

    waveChanged = Signal()
    previewWaveChanged = Signal()

    def __init__(self, app):
        super().__init__(app, previewRow=-1, previewAudio=-1, previewUrl='', previewLoading=False, previewError='',
                         previewTitle='', previewTrack='', previewTracks=[], previewVideo=False,
                         waveState='off', waveProgress=0)
        self._wave = []
        self.ripple = []        # level swing per outline step (see preview._ripple)
        self._preview_wave = []
        self.wave_job = SideJob(self, self.wave_done, self.wave_failed, self.wave_progress)
        self.preview_session = PreviewSession()     # off / loading / ready / error, and its renders

    # ------------------------------------------------------------ audio preview
    def preview_track_row(self, audio_row):
        rows = self.disc.audio_model.rows
        if 0 <= audio_row < len(rows):
            return audio_row
        if 0 <= self.state['previewAudio'] < len(rows):
            return self.state['previewAudio']
        chosen = [i for i, r in enumerate(rows) if r['chosen']]
        if chosen:
            return chosen[0]
        if self.disc.playlist is not None and self.disc.audio in self.disc.playlist.audio_tracks:
            return self.disc.playlist.audio_tracks.index(self.disc.audio)
        return 0 if rows else -1

    def preview_job(self, row, audio_row):
        """Everything needed to render one chapter with one track, or None."""
        playlist = self.disc.playlist
        if playlist is None or not playlist.audio_tracks or not 0 <= row < len(self.disc.chapter_model.rows):
            return None
        audio_row = self.preview_track_row(audio_row)
        track = playlist.audio_tracks[audio_row]
        number = self.disc.chapter_model.rows[row]['number']
        chapter = next((c for c in self.disc.chapters if c.index == number), None)
        if chapter is None:
            return None
        key = hashlib.sha1(f'{playlist.iso_image}|{playlist.path}'.encode('utf-8')).hexdigest()[:10]
        video = playlist.video_track if self.preview_wants_video() else None
        end = chapter.end_seconds if chapter.end_seconds is not None else playlist.duration_seconds
        quick = self.preview_session.listen
        if quick:     # telling a song from talk needs only the opening: starts in a couple of seconds
            end = min(end, chapter.start_seconds + self.QUICK_LISTEN) if end is not None else chapter.start_seconds + self.QUICK_LISTEN
        suffix = '-v.mkv' if video else '-q.flac' if quick else '.flac'
        return dict(row=row, audio_row=audio_row, track=track, number=number, playlist=playlist, video=video,
                    start=chapter.start_seconds, end=end,
                    target=self.app.preview_dir / f'{key}-{number:03d}-{round(chapter.start_seconds * 1000)}'
                                              f'-{round((end or 0) * 1000)}-{track.track_id}{suffix}')

    QUICK_LISTEN = 120

    def preview_wants_video(self):
        if self.preview_session.listen:     # quick listening from the paste dialog: sound only
            return False
        return (self.state['outputFormat'] == 'mkv' and self.state['keepVideo']
                and self.disc.playlist is not None and self.disc.playlist.video_track is not None)

    # Clips kept in the scratch folder: video is about 1 GB per 5 minutes, lossless audio tens of MB per song.
    KEEP_CLIPS = {'*-v.mkv': 3, '*.flac': 12}

    def prune_clips(self, keep):
        """Keep only the newest few clips of each kind (never the one playing or one still rendering)."""
        busy = {keep, self.preview_session.wanted, *self.preview_session.renders}
        for pattern, count in self.KEEP_CLIPS.items():
            clips = []
            for clip in self.app.preview_dir.glob(pattern):
                try:
                    clips.append((clip.stat().st_mtime, clip))
                except OSError:
                    pass
            for _, clip in sorted(clips, reverse=True)[count:]:
                if str(clip) not in busy and '.partial' not in clip.name:
                    try:
                        clip.unlink(missing_ok=True)
                        clip.with_suffix('.json').unlink(missing_ok=True)
                    except OSError:
                        pass        # still open in the player: the next round takes it

    def clip_wave(self, target):
        try:
            return json.loads(Path(target).with_suffix('.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []

    def start_render(self, job):
        target = str(job['target'])
        if self.preview_session.rendering(target) or job['target'].is_file():
            return
        playlist, track, keeper = job['playlist'], job['track'], self.app.preview_mounts
        audio_index = playlist.audio_tracks.index(track)
        video = job['video']
        cancel = None     # set by make_worker below, before the render can run

        def render():
            if cancel.is_set():
                raise jobs.JobCancelled('Preview cancelled')
            with keeper.use(playlist.path, playlist.iso_image) as path:
                if video is not None:
                    clip = preview.render_video(path, track, audio_index, video, job['start'], job['end'],
                                                job['target'], cancel)
                else:
                    clip = preview.render(path, track, audio_index, job['start'], job['end'], job['target'], cancel)
            try:   # loudness outline for the preview bar; a failure here never blocks playback
                job['target'].with_suffix('.json').write_text(json.dumps(preview.clip_peaks(clip)), encoding='utf-8')
            except Exception:
                pass
            return clip

        def make_worker(serial, event):
            nonlocal cancel
            cancel = event
            worker = PreviewWorker(serial, render)
            worker.signals.done.connect(self.preview_done)
            worker.signals.failed.connect(self.preview_failed)
            return worker
        self.app.pool.start(self.preview_session.begin_render(target, make_worker))

    def prefetch_next(self):
        """Decode the following chapter in the background so "next" starts at once (audio only: video clips are big)."""
        job = self.preview_job(self.state['previewRow'] + 1, self.state['previewAudio'])
        if job is not None and job['video'] is None and not self.preview_session.renders:
            self.start_render(job)

    def publish_preview(self, **values):
        """Mirror the session into the fields QML reads (previewRow -1 means off)."""
        session = self.preview_session
        if not session.active:
            values.update(previewRow=-1, previewUrl='')
        self.put(previewLoading=session.state is PreviewState.LOADING, previewError=session.error, **values)

    # ------------------------------------------------------------ waveforms
    WAVE_CACHE = settings.SETTINGS_PATH.parent / 'waveforms'

    @Property('QVariantList', notify=waveChanged)
    def waveform(self):
        return self._wave

    @Property('QVariantList', notify=previewWaveChanged)
    def previewWave(self):
        return self._preview_wave

    def set_preview_wave(self, peaks):
        self._preview_wave = list(peaks or [])
        self.previewWaveChanged.emit()

    def wave_key(self, playlist, track):
        source = Path(playlist.iso_image or self.state['source'] or '.')
        try:
            stamp = source.stat()
            ident = f'{stamp.st_size}-{int(stamp.st_mtime)}'
        except OSError:
            ident = ''
        # "r2": the cache holds the level ripple next to the peaks (music / interlude / talk)
        text = f'{source}|{playlist.path}|{track.track_id}|{ident}|{preview.DISC_PER_SECOND}|r2'
        return hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]

    def stop_waveform(self, clear=True):
        self.wave_job.cancel()
        if clear:
            self._wave, self.ripple = [], []
            self.waveChanged.emit()
            self.put(waveState='off', waveProgress=0)

    def show_waveform(self, peaks, ripple):
        self._wave, self.ripple = peaks, ripple
        self.waveChanged.emit()
        self.put(waveState='ready', waveProgress=100)
        self.disc.refresh_insights()

    def start_waveform(self):
        """Outline of the whole programme for the timeline, read once in the background and cached."""
        self.stop_waveform()
        playlist = self.disc.playlist
        if not self.cfg.get('waveform', True) or playlist is None or not playlist.audio_tracks or self.smoke:
            return
        track = self.disc.audio if self.disc.audio in playlist.audio_tracks else playlist.audio_tracks[0]
        cache = self.WAVE_CACHE / f'{self.wave_key(playlist, track)}.json'
        try:
            stored = json.loads(cache.read_text(encoding='utf-8'))
            self.show_waveform(stored['peaks'], stored.get('ripple') or [])
            return
        except (OSError, ValueError, KeyError, TypeError):
            pass
        total = playlist.duration_seconds or max((c.end_seconds or 0 for c in self.disc.chapters), default=0)
        keeper, index = self.app.preview_mounts, playlist.audio_tracks.index(track)
        self.put(waveState='computing', waveProgress=0)

        def scan(cancel, progress):
            with keeper.use(playlist.path, playlist.iso_image) as path:
                ripple = []
                peaks = preview.disc_peaks(path, track, index, total, progress, cancel, ripple)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(dict(peaks=peaks, ripple=ripple)), encoding='utf-8')
            self.trim_wave_cache(cache)
            return peaks, ripple
        self.wave_job.start(scan)

    WAVE_CACHE_KEEP = 200       # outlines kept on disk (about 100-300 KB each); the oldest go first

    @classmethod
    def trim_wave_cache(cls, keep):
        try:
            files = sorted(cls.WAVE_CACHE.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            for stale in files[cls.WAVE_CACHE_KEEP:]:
                if stale != keep:
                    stale.unlink(missing_ok=True)
        except OSError:
            pass

    def wave_progress(self, fraction):
        percent = int(fraction * 100)
        if percent != self.state['waveProgress']:
            self.put(waveProgress=percent)

    def wave_done(self, result):
        self.show_waveform(*result)

    def wave_failed(self, exc):
        self.put(waveState='failed')

    @Slot(int, int)
    def previewChapter(self, row, audio_row=-1):
        """Play one chapter with one audio track (-1: keep the current / first selected track)."""
        self.start_preview(row, audio_row, listen=False)

    @Slot(int)
    def listenChapter(self, row):
        """Hear a chapter without its picture (deciding whether it is a song or talk)."""
        self.start_preview(row, self.state['previewAudio'], listen=True)

    def start_preview(self, row, audio_row=-1, listen=False):
        if self.state['busy']:
            return
        session = self.preview_session
        previous, session.listen = session.listen, listen     # preview_job reads the mode
        job = self.preview_job(row, audio_row)
        if job is None:
            session.listen = previous
            return
        target, track = job['target'], job['track']
        title = self.disc.chapter_model.rows[row]['title'].strip() or models.default_title(job['number'])
        ready = target.is_file()
        session.want(str(target), ready)
        self.set_preview_wave(self.clip_wave(target) if ready else [])
        self.publish_preview(previewRow=row, previewAudio=job['audio_row'], previewTitle=f"{job['number']:02d} · {title}",
                             previewVideo=job['video'] is not None, previewTrack=track.display_label,
                             previewUrl=QUrl.fromLocalFile(str(target)).toString() if ready else '',
                             previewTracks=[t.codec + (f' {t.channel_layout}' if t.channel_layout else '')
                                            for t in job['playlist'].audio_tracks])
        if ready:
            self.prefetch_next()
        else:
            self.start_render(job)

    @Slot(int, str)
    def preview_done(self, number, path):
        session = self.preview_session
        target = session.end_render(number)
        if target is None or not session.active:
            return
        if session.arrived(target):
            self.set_preview_wave(self.clip_wave(path))
            self.publish_preview(previewUrl=QUrl.fromLocalFile(path).toString())
        self.prune_clips(path)
        self.prefetch_next()

    @Slot(int, str)
    def preview_failed(self, number, message):
        target = self.preview_session.end_render(number)
        if target is not None and self.preview_session.failed(
                target, message.strip().splitlines()[-1] if message.strip() else ''):
            self.publish_preview()

    def restart_preview(self):
        if self.preview_session.active and self.state['previewVideo'] != self.preview_wants_video():
            self.previewChapter(self.state['previewRow'], self.state['previewAudio'])

    @Slot(int)
    def previewStep(self, delta):
        row = self.state['previewRow'] + delta
        if self.preview_session.active and 0 <= row < len(self.disc.chapter_model.rows):
            self.previewChapter(row, self.state['previewAudio'])

    @Slot()
    def stopPreview(self):
        was_active = self.preview_session.active
        self.preview_session.stop()
        if was_active:
            self.publish_preview()
        # Eject a kept ISO in the background (PowerShell takes about a second); nothing to do without one.
        if self.app.preview_mounts.mounted:
            threading.Thread(target=self.app.preview_mounts.close, daemon=True).start()
