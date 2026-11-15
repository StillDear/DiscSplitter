from datetime import datetime, timedelta
from pathlib import Path

import pytest

from gui import smoke
import core.models
from gui import backend as backend_module
import core.space


@pytest.fixture
def loaded(backend, tmp_path):
    smoke.populate(backend)
    backend.cfg['recent_exports'] = []
    backend.put(source=str(tmp_path / 'DISC'), output=str(tmp_path / 'out'))
    return backend


def test_estimate_counts_selected_chapters_and_free_space(loaded):
    est = loaded.disc.export_estimate()
    assert est['files'] == 6 and est['duration'] == '30:00'       # six 5-minute chapters
    assert est['size'] and est['free'] and est['enough'] is True
    assert est['folder'].startswith(loaded.state['output'])


def test_estimate_switches_with_the_format(loaded):
    loaded.disc.setKeepVideo(True)
    mkv = loaded.state['exportEstimate']['size']
    loaded.disc.setOutputFormat('flac')
    flac = loaded.state['exportEstimate']['size']
    assert mkv and flac and mkv != flac


def test_estimate_waits_for_chapter_times(loaded):
    # Right after a playlist is picked every chapter is a placeholder at 0:00 with no end.
    loaded.disc.chapters = [core.models.Chapter(i, 0) for i in range(1, 10)]
    est = loaded.disc.export_estimate()
    assert est['files'] == 6 and est['duration'] == '' and est['size'] == '' and est['enough'] is None


def test_estimate_flags_a_drive_that_is_too_full(loaded, monkeypatch):
    monkeypatch.setattr(core.space, 'free_space_bytes', lambda folder: 1_000)
    est = loaded.disc.export_estimate()
    assert est['enough'] is False


def test_output_bytes_flac_and_mkv():
    playlist = core.models.Playlist(path=Path('x.mpls'), duration_seconds=600, chapter_count=2, tracks=[
        core.models.Track(0, 'video', 'AVC', 'V_MPEG4/ISO/AVC'),
        core.models.Track(1, 'audio', 'LPCM', 'A_PCM/INT/BIG', 'eng', 2, '', 48000, 16)])
    chapters = [core.models.Chapter(1, 0, 300), core.models.Chapter(2, 300, None)]
    audio = playlist.audio_tracks
    flac = core.space.estimate_output_bytes(playlist, chapters[:1], audio_tracks=audio, keep_video=False,
                                           container='flac', source_size=None)
    assert flac == int(48000 * 2 * 2 * core.space.FLAC_RATIO * 300)
    # MKV with picture: audio plus the rest of the source's average rate; the last chapter runs to the end.
    mkv = core.space.estimate_output_bytes(playlist, chapters, audio_tracks=audio, keep_video=True,
                                          container='mkv', source_size=600 * 1_000_000)
    assert mkv == pytest.approx(600 * 1_000_000, rel=0.01)
    assert core.space.estimate_output_bytes(playlist, [], audio_tracks=audio, keep_video=False,
                                           container='flac', source_size=None) == 0


def test_source_summary_names_the_source(loaded):
    assert loaded.disc.source_summary().startswith(loaded.tr('ovBdFolder'))
    assert loaded.disc.state['sourceSummary'] == loaded.disc.source_summary()
    loaded.setPreference('language', 'en')
    assert loaded.disc.state['sourceSummary'].startswith(loaded.tr('ovBdFolder'))
    loaded.setPreference('language', 'zh')


def test_playlist_cards_get_one_new_reason():
    from gui import logic
    from core.sources import Reason
    assert logic.headline_reason([Reason('lossless', 'PCM'), Reason('chapters', 36), Reason('video', 'AVC'),
                                  Reason('minutes', 137)]) == 'No Atmos, but best available track is lossless (PCM)'
    assert logic.headline_reason([Reason('atmos', 1), Reason('chapters', 9),
                                  Reason('duplicate', '00001.mpls')]).code == 'duplicate'
    assert logic.headline_reason([Reason('chapters', 9), Reason('minutes', 5)]) == ''


def test_chapter_kinds_need_a_ready_waveform(loaded):
    assert set(loaded.disc.chapter_kind_map()) <= {str(i) for i in range(1, 10)}
    assert loaded.disc.chapter_kind_map()
    loaded.put(waveState='running')
    assert loaded.disc.chapter_kind_map() == {}


def test_recent_exports_newest_first_one_per_folder(loaded, tmp_path):
    folder = tmp_path / 'out' / 'Album'
    folder.mkdir(parents=True)
    loaded.exporter.flow.output = folder
    loaded.put(album='Album')
    loaded.exporter.remember_export(5)
    loaded.exporter.remember_export(7)                 # same folder again: replaces, not duplicates
    assert len(loaded.cfg['recent_exports']) == 1
    row = loaded.state['recentExports'][0]
    assert row['album'] == 'Album' and loaded.tr('today') in row['detail'] and '7' in row['detail']
    loaded.exporter.remember_export(0)                 # nothing exported: not recorded
    assert len(loaded.cfg['recent_exports']) == 1


def test_recent_dates_and_reload(loaded, tmp_path, monkeypatch):
    source = tmp_path / 'DISC'
    source.mkdir()
    old = datetime.now() - timedelta(days=1)
    loaded.cfg['recent_exports'] = [
        dict(album='A', count=3, folder=str(tmp_path / 'gone'), source=str(source), container='mkv',
             when=old.isoformat(timespec='minutes')),
        dict(album='B', count=1, folder=str(tmp_path), source=str(tmp_path / 'missing'), container='flac',
             when='bad')]
    loaded.publish_recent()
    first, second = loaded.state['recentExports']
    assert loaded.tr('yesterday') in first['detail'] and first['canReload']
    assert not second['canReload']

    notices, opened, loads = [], [], []
    monkeypatch.setattr(loaded, 'notify', lambda text, title='error': notices.append(text))
    monkeypatch.setattr(backend_module.QDesktopServices, 'openUrl', lambda url: opened.append(url))
    monkeypatch.setattr(loaded.disc, 'setSource', lambda path: loads.append(path))
    loaded.disc.openRecent(0)                      # its folder was deleted
    loaded.disc.openRecent(1)
    loaded.disc.reloadRecent(0)
    loaded.disc.reloadRecent(1)                    # source gone: ignored
    assert notices == [loaded.tr('recentGone')] and len(opened) == 1 and loads == [str(source)]


def test_playlist_cards_summarise_their_streams(loaded):
    summary = loaded.disc.track_summary(loaded.disc.playlist)
    assert summary.startswith('TrueHD Atmos') and 'LPCM' in summary
    assert summary.endswith(loaded.tr('plSubs').replace('{n}', '1'))
    assert loaded.disc.playlist_model.rows[0]['tracks'] == summary
