"""PySide6 / Qt Quick entry point, including a warning-strict offline smoke run."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from gui.backend import Backend
from gui.focus import OutsideClickRelease


def assert_qml_sources(qml_dir=None):
    """Prevent font-dependent icon glyphs from returning to the QML UI."""
    qml_dir = qml_dir or Path(__file__).resolve().parent / 'qml'
    forbidden = {chr(code) for code in (0x21BB, 0x25C9, 0x25CB, 0x25A1, 0x25CE, 0x2713)}
    for path in qml_dir.rglob('*.qml'):
        source = path.read_bytes()
        assert not source.startswith(b'\xef\xbb\xbf'), f'UTF-8 BOM in {path}'
        found = forbidden.intersection(source.decode('utf-8'))
        assert not found, f'Font-dependent icon glyphs in {path}: {sorted(found)}'


def load_engine(backend):
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty('backend', backend)
    disc = backend.disc
    for name, model in dict(playlist=disc.playlist_model, audio=disc.audio_model, subtitle=disc.subtitle_model,
                            chapter=disc.chapter_model, export=disc.export_model, review=backend.names.review_model,
                            release=backend.names.release_model, tool=backend.tool_model,
                            meta=backend.metadata.meta_model).items():
        context.setContextProperty(name + 'Model', model)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parent / 'qml' / 'Main.qml')))
    for window in engine.rootObjects():
        OutsideClickRelease(window)
    return engine


def populate_smoke(backend):
    """Exercise delegates with deterministic data; no tools, network or settings writes."""
    import extractor
    backend.cfg.update(theme='dark', language='zh', accent='#F2A33A', motion='reduced')
    backend.disc.chapters = [extractor.Chapter(i, (i-1)*300, i*300, embedded_name=f'Song {i}') for i in range(1, 10)]
    backend.disc.rebuild_chapters({i: f'Song {i}' for i in range(1, 10) if i not in (3, 7)})
    for i in range(9):
        backend.disc.chapter_model.change(i, origin='disc' if i < 5 else 'edited', file=f'{i+1:02d} - Song {i+1}.mkv',
                                     status='done' if i < 4 else 'running' if i == 4 else 'pending',
                                     verify='warn' if i == 2 else 'ok' if i < 4 else '',
                                     verifyText='时长 4:57.0，应为 5:00.0' if i == 2 else '', included=i < 6)
    backend.disc.update_chapter_selection()
    backend.disc.source_chapters = [extractor.Chapter(i, (i-1)*300, i*300) for i in range(1, 10)]
    backend.put(chaptersEdited=True, verifyState='done', verified=3, verifyIssues=1)
    backend.disc.playlist_model.replace([dict(label='00001.mpls', detail='45:00 · 9 章', tracks='TrueHD Atmos 7.1 / LPCM 2.0 · 1920×1080 · 1 条字幕', headline='Dolby Atmos / TrueHD',
        reasons='Dolby Atmos / TrueHD\n9 chapters · AVC video', chosen=True),
        dict(label='00002.mpls', detail='05:00 · 1 章', tracks='LPCM 2.0 · 无视频 · 无字幕', headline='LPCM 2.0', reasons='LPCM 2.0', chosen=False)])
    backend.disc.audio_model.replace([dict(label='TrueHD Atmos - 7.1, 96kHz, 24-bit [eng]', codec='TrueHD Atmos', details='7.1 · 96kHz · 24-bit [eng]', chosen=True),
                                 dict(label='LPCM - 2.0, 96kHz, 24-bit [eng]', codec='LPCM', details='2.0 · 96kHz · 24-bit [eng]', chosen=False)])
    backend.disc.subtitle_model.replace([dict(label='PGS · eng', chosen=True)])
    # Playlist object behind the cards, for the track details sheet.
    backend.disc.playlist = extractor.Playlist(path=Path('BDMV/PLAYLIST/00001.mpls'), tracks=[
        extractor.Track(0, 'video', 'AVC/H.264/MPEG-4p10', 'V_MPEG4/ISO/AVC', stream_id=0x1011,
                        properties={'pixel_dimensions': '1920x1080'}),
        extractor.Track(1, 'audio', 'TrueHD Atmos', 'A_TRUEHD', 'eng', 8, 'Dolby Atmos 7.1', 96000, 24, default_track=True,
                        stream_id=0x1100, properties={'language_ietf': 'en-US', 'forced_track': False}),
        extractor.Track(2, 'audio', 'LPCM', 'A_PCM/INT/BIG', 'eng', 2, '', 96000, 24, stream_id=0x1101),
        extractor.Track(3, 'subtitles', 'HDMV PGS', 'S_HDMV/PGS', 'eng', stream_id=0x1200)], chapter_count=9, duration_seconds=2700)
    backend.disc.refresh_stream_texts()     # card titles, chips and info lines from the tracks above
    backend.disc.update_track_selection()
    backend.put(hasVideo=True, keepVideo=True, videoSummary='H.264 · 1920×1080 · 23.976p · SDR')
    # Preview bar open (no clip, so nothing plays): exercises its layout on every screen.
    backend.put(previewRow=1, previewAudio=0, previewTitle='02 · Song 2', previewTrack='TrueHD Atmos - 7.1',
                previewTracks=['TrueHD Atmos 7.1', 'LPCM 2.0'], previewLoading=False, previewVideo=True)
    # Synthetic loudness outlines: the timeline (2 peaks per second) and the preview clip.
    import math
    backend.preview._wave = [round(0.15 + 0.7 * abs(math.sin(i / 37) * math.sin(i / 5.3)), 3) for i in range(2700 * 2)]
    backend.preview.waveChanged.emit()
    backend.put(waveState='ready', waveProgress=100)
    backend.disc.source_size = 38_000_000_000
    backend.cfg['recent_exports'] = [
        dict(album='Love Over Gold', count=5, folder='D:/Music/Love Over Gold', source='', container='flac',
             when='2026-11-12T20:15'),
        dict(album='Alchemy', count=12, folder='D:/Music/Alchemy', source='', container='mkv', when='2026-10-02T09:00')]
    backend.publish_recent()
    backend.disc.refresh_insights()
    backend.preview.set_preview_wave([round(0.2 + 0.6 * abs(math.sin(i / 23) * math.cos(i / 4.1)), 3) for i in range(800)])
    backend.put(pasteDraft='\n'.join(['＜収録内容＞', 'Disc 1', 'Opening Movie', 'M1. Song 1', 'M2. Song 2 (Live)', '-MC-',
                                       'M3. Song 3', 'M4. Song 4', 'ENCORE', 'EN1. Song 5', 'EN2. Song 6', 'EN3. Song 7',
                                       '', 'Disc 2', '特典映像', '1. Documentary']))
    backend.tool_model.replace([dict(tool=t, path=t, available=t != 'ffprobe') for t in extractor.TOOL_PATHS])
    backend.metadata.meta['album'].update(artist='Dire Straits', album='Brothers In Arms', album_artist='Dire Straits', date='1985', genre='Rock')
    backend.metadata.meta['audio'].update(title='TrueHD Atmos 7.1', language='eng')
    backend.metadata.setTrackArtist(1, 'Dire Straits feat. Sting')
    backend.metadata.publish_metadata()
    backend.metadata.meta_model.replace([dict(source='musicbrainz', label='Dire Straits \u2014 Brothers In Arms', detail='Blu-ray \u00b7 2025 \u00b7 9', thumb='', chosen=True),
                                dict(source='musicbrainz', label='Dire Straits \u2014 Brothers In Arms', detail='CD \u00b7 1985 \u00b7 9', thumb='', chosen=False)])
    backend.put(metaChosen=0, metaStatus='results')
    backend.names.release_model.replace([dict(label='Dire Straits — Brothers In Arms', detail='Blu-ray · 2025', tracks=9, chapters=9, fit='exact', chosen=True, thumb=''),
                                   dict(label='Dire Straits — Brothers In Arms (Deluxe)', detail='CD · 2005', tracks=12, chapters=9, fit='far', chosen=False, thumb='')])
    backend.put(mb='results', mbRelease='Dire Straits — Brothers In Arms', mbArtist='Dire Straits', mbAlbum='Brothers In Arms')
    backend.names.review_entries([extractor.TracklistEntry(f'Song {i} (Live on Tour 2025)', index=i, duration_seconds=d) for i, d in enumerate([296, 303, 300, 299, 301, 298, 304, 300], 1)])
    backend.names.review_model.change(6, confidence='duration_mismatch', checked=False)
    backend.put(page='start', source='E:/Blurays/Dire Straits - Brothers In Arms [Blu-ray]',
                output='D:/Music', album='Brothers In Arms', artist='Dire Straits',
                sidecars=['E:/Blurays/Track Listing.txt'], resume=True,
                resumeText='Brothers In Arms · TrueHD Atmos 7.1 · 4 / 9',
                logs='Extracting video track 0 + audio track 1\nSplitting chapter 5: Why Worry',
                collisionFiles=['01 - Song 1.mkv', '02 - Song 2.mkv'], completed=4, current=5, stage='splitting')


def apply_qt_proxy(cfg):
    """Use the same proxy for images QML loads (search result thumbnails) as for Python requests."""
    from urllib.parse import urlsplit
    from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
    mode = cfg.get('proxy_mode', 'system')
    url = cfg.get('proxy_url', '')
    if mode == 'custom' and url:
        parts = urlsplit(url)
        QNetworkProxyFactory.setUseSystemConfiguration(False)
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy, parts.hostname, parts.port))
    elif mode == 'none':
        QNetworkProxyFactory.setUseSystemConfiguration(False)
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
    else:
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.DefaultProxy))
        QNetworkProxyFactory.setUseSystemConfiguration(True)


def system_scale() -> int:
    """Windows display scaling in percent (Qt has made the process DPI aware by now)."""
    if sys.platform != 'win32':
        return 100
    try:
        import ctypes
        return round(ctypes.windll.user32.GetDpiForSystem() * 100 / 96)
    except Exception:
        return 100


def system_accent(app) -> str:
    """Windows accent colour as #RRGGBB (Qt 6.6+ exposes it as QPalette.Accent)."""
    try:
        from PySide6.QtGui import QPalette
        return app.palette().color(QPalette.ColorRole.Accent).name().upper()
    except Exception:
        return '#60CDFF'


def apply_native_titlebar(window, cfg, app):
    """Make the native Windows caption match the app theme (dark mode + caption colour)."""
    import ctypes
    from PySide6.QtCore import Qt
    theme = cfg.get('theme', 'dark')
    dark = theme == 'dark' or (theme == 'system' and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    try:
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        flag = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(flag), ctypes.sizeof(flag))  # DWMWA_USE_IMMERSIVE_DARK_MODE
        r, g, b = (0x0C, 0x0E, 0x12) if dark else (0xEE, 0xF0, 0xF3)          # Theme.bg
        caption = ctypes.c_uint(r | (g << 8) | (b << 16))                      # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))  # DWMWA_CAPTION_COLOR (Win11)
    except Exception:
        pass  # Older Windows: keep the default caption.


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--smoke-screenshots', type=Path)
    args = parser.parse_args(argv)
    if args.smoke_test:
        assert_qml_sources()
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        os.environ.setdefault('QSG_RHI_BACKEND', 'software')
        if sys.platform == 'win32':
            # Offscreen Qt has no Windows font backend. Use an existing local
            # directory and explicitly load installed system fonts below; do not
            # scan every font/shortcut in the Windows Fonts virtual directory.
            os.environ.setdefault('QT_QPA_FONTDIR', str(Path(__file__).parent / 'qml'))
    warnings = []
    def handler(kind, context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            warnings.append(message)
        print(message, file=sys.stderr)
    previous = qInstallMessageHandler(handler) if args.smoke_test else None
    if not args.smoke_test and 'QT_SCALE_FACTOR' not in os.environ:
        import settings
        from gui import logic
        factor = logic.scale_factor(settings.load())
        if factor:
            # Absolute scale: ignore Windows display scaling, then apply the chosen factor.
            os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
            os.environ['QT_SCALE_FACTOR'] = factor
    QQuickStyle.setStyle('Basic')
    app = QApplication(sys.argv[:1])
    if args.smoke_test and sys.platform == 'win32':
        fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('segoeui.ttf', 'seguisb.ttf', 'seguisym.ttf', 'msyh.ttc', 'consola.ttf'):
            if (fonts / name).is_file():
                QFontDatabase.addApplicationFont(str(fonts / name))
    app.setApplicationName('DiscSplitter')
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'disc_splitter.ico')))
    backend = Backend(smoke=args.smoke_test)
    backend.put(systemAccent=system_accent(app), systemScale=system_scale(),
                startScale=str(backend.cfg.get('interface_scale', 'system')))
    if args.smoke_test:
        populate_smoke(backend)
    apply_qt_proxy(backend.cfg)
    backend.configChanged.connect(lambda: apply_qt_proxy(backend.cfg))
    engine = load_engine(backend)
    if not engine.rootObjects():
        return 1
    if not args.smoke_test and sys.platform == 'win32':
        window = engine.rootObjects()[0]
        sync = lambda: apply_native_titlebar(window, backend.cfg, app)
        backend.configChanged.connect(sync)
        app.styleHints().colorSchemeChanged.connect(lambda *_: sync())
        sync()
    if not args.smoke_test:
        from gui.desktop import Desktop
        desktop = Desktop(app, engine.rootObjects()[0], backend, str(Path(__file__).parent / 'disc_splitter.ico'))
    if args.smoke_test:
        window = engine.rootObjects()[0]
        steps = []
        for language in ('zh', 'en'):
            for theme in ('dark', 'light', 'system'):
                for page in ('start', 'main', 'review', 'export', 'done', 'settings', 'metadata'):
                    steps.append((language, theme, page))
                for section in ('files', 'matching', 'appearance', 'help'):
                    steps.append((language, theme, 'settings:' + section))
        # Full-motion pass: every page transition and Behavior runs once, no screenshots.
        for page in ('start', 'main', 'review', 'export', 'done', 'settings', 'metadata', 'main'):
            steps.append(('zh', 'dark', 'motion:' + page))
        dialogs = iter(('tools', 'collision', 'diskSpace', 'discard', 'resume', 'duplicate', 'closeBusy', 'tips', 'about', 'paste', 'trackinfo', 'videoinfo'))
        def advance():
            if steps:
                language, theme, page = steps.pop(0)
                if page.startswith('motion:'):
                    backend.setPreference('motion', 'full')
                    backend.put(pipeline=False)
                    backend.navigate(page.split(':')[1])
                    backend.put(pipeline=page == 'motion:export')
                    QTimer.singleShot(260, advance)
                    return
                backend.setPreference('language', language)
                backend.setPreference('theme', theme)
                backend.put(pipeline=False)
                backend.navigate(page.split(':')[0])
                backend.put(pipeline=page == 'export')
                if page.startswith('settings:'):
                    window.smokeSection(page.split(':')[1])
                elif page == 'settings':
                    window.smokeSection('tools')
                if args.smoke_screenshots:
                    args.smoke_screenshots.mkdir(parents=True, exist_ok=True)
                    name = f'{language}-{theme}-{page.replace(":", "-")}.png'
                    QTimer.singleShot(60, lambda: window.grabWindow().save(str(args.smoke_screenshots / name)))
                QTimer.singleShot(100, advance)
            else:
                kind = next(dialogs, None)
                window.closeDialog()     # an open dialog would queue the next one instead of showing it
                if kind:
                    if kind == 'paste':
                        window.pasteTracklist()
                        if args.smoke_screenshots:
                            QTimer.singleShot(400, lambda: window.grabWindow().save(str(args.smoke_screenshots / 'paste.png')))
                        QTimer.singleShot(500, advance)
                    elif kind in ('trackinfo', 'videoinfo'):
                        window.showTrackInfo('audio' if kind == 'trackinfo' else 'video', 0)
                        if args.smoke_screenshots:
                            QTimer.singleShot(60, lambda k=kind: window.grabWindow().save(str(args.smoke_screenshots / f'{k}.png')))
                    else:
                        backend.dialogRequested.emit(kind, backend.tr('toolsHint' if kind == 'tools' else kind))
                    if kind != 'paste':
                        QTimer.singleShot(100, advance)
                else:
                    app.exit(1 if warnings else 0)
        QTimer.singleShot(100, advance)
    code = app.exec()
    # Destroy QML while its Python context objects are still alive.
    engine.deleteLater()
    app.processEvents()
    if args.smoke_test:
        qInstallMessageHandler(previous)
        if warnings:
            print(f'Smoke FAILED: {len(warnings)} Qt/QML warning(s)', file=sys.stderr)
            return 1
        print('Smoke PASS: all screens, delegates, dialogs, languages and themes; zero Qt/QML warnings.')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
