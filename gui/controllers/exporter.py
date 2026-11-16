"""The export: checkpoints and resuming, the questions before it starts, the running job,
checking the finished files, and the result."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import shutil

from PySide6.QtCore import QUrl, Slot
from PySide6.QtGui import QDesktopServices

from core import jobs, manifest as job_manifest, models, naming, pipeline, sources, space, verify
from .. import settings
from .. import logic
from ..export_flow import ExportFlow, Phase
from .base import Controller


class ExportController(Controller):
    """The export: checkpoints and resuming, the questions before it starts, the running job,
    checking the finished files, and the result."""

    def __init__(self, app):
        super().__init__(app, destination='', resume=False, resumeText='',
                         exportConfirmation='', collisionFiles=[], logs='', result='idle',
                         stage='extracting', current=0, chapterFraction=0.0, completed=0, failed=0, remaining=0,
                         verified=0, verifyIssues=0, verifyState='off')
        self.flow = ExportFlow()        # checkpoint, confirmations, running job, result
        self.log_path = None
        self.log_lines = deque(maxlen=800)     # the export log shown on the export screen
        self.verify_results = []

    # ------------------------------------------------------------ checking finished files
    def issue_text(self, issue):
        def length(value):
            try:
                seconds = float(value)
            except ValueError:
                return value
            return f"{int(seconds // 60):02d}:{seconds % 60:04.1f}"      # 04:57.0, like the table's 05:00
        expected, actual = issue.expected, issue.actual
        if issue.code == 'duration':
            expected, actual = length(expected), length(actual)
        return self.tr('verify' + issue.code.capitalize()).format(e=expected, a=actual)

    def apply_verification(self, results):
        self.verify_results = list(results)
        by_name = {r.path.name: r for r in results}
        for i, row in enumerate(self.disc.chapter_model.rows):
            result = by_name.get(row['file']) if row['included'] and row['file'] else None
            if result is None:
                self.disc.chapter_model.change(i, verify='', verifyText='')
            else:
                self.disc.chapter_model.change(i, verify='ok' if result.ok else 'warn',
                                          verifyText='\n'.join(self.issue_text(x) for x in result.issues))
        self.put(verifyState='done' if results else 'off', verified=sum(r.ok for r in results),
                 verifyIssues=sum(not r.ok for r in results))

    @Slot()
    def reexportFlagged(self):
        """Export again only the songs that failed the check; the other files are kept as they are."""
        if self.working or not self.verify_results or self.flow.output is None:
            return
        flagged = {r.path for r in self.verify_results if not r.ok}
        kept = {r.path for r in self.verify_results if r.ok}
        if not flagged or not self.flow.reset_stale():
            return
        self.refresh_resume(self.flow.output)
        if self.flow.manifest:
            return      # an unfinished job is resumed with Retry instead
        self.prepare_export(self.flow.output, self.disc.titles(), False, self.state['outputFormat'], overwrite_ok=flagged, skip_ok=kept)

    # ------------------------------------------------------------ recent exports
    RECENT_KEEP = 8

    def remember_export(self, count):
        """Add the finished job to the recent list (newest first, one entry per album folder)."""
        if count <= 0 or self.flow.output is None:
            return
        entry = dict(album=self.state['album'] or self.flow.output.name, artist=self.state['artist'],
                     count=count, folder=str(self.flow.output), source=self.state['source'],
                     container=self.state['outputFormat'], when=datetime.now().isoformat(timespec='minutes'))
        recent = [e for e in self.cfg.get('recent_exports') or [] if e.get('folder') != entry['folder']]
        self.app.set_config(recent_exports=[entry] + recent[:self.RECENT_KEEP - 1])
        self.app.publish_recent()

    def refresh_resume(self, output=None):
        output = output or logic.album_output(self.state['source'], self.state['output'])
        self.flow.manifest = logic.resumable_job(output)
        manifest = self.flow.manifest
        self.put(destination=str(output) if output else '', resume=bool(manifest), resumeText=(f'{Path(manifest.output_folder).name} · '
            f'{manifest.audio_track_label} · {len(manifest.completed_outputs)} / '
            f'{len(manifest.chapter_indices if manifest.chapter_indices is not None else manifest.chapters)}') if manifest else '')

    @Slot()
    def requestDiscard(self):
        if self.flow.manifest and not self.working:
            self.dialogRequested.emit('discard', self.tr('discardHint'))

    @Slot()
    def discard(self):
        if self.flow.manifest and not self.working:
            output = Path(self.flow.manifest.output_folder)
            target = logic.safe_work_folder(output)
            self.task(lambda p: shutil.rmtree(target) if target.exists() else None, lambda r: self.refresh_resume())

    @Slot()
    def resume(self):
        if not self.flow.manifest or self.working or not self.flow.reset_stale():
            return
        manifest = self.flow.manifest
        output = Path(manifest.output_folder)
        audio_ids = manifest.audio_track_ids or [manifest.audio_track_id]
        subtitle_ids = manifest.subtitle_track_ids
        def work(p):
            playlist_path = Path(manifest.source_playlist)
            image = Path(manifest.source_iso) if manifest.source_iso else None
            with self.app.preview_mounts.use(playlist_path, image, direct=manifest.track_numbers == 'engine') as path:
                # Read the way the job was checkpointed: its track IDs are PIDs (engine) or mkvmerge's numbers.
                playlist = sources.inspect_playlist(path, use_engine=manifest.track_numbers == 'engine')
                if not playlist.measured:
                    sources.apply_bitrates(playlist, sources.audio_bitrates(playlist, path))
                playlist.measured = True
                size = space.source_size_bytes(path)
            if image is not None:
                playlist = replace(playlist, path=playlist_path, iso_image=image)
            audio = next((t for t in playlist.audio_tracks if t.track_id == manifest.audio_track_id), None)
            if (audio is None or not set(audio_ids).issubset(t.track_id for t in playlist.audio_tracks)
                    or not set(subtitle_ids).issubset(t.track_id for t in playlist.subtitle_tracks)):
                raise ValueError(self.tr('noResumeTracks'))
            return playlist, audio, size
        def done(result):
            self.disc.restore_job(*result, manifest)
            self.prepare_export(output, self.disc.titles(), True, manifest.container)
        def failed(exc):
            self.flow.abort()
            self.report(exc)
        self.task(work, done, failed)

    @Slot()
    def startExport(self):
        if self.working or not self.flow.reset_stale():
            return
        if not self.disc.playlist or not self.disc.audio or not self.disc.playlist.chapter_count or not self.state['output']:
            self.notify(self.tr('noSelection'))
            return
        self.refresh_resume()
        if self.flow.manifest:
            self.flow.ask(Phase.CONFIRM_RESUME)
            self.dialogRequested.emit('resume', self.tr('resumeHint'))
            return
        if not self.state['chapterSelected']:
            self.notify(self.tr('noSelectedChapters'))
            return
        self.prepare_export(logic.album_output(self.state['source'], self.state['output']), self.disc.titles(), False,
                            self.state['outputFormat'])

    def prepare_export(self, output, names, resume, container, overwrite_ok=None, skip_ok=None):
        indices = self.disc.included_numbers()
        audio_ids, subtitle_ids = self.disc.selected_ids('audio'), self.disc.selected_ids('subtitle')
        keep_video = self.state['keepVideo']
        if container == 'flac':
            subtitle_ids = []
            keep_video = False
        plan = logic.collision_plan(output, len(self.disc.chapters), names, container,
                                    self.flow.manifest if resume else None, chapter_indices=indices,
                                    filename_template=self.filename_template(), metadata=self.app.metadata.export_metadata())
        if not self.flow.prepare(dict(output=output, names=names, resume=resume, container=container, plan=plan,
                                        indices=indices, audio_ids=audio_ids, subtitle_ids=subtitle_ids,
                                        keep_video=keep_video, layout=self.disc.edited_layout(),
                                        overwrite_ok=set(overwrite_ok or ()), skip_ok=set(skip_ok or ()))):
            return
        if container == 'flac':
            summary = self.tr('flacExportSummary').format(n=len(indices), a=len(audio_ids))
        else:
            summary = self.tr('exportSummary').format(n=len(indices), a=len(audio_ids), s=len(subtitle_ids), f=container.upper())
            if not keep_video:
                summary += ' · ' + self.tr('videoExcluded')
        self.put(exportConfirmation=summary)
        if plan.duplicates:
            self.flow.ask(Phase.CONFIRM_DUPLICATE)
            self.dialogRequested.emit('duplicate', self.tr('duplicate'))
        else:
            self.check_collisions()

    def tolerance(self):
        try:
            return float(self.cfg.get('duration_tolerance') or 20)
        except ValueError:
            return 20.0

    def filename_template(self):
        template = self.cfg.get('filename_template')
        return template if template in naming.FILENAME_TEMPLATES else 'title'

    @Slot()
    def check_collisions(self):
        """Answer to the duplicate-names question (or the step after preparing): look at existing files next."""
        pending = self.flow.pending
        if not pending:
            return
        colliding = pending['plan'].collisions
        policy = self.cfg.get('collision_policy')
        replace_ok, keep_ok = pending.get('overwrite_ok', set()), pending.get('skip_ok', set())
        if colliding and (replace_ok or keep_ok) and {p.path for p in colliding} <= replace_ok | keep_ok:
            # Re-exporting the files that failed the check: replace those, keep the rest as they are.
            paths = {p.path for p in colliding}
            self.launch_export(paths & replace_ok, paths & keep_ok)
        elif colliding and policy == 'overwrite':
            self.launch_export({p.path for p in colliding})
        elif colliding and policy == 'skip':
            self.skipExisting()
        elif colliding:
            self.flow.ask(Phase.CONFIRM_COLLISION)
            self.put(collisionFiles=[str(p.path) for p in colliding])
            self.dialogRequested.emit('collision', self.tr('collisionHint'))
        else:
            self.launch_export(set())

    @Slot()
    def approveOverwrite(self):
        if self.flow.pending:
            self.launch_export({p.path for p in self.flow.pending['plan'].collisions})

    @Slot()
    def skipExisting(self):
        """Keep the files already in the folder and export only the missing chapters."""
        if self.flow.pending:
            self.launch_export(set(), {p.path for p in self.flow.pending['plan'].collisions})

    @Slot()
    def cancelExport(self):
        """A question was dismissed without an answer."""
        self.flow.abort()

    @Slot()
    def fresh(self):
        if not self.flow.manifest or self.working:
            return
        target = logic.safe_work_folder(Path(self.flow.manifest.output_folder))
        # Still confirming: the old checkpoint goes, then the normal export flow starts over.
        self.task(lambda p: shutil.rmtree(target) if target.exists() else None, lambda r: self.startExport(),
                  lambda exc: self.flow.abort() or self.report(exc))

    # Logs live with the app's own data, never in the music library.
    LOG_DIR = settings.SETTINGS_PATH.parent / 'logs'

    LOG_KEEP = 50

    def new_log_path(self, output):
        folder = Path(self.LOG_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        old = sorted(folder.glob('*.log'))
        for stale in old[:max(0, len(old) - self.LOG_KEEP + 1)]:
            stale.unlink(missing_ok=True)
        name = ''.join('_' if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in output.name).strip(' .') or 'export'
        return folder / f"{datetime.now():%Y%m%d-%H%M%S} {name[:80]}.log"

    def space_needed(self, pending, overwrite, skip):
        """(needed, free) bytes when the target drive looks too small for this export, else None."""
        output = pending['output']
        skip = set(skip)
        # Files that stay as they are (kept, or finished by the run being resumed) are not written again.
        writes = {p.chapter.index for p in pending['plan'].items
                  if not (p.path in skip or (p.exists and p.path not in overwrite))}
        chapters = [c for c in self.disc.chapters if c.index in writes and c.index in set(pending['indices'])]
        needed = space.estimate_export_bytes(self.disc.playlist, chapters, audio_track_ids=pending['audio_ids'],
                                                 keep_video=pending['keep_video'], container=pending['container'],
                                                 source_size=self.disc.source_size)
        free = space.free_space_bytes(output)
        if needed is None or free is None or needed <= free:
            return None
        return needed, free

    @Slot()
    def exportDespiteSpace(self):
        pending = self.flow.pending
        if pending and 'space_args' in pending:
            self.launch_export(*pending['space_args'], space_checked=True)

    def launch_export(self, overwrite, skip=frozenset(), space_checked=False):
        if self.working:
            return
        pending = self.flow.pending
        if not space_checked and pending is not None and self.disc.playlist is not None:
            shortage = self.space_needed(pending, set(overwrite), skip)
            if shortage:
                pending['space_args'] = (set(overwrite), set(skip))
                self.flow.ask(Phase.CONFIRM_SPACE)
                needed, free = shortage
                self.dialogRequested.emit('diskSpace', self.tr('diskSpaceHint').format(
                    need=logic.format_bytes(needed), free=logic.format_bytes(free), folder=str(pending['output'])))
                return
        plan = self.flow.launch()
        if plan is None:
            return
        self.app.preview.stopPreview()
        self.app.preview.stop_waveform(clear=False)
        output = plan['output']
        self.log_path = self.new_log_path(output)
        self.log_lines.clear()
        self.app.put(page='export', pipeline=True)
        self.put(destination=str(output), logs='', stage='extracting', current=0, chapterFraction=0.0, completed=0,
                 failed=0, remaining=len(plan['indices']), result=self.flow.result)
        for i, row in enumerate(self.disc.chapter_model.rows):
            item = next((p for p in plan['plan'].items if p.chapter.index == row['number']), None)
            self.disc.chapter_model.change(i, status='pending', file=item.path.name if item else '')
        playlist, audio, cancel = self.disc.playlist, self.disc.audio, self.flow.cancel_event
        metadata = self.app.metadata.export_metadata()
        template = self.filename_template()
        keeper = self.app.preview_mounts
        log_path = self.log_path
        chapters = {c.index: replace(c) for c in self.disc.chapters}
        self.verify_results = []
        self.put(verifyState='off', verified=0, verifyIssues=0)
        def work(progress):
            keeper.close()   # release an ISO kept mounted for previews before the export mounts it
            output.mkdir(parents=True, exist_ok=True)
            results = pipeline.run_full_pipeline(playlist, audio, plan['names'],
                work_folder=output / '_work', output_folder=output, container=plan['container'],
                progress_cb=progress, overwrite=overwrite, cancel_event=cancel,
                resume=plan['resume'], log_path=log_path, metadata=metadata,
                chapter_indices=plan['indices'], audio_track_ids=plan['audio_ids'],
                subtitle_track_ids=plan['subtitle_ids'], keep_video=plan['keep_video'],
                filename_template=template, skip_existing=set(skip), chapter_layout=plan.get('layout'))
            return results, self.verify_files(plan, playlist, chapters, progress, log_path)
        if not self.task(work, lambda r: self.finish_export(None, *r), lambda exc: self.finish_export(exc, [])):
            self.finish_export(RuntimeError('Another job is still running.'), [])   # not expected: busy was checked above

    @staticmethod
    def verify_files(plan, playlist, chapters, progress, log_path=None):
        """Read every finished file back (worker thread): length, streams and title against the plan."""
        audio_tracks = [t for t in playlist.audio_tracks if t.track_id in plan['audio_ids']]
        keep_video = plan['keep_video'] and plan['container'] != 'flac' and playlist.video_track is not None
        # An M2TS copies the picture as the disc plays it, a Dolby Vision enhancement layer included.
        video_count = len(playlist.picture_tracks) if plan['container'] == 'm2ts' else 1
        items = [p for p in plan['plan'].items if p.chapter.index in chapters]
        progress(jobs.ProgressEvent(f'Checking {len(items)} file(s)', stage='verifying'))
        results = []
        for item in items:
            chapter = chapters[item.chapter.index]
            title = plan['names'].get(chapter.index, '').strip() or models.default_title(chapter.index)
            result = verify.verify_output(item.path, chapter, container=plan['container'], audio_tracks=audio_tracks,
                                             subtitle_count=len(plan['subtitle_ids']) if plan['container'] != 'flac' else 0,
                                             keep_video=keep_video, title=title, video_count=video_count)
            results.append(result)
            line = f'Check {item.path.name}: ' + ('OK' if result.ok else '; '.join(
                f'{i.code} expected {i.expected!r} got {i.actual!r}' if i.expected or i.actual else i.code for i in result.issues))
            progress(line)
            if log_path:
                with Path(log_path).open('a', encoding='utf-8') as f:
                    f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}  {line}\n")
        return results

    @Slot(object)
    def progress(self, message):
        """One pipeline message: the log, the stage and the chapter rows, announced to QML once."""
        fraction = getattr(message, 'fraction', None)
        if fraction is not None:            # how far into the running chapter: the bar only, not the log
            if self.state['current'] == message.chapter:
                self.put(chapterFraction=fraction)
            return
        self.log_lines.append(str(message))
        update = dict(logs='\n'.join(self.log_lines))
        event = logic.progress_event(message)
        if event.stage:
            update['stage'] = event.stage
        if event.chapter:
            # A subsequent chapter begins only after the previous write succeeded.
            for i, row in enumerate(self.disc.chapter_model.rows):
                if row['status'] == 'running' and row['number'] != event.chapter:
                    self.disc.chapter_model.change(i, status='done')
                if row['number'] == event.chapter:
                    self.disc.chapter_model.change(i, status=event.status)
            if event.chapter != self.state['current']:
                update['chapterFraction'] = 0.0
            update['current'] = event.chapter
        elif event.status in ('failed', 'cancelled'):
            # The job stopped: the chapter being written did not finish (finish_export settles the rest).
            for i, row in enumerate(self.disc.chapter_model.rows):
                if row['status'] == 'running':
                    self.disc.chapter_model.change(i, status=event.status)
        if event.stage == 'cleanup':
            for i, row in enumerate(self.disc.chapter_model.rows):
                if row['included']:
                    self.disc.chapter_model.change(i, status='done')
        update['completed'] = sum(r['included'] and r['status'] == 'done' for r in self.disc.chapter_model.rows)
        self.put(**update)

    def finish_export(self, exc, results, verified=None):
        cancelled = isinstance(exc, jobs.JobCancelled)
        result = self.flow.finish(failed=exc is not None, cancelled=cancelled)
        if result is None:
            return
        manifest = job_manifest.read_manifest(self.flow.output / '_work')
        complete = {Path(p).name for p in manifest.completed_outputs} if manifest else {p.name for p in results}
        for i, row in enumerate(self.disc.chapter_model.rows):
            if not row['included']:
                continue
            stopped = row['status'] in ('running', 'failed')    # progress() may already have marked it
            status = 'done' if row['file'] in complete else ('cancelled' if cancelled else 'failed' if stopped else 'pending')
            self.disc.chapter_model.change(i, status=status)
        self.remember_export(sum(r['status'] == 'done' for r in self.disc.chapter_model.rows))
        # The outcome first, then the page: whatever watches the state (the taskbar, the finished notification)
        # must never see the job over while the result still says "running".
        self.put(result=result,
                 completed=sum(r['status'] == 'done' for r in self.disc.chapter_model.rows),
                 failed=sum(r['status'] == 'failed' for r in self.disc.chapter_model.rows),
                 remaining=sum(r['included'] and r['status'] in {'pending', 'cancelled'} for r in self.disc.chapter_model.rows))
        self.app.put(page='done', pipeline=False)
        self.apply_verification(verified or [])
        self.refresh_resume(self.flow.output)
        if exc and not cancelled:
            self.report(exc)

    @Slot()
    def cancel(self):
        if self.flow.cancel():
            self.put(result=self.flow.result)

    @Slot()
    def openLog(self):
        if self.log_path and self.log_path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path.resolve())))
        else:
            self.notify(self.tr('noLog'))

    @Slot()
    def openOutput(self):
        output = self.flow.output or logic.album_output(self.state['source'], self.state['output'])
        if output and output.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output.resolve())))
