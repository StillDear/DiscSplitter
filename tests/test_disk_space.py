"""The disk space estimate and the question asked before an export that may not fit."""
from pathlib import Path

import core.models
from gui.export_flow import Phase
from test_backend import setup_disc, wait_idle
import core.pipeline
import core.sources
import core.space

MB = 1024 * 1024


def playlist(video=True):
    tracks = [core.models.Track(1, 'audio', 'LPCM', channels=2, sample_rate=48000, bits_per_sample=24),   # 288 000 B/s
              core.models.Track(2, 'audio', 'AC-3', bitrate_kbps=640)]                                       # 80 000 B/s
    if video:
        tracks.insert(0, core.models.Track(0, 'video', 'AVC'))
    return core.models.Playlist(Path('disc/BDMV/PLAYLIST/00001.mpls'), tracks, 3, 300)


CHAPTERS = [core.models.Chapter(1, 0, 100), core.models.Chapter(2, 100, 200), core.models.Chapter(3, 200, None)]


def expected(raw):
    return int(raw * core.space.SPACE_MARGIN + core.space.SPACE_RESERVE)


def test_video_export_adds_the_picture_from_the_source_average():
    # Source: 300 s at 4 MB/s; known audio 368 000 B/s, so the rest is 4 MB/s - 368 000.
    size = 300 * 4 * MB
    rest = 4 * MB - 368000
    got = core.space.estimate_export_bytes(playlist(), CHAPTERS[:2], audio_track_ids=[1], keep_video=True,
                                  container='mkv', source_size=size)
    assert got == expected((288000 + rest) * 200)


def test_audio_only_and_open_ended_last_chapter():
    got = core.space.estimate_export_bytes(playlist(), CHAPTERS[2:], audio_track_ids=[1, 2], keep_video=False,
                                  container='mkv', source_size=None)
    assert got == expected(368000 * 100)       # the last chapter runs to the end of the 300 s playlist


def test_flac_counts_the_extracted_audio_and_compressed_output():
    got = core.space.estimate_export_bytes(playlist(), CHAPTERS[:1], audio_track_ids=[1], keep_video=False,
                                  container='flac', source_size=None)
    assert got == expected(288000 * 300 + 288000 * core.space.FLAC_RATIO * 100)


def test_packed_lossless_without_a_bitrate_is_estimated_from_its_format():
    dts = core.models.Track(2, 'audio', 'DTS-HD Master Audio', channels=6, sample_rate=96000)
    assert core.space.audio_rate_bytes(dts) == 96000 * 24 * 6 / 8 * core.space.LOSSLESS_PACKED_RATIO
    truehd = core.models.Track(3, 'audio', 'TrueHD Atmos', channels=8, sample_rate=48000, bits_per_sample=24)
    assert core.space.audio_rate_bytes(truehd) == 48000 * 24 * 8 / 8 * core.space.LOSSLESS_PACKED_RATIO   # not taken as raw PCM
    assert core.space.audio_rate_bytes(core.models.Track(4, 'audio', 'AC-3', channels=6, sample_rate=48000)) is None


def test_unknown_rates_skip_the_check_instead_of_guessing():
    unknown = core.models.Playlist(Path('a.mpls'), [core.models.Track(0, 'video', 'AVC'), core.models.Track(1, 'audio', 'TrueHD')], 1, 100)
    assert core.space.estimate_export_bytes(unknown, CHAPTERS[:1], audio_track_ids=[1], keep_video=False,
                                   container='mkv', source_size=10 * MB) is None
    assert core.space.estimate_export_bytes(playlist(), CHAPTERS[:1], audio_track_ids=[1], keep_video=True,
                                   container='mkv', source_size=None) is None


def test_source_size_sums_the_playlist_clips(tmp_path, monkeypatch):
    stream = tmp_path / 'BDMV' / 'STREAM'
    stream.mkdir(parents=True)
    (stream / '00001.m2ts').write_bytes(b'x' * 300)
    (stream / '00002.m2ts').write_bytes(b'x' * 200)
    mpls = tmp_path / 'BDMV' / 'PLAYLIST' / '00001.mpls'
    monkeypatch.setattr(core.sources, 'read_play_items', lambda p: [core.sources.PlayItem('00001', 0, 10), core.sources.PlayItem('00002', 0, 5),
                                                          core.sources.PlayItem('00001', 10, 20)])
    assert core.space.source_size_bytes(mpls) == 500
    assert core.space.source_size_bytes(tmp_path / 'missing.mkv') is None


def test_free_space_looks_at_the_nearest_existing_folder(tmp_path):
    assert core.space.free_space_bytes(tmp_path / 'not' / 'yet' / 'made') > 0


def test_short_drive_asks_and_export_anyway_continues(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    calls, dialogs = [], []
    backend.dialogRequested.connect(lambda kind, msg: dialogs.append((kind, msg)))
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **kw: calls.append(kw) or [])
    monkeypatch.setattr(core.space, 'estimate_export_bytes', lambda *a, **kw: 50 * 1024 ** 3)
    monkeypatch.setattr(core.space, 'free_space_bytes', lambda folder: 8 * 1024 ** 3)
    backend.exporter.startExport()
    assert dialogs[-1][0] == 'diskSpace' and '50.0 GB' in dialogs[-1][1] and '8.0 GB' in dialogs[-1][1]
    assert backend.exporter.flow.phase is Phase.CONFIRM_SPACE and calls == []
    backend.exporter.exportDespiteSpace()
    wait_idle(backend, qt_app)
    assert len(calls) == 1


def test_dismissing_the_space_question_drops_the_export(backend, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    monkeypatch.setattr(core.space, 'estimate_export_bytes', lambda *a, **kw: 50 * 1024 ** 3)
    monkeypatch.setattr(core.space, 'free_space_bytes', lambda folder: 8 * 1024 ** 3)
    backend.exporter.startExport()
    backend.exporter.cancelExport()
    assert backend.exporter.flow.phase is Phase.IDLE and backend.exporter.flow.pending is None


def test_enough_space_starts_at_once(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    calls, dialogs = [], []
    backend.dialogRequested.connect(lambda kind, msg: dialogs.append(kind))
    seen = {}
    def estimate(pl, chapters, **kw):
        seen['chapters'] = [c.index for c in chapters]
        return 10
    monkeypatch.setattr(core.space, 'estimate_export_bytes', estimate)
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **kw: calls.append(kw) or [])
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    assert dialogs == [] and len(calls) == 1 and seen['chapters'] == [1, 2, 3]


def test_kept_files_are_not_counted(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    album = tmp_path / 'Album'
    album.mkdir()
    (album / 'Track 02.mkv').write_bytes(b'old')
    seen = {}
    monkeypatch.setattr(core.space, 'estimate_export_bytes', lambda pl, ch, **kw: seen.setdefault('chapters', [c.index for c in ch]) and 10)
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **kw: [])
    backend.exporter.startExport()          # asks about the existing file
    backend.exporter.skipExisting()
    wait_idle(backend, qt_app)
    assert seen['chapters'] == [1, 3]
