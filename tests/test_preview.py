import struct
import time
from pathlib import Path

import extractor as x
import preview
import core.sources
import core.tools


def write_mpls(path: Path, items):
    """Minimal MPLS: header, PlayList with PlayItems (clip, in, out in 45 kHz ticks)."""
    body = b''
    for clip, in_t, out_t in items:
        item = clip.encode() + b'M2TS' + b'\x00\x01' + b'\x00' + struct.pack('>II', in_t, out_t) + b'\x00' * 8
        body += struct.pack('>H', len(item)) + item
    playlist = struct.pack('>I', 6 + len(body)) + b'\x00\x00' + struct.pack('>HH', len(items), 0) + body
    header = b'MPLS0200' + struct.pack('>III', 40, 0, 0) + b'\x00' * 20
    path.write_bytes(header + playlist)


def test_play_items_map_chapter_time_to_clip_offsets(tmp_path):
    mpls = tmp_path / '00001.mpls'
    write_mpls(mpls, [('00001', 4200 * 45000, 4500 * 45000), ('00002', 100 * 45000, 160 * 45000)])
    items = preview.read_play_items(mpls)
    assert [(i.clip, i.in_seconds, i.length) for i in items] == [('00001', 4200, 300), ('00002', 100, 60)]
    assert preview.locate(items, 10)[1] == 10
    item, offset = preview.locate(items, 310)
    assert (item.clip, offset) == ('00002', 10)


def test_blu_ray_clip_seeks_inside_the_m2ts_and_maps_the_pid(tmp_path, monkeypatch):
    playlist_dir = tmp_path / 'BDMV' / 'PLAYLIST'
    stream_dir = tmp_path / 'BDMV' / 'STREAM'
    playlist_dir.mkdir(parents=True)
    stream_dir.mkdir()
    (stream_dir / '00001.m2ts').write_bytes(b'')
    write_mpls(playlist_dir / '00001.mpls', [('00001', 4200 * 45000, 4500 * 45000)])
    monkeypatch.setattr(preview, '_start_time', lambda path: 4199.5)   # clock starts just before the in-point
    track = x.Track(1, 'audio', 'PCM', stream_id=0x1100)
    args, length = preview.clip_input(playlist_dir / '00001.mpls', track, 0, 250, 120)
    assert args[:2] == ['-ss', '250.500'] and args[-2:] == ['-map', '0:i:0x1100']
    assert length == 50          # stays inside the clip
    mkv_args, _ = preview.clip_input(tmp_path / 'concert.mkv', x.Track(3, 'audio', 'FLAC'), 1, 60, 30)
    assert mkv_args[-2:] == ['-map', '0:3']


def wait_for(qt_app, condition, seconds=5):
    end = time.time() + seconds
    while not condition() and time.time() < end:
        qt_app.processEvents()
        time.sleep(0.01)
    return condition()


def test_backend_previews_a_chapter_and_prefetches_the_next(backend, qt_app, monkeypatch):
    from test_backend import setup_disc
    setup_disc(backend)
    rendered = []

    def fake_render(source, track, audio_index, start, end, output, cancel_event=None):
        rendered.append((start, end, track.track_id))
        output.write_bytes(b'fLaC' + b'\x00' * 2048)
        return output

    monkeypatch.setattr(preview, 'render', fake_render)
    monkeypatch.setattr(preview, 'clip_peaks', lambda clip: [0.5, 1.0])
    backend.disc.setOutputFormat('flac')               # audio mode: stereo clip, next chapter prefetched
    backend.preview.previewChapter(1, -1)
    assert backend.state['previewLoading'] and backend.state['previewRow'] == 1
    assert wait_for(qt_app, lambda: backend.state['previewUrl'] != '')
    assert not backend.state['previewLoading']
    first = backend.disc.chapters[1]
    assert rendered[0][:2] == (first.start_seconds, first.end_seconds)
    assert wait_for(qt_app, lambda: len(rendered) == 2)          # next chapter decoded in the background
    rendered_before = len(rendered)
    backend.preview.previewStep(1)
    assert backend.state['previewRow'] == 2 and backend.state['previewUrl'] and not backend.state['previewLoading']
    wait_for(qt_app, lambda: len(rendered) > rendered_before, 1)
    backend.preview.stopPreview()
    assert backend.state['previewRow'] == -1 and backend.state['previewUrl'] == ''


def test_preview_errors_are_reported_on_the_bar(backend, qt_app, monkeypatch):
    from test_backend import setup_disc
    setup_disc(backend)

    def broken(*_args, **_kwargs):
        raise RuntimeError('ffmpeg failed\nInvalid data found when processing input')

    monkeypatch.setattr(preview, 'render', broken)
    monkeypatch.setattr(preview, 'render_video', broken)
    backend.preview.previewChapter(0, -1)
    assert wait_for(qt_app, lambda: backend.state['previewError'] != '')
    assert backend.state['previewError'] == 'Invalid data found when processing input'
    assert not backend.state['previewLoading']


def test_no_preview_while_busy(backend):
    from test_backend import setup_disc
    setup_disc(backend)
    backend.put(busy=True)
    backend.preview.previewChapter(0, -1)
    assert backend.state['previewRow'] == -1


def test_playlist_length_comes_from_play_items_when_mkvmerge_has_none(tmp_path, monkeypatch):
    import json
    import subprocess
    from gui import logic
    mpls = tmp_path / '00001.mpls'
    write_mpls(mpls, [('00001', 189000000, 559855485), ('00002', 189000000, 189360360)])
    output = json.dumps({'tracks': [], 'chapters': [{'num_entries': 43}], 'container': {'properties': {}}})
    monkeypatch.setattr(core.tools, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, output, ''))
    monkeypatch.setattr(core.sources, '_enrich_bitrates_ffprobe', lambda pl: None)
    playlist = x.inspect_playlist(mpls)
    assert round(playlist.duration_seconds, 2) == 8249.24
    assert logic.format_length(playlist.duration_seconds) == '2:17:29'
    assert logic.format_length(30.03) == '00:30'


def test_video_mode_previews_with_picture_and_waveform(backend, qt_app, monkeypatch):
    from test_backend import setup_disc
    setup_disc(backend)
    calls = []

    def fake_video(source, track, audio_index, video, start, end, output, cancel_event=None):
        calls.append(('video', video.track_id))
        output.write_bytes(b'\x1aE' + b'\x00' * 2048)
        return output

    def fake_audio(source, track, audio_index, start, end, output, cancel_event=None):
        calls.append(('audio', None))
        output.write_bytes(b'fLaC' + b'\x00' * 2048)
        return output

    monkeypatch.setattr(preview, 'render_video', fake_video)
    monkeypatch.setattr(preview, 'render', fake_audio)
    monkeypatch.setattr(preview, 'clip_peaks', lambda clip: [0.25, 0.75, 0.5])
    assert backend.state['outputFormat'] == 'mkv' and backend.state['keepVideo']
    backend.preview.previewChapter(0, -1)
    assert wait_for(qt_app, lambda: backend.state['previewUrl'] != '')
    assert backend.state['previewVideo'] and backend.state['previewUrl'].endswith('-v.mkv')
    assert backend.preview.previewWave == [0.25, 0.75, 0.5]
    assert calls == [('video', backend.disc.playlist.video_track.track_id)]   # no prefetch of big video clips
    backend.disc.setOutputFormat('flac')                                      # switching mode restarts as audio
    assert wait_for(qt_app, lambda: backend.state['previewUrl'].endswith('.flac'))
    assert not backend.state['previewVideo']
    backend.preview.stopPreview()


def test_listening_from_the_paste_dialog_is_sound_only_in_video_mode(backend, qt_app, monkeypatch):
    from test_backend import setup_disc
    setup_disc(backend)
    made = []
    monkeypatch.setattr(preview, 'render', lambda source, track, audio_index, start, end, output, cancel_event=None:
                        (made.append('audio'), output.write_bytes(b'fLaC' + b'\x00' * 2048), output)[2])
    monkeypatch.setattr(preview, 'render_video', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no video')))
    monkeypatch.setattr(preview, 'clip_peaks', lambda clip: [])
    assert backend.state['outputFormat'] == 'mkv' and backend.state['keepVideo']
    backend.preview.listenChapter(1)
    assert wait_for(qt_app, lambda: backend.state['previewUrl'].endswith('.flac'))
    assert backend.state['previewRow'] == 1 and not backend.state['previewVideo'] and made[0] == 'audio'
    backend.preview.stopPreview()
    assert backend.preview.preview_wants_video()          # the workspace preview shows the picture again


def test_disc_waveform_is_cached_and_follows_the_switch(backend, qt_app, monkeypatch, tmp_path):
    from test_backend import setup_disc
    setup_disc(backend)
    backend.smoke = False
    monkeypatch.setattr(type(backend.preview), 'WAVE_CACHE', tmp_path / 'waves')
    runs = []

    def fake_peaks(source, track, index, total, progress=None, cancel_event=None, ripple=None):
        runs.append(total)
        progress(0.5)
        return [0.1, 0.9, 0.4]

    monkeypatch.setattr(preview, 'disc_peaks', fake_peaks)
    backend.preview.start_waveform()
    assert wait_for(qt_app, lambda: backend.state['waveState'] == 'ready')
    assert backend.preview.waveform == [0.1, 0.9, 0.4] and len(runs) == 1
    backend.preview.start_waveform()                       # second time: from the cache, no disc read
    assert backend.state['waveState'] == 'ready' and len(runs) == 1
    backend.setPreference('waveform', 'false')
    assert backend.preview.waveform == [] and backend.state['waveState'] == 'off'
    backend.setPreference('waveform', 'true')
    assert backend.state['waveState'] == 'ready'


def test_clip_peaks_and_disc_peaks_measure_loudness(tmp_path, monkeypatch):
    import array
    samples = array.array('h', [0, 16384, -32768, 100] * 1000)
    monkeypatch.setattr(preview, '_run_bytes', lambda args, timeout=300: samples.tobytes())
    peaks = preview.clip_peaks(tmp_path / 'clip.flac', buckets=4)
    assert len(peaks) == 4 and all(p == 1.0 for p in peaks)

    class FakeProcess:
        def __init__(self, data):
            import io
            self.stdout = io.BytesIO(data)
        def wait(self, timeout=None):
            return 0
        def poll(self):
            return 0
    quiet_then_loud = array.array('h', [100] * 400 + [32767] * 400)    # 1 s quiet, 1 s loud at 400 Hz
    monkeypatch.setattr(preview.subprocess, 'Popen', lambda *a, **k: FakeProcess(quiet_then_loud.tobytes()))
    seen = []
    disc = preview.disc_peaks(Path('concert.mkv'), x.Track(1, 'audio', 'PCM'), 0, 2, seen.append)
    assert disc == [0.003, 0.003, 1.0, 1.0] and seen
