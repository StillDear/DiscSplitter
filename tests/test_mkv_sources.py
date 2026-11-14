from pathlib import Path
import json
import shutil
import subprocess
import threading

import pytest
from PySide6.QtCore import QUrl

import extractor
from gui import logic
from test_backend import wait_idle
import core.chapter_marks
import core.sources


@pytest.mark.skipif(not all(shutil.which(tool) for tool in extractor.TOOL_PATHS),
                    reason='MKVToolNix and FFmpeg are required')
@pytest.mark.parametrize('keep_video', [True, False])
def test_selected_chapters_keep_multiple_tracks_through_resume(tmp_path, monkeypatch, keep_video):
    for tool in extractor.TOOL_PATHS:
        monkeypatch.setitem(extractor.TOOL_PATHS, tool, shutil.which(tool))
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
        '-c:v', 'mpeg2video', '-g', '1', '-c:a', 'flac', '-c:s', 'copy',
        '-metadata:s:a:1', 'title=Stereo', '-metadata:s:a:2', 'title=Alternate',
        '-metadata:s:a:2', 'language=jpn', '-metadata:s:s:1', 'language=chi',
        '-disposition:a:0', 'default', '-disposition:a:1', '0', '-disposition:a:2', '0',
        '-disposition:s:0', '0', '-disposition:s:1', 'forced', str(source),
    ], check=True, capture_output=True)
    playlist = extractor.inspect_playlist(source)
    audio_ids = [t.track_id for t in playlist.audio_tracks[1:]]
    subtitle_ids = [t.track_id for t in playlist.subtitle_tracks]
    output = tmp_path / 'output'
    work = output / '_work'
    cancel = threading.Event()

    def progress(message):
        if message.startswith('Splitting chapter 3:'):
            cancel.set()

    with pytest.raises(extractor.JobCancelled):
        extractor.run_full_pipeline(
            playlist, playlist.audio_tracks[1], {3: 'Finale'}, work, output,
            audio_track_ids=audio_ids, subtitle_track_ids=subtitle_ids, chapter_indices=[1, 3],
            cancel_event=cancel, progress_cb=progress, keep_video=keep_video,
        )
    manifest = extractor.read_manifest(work)
    first = Path(manifest.completed_outputs[0])
    assert first.name == 'Track 01.mkv'
    assert manifest.audio_track_ids == audio_ids
    assert manifest.subtitle_track_ids == subtitle_ids
    assert manifest.chapter_indices == [1, 3]
    assert manifest.number_filenames is False
    assert manifest.renumber_tracks is True
    assert manifest.video_track_id == (playlist.video_track.track_id if keep_video else None)
    first_modified = first.stat().st_mtime_ns

    if not keep_video:
        # Resume must honour the saved video setting even when a new remux is needed.
        (work / '_audio_extracted.mkv').unlink()
    paths = extractor.run_full_pipeline(
        playlist, playlist.audio_tracks[0], {}, work, output, resume=True, chapter_indices=[2],
        keep_video=not keep_video,
    )
    assert [p.name for p in paths] == ['Track 01.mkv', 'Finale.mkv']
    assert first.stat().st_mtime_ns == first_modified
    assert set(output.glob('*.mkv')) == set(paths)
    for track_number, path in enumerate(paths, start=1):
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                         '-of', 'json', str(path)], encoding='utf-8')
        media = json.loads(probe)
        assert {k.lower(): v for k, v in media['format']['tags'].items()}['track'] == f'{track_number}/2'
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


@pytest.mark.parametrize('suffix', ['.mkv', '.MKV', '.mk3d', '.MK3D', '.mka', '.MKA'])
def test_single_matroska_source(tmp_path, monkeypatch, suffix):
    source = tmp_path / ('concert' + suffix)
    source.touch()
    calls = []

    def inspect(path):
        calls.append(path)
        return extractor.Playlist(path, chapter_count=3)

    monkeypatch.setattr(core.sources, 'inspect_playlist', inspect)
    assert extractor.find_sources(source) == [source]
    assert [p.path for p in extractor.scan_source(source)] == [source]
    assert calls == [source]


def test_folder_matroska_sources_are_sorted_and_top_level_only(tmp_path, monkeypatch):
    files = [tmp_path / name for name in ['title_t02.mkv', 'title_t00.MKV', 'title_t01.mka']]
    for path in files:
        path.touch()
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'hidden.mkv').touch()
    (tmp_path / 'not-a-file.mk3d').mkdir()
    (tmp_path / 'notes.txt').touch()
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p: extractor.Playlist(p))
    assert extractor.find_sources(tmp_path) == sorted(files)
    assert [p.path for p in extractor.scan_source(tmp_path)] == sorted(files)


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
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p: extractor.Playlist(p))
    assert extractor.find_sources(tmp_path) == expected
    assert [p.path for p in extractor.scan_source(tmp_path)] == expected


def test_unsupported_and_empty_sources(tmp_path, monkeypatch):
    def unexpected(path):
        pytest.fail(f'Unexpected inspection: {path}')

    monkeypatch.setattr(core.sources, 'inspect_playlist', unexpected)
    assert extractor.scan_source(tmp_path) == []
    other = tmp_path / 'concert.mp4'
    other.touch()
    for source in [other, tmp_path / 'missing.mkv', tmp_path]:
        assert extractor.find_sources(source) == []
        assert extractor.scan_source(source) == []


def test_mkv_filename_drives_album_output_and_metadata(tmp_path):
    source = tmp_path / 'Dire Straits - Brothers In Arms (1985) [DVD].mkv'
    source.touch()
    name_path = extractor.source_name_path(source)
    assert name_path.name == 'Dire Straits - Brothers In Arms (1985) [DVD]'
    assert extractor.guess_artist_album_year(name_path) == ('Dire Straits', 'Brothers In Arms', 1985)
    assert logic.album_output(str(source), str(tmp_path / 'library')) == (
        tmp_path / 'library' / 'Dire Straits - Brothers In Arms (1985)')
    # A folder with a Matroska suffix still follows the original folder rules.
    folder = tmp_path / 'Album.mkv'
    folder.mkdir()
    assert extractor.source_name_path(folder) == folder
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
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p: extractor.Playlist(p, chapter_count=2))
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: [extractor.Chapter(1, 0), extractor.Chapter(2, 60)])
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
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p: extractor.Playlist(
        p, chapter_count=12 if p == concert else 1, duration_seconds=3600 if p == concert else 30))
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: [])
    backend.disc.setSource(str(tmp_path))
    wait_idle(backend, qt_app)
    assert [s.playlist.path for s in backend.disc.playlists] == [concert, short]
    assert backend.disc.playlist.path == concert
