import json
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl

from core import dvd
import core.models
import core.naming
import core.pipeline
import core.sources
from core import preview
from test_backend import wait_idle
import core.chapter_marks
import core.split
import core.tools

STREAMS = [
    dict(index=0, codec_type='video', codec_name='mpeg2video', width=720, height=480),
    dict(index=1, codec_type='audio', codec_name='pcm_dvd', channels=2, sample_rate='48000', sample_fmt='s16',
         bits_per_raw_sample='16', tags=dict(language='jpn')),
    dict(index=2, codec_type='audio', codec_name='ac3', channels=6, sample_rate='48000', bit_rate='448000'),
    dict(index=3, codec_type='subtitle', codec_name='dvd_subtitle', tags=dict(language='eng')),
]
CHAPTERS = [dict(start_time='0.0', end_time='177.63'), dict(start_time='177.63', end_time='459.13'),
            dict(start_time='459.13', end_time='600.5')]


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    """ffprobe/ffmpeg stand-in: a disc with two titles; records every command."""
    calls = []

    def run(args, timeout=None, cancel_event=None):
        calls.append(args)
        if args[1:3] == ['-hide_banner', '-demuxers']:
            return subprocess.CompletedProcess(args, 0, ' D  dvdvideo        DVD-Video\n', '')
        title = int(args[args.index('-title') + 1])
        if '-show_streams' in args:
            if title > 2:
                return subprocess.CompletedProcess(args, 1, '{}', f'Title {title} not found')
            chapters = CHAPTERS if title == 1 else CHAPTERS[:1]
            data = dict(streams=STREAMS, chapters=chapters, format=dict(duration=chapters[-1]['end_time']))
            return subprocess.CompletedProcess(args, 0, json.dumps(data), '')
        Path(args[-1]).write_bytes(b'mkv' * 100)       # a remux
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(core.tools, 'run', run)
    dvd._supported.cache_clear()
    dvd._chapters.cache_clear()
    return calls


def make_dvd(folder: Path) -> Path:
    (folder / 'VIDEO_TS').mkdir(parents=True)
    (folder / 'VIDEO_TS' / 'VIDEO_TS.IFO').write_bytes(b'DVDVIDEO-VMG')
    return folder


def test_title_paths_round_trip(tmp_path):
    path = dvd.title_path(tmp_path / 'DISC.ISO', 3)
    assert path.name == 'Title 03.dvdtitle'
    assert dvd.title_of(path) == (tmp_path / 'DISC.ISO', 3)
    assert not dvd.is_title(tmp_path / 'BDMV/PLAYLIST/00001.mpls')
    assert dvd.input_args(path, chapter=2) == ['-f', 'dvdvideo', '-title', '3', '-chapter_start', '2',
                                               '-chapter_end', '2', '-i', str(tmp_path / 'DISC.ISO')]


def test_disc_folder_and_iso_detection(tmp_path):
    disc = make_dvd(tmp_path / 'Concert')
    assert dvd.disc_folder(disc) == disc
    assert dvd.disc_folder(disc / 'VIDEO_TS') == disc        # picking VIDEO_TS itself works too
    assert dvd.disc_folder(tmp_path) is None
    image = tmp_path / 'dvd.iso'
    image.write_bytes(b'\0' * 4096 + b'VIDEO_TS' + b'\0' * 64)
    assert dvd.iso_looks_like_dvd(image)
    image.write_bytes(b'\0' * 4096 + b'BDMV' + b'\0' * 64)
    assert not dvd.iso_looks_like_dvd(image)


def test_scan_lists_every_title_with_its_streams(tmp_path, fake_ffmpeg):
    disc = make_dvd(tmp_path / 'Concert')
    titles = core.sources.scan_source(disc)
    assert [p.path.name for p in titles] == ['Title 01.dvdtitle', 'Title 02.dvdtitle']
    first = titles[0]
    assert first.chapter_count == 3 and first.duration_seconds == pytest.approx(600.5)
    assert [(t.kind, t.codec) for t in first.tracks] == [('video', 'MPEG-2'), ('audio', 'LPCM'), ('audio', 'AC-3'),
                                                          ('subtitles', 'VobSub')]
    lpcm = first.audio_tracks[0]
    assert (lpcm.bits_per_sample, lpcm.bitrate_kbps, lpcm.language) == (16, 1536.0, 'jpn')
    assert first.best_default_audio_track() is lpcm
    chapters = core.chapter_marks.read_chapters_from_source(first.path)
    assert [(c.index, c.start_seconds) for c in chapters] == [(1, 0.0), (2, 177.63), (3, 459.13)]
    assert '-preindex' in fake_ffmpeg[-1]        # chapter times come from the real stream


def test_previews_start_exactly_on_the_chapter(tmp_path, fake_ffmpeg):
    path = dvd.title_path(make_dvd(tmp_path / 'Concert'), 1)
    track = dvd.inspect(path).audio_tracks[0]
    args, _ = preview.clip_input(path, track, 0, 177.63, 60)
    assert args[args.index('-chapter_start') + 1] == '2' and args[-2:] == ['-map', '0:1']
    args, _ = preview.clip_input(path, track, 0, 200.0, 60)        # not a chapter start: a plain seek
    assert '-chapter_start' not in args and args[args.index('-ss') + 1] == '200.000'


def test_remux_rewrites_dvd_lpcm_as_plain_pcm(tmp_path, fake_ffmpeg):
    path = dvd.title_path(make_dvd(tmp_path / 'Concert'), 1)
    title = dvd.inspect(path)
    out = dvd.remux(path, tmp_path / 'work' / 'title.mkv', tracks=[title.audio_tracks[0], title.audio_tracks[1]])
    assert out.is_file()
    args = fake_ffmpeg[-1]
    assert args[args.index('-c:0') + 1] == 'pcm_s16le' and '-c:1' not in args      # AC-3 is copied as is
    assert [args[i + 1] for i, a in enumerate(args) if a == '-map'] == ['0:1', '0:2']


def test_mkv_export_cuts_a_copy_of_the_title(tmp_path, fake_ffmpeg, monkeypatch):
    path = dvd.title_path(make_dvd(tmp_path / 'Concert'), 1)
    title = dvd.inspect(path)
    seen = {}
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source',
                        lambda p, **kw: seen.setdefault('chapters_from', p) and [core.models.Chapter(1, 0, 10)])
    monkeypatch.setattr(core.split, 'split_mkv_direct', lambda source, *a, **kw: seen.setdefault('split', source) and [])
    monkeypatch.setattr(core.tools, 'tool_versions', lambda: {})
    work = tmp_path / 'out' / '_work'
    core.pipeline.run_full_pipeline(title, title.audio_tracks[0], {}, work, tmp_path / 'out', container='mkv',
                                audio_track_ids=[1])
    assert seen['split'] == seen['chapters_from'] == work / '_dvd_title.mkv'


def test_backend_imports_a_dvd_folder(backend, qt_app, tmp_path, fake_ffmpeg):
    disc = make_dvd(tmp_path / '[DVD-ISO] Kana - Live Digest')
    backend.disc.setSource(QUrl.fromLocalFile(str(disc / 'VIDEO_TS')).toString())
    wait_idle(backend, qt_app)
    assert [r['label'] for r in backend.disc.playlist_model.rows] == ['DVD · 标题 01', 'DVD · 标题 02']
    assert (backend.state['artist'], backend.state['album']) == ('Kana', 'Live Digest')
    assert backend.disc.playlist.chapter_count == 3


def test_album_names_drop_leading_format_tags():
    assert core.naming.derive_album_folder_name(Path('[DVD-ISO] Kana - Tour')) == 'Kana - Tour'
    assert core.naming.derive_album_folder_name(Path('[2020] Kana - Tour')) == '[2020] Kana - Tour'
    assert core.sources.source_name_path(Path('D:/Rips/Kana - Tour/DVDIMAGE.ISO')) == Path('D:/Rips/Kana - Tour')
