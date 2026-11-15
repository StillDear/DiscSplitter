"""Defects found in the codebase review, each pinned by the smallest case that showed it."""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import core.jobs
import core.models
import core.sources
import core.tools
import core.tracklist
from core import metadata_sources, setlist
from gui import settings


def chapters(lengths):
    out, start = [], 0.0
    for index, length in enumerate(lengths, 1):
        out.append(core.models.Chapter(index, start, start + length))
        start += length
    return out


def test_catalogue_tracks_align_by_length_past_talk_chapters():
    # intro, two songs, MC, four songs: an album's running start times drift from the MC on.
    disc = chapters([60, 240, 250, 180, 260, 245, 255, 300])
    tracks = [metadata_sources.TrackInfo(f'Song {i}', seconds=s) for i, s in enumerate([240, 250, 260, 245, 255, 300], 1)]
    entries = metadata_sources.tracklist_entries(tracks)
    assert all(e.start_seconds is None for e in entries)
    result = core.tracklist.match_tracklist_to_chapters(disc, entries)
    assert [m.name or None for m in result.matches] == [None, 'Song 1', 'Song 2', None, 'Song 3', 'Song 4', 'Song 5', 'Song 6']


def test_order_mode_is_honoured_for_timed_entries():
    disc = chapters([100, 100])
    timed = [core.tracklist.TracklistEntry('A', start_seconds=500.0), core.tracklist.TracklistEntry('B', start_seconds=900.0)]
    result = core.tracklist.match_tracklist_to_chapters(disc, timed, mode='order')
    assert [m.name for m in result.matches] == ['A', 'B']


def test_multi_disc_release_is_narrowed_to_one_disc():
    track = metadata_sources.TrackInfo
    info = metadata_sources.AlbumInfo('musicbrainz', discs=[[track('a'), track('b')], [track('c'), track('d'), track('e')]])
    info.tracks = [t for disc in info.discs for t in disc]
    assert [t.title for t in info.disc_tracks(chapter_count=3)] == ['c', 'd', 'e']
    assert [t.title for t in info.disc_tracks(chapter_count=3, disc_number=1)] == ['a', 'b']


def test_numeric_file_names_do_not_sink_an_mkv():
    feature = core.models.Playlist(Path('20240101.mkv'), [core.models.Track(0, 'video', 'AVC'),
                                                         core.models.Track(1, 'audio', 'FLAC', channels=2)], 20, 5400)
    bonus = core.models.Playlist(Path('bonus.mkv'), [core.models.Track(1, 'audio', 'AC-3', channels=2)], 0, 120)
    assert core.sources.score_playlists([bonus, feature])[0].playlist is feature


def test_scoring_reasons_carry_their_meaning():
    playlist = core.models.Playlist(Path('00001.mpls'), [core.models.Track(1, 'audio', 'TrueHD Atmos')], 9, 3600)
    reasons = core.sources.score_playlists([playlist])[0].reasons
    assert [r.code for r in reasons] == ['atmos', 'chapters', 'no_video', 'minutes']
    assert reasons[1] == '9 chapters' and reasons[1].value == '9'


def test_a_title_made_of_digits_survives_a_text_set_list():
    parsed = setlist.parse('Tonight, Tonight\n1979\nZero\nMuzzle')
    assert [line.title for line in parsed.items()] == ['Tonight, Tonight', '1979', 'Zero', 'Muzzle']


def test_chapter_mappings_saved_under_the_old_name_still_load():
    text = json.dumps({'format': 'DiscTrackSplitter.chapter-titles.v1', 'chapters': [{'chapter': 2, 'title': 'Two'}]})
    entries = core.tracklist.parse_exported_tracklist(text)
    assert [(e.index, e.name) for e in entries] == [(2, 'Two')]


def test_the_old_settings_folder_is_adopted_once(tmp_path, monkeypatch):
    legacy = tmp_path / settings.LEGACY_FOLDER
    legacy.mkdir()
    (legacy / 'settings.json').write_text(json.dumps({'language': 'en'}), encoding='utf-8')
    (legacy / 'logs').mkdir()
    monkeypatch.setattr(settings, 'SETTINGS_PATH', tmp_path / '.disc_splitter' / 'settings.json')
    assert settings.load()['language'] == 'en'
    assert (tmp_path / '.disc_splitter' / 'logs').is_dir() and not legacy.exists()


def test_tool_check_covers_mkvpropedit(monkeypatch):
    monkeypatch.setattr(core.tools, 'verify_tool_at_path', lambda path, name, timeout=10.0: (name != 'mkvpropedit', ''))
    found = core.tools.check_tools()
    assert found['mkvmerge'] is True and found['mkvpropedit'] is False
    assert core.tools.tool_family('mkvpropedit') == ('mkvmerge', 'mkvextract', 'mkvpropedit')


def test_sibling_tools_are_found_next_to_the_chosen_one(tmp_path):
    for name in ('ffmpeg.exe', 'ffprobe.exe'):
        (tmp_path / name).touch()
    assert core.tools.guess_sibling_tool_path(str(tmp_path / 'ffmpeg.exe'), 'ffprobe') == str(tmp_path / 'ffprobe.exe')
    assert core.tools.guess_sibling_tool_path(str(tmp_path / 'ffmpeg.exe'), 'mkvmerge') is None


def test_cancelling_a_streamed_tool_ends_it():
    cancel = threading.Event()
    started = []
    real_popen = subprocess.Popen

    class Recorded(real_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            started.append(self)

    core.tools.subprocess.Popen = Recorded
    try:
        threading.Timer(0.3, cancel.set).start()
        with pytest.raises(core.jobs.JobCancelled):
            core.tools.run_streaming([sys.executable, '-c', 'import time; time.sleep(30)'], lambda line: None, cancel)
    finally:
        core.tools.subprocess.Popen = real_popen
    assert started[0].poll() is not None


def test_playlists_are_inspected_side_by_side_in_order(tmp_path, monkeypatch):
    playlist_dir = tmp_path / 'BDMV' / 'PLAYLIST'
    playlist_dir.mkdir(parents=True)
    for number in range(6):
        (playlist_dir / f'{number:05d}.mpls').touch()
    threads = set()

    def inspect(path):
        threads.add(threading.get_ident())
        time.sleep(0.05)
        return core.models.Playlist(path)

    monkeypatch.setattr(core.sources, 'inspect_playlist', inspect)
    found = core.sources.scan_disc_folder(tmp_path)
    assert [p.path.name for p in found] == [f'{n:05d}.mpls' for n in range(6)]
    assert len(threads) > 1


def test_engine_errors_are_worded_in_the_interface_language(backend):
    error = core.jobs.tool_failed('mkvmerge', 'Error: the file could not be opened', 'on chapter 3')
    assert str(error).startswith('mkvmerge failed on chapter 3:')        # logs keep the English message
    backend.cfg['language'] = 'zh'
    text = backend.error_text(error)
    assert text.startswith('mkvmerge 运行出错。') and text.endswith('the file could not be opened')
    assert backend.error_text(ValueError('plain')) == 'plain'


def test_a_controller_only_writes_its_own_state(backend):
    with pytest.raises(AssertionError):
        backend.disc.put(mbRelease='x')          # the titles controller's
    backend.disc.put(album='Live')
    assert backend.state['album'] == 'Live'


def test_network_jobs_leave_the_selection_editable(backend, qt_app):
    from test_backend import setup_disc, wait_idle
    setup_disc(backend)
    gate = threading.Event()
    assert backend.task(lambda progress: gate.wait(5), lambda result: None, blocking=False)
    assert backend.state['working'] and not backend.state['busy']
    backend.disc.editTitle(0, 'Typed while searching')
    assert backend.disc.chapter_model.rows[0]['title'] == 'Typed while searching'
    assert backend.task(lambda progress: None, lambda result: None) is False     # but no second job
    gate.set()
    wait_idle(backend, qt_app)


def test_only_the_first_editions_own_chapters_are_read(monkeypatch):
    from core import chapter_marks
    xml = ('<Chapters><EditionEntry>'
           '<ChapterAtom><ChapterTimeStart>00:00:00.000</ChapterTimeStart>'
           '<ChapterAtom><ChapterTimeStart>00:00:30.000</ChapterTimeStart></ChapterAtom></ChapterAtom>'
           '<ChapterAtom><ChapterTimeStart>00:04:00.000</ChapterTimeStart></ChapterAtom>'
           '</EditionEntry><EditionEntry>'
           '<ChapterAtom><ChapterTimeStart>00:00:00.000</ChapterTimeStart></ChapterAtom>'
           '</EditionEntry></Chapters>')
    monkeypatch.setattr(core.tools, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0, xml, ''))
    found = chapter_marks.read_chapters(Path('x.mkv'))
    assert [(c.index, c.start_seconds) for c in found] == [(1, 0.0), (2, 240.0)]


def test_a_dvd_title_is_cut_by_its_copys_track_numbers(monkeypatch):
    from core import dvd
    title = core.models.Playlist(Path('VIDEO_TS/VTS_01_0.IFO'), [core.models.Track(0, 'video', 'MPEG-2'),
                                 core.models.Track(2, 'audio', 'AC-3'), core.models.Track(3, 'audio', 'LPCM')])
    monkeypatch.setattr(dvd, 'inspect', lambda path: title)       # stream 1 (navigation data) is not copied
    assert [t.track_id for t in dvd.in_copy(title.path, title.tracks[2:])] == [2]
    assert [t.track_id for t in dvd.in_copy(title.path, title.tracks)] == [0, 1, 2]


def test_long_titles_are_shortened_to_fit_windows_paths(tmp_path):
    from core import naming
    folder = tmp_path / ('d' * 60)
    planned = naming.plan_output_files([core.models.Chapter(1, 0, 10, name='长' * 300),
                                        core.models.Chapter(2, 10, 20, name='长' * 301)], folder)
    names = [p.path.name for p in planned]
    assert len(set(names)) == 2
    assert all(len(name) <= naming.MAX_STEM + 8 for name in names)
    assert all(len(str(p.path)) <= max(naming.MAX_PATH, len(str(folder)) + naming.MIN_STEM + 12) for p in planned)


def test_a_damaged_setting_falls_back_to_its_default(tmp_path, monkeypatch):
    path = tmp_path / '.disc_splitter' / 'settings.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'net_timeout': 'soon', 'waveform': 'yes', 'language': 'en', 'layout': []}), encoding='utf-8')
    monkeypatch.setattr(settings, 'SETTINGS_PATH', path)
    loaded = settings.load()
    assert (loaded['net_timeout'], loaded['waveform'], loaded['language'], loaded['layout']) == ('15', True, 'en', {})
    path.write_text('[1, 2]', encoding='utf-8')
    assert settings.load() == settings.DEFAULTS


def test_a_resumed_job_shows_its_own_playlist_card(backend, qt_app, monkeypatch, tmp_path):
    from test_backend import setup_disc, wait_idle
    from test_logic import manifest
    playlist = setup_disc(backend)
    backend.put(source=str(tmp_path / 'disc'))
    backend.disc.playlists = core.sources.score_playlists([core.models.Playlist(Path('other/00002.mpls'), [], 1, 60)])
    output = tmp_path / 'Album'
    m = manifest(output, 'cancelled')
    m.audio_track_id = 1
    core.manifest.write_manifest(output / '_work', m)
    backend.exporter.flow.manifest = m
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda path: playlist)
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **k: [])
    backend.exporter.resume()
    wait_idle(backend, qt_app)
    assert [s.playlist.path for s in backend.disc.playlists] == [playlist.path]
    assert [r['chosen'] for r in backend.disc.playlist_model.rows] == [True]
    assert backend.disc.scanned_source == str(tmp_path / 'disc')
