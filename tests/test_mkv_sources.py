from pathlib import Path
import json
import shutil
import subprocess
import threading

import pytest
from PySide6.QtCore import QUrl

import core.jobs
import core.manifest
import core.models
import core.naming
import core.pipeline
import core.tools
from gui import logic
from test_backend import wait_idle
import core.chapter_marks
import core.sources


@pytest.mark.skipif(not all(shutil.which(tool) for tool in core.tools.TOOL_PATHS),
                    reason='MKVToolNix and FFmpeg are required')
@pytest.mark.parametrize('keep_video', [True, False])
def test_selected_chapters_keep_multiple_tracks_through_resume(tmp_path, monkeypatch, keep_video):
    for tool in core.tools.TOOL_PATHS:
        monkeypatch.setitem(core.tools.TOOL_PATHS, tool, shutil.which(tool))
    source = tmp_path / 'concert.mkv'
    subtitles = tmp_path / 'lyrics.srt'
    subtitles.write_text('1\n00:00:00,400 --> 00:00:01,400\nIntro\n\n'
                         '2\n00:00:04,400 --> 00:00:05,400\nFinale\n', encoding='utf-8')
    chapter_file = tmp_path / 'chapters.txt'
    chapter_file.write_text(';FFMETADATA1\n' + ''.join(
        f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={i * 2000}\nEND={(i + 1) * 2000}\ntitle=Song {i + 1}\n'
        for i in range(3)), encoding='utf-8')

    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=64x64:r=10:d=6',
        '-f', 'lavfi', '-i', 'sine=duration=6', '-i', str(subtitles), '-i', str(chapter_file),
        '-map', '0:v', '-map', '1:a', '-map', '1:a', '-map', '1:a',
        '-map', '2:s', '-map', '2:s', '-map_chapters', '3',
        '-c:v', 'mpeg2video', '-g', '1', '-c:a', 'pcm_s16le', '-c:s', 'copy',
        '-metadata:s:a:1', 'title=Stereo', '-metadata:s:a:2', 'title=Alternate',
        '-metadata:s:a:2', 'language=jpn', '-metadata:s:s:1', 'language=chi',
        '-disposition:a:0', 'default', '-disposition:a:1', '0', '-disposition:a:2', '0',
        '-disposition:s:0', '0', '-disposition:s:1', 'forced', str(source),
    ], check=True, capture_output=True)
    playlist = core.sources.inspect_playlist(source)
    audio_ids = [t.track_id for t in playlist.audio_tracks[1:]]
    subtitle_ids = [t.track_id for t in playlist.subtitle_tracks]
    output = tmp_path / 'output'
    work = output / '_work'
    cancel = threading.Event()

    def progress(message):
        if message.startswith('Splitting chapter 3:'):
            cancel.set()

    with pytest.raises(core.jobs.JobCancelled):
        core.pipeline.run_full_pipeline(
            playlist, playlist.audio_tracks[1], {3: 'Finale'}, work, output,
            audio_track_ids=audio_ids, subtitle_track_ids=subtitle_ids, chapter_indices=[1, 3],
            cancel_event=cancel, progress_cb=progress, keep_video=keep_video,
        )
    manifest = core.manifest.read_manifest(work)
    first = Path(manifest.completed_outputs[0])
    assert first.name == 'Track 01.mkv'
    assert manifest.audio_track_ids == audio_ids
    assert manifest.subtitle_track_ids == subtitle_ids
    assert manifest.chapter_indices == [1, 3]
    assert manifest.number_filenames is False
    assert manifest.renumber_tracks is True
    assert manifest.video_track_id == (playlist.video_track.track_id if keep_video else None)
    first_modified = first.stat().st_mtime_ns

    # A Matroska source is cut straight from the file: no intermediate copy for a resume to reuse.
    assert not (work / '_audio_extracted.mkv').exists()
    # The resume asks for the other video setting; the saved one must win (the streams checked below).
    paths = core.pipeline.run_full_pipeline(
        playlist, playlist.audio_tracks[0], {}, work, output, resume=True, chapter_indices=[2],
        keep_video=not keep_video,
    )
    assert [p.name for p in paths] == ['Track 01.mkv', 'Finale.mkv']
    assert first.stat().st_mtime_ns == first_modified
    assert set(output.glob('*.mkv')) == set(paths)
    # Video files carry only their song titles (no track or album tags).
    for title, path in zip(['Track 01', 'Finale'], paths):
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                         '-of', 'json', str(path)], encoding='utf-8')
        media = json.loads(probe)
        tags = {k.lower(): v for k, v in media['format'].get('tags', {}).items()}
        assert tags.get('title') == title and 'track' not in tags
        assert float(media['format']['duration']) == pytest.approx(2, abs=0.3 if keep_video else 0.12)
        streams = media['streams']
        assert [s['codec_type'] for s in streams] == (['video'] if keep_video else []) + [
            'audio', 'audio', 'subtitle', 'subtitle',
        ]
        audio1, audio2, subtitle1, subtitle2 = streams[-4:]
        assert [audio1['tags']['title'], audio2['tags']['title']] == ['Stereo', 'Alternate']
        assert audio2['tags']['language'] == 'jpn'
        assert subtitle2['tags']['language'] == 'chi'
        assert [s['disposition']['default'] for s in (audio1, audio2, subtitle1, subtitle2)] == [0, 0, 0, 0]
        assert subtitle2['disposition']['forced'] == 1


@pytest.mark.skipif(not all(shutil.which(tool) for tool in core.tools.TOOL_PATHS),
                    reason='MKVToolNix and FFmpeg are required')
@pytest.mark.parametrize('keep_video,with_pcm', [(True, True), (True, False), (False, True), (False, False)])
def test_mkv_export_keeps_flac_tracks_of_a_matroska_source(tmp_path, monkeypatch, keep_video, with_pcm):
    """mkvmerge cannot split FLAC: those tracks are cut by ffmpeg over the span of each part and added to it."""
    for tool in core.tools.TOOL_PATHS:
        monkeypatch.setitem(core.tools.TOOL_PATHS, tool, shutil.which(tool))
    source = tmp_path / 'concert.mkv'
    subtitles = tmp_path / 'lyrics.srt'
    subtitles.write_text('1\n00:00:03,400 --> 00:00:03,900\nVerse\n', encoding='utf-8')
    chapter_file = tmp_path / 'chapters.txt'
    # Chapter 2 starts and ends between key pictures (one a second): mkvmerge cuts it from 3 s to 5 s.
    chapter_file.write_text(';FFMETADATA1\n' + ''.join(
        f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle=Song {i + 1}\n'
        for i, (start, end) in enumerate([(0, 2050), (2050, 4050), (4050, 6000)])), encoding='utf-8')
    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=s=64x64:r=10:d=6',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6:sample_rate=48000',
        '-f', 'lavfi', '-i', 'aevalsrc=sin(1000*t*t):d=6:s=48000', '-i', str(subtitles), '-i', str(chapter_file),
        '-map', '0:v', '-map', '1:a', '-map', '2:a', '-map', '1:a', '-map', '3:s', '-map_chapters', '4',
        '-c:v', 'mpeg2video', '-g', '10', '-c:a:0', 'pcm_s16le', '-c:a:1', 'flac', '-sample_fmt:a:1', 's32',
        '-c:a:2', 'flac', '-c:s', 'srt',
        '-metadata:s:a:1', 'title=Chirp', '-metadata:s:a:1', 'language=jpn', '-disposition:a:1', 'default',
        '-disposition:a:0', '0', '-disposition:a:2', '0', str(source),
    ], check=True, capture_output=True)
    playlist = core.sources.inspect_playlist(source)
    pcm, chirp, sine = playlist.audio_tracks
    audio = [pcm, chirp, sine] if with_pcm else [chirp, sine]
    output = tmp_path / 'output'
    path, = core.pipeline.run_full_pipeline(
        playlist, chirp, {2: 'Two'}, output / '_work', output, chapter_indices=[2], keep_video=keep_video,
        audio_track_ids=[t.track_id for t in audio], subtitle_track_ids=[playlist.subtitle_tracks[0].track_id])
    media = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                                '-of', 'json', str(path)], encoding='utf-8'))
    streams = media['streams']
    assert [(s['codec_type'], s['codec_name']) for s in streams] == (
        [('video', 'mpeg2video')] if keep_video else []) + (
        [('audio', 'pcm_s16le')] if with_pcm else []) + [('audio', 'flac'), ('audio', 'flac'), ('subtitle', 'subrip')]
    chirp_out = streams[-3]
    assert chirp_out['tags']['title'] == 'Chirp' and chirp_out['tags']['language'] == 'jpn'
    assert chirp_out['disposition']['default'] == 1 and streams[-2]['disposition']['default'] == 0
    assert chirp_out['bits_per_raw_sample'] == '24'
    assert {k.lower(): v for k, v in media['format']['tags'].items()}['title'] == 'Two'

    # The FLAC samples are the source's own over the span the part covers: 3 s to 5 s with video, the chapter without.
    start = 3 if keep_video else 2.05

    def samples(path, stream, *cut):
        return subprocess.check_output(['ffmpeg', '-v', 'error', *cut, '-i', str(path), '-map', stream,
                                        '-f', 's32le', '-'])
    got = samples(path, f'0:{len(streams) - 3}')
    assert got == samples(source, f'0:{chirp.track_id}', '-ss', str(start), '-t', '2')
    assert len(got) == 2 * 48000 * 4
    assert 'Verse' in subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:s', '-f', 'srt',
                                               '-'], encoding='utf-8')
    if keep_video:
        assert float(streams[0].get('duration') or media['format']['duration']) == pytest.approx(2, abs=0.15)


@pytest.mark.skipif(not all(shutil.which(tool) for tool in core.tools.TOOL_PATHS),
                    reason='MKVToolNix and FFmpeg are required')
def test_flac_reads_the_chosen_track_of_a_matroska_source_without_a_copy(tmp_path, monkeypatch):
    for tool in core.tools.TOOL_PATHS:
        monkeypatch.setitem(core.tools.TOOL_PATHS, tool, shutil.which(tool))
    source = tmp_path / 'concert.mkv'
    chapter_file = tmp_path / 'chapters.txt'
    chapter_file.write_text(';FFMETADATA1\n' + ''.join(
        f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={i * 2000}\nEND={(i + 1) * 2000}\ntitle=Song {i + 1}\n'
        for i in range(2)), encoding='utf-8')
    subprocess.run([
        'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=64x64:r=10:d=4',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4:sample_rate=48000',
        '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=4:sample_rate=48000', '-i', str(chapter_file),
        '-map', '0:v', '-map', '1:a', '-map', '2:a', '-map_chapters', '3',
        '-c:v', 'mpeg2video', '-c:a', 'flac', str(source),
    ], check=True, capture_output=True)
    playlist = core.sources.inspect_playlist(source)
    chosen = playlist.audio_tracks[1]
    work = tmp_path / 'output' / '_work'
    paths = core.pipeline.run_full_pipeline(playlist, chosen, {}, work, tmp_path / 'output', container='flac',
                                            chapter_indices=[2])
    assert not (work / '_audio_extracted.mkv').exists()

    def samples(path, stream):
        return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', stream,
                                        '-t', '0.5', '-f', 's16le', '-'])

    # The cut is the second chapter of the 1000 Hz track: the same samples as that track two seconds in.
    expected = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', '2', '-i', str(source),
                                        '-map', f'0:{chosen.track_id}', '-t', '0.5', '-f', 's16le', '-'])
    assert len(paths) == 1 and samples(paths[0], '0:a:0') == expected


@pytest.mark.parametrize('suffix', ['.mkv', '.MKV', '.mk3d', '.MK3D', '.mka', '.MKA'])
def test_single_matroska_source(tmp_path, monkeypatch, suffix):
    source = tmp_path / ('concert' + suffix)
    source.touch()
    calls = []

    def inspect(path):
        calls.append(path)
        return core.models.Playlist(path, chapter_count=3)

    monkeypatch.setattr(core.sources, 'inspect_playlist', inspect)
    assert core.sources.find_sources(source) == [source]
    assert [p.path for p in core.sources.scan_source(source)] == [source]
    assert calls == [source]


def test_folder_matroska_sources_are_sorted_and_top_level_only(tmp_path, monkeypatch):
    files = [tmp_path / name for name in ['title_t02.mkv', 'title_t00.MKV', 'title_t01.mka']]
    for path in files:
        path.touch()
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'hidden.mkv').touch()
    (tmp_path / 'not-a-file.mk3d').mkdir()
    (tmp_path / 'notes.txt').touch()
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p, **_: core.models.Playlist(p))
    assert core.sources.find_sources(tmp_path) == sorted(files)
    assert [p.path for p in core.sources.scan_source(tmp_path)] == sorted(files)


@pytest.mark.parametrize('with_playlist', [True, False])
def test_bdmv_takes_precedence_even_without_playlists(tmp_path, monkeypatch, with_playlist):
    folder = tmp_path / 'BDMV' / 'PLAYLIST'
    folder.mkdir(parents=True)
    expected = []
    if with_playlist:
        playlist = folder / '00001.mpls'
        playlist.touch()
        expected = [playlist]
    (tmp_path / 'title_t00.mkv').touch()
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p, **_: core.models.Playlist(p))
    assert core.sources.find_sources(tmp_path) == expected
    assert [p.path for p in core.sources.scan_source(tmp_path)] == expected


def test_unsupported_and_empty_sources(tmp_path, monkeypatch):
    def unexpected(path):
        pytest.fail(f'Unexpected inspection: {path}')

    monkeypatch.setattr(core.sources, 'inspect_playlist', unexpected)
    assert core.sources.scan_source(tmp_path) == []
    other = tmp_path / 'concert.mp4'
    other.touch()
    for source in [other, tmp_path / 'missing.mkv', tmp_path]:
        assert core.sources.find_sources(source) == []
        assert core.sources.scan_source(source) == []


def test_mkv_filename_drives_album_output_and_metadata(tmp_path):
    source = tmp_path / 'Dire Straits - Brothers In Arms (1985) [DVD].mkv'
    source.touch()
    name_path = core.sources.source_name_path(source)
    assert name_path.name == 'Dire Straits - Brothers In Arms (1985) [DVD]'
    assert core.naming.guess_artist_album_year(name_path) == ('Dire Straits', 'Brothers In Arms', 1985)
    assert logic.album_output(str(source), str(tmp_path / 'library')) == (
        tmp_path / 'library' / 'Dire Straits - Brothers In Arms (1985)')
    # A folder with a Matroska suffix still follows the original folder rules.
    folder = tmp_path / 'Album.mkv'
    folder.mkdir()
    assert core.sources.source_name_path(folder) == folder
    assert logic.album_output(str(folder), str(tmp_path / 'library')).name == 'Album.mkv'


@pytest.mark.parametrize('as_url', [False, True])
def test_set_source_scans_mkv_file(backend, tmp_path, monkeypatch, as_url):
    source = tmp_path / 'concert.MKV'
    source.touch()
    calls = []
    monkeypatch.setattr(backend.disc, 'scan', lambda: calls.append(backend.state['source']))
    backend.disc.setSource(QUrl.fromLocalFile(str(source)).toString() if as_url else str(source))
    assert [Path(path) for path in calls] == [source]


def test_backend_mkv_scan_uses_parent_sidecars_and_filename(backend, qt_app, tmp_path, monkeypatch):
    source = tmp_path / 'Dire Straits - Brothers In Arms (1985) [DVD].mkv'
    source.touch()
    sidecar = tmp_path / 'tracks.txt'
    sidecar.write_text('One\nTwo', encoding='utf-8')
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p, **_: core.models.Playlist(p, chapter_count=2))
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: [core.models.Chapter(1, 0), core.models.Chapter(2, 60)])
    backend.disc.setSource(str(source))
    wait_idle(backend, qt_app)
    assert backend.state['sidecars'] == [str(sidecar)]
    assert backend.state['artist'] == 'Dire Straits'
    assert backend.state['album'] == 'Brothers In Arms'
    assert backend.disc.playlist_model.rows[0]['label'] == source.name
    assert backend.disc.playlist.path == source


def test_backend_scores_multiple_mkv_candidates(backend, qt_app, tmp_path, monkeypatch):
    short, concert = tmp_path / 'title_t00.mkv', tmp_path / 'title_t01.mkv'
    short.touch()
    concert.touch()
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p, **_: core.models.Playlist(
        p, chapter_count=12 if p == concert else 1, duration_seconds=3600 if p == concert else 30))
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: [])
    backend.disc.setSource(str(tmp_path))
    wait_idle(backend, qt_app)
    assert [s.playlist.path for s in backend.disc.playlists] == [concert, short]
    assert backend.disc.playlist.path == concert
