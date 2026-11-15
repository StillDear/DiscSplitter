import subprocess
import threading
from pathlib import Path

import pytest

import core.jobs
import core.models
import core.naming
from core import tagging
import core.split
import core.tools


class FakeMkvmerge:
    """Writes one part file per range and reports progress the way mkvmerge --gui-mode does."""

    def __init__(self, cancel_after=None, cancel_event=None):
        self.args = None
        self.cancel_after, self.cancel_event = cancel_after, cancel_event

    def __call__(self, args, on_line, cancel_event=None):
        self.args = args
        out = Path(args[args.index('-o') + 1])
        ranges = args[args.index('--split') + 1].removeprefix('parts:').split(',')
        names = [out] if len(ranges) == 1 else [out.with_name(f'{out.stem}-{i:03d}{out.suffix}') for i in range(1, len(ranges) + 1)]
        for i, name in enumerate(names):
            name.write_bytes(b'mkv' * 10)
            on_line(f'#GUI#progress {int(100 * (i + 1) / len(names))}%')
            if self.cancel_after is not None and i == self.cancel_after:
                self.cancel_event.set()
                raise core.jobs.JobCancelled('Cancelled by user.')
        return 0


@pytest.fixture
def tools(monkeypatch, tmp_path):
    propedit = tmp_path / 'mkvpropedit.exe'
    propedit.touch()
    monkeypatch.setitem(core.tools.TOOL_PATHS, 'mkvmerge', str(tmp_path / 'mkvmerge.exe'))
    tagged = []

    def run(args, timeout=None, cancel_event=None):
        tagged.append(args)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(core.tools, 'run', run)
    return tagged


def chapters():
    names = ['Intro', 'Song A', 'Song B', 'Outro']
    out = [core.models.Chapter(i, (i - 1) * 100.0 + (7.007 if i > 1 else 0), i * 100.0 + 7.007, name=n) for i, n in enumerate(names, 1)]
    out[-1].end_seconds = None            # last disc chapter runs to the end
    return out


def test_one_mkvmerge_pass_with_exact_ranges_and_titles(tmp_path, tools, monkeypatch):
    fake = FakeMkvmerge()
    monkeypatch.setattr(core.tools, 'run_streaming', fake)
    meta = tagging.empty_metadata()
    meta['album'].update(artist='Kana', album='Tour')
    audio = [core.models.Track(1, 'audio', 'PCM'), core.models.Track(2, 'audio', 'AC-3')]
    written, log = [], []
    selected = chapters()[1:]
    result = core.split.split_mkv_direct(Path('BDMV/PLAYLIST/00001.mpls'), selected, tmp_path / 'out',
                                audio_tracks=audio, subtitle_tracks=[], video_track=core.models.Track(0, 'video', 'AVC'),
                                metadata=meta, progress_cb=log.append, on_output_written=written.append,
                                filename_template='nn_title')
    args = fake.args
    assert args[args.index('--split') + 1] == 'parts:00:01:47.007000000-00:03:27.007000000,00:03:27.007000000-00:05:07.007000000,00:05:07.007000000-'
    assert args[args.index('-d') + 1] == '0' and args[args.index('-a') + 1] == '1,2' and '--no-subtitles' in args
    # Video files carry only their titles: no track renaming, attachments or album tags.
    assert '--track-name' not in args and '--language' not in args and '--attach-file' not in args
    assert [p.name for p in result] == ['01 - Song A.mkv', '02 - Song B.mkv', '03 - Outro.mkv']
    assert all(p.is_file() for p in result) and written == result
    assert [t[t.index('--set') + 1] for t in tools] == ['title=Song A', 'title=Song B', 'title=Outro']
    assert not any('--tags' in t for t in tools)
    assert [m for m in log if m.startswith('Splitting')] == ['Splitting chapter 2: Song A', 'Splitting chapter 3: Song B', 'Splitting chapter 4: Outro']
    # The UI reads the meaning from the events, not the wording.
    events = [(m.stage, m.chapter, m.status) for m in log if isinstance(m, core.jobs.ProgressEvent)]
    assert events == [('extracting', None, ''), ('splitting', 2, 'running'), ('splitting', 3, 'running'),
                      ('splitting', 4, 'running')]
    assert not list((tmp_path / 'out').glob('.split-*'))     # temp folder removed


def test_file_names_still_use_the_artist(tmp_path, tools, monkeypatch):
    fake = FakeMkvmerge()
    monkeypatch.setattr(core.tools, 'run_streaming', fake)
    meta = tagging.empty_metadata()
    meta['album'].update(artist='Kana', album='Tour')
    result = core.split.split_mkv_direct(Path('movie.mkv'), chapters()[1:3], tmp_path / 'out',
                                audio_tracks=[core.models.Track(1, 'audio', 'PCM')], subtitle_tracks=[],
                                video_track=core.models.Track(0, 'video', 'AVC'), metadata=meta,
                                filename_template='artist_title')
    assert [p.name for p in result] == ['Kana - Song A.mkv', 'Kana - Song B.mkv']


def test_a_failed_part_stops_mkvmerge(tmp_path, monkeypatch):
    """A song that cannot be tagged ends the job; mkvmerge must not keep reading the disc."""
    import sys
    (tmp_path / 'mkvpropedit.exe').touch()
    monkeypatch.setitem(core.tools.TOOL_PATHS, 'mkvmerge', str(tmp_path / 'mkvmerge.exe'))
    started = []
    real_popen = subprocess.Popen

    class Recorded(real_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            started.append(self)

    monkeypatch.setattr(core.tools.subprocess, 'Popen', Recorded)

    def on_line(line):
        raise RuntimeError('mkvpropedit could not tag chapter 2')

    with pytest.raises(RuntimeError, match='could not tag'):
        core.tools.run_streaming([sys.executable, '-u', '-c', 'import time; print("#GUI#progress 1%"); time.sleep(30)'],
                                 on_line)
    assert started and started[0].poll() is not None


def test_cancel_keeps_finished_songs_and_resume_skips_them(tmp_path, tools, monkeypatch):
    cancel = threading.Event()
    monkeypatch.setattr(core.tools, 'run_streaming', FakeMkvmerge(cancel_after=2, cancel_event=cancel))
    written = []
    with pytest.raises(core.jobs.JobCancelled):
        core.split.split_mkv_direct(Path('movie.mkv'), chapters(), tmp_path, audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                           subtitle_tracks=[], video_track=None, cancel_event=cancel, on_output_written=written.append)
    assert [p.name for p in written] == ['Intro.mkv', 'Song A.mkv']   # the third part was still being written
    assert not list(tmp_path.glob('.split-*'))
    fake = FakeMkvmerge()
    monkeypatch.setattr(core.tools, 'run_streaming', fake)
    result = core.split.split_mkv_direct(Path('movie.mkv'), chapters(), tmp_path, audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                                subtitle_tracks=[], video_track=None, skip_paths=set(written))
    assert '--no-video' in fake.args
    assert fake.args[fake.args.index('--split') + 1].count('-') == 2     # only the two missing chapters
    assert sorted(p.name for p in result) == ['Intro.mkv', 'Outro.mkv', 'Song A.mkv', 'Song B.mkv']


def test_existing_files_are_never_overwritten_silently(tmp_path, tools, monkeypatch):
    monkeypatch.setattr(core.tools, 'run_streaming', FakeMkvmerge())
    (tmp_path / 'Song A.mkv').write_bytes(b'mine')
    with pytest.raises(core.naming.OutputCollisionError):
        core.split.split_mkv_direct(Path('movie.mkv'), chapters()[1:2], tmp_path, audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                           subtitle_tracks=[], video_track=None)
    result = core.split.split_mkv_direct(Path('movie.mkv'), chapters()[1:2], tmp_path, audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                                subtitle_tracks=[], video_track=None, overwrite={tmp_path / 'Song A.mkv'})
    assert result[0].read_bytes() != b'mine'


def test_missing_mkvpropedit_fails_before_reading_the_disc(tmp_path, monkeypatch):
    monkeypatch.setitem(core.tools.TOOL_PATHS, 'mkvmerge', str(tmp_path / 'mkvmerge.exe'))
    monkeypatch.setattr(core.split.shutil, 'which', lambda name: None)
    calls = []
    monkeypatch.setattr(core.tools, 'run_streaming', lambda *a, **k: calls.append(a))
    with pytest.raises(RuntimeError, match='mkvpropedit'):
        core.split.split_mkv_direct(Path('movie.mkv'), chapters()[1:2], tmp_path, audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                           subtitle_tracks=[], video_track=None)
    assert calls == []
