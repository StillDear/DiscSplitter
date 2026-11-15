"""
The Qt bridge. Backend is what QML sees as `backend`: settings, the worker pool, dialogs, and the
app-wide state. Each area of the app is a controller hanging off it (backend.disc, .preview, .names,
.metadata, .exporter), with its own slots and its own slice of the UI state. All external-tool and
network calls run in QThreadPool workers.
"""
from __future__ import annotations

import atexit
from datetime import datetime
from pathlib import Path
import shutil
import tempfile
import threading
import time

from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from core import appinfo, engine, jobs, metadata_sources, naming, preview, tools
from . import settings
from . import logic
from .controllers.base import View, local_path
from .controllers.disc import DiscController
from .controllers.exporter import ExportController
from .controllers.metadata import MetadataController
from .controllers.names import NamesController
from .controllers.preview import PreviewController
from .i18n import CATALOGUES
from .models import Rows


class WorkerSignals(QObject):
    done = Signal(int, object)
    failed = Signal(int, object)
    progress = Signal(object)    # object, not str: Qt would turn an jobs.ProgressEvent into a plain string


class Worker(QRunnable):
    def __init__(self, number, fn):
        super().__init__()
        self.number, self.fn = number, fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.done.emit(self.number, self.fn(self.signals.progress.emit))
        except Exception as exc:
            self.signals.failed.emit(self.number, exc)


class Backend(View):
    changed = Signal()          # any slice of the state (QML binds to the slices; Python listeners use this)
    configChanged = Signal()    # settings (self.cfg)
    textsChanged = Signal()     # language
    dialogRequested = Signal(str, str)
    quitReady = Signal()

    def __init__(self, smoke=False):
        cfg = settings.load()
        super().__init__(None, page='start', returnPage='start', toolNames='', busy=False, working=False, pipeline=False, status='ready', toolMissing=False,
                         systemAccent='', systemScale=100, startScale=str(cfg.get('interface_scale', 'system')),
                         recentExports=[], netTest=[])
        self.smoke = smoke
        self.cfg = cfg
        self.pool = QThreadPool(self)
        self.jobs = {}
        self.serial = 0
        self.close_pending = False
        self.layout_saver = QTimer(self)        # splitter drags save once they settle
        self.layout_saver.setSingleShot(True)
        self.layout_saver.setInterval(400)
        self.layout_saver.timeout.connect(lambda: settings.save(self.cfg))
        # Shared by previews, track details and exports: one mounted disc image, one scratch folder.
        self.preview_mounts = preview.MountKeeper()
        atexit.register(self.preview_mounts.close)
        self.preview_dir = Path(tempfile.mkdtemp(prefix=self.PREVIEW_PREFIX))
        atexit.register(shutil.rmtree, self.preview_dir, True)
        if not smoke:
            threading.Thread(target=self.clear_stale_previews, args=(self.preview_dir,), daemon=True).start()
        self.tool_model = Rows(['tool', 'path', 'available', 'builtin', 'optional'], self)

        self._disc = DiscController(self)
        self._preview = PreviewController(self)
        self._names = NamesController(self)
        self._metadata = MetadataController(self)
        self._exporter = ExportController(self)
        self.views = (self, self._disc, self._preview, self._names, self._metadata, self._exporter)
        self._state = None              # the merged map behind `state`, rebuilt after any slice changes
        for view in self.views:
            view.viewChanged.connect(self._forget_state)
        self.view_of = {}               # state key -> the slice that holds it
        for view in self.views:
            for key in view.view:
                assert key not in self.view_of, f'state key {key!r} is in two slices'
                self.view_of[key] = view

        self.apply_tool_paths()
        self.apply_network()
        self.exporter.refresh_resume()
        self.publish_recent()
        if not smoke:
            QTimer.singleShot(100, self.checkTools)

    PREVIEW_PREFIX = 'discsplitter-preview-'
    STALE_PREVIEW_SECONDS = 2 * 24 * 3600

    @classmethod
    def clear_stale_previews(cls, keep):
        """Scratch folders a crashed run left behind (clips are large); a running copy's folder is recent."""
        now = time.time()
        for prefix in (cls.PREVIEW_PREFIX, 'dts-preview-'):
            for folder in Path(tempfile.gettempdir()).glob(prefix + '*'):
                try:
                    if folder != keep and folder.is_dir() and now - folder.stat().st_mtime > cls.STALE_PREVIEW_SECONDS:
                        shutil.rmtree(folder, ignore_errors=True)
                except OSError:
                    pass

    def quit(self):
        """Leave: background readers (waveform, preview renders) stop first, so no disc image stays in use."""
        self.preview.stop_waveform(clear=False)
        self.preview.preview_session.stop()
        self.quitReady.emit()

    # The controllers, the same names in Python and QML: backend.disc.selectAudio(...), backend.exporter.view.logs
    disc = Property(QObject, lambda self: self._disc, constant=True)
    preview = Property(QObject, lambda self: self._preview, constant=True)
    names = Property(QObject, lambda self: self._names, constant=True)
    metadata = Property(QObject, lambda self: self._metadata, constant=True)
    exporter = Property(QObject, lambda self: self._exporter, constant=True)

    @Property('QVariantMap', notify=changed)
    def state(self):
        """Every slice of the state in one read-only map, for Python callers. QML binds to the slices."""
        if self._state is None:
            self._state = {key: value for view in self.views for key, value in view.view.items()}
        return self._state

    def _forget_state(self):
        self._state = None

    def put(self, **values):
        """Update the state, wherever each key lives; each slice announces only a real change."""
        parts = {}
        for key, value in values.items():
            parts.setdefault(self.view_of[key], {})[key] = value
        if [view for view, part in parts.items() if view.update_view(part)]:
            self.changed.emit()

    @Property('QVariantMap', notify=configChanged)
    def config(self):
        return self.cfg

    @Property('QVariantMap', notify=textsChanged)
    def texts(self):
        return CATALOGUES.get(self.cfg.get('language'), CATALOGUES['zh'])

    def tr(self, key):
        return self.texts.get(key, key)

    def set_config(self, *, save=True, **values):
        """Change settings: saved to disk (unless save=False or in a smoke run), then announced."""
        self.cfg.update(values)
        if save and not self.smoke:
            settings.save(self.cfg)
        self.configChanged.emit()

    def apply_tool_paths(self):
        for tool in tools.TOOL_PATHS:
            tools.set_tool_path(tool, tools.default_tool_path(tool, self.cfg.get(tool + '_path', tool)))

    @property
    def working(self):
        """A job of either kind is under way (see task)."""
        return self.state['working']

    def task(self, fn, done, failed=None, label='ready', begin=None, blocking=True):
        """
        Run fn on the worker pool; one job at a time (idle -> working -> idle).

        blocking: the job reads the disc or decides what is on screen (scan, read chapters, export),
        so `busy` is set and nothing may be edited meanwhile. A job that only waits on the network
        or reads a screenshot passes blocking=False: `working` alone is set, so no second job can
        start, but titles, ticks and track choices stay editable while it runs.
        label: the title bar's status text while it runs, reset to "ready" when it ends.
        begin: state that says "this job is under way" (a spinner, a "running" badge). It is
        applied only if the job really starts, so a rejected job can never leave it stuck.
        Returns False when another job is running (nothing is changed then).
        """
        if self.working:
            return False
        self.serial += 1
        worker = Worker(self.serial, fn)
        self.jobs[self.serial] = (worker, done, failed)
        worker.signals.done.connect(self.task_done)
        worker.signals.failed.connect(self.task_failed)
        worker.signals.progress.connect(self.exporter.progress)
        # Results are queued to this thread, so they cannot arrive before this put.
        self.put(busy=blocking, working=True, status=label, **(begin or {}))
        self.pool.start(worker)
        return True

    @Slot(int, object)
    def task_done(self, number, result):
        _, done, _ = self.jobs.pop(number)
        self.put(busy=False, working=False, status='ready')
        done(result)
        if self.close_pending and not self.working:
            self.quit()

    @Slot(int, object)
    def task_failed(self, number, exc):
        _, _, failed = self.jobs.pop(number)
        self.put(busy=False, working=False, status='ready')
        if failed:
            failed(exc)
        else:
            self.report(exc)
        if self.close_pending and not self.working:
            self.quit()

    def notify(self, text, title='error'):
        self.dialogRequested.emit(title, text)

    def error_text(self, exc):
        """
        An error in the user's words: a core Failure is said in the interface language (its code
        picks the sentence), with the tool's own output kept underneath; anything else as it is.
        """
        if isinstance(exc, jobs.Failure):
            template = self.texts.get('err_' + exc.code)
            if template:
                try:
                    text = template.format(**exc.params)
                except (KeyError, IndexError):
                    text = ''
                if text:
                    return f'{text}\n\n{exc.detail}' if exc.detail else text
        return str(exc)

    def report(self, exc):
        """Tell the user a job failed."""
        self.notify(self.error_text(exc))

    SUB_PAGES = ('settings', 'metadata', 'review')

    def has_disc(self):
        """A disc has been read: the workspace has something to show."""
        return bool(self.disc.playlists or self.disc.chapters)

    @Slot(str)
    def navigate(self, page):
        if self.state['pipeline']:
            return
        if page == 'main' and not self.has_disc():
            page = 'start'      # an empty workspace is never a destination
        here = self.state['page']
        if page in self.SUB_PAGES and here not in self.SUB_PAGES:
            self.put(returnPage=here)
        self.put(page=page)
        if page == 'settings':
            self.metadata.refresh_cover_cache()

    @Slot()
    def back(self):
        """Leave a sub-page for the page it was opened from."""
        self.navigate(self.state['returnPage'] or 'start')

    @Slot(str, str)
    def setPreference(self, key, value):
        allowed = {'theme': {'dark', 'light', 'system'}, 'language': {'zh', 'en'},
                   'interface_scale': logic.INTERFACE_SCALES, 'font_scale': logic.FONT_SCALES,
                   'density': {'comfortable', 'compact'}, 'motion': {'full', 'reduced'},
                   'proxy_mode': {'system', 'none', 'custom'}, 'net_timeout': {'10', '15', '30'},
                   'meta_source': set(metadata_sources.SOURCES), 'itunes_country': logic.ITUNES_COUNTRIES,
                   'cover_size': set(metadata_sources.COVER_SIZES), 'cover_target': {'both', 'embed', 'folder'},
                   'meta_auto_search': {'true', 'false'},
                   'filename_template': set(naming.FILENAME_TEMPLATES),
                   'collision_policy': {'ask', 'skip', 'overwrite'},
                   'chapter_language': {'first', 'eng', 'jpn', 'zho', 'kor'},
                   'duration_tolerance': {'10', '20', '40'}, 'waveform': {'true', 'false'},
                   'kind_column': {'auto', 'show', 'hide'}, 'crop_backdrop': {'dark', 'light', 'checker'}}
        if key == 'accent':
            value = logic.normalize_accent(value)
            if value is None:
                return
        elif key not in allowed or value not in allowed[key]:
            return
        if key in ('meta_auto_search', 'waveform'):
            value = value == 'true'
        self.set_config(**{key: value})
        if key in self.NETWORK_KEYS:
            self.apply_network()
        if key == 'waveform':
            self.preview.start_waveform() if value else self.preview.stop_waveform()
        if key == 'language':
            for i, score in enumerate(self.disc.playlists):
                self.disc.playlist_model.change(i, **self.disc.card_texts(score, value))
            self.disc.put(sourceSummary=self.disc.source_summary())
            self.disc.refresh_stream_texts()
            self.textsChanged.emit()

    # ------------------------------------------------------------ adjustable layout
    # Column widths in pixels; the video preview as a share of the window height.
    LAYOUT_LIMITS = {'work_left': (200, 480), 'work_right': (260, 520), 'review_right': (300, 620),
                     'meta_left': (220, 480), 'meta_right': (280, 560), 'preview_ratio': (0.2, 0.7)}

    def save_layout_later(self):
        if not self.smoke:
            self.layout_saver.start()

    @Slot(str, float)
    def setLayoutSize(self, key, value):
        """A splitter was dragged (value) or double-clicked (value < 0: back to the default)."""
        if key not in self.LAYOUT_LIMITS:
            return
        sizes = dict(self.cfg.get('layout') or {})
        if value < 0:
            sizes.pop(key, None)
        else:
            low, high = self.LAYOUT_LIMITS[key]
            value = min(high, max(low, value))
            sizes[key] = round(value, 3) if key == 'preview_ratio' else int(round(value))
        self.set_config(save=False, layout=sizes)
        self.save_layout_later()

    def publish_recent(self):
        today = datetime.now().date()
        rows = []
        for e in (self.cfg.get('recent_exports') or [])[:3]:
            try:
                when = datetime.fromisoformat(e.get('when', ''))
                days = (today - when.date()).days
                stamp = (self.tr('today') if days == 0 else self.tr('yesterday') if days == 1
                         else f'{when.month}/{when.day}' if when.year == today.year else when.strftime('%Y/%m/%d'))
            except ValueError:
                stamp = ''
            rows.append(dict(album=e.get('album', ''), detail=' · '.join(filter(None, (
                self.tr('recentCount').replace('{n}', str(e.get('count', 0))), (e.get('container') or '').upper(), stamp))),
                folder=e.get('folder', ''), source=e.get('source', ''),
                canReload=bool(e.get('source')) and Path(e.get('source')).exists()))
        self.put(recentExports=rows)

    NETWORK_KEYS = {'proxy_mode', 'proxy_url', 'net_timeout', 'itunes_country', 'cover_size', 'discogs_token'}

    def apply_network(self):
        metadata_sources.configure(self.cfg.get('proxy_mode', 'system'), self.cfg.get('proxy_url', ''),
                                   float(self.cfg.get('net_timeout', '15') or 15), self.cfg.get('itunes_country', 'US'),
                                   self.cfg.get('cover_size', 'large'), self.cfg.get('discogs_token', ''))

    @Slot(str)
    def setProxyUrl(self, value):
        normalized = logic.normalize_proxy(value)
        if normalized is None:
            self.notify(self.tr('proxyInvalid'))
            return
        self.set_config(proxy_url=normalized)
        self.apply_network()

    @Slot(str)
    def setDiscogsToken(self, value):
        self.set_config(discogs_token="".join(value.split()))
        self.apply_network()

    @Slot()
    def testConnection(self):
        if self.cfg.get('proxy_mode') == 'custom' and not self.cfg.get('proxy_url'):
            self.notify(self.tr('proxyMissing'))
            return
        names = {'musicbrainz': 'MusicBrainz', 'itunes': 'Apple Music', 'deezer': 'Deezer', 'discogs': 'Discogs'}
        def work(progress):
            return [(source,) + metadata_sources.check(source) for source in metadata_sources.SOURCES]
        def done(results):
            self.put(netTest=[dict(source=s, label=names[s], state=state, ms=ms, detail=detail)
                              for s, state, ms, detail in results])
        self.task(work, done, lambda exc: self.put(netTest=[]) or self.report(exc),
                  begin=dict(netTest=[dict(source=s, label=names[s], state='running', ms=0, detail='')
                                      for s in metadata_sources.SOURCES]), blocking=False)

    @Slot()
    def requestClose(self):
        if self.working:
            self.dialogRequested.emit('closeBusy', self.tr('closeBusy'))
        else:
            self.quit()

    @Slot()
    def closeWhenReady(self):
        self.close_pending = True
        self.exporter.cancel()
        if not self.working:
            self.quit()

    @Slot()
    def checkTools(self):
        def work(p):
            engine._available.clear()           # look again: it may have been built meanwhile
            return {'tsMuxeR': engine.available(), **tools.check_tools()}
        def done(found):
            paths = {**tools.tool_paths(), 'tsMuxeR': engine.version() or engine.path()}
            self.tool_model.replace([dict(tool=t, path=paths.get(t, t), available=ok, builtin=t == 'tsMuxeR',
                                          optional=t in self.OPTIONAL_TOOLS and found.get('tsMuxeR', False))
                                     for t, ok in sorted(found.items(), key=lambda item: tools.tool_rank(item[0]))])
            self.put(toolNames=' · '.join(row['tool'] for row in self.tool_model.rows))
            # With the engine, Blu-rays need no MKVToolNix: it reads MKV sources and cuts DVDs to MKV only.
            needed = [ok for t, ok in found.items() if not (t in self.OPTIONAL_TOOLS and found.get('tsMuxeR'))]
            self.put(toolMissing=not all(needed))
            if not all(needed):
                self.dialogRequested.emit('tools', self.tr('toolsHint'))
        self.task(work, done)

    OPTIONAL_TOOLS = ('mkvmerge', 'mkvextract', 'mkvpropedit')

    @Slot(str, str)
    def locateTool(self, tool, path):
        if tool not in tools.tool_paths():
            return
        path = local_path(path)
        def work(p):
            ok, message = tools.verify_tool_at_path(path, tool)
            if not ok:
                raise ValueError(message)
            # The rest of the same install sits next to it. mkvpropedit has no setting of its own:
            # it is found through mkvmerge, so picking it sets the tools beside it.
            paths = {tool: path} if tool in tools.TOOL_PATHS else {}
            for sibling in tools.tool_family(tool):
                if sibling != tool and sibling in tools.TOOL_PATHS:
                    guessed = tools.guess_sibling_tool_path(path, sibling)
                    if guessed and tools.verify_tool_at_path(guessed, sibling)[0]:
                        paths[sibling] = guessed
            if not paths:
                raise ValueError(f"mkvmerge was not found next to {Path(path).name}.")
            return paths
        def done(paths):
            self.set_config(**{name + '_path': value for name, value in paths.items()})
            self.apply_tool_paths()
            self.checkTools()
        self.task(work, done)

    @Slot(str)
    def downloadTool(self, tool):
        url = tools.TOOL_DOWNLOAD_URLS.get(tool)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def help(self, topic):
        if topic == 'about':
            self.notify(f"{self.tr('aboutText')}\n\n{self.tr('versionLabel')} {appinfo.version()}\n{appinfo.REPOSITORY}", topic)
        elif topic == 'tips':
            self.notify(self.tr('tipsText'), topic)
        else:
            suffix = '/issues' if topic == 'report' else '#readme'
            QDesktopServices.openUrl(QUrl(appinfo.REPOSITORY + suffix))
