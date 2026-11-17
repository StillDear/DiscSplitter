"""
The offline smoke run (app.py --smoke-test): every screen and dialog, in both languages and all
themes, with made-up disc data. No tools, network or settings writes; any Qt/QML warning fails it.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

from core import models, tools, tracklist


def populate(backend):
    """Exercise delegates with deterministic data; no tools, network or settings writes."""
    backend.cfg.update(theme='dark', language='zh', accent='#F2A33A', motion='reduced', waveform=True)
    # A concert's shape: an intro, songs of different lengths, two spoken breaks (4 and 8), a long closer.
    lengths = [95, 312, 268, 140, 355, 290, 420, 85, 735]
    starts = [sum(lengths[:i]) for i in range(9)]
    backend.disc.chapters = [models.Chapter(i + 1, starts[i], starts[i] + lengths[i], embedded_name=f'Song {i + 1}')
                             for i in range(9)]
    backend.disc.rebuild_chapters({i: f'Song {i}' for i in range(1, 10) if i not in (3, 7)})
    for i in range(9):
        backend.disc.chapter_model.change(i, origin='disc' if i < 5 else 'edited', file=f'{i+1:02d} - Song {i+1}.mkv',
                                     status='done' if i < 4 else 'running' if i == 4 else 'pending',
                                     verify='warn' if i == 2 else 'ok' if i < 4 else '',
                                     verifyText='时长 4:57.0，应为 5:00.0' if i == 2 else '', included=i < 6)
    backend.disc.update_chapter_selection()
    backend.disc.source_chapters = [models.Chapter(i, (i-1)*300, i*300) for i in range(1, 10)]
    backend.put(chaptersEdited=True, verifyState='done', verified=3, verifyIssues=1)
    backend.disc.playlist_model.replace([dict(label='00001.mpls', detail='45:00 · 9 章', tracks='TrueHD Atmos 7.1 / LPCM 2.0 · 1920×1080 · 1 条字幕', headline='Dolby Atmos / TrueHD',
        reasons='Dolby Atmos / TrueHD\n9 chapters · AVC video', chosen=True),
        dict(label='00002.mpls', detail='05:00 · 1 章', tracks='LPCM 2.0 · 无视频 · 无字幕', headline='LPCM 2.0', reasons='LPCM 2.0', chosen=False)])
    backend.disc.audio_model.replace([dict(label='TrueHD Atmos - 7.1, 96kHz, 24-bit [eng]', codec='TrueHD Atmos', details='7.1 · 96kHz · 24-bit [eng]', chosen=True),
                                 dict(label='LPCM - 2.0, 96kHz, 24-bit [eng]', codec='LPCM', details='2.0 · 96kHz · 24-bit [eng]', chosen=False)])
    backend.disc.subtitle_model.replace([dict(label='PGS · eng', chosen=True)])
    # Playlist object behind the cards, for the track details sheet.
    backend.disc.playlist = models.Playlist(path=Path('BDMV/PLAYLIST/00001.mpls'), tracks=[
        models.Track(0, 'video', 'AVC/H.264/MPEG-4p10', 'V_MPEG4/ISO/AVC', stream_id=0x1011,
                        properties={'pixel_dimensions': '1920x1080'}),
        models.Track(1, 'audio', 'TrueHD Atmos', 'A_TRUEHD', 'eng', 8, 'Dolby Atmos 7.1', 96000, 24, default_track=True,
                        stream_id=0x1100, properties={'language_ietf': 'en-US', 'forced_track': False}),
        models.Track(2, 'audio', 'LPCM', 'A_PCM/INT/BIG', 'eng', 2, '', 96000, 24, stream_id=0x1101),
        models.Track(3, 'subtitles', 'HDMV PGS', 'S_HDMV/PGS', 'eng', stream_id=0x1200)], chapter_count=9, duration_seconds=2700,
        reader='engine', main_title=True)
    backend.disc.refresh_stream_texts()     # card titles, chips and info lines from the tracks above
    backend.disc.update_track_selection()
    backend.put(hasVideo=True, keepVideo=True, canM2ts=True, videoSummary='H.264 · 1920×1080 · 23.976p · SDR')
    # Preview bar open (no clip, so nothing plays): exercises its layout on every screen.
    backend.put(previewRow=1, previewAudio=0, previewTitle='02 · Song 2', previewTrack='TrueHD Atmos - 7.1',
                previewTracks=['TrueHD Atmos 7.1', 'LPCM 2.0'], previewLoading=False, previewVideo=True,
                previewLength=161)
    backend.preview.refresh_preview_info()     # set by hand above, so the panel's chapter info too
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
    backend.tool_model.replace([dict(tool='tsMuxeR', path='tsMuxeR version 3.1.0', available=True, builtin=True, optional=False)]
                               + [dict(tool=t, path=t, available=t != 'ffprobe', builtin=False, optional=t.startswith('mkv'))
                                  for t in sorted(tools.TOOL_PATHS, key=tools.tool_rank)])
    backend.put(toolNames=' · '.join(row['tool'] for row in backend.tool_model.rows))
    backend.metadata.meta['album'].update(artist='Dire Straits', album='Brothers In Arms', album_artist='Dire Straits', date='1985', genre='Rock')
    backend.metadata.setTrackArtist(1, 'Dire Straits feat. Sting')
    backend.metadata.publish_metadata()
    # A local album tagged with its MusicBrainz release (its button shows when chosen), then an online result
    backend.metadata.meta_model.replace([dict(source='local', label='Dire Straits \u2014 Brothers In Arms', detail='Brothers In Arms \u00b7 FLAC \u00b7 1985 \u00b7 9', thumb='', chosen=True, mbid='mb-smoke'),
                                dict(source='musicbrainz', label='Dire Straits \u2014 Brothers In Arms', detail='CD \u00b7 1985 \u00b7 9', thumb='', chosen=False, mbid='')])
    backend.put(metaChosen=0, metaStatus='results')
    backend.names.release_model.replace([dict(label='Dire Straits — Brothers In Arms', detail='Blu-ray · 2025', tracks=9, chapters=9, fit='exact', chosen=True, thumb=''),
                                   dict(label='Dire Straits — Brothers In Arms (Deluxe)', detail='CD · 2005', tracks=12, chapters=9, fit='far', chosen=False, thumb='')])
    backend.put(mb='results', mbRelease='Dire Straits — Brothers In Arms', mbArtist='Dire Straits', mbAlbum='Brothers In Arms')
    backend.names.review_entries([tracklist.TracklistEntry(f'Song {i} (Live on Tour 2025)', index=i, duration_seconds=d) for i, d in enumerate([296, 303, 300, 299, 301, 298, 304, 300], 1)])
    backend.names.review_model.change(6, confidence='duration_mismatch', checked=False)
    backend.put(page='start', source='E:/Blurays/Dire Straits - Brothers In Arms [Blu-ray]',
                output='D:/Music', album='Brothers In Arms', artist='Dire Straits',
                sidecars=['E:/Blurays/Track Listing.txt'], resume=True,
                resumeText='Brothers In Arms · TrueHD Atmos 7.1 · 4 / 9',
                logs='Extracting video track 0 + audio track 1\nSplitting chapter 5: Why Worry',
                collisionFiles=['01 - Song 1.mkv', '02 - Song 2.mkv'], completed=4, current=5, chapterFraction=0.4, stage='splitting')
    # One chapter of each kind the timeline draws (hand-set ones are kept per disc, so after the source above):
    # 4 and 8 spoken breaks (hollow), 1 an instrumental intro (half fill).
    for row, kind in ((3, 'talk'), (7, 'talk'), (0, 'interlude')):
        backend.disc.setChapterKind(row, kind)


def run(app, backend, window, warnings, screenshots=None):
    """Walk through the screens, then the dialogs; ends the app with 1 if Qt warned about anything."""
    steps = []
    for language in ('zh', 'en'):
        for theme in ('dark', 'light', 'system'):
            for page in ('start', 'main', 'review', 'export', 'done', 'settings', 'metadata', 'metadata:local'):
                steps.append((language, theme, page))
            for section in ('files', 'matching', 'appearance'):
                steps.append((language, theme, 'settings:' + section))
            for section in ('guide', 'tips', 'faq', 'troubleshoot', 'about'):
                steps.append((language, theme, 'help:' + section))
    # Full-motion pass: every page transition and Behavior runs once, no screenshots.
    for page in ('start', 'main', 'review', 'export', 'done', 'settings', 'help', 'metadata', 'main'):
        steps.append(('zh', 'dark', 'motion:' + page))
    # The disc copied as M2TS (a Blu-ray the built-in engine read): the format switch, the summary, the stages.
    for language, theme in (('zh', 'dark'), ('en', 'light')):
        for page in ('main', 'export', 'settings'):
            steps.append((language, theme, 'm2ts:' + page))
    dialogs = iter(('tools', 'collision', 'diskSpace', 'discard', 'resume', 'duplicate', 'closeBusy', 'error', 'helpmenu', 'paste', 'trackinfo', 'videoinfo'))
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
            if page.startswith('m2ts:'):
                backend.setPreference('motion', 'reduced')
                backend.put(outputFormat='m2ts')
                page = page.split(':')[1]
                name_page = 'm2ts-' + page
            else:
                name_page = page.replace(":", "-")
            backend.navigate(page.split(':')[0])
            backend.put(pipeline=page == 'export')
            if page.startswith('settings:'):
                window.smokeSection(page.split(':')[1])
            elif page.startswith('help:'):
                window.smokeHelp(page.split(':')[1])
            elif page == 'settings':
                window.smokeSection('tools')
            if page.startswith('metadata'):
                window.smokeMetaSource('local' if page == 'metadata:local' else 'musicbrainz')
            if screenshots:
                screenshots.mkdir(parents=True, exist_ok=True)
                name = f'{language}-{theme}-{name_page}.png'
                QTimer.singleShot(60, lambda: window.grabWindow().save(str(screenshots / name)))
            QTimer.singleShot(100, advance)
        else:
            kind = next(dialogs, None)
            window.closeDialog()     # an open dialog would queue the next one instead of showing it
            if kind:
                if kind == 'paste':
                    window.pasteTracklist()
                    if screenshots:
                        QTimer.singleShot(400, lambda: window.grabWindow().save(str(screenshots / 'paste.png')))
                    QTimer.singleShot(500, advance)
                elif kind == 'helpmenu':
                    window.smokeHelpMenu()
                    if screenshots:
                        QTimer.singleShot(300, lambda: window.grabWindow().save(str(screenshots / 'helpmenu.png')))
                elif kind in ('trackinfo', 'videoinfo'):
                    window.showTrackInfo('audio' if kind == 'trackinfo' else 'video', 0)
                    if screenshots:
                        QTimer.singleShot(60, lambda k=kind: window.grabWindow().save(str(screenshots / f'{k}.png')))
                else:
                    backend.dialogRequested.emit(kind, backend.tr('toolsHint' if kind == 'tools' else kind))
                if kind == 'helpmenu':
                    QTimer.singleShot(400, lambda: (window.closeHelpMenu(), advance()))
                elif kind != 'paste':
                    QTimer.singleShot(100, advance)
            else:
                app.exit(1 if warnings else 0)
    QTimer.singleShot(100, advance)
