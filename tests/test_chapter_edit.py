"""Chapter editing (merge / split / move a boundary) and the check of finished files."""
from pathlib import Path

import pytest

import core.manifest
import core.models
from test_backend import setup_disc, wait_idle
import core.chapter_marks
import core.pipeline
import core.tools
import core.verify


def source():
    return [core.models.Chapter(1, 0.0, 100.0, embedded_name='One'), core.models.Chapter(2, 100.0, 200.0, embedded_name='Two'),
            core.models.Chapter(3, 200.0, None, embedded_name='Three')]


# ------------------------------------------------------------------ core operations
def test_merge_joins_neighbours_and_renumbers():
    merged = core.chapter_marks.merge_chapters(source(), 0)
    assert [(c.index, c.start_seconds, c.end_seconds) for c in merged] == [(1, 0.0, 200.0), (2, 200.0, None)]
    assert merged[0].embedded_name == 'One'
    with pytest.raises(ValueError):
        core.chapter_marks.merge_chapters(source(), 2)     # the last chapter has no next one


def test_split_cuts_inside_and_refuses_cuts_at_the_edges():
    split = core.chapter_marks.split_chapter(source(), 1, 130.5)
    assert [(c.index, c.start_seconds, c.end_seconds) for c in split] == [
        (1, 0.0, 100.0), (2, 100.0, 130.5), (3, 130.5, 200.0), (4, 200.0, None)]
    assert split[2].embedded_name == '' and split[3].embedded_name == 'Three'
    with pytest.raises(ValueError):
        core.chapter_marks.split_chapter(source(), 1, 100.5)
    with pytest.raises(ValueError):
        core.chapter_marks.split_chapter(source(), 1, 199.5)
    assert len(core.chapter_marks.split_chapter(source(), 2, 500.0)) == 4    # the open-ended last chapter can be cut anywhere after its start


def test_moving_a_boundary_moves_both_neighbours_and_is_clamped():
    moved = core.chapter_marks.move_chapter_start(source(), 1, 99.5)
    assert (moved[0].end_seconds, moved[1].start_seconds) == (99.5, 99.5)
    clamped = core.chapter_marks.move_chapter_start(source(), 1, 500.0)
    assert clamped[1].start_seconds == 200.0 - core.chapter_marks.MIN_CHAPTER_SECONDS
    with pytest.raises(ValueError):
        core.chapter_marks.move_chapter_start(source(), 0, 3.0)


def test_layout_round_trips_against_the_source():
    edited = core.chapter_marks.split_chapter(core.chapter_marks.merge_chapters(source(), 0), 0, 150.0)
    layout = core.chapter_marks.chapter_layout(edited)
    assert layout == [0.0, 150.0, 200.0]
    rebuilt = core.chapter_marks.apply_chapter_layout(source(), layout)
    assert [(c.index, c.start_seconds, c.end_seconds, c.embedded_name) for c in rebuilt] == [
        (1, 0.0, 150.0, 'One'), (2, 150.0, 200.0, ''), (3, 200.0, None, 'Three')]
    assert core.chapter_marks.same_layout(rebuilt, edited) and not core.chapter_marks.same_layout(rebuilt, source())


def test_manifest_keeps_the_layout():
    m = core.manifest.JobManifest('a.mpls', 1, 'TrueHD', None, 'out', 'mkv', {}, {}, 'now', chapter_layout=[0.0, 42.5])
    assert core.manifest.JobManifest.from_json(m.to_json()).chapter_layout == [0.0, 42.5]


def test_direct_export_cuts_the_edited_chapters(tmp_path, monkeypatch):
    from test_direct_split import FakeMkvmerge
    import subprocess
    (tmp_path / 'mkvpropedit.exe').touch()
    monkeypatch.setitem(core.tools.TOOL_PATHS, 'mkvmerge', str(tmp_path / 'mkvmerge.exe'))
    monkeypatch.setattr(core.tools, 'run', lambda args, timeout=None, cancel_event=None: subprocess.CompletedProcess(args, 0, '', ''))
    monkeypatch.setattr(core.tools, 'tool_versions', lambda: {})
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda path, preferred_language='eng': source())
    fake = FakeMkvmerge()
    monkeypatch.setattr(core.tools, 'run_streaming', fake)
    audio = core.models.Track(1, 'audio', 'PCM')
    playlist = core.models.Playlist(Path('disc/BDMV/PLAYLIST/00001.mpls'), [core.models.Track(0, 'video', 'AVC'), audio], 3, 300)
    out = tmp_path / 'Album'
    result = core.pipeline.run_full_pipeline(playlist, audio, {1: 'Joined', 2: 'Second half'}, work_folder=out / '_work',
                                 output_folder=out, chapter_indices=[1, 2], chapter_layout=[0.0, 150.0, 200.0])
    ranges = fake.args[fake.args.index('--split') + 1]
    assert ranges == 'parts:00:00:00.000000000-00:02:30.000000000,00:02:30.000000000-00:03:20.000000000'
    assert [p.name for p in result] == ['Joined.mkv', 'Second half.mkv']


# ------------------------------------------------------------------ backend
def test_backend_edits_carry_titles_ticks_and_artists(backend):
    setup_disc(backend)
    backend.disc.editTitle(0, 'Intro')
    backend.disc.editTitle(1, 'Song')
    backend.metadata.setTrackArtist(1, 'Guest')
    backend.disc.setChapterIncluded(2, False)
    assert backend.disc.edited_layout() is None

    backend.disc.mergeChapterWithNext(0)          # "Intro" + "Song": the first title wins
    rows = backend.disc.chapter_model.rows
    assert [(r['number'], r['title'], r['included']) for r in rows] == [(1, 'Intro', True), (2, '', False)]
    assert rows[0]['artist'] == 'Guest' and backend.metadata.meta['track_artists'] == {'1': 'Guest'}
    assert backend.state['chaptersEdited'] and backend.disc.edited_layout() == [0, 200]

    backend.disc.splitChapter(0, 120.0)
    rows = backend.disc.chapter_model.rows
    assert [(r['number'], r['title'], r['begin']) for r in rows] == [(1, 'Intro', 0), (2, '', 120.0), (3, '', 200)]
    backend.disc.nudgeChapterStart(1, 0.5)
    assert backend.disc.chapters[1].start_seconds == 120.5 and backend.disc.chapters[0].end_seconds == 120.5

    backend.disc.restoreChapters()
    assert [r['title'] for r in backend.disc.chapter_model.rows] == ['Intro', '', '']
    assert not backend.state['chaptersEdited'] and backend.disc.edited_layout() is None


def test_too_close_split_is_explained_not_applied(backend):
    setup_disc(backend)
    dialogs = []
    backend.dialogRequested.connect(lambda kind, msg: dialogs.append(kind))
    backend.disc.splitChapter(0, 0.2)
    assert dialogs == ['chapterEdit'] and len(backend.disc.chapters) == 3


def test_export_sends_the_layout_and_the_edited_count(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    backend.disc.splitChapter(2, 50.0)
    calls = []
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **kw: calls.append(kw) or [])
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    assert calls[0]['chapter_layout'] == [0, 100, 200, 250.0]
    assert calls[0]['chapter_indices'] == [1, 2, 3, 4]


def test_preview_clip_follows_the_chapter_range(backend):
    setup_disc(backend)
    before = backend.preview.preview_job(0, 0)['target']
    backend.disc.splitChapter(0, 40.0)
    after = backend.preview.preview_job(0, 0)['target']
    assert before != after


# ------------------------------------------------------------------ checking finished files
def probe(duration, streams, title):
    return lambda path: {'format': {'duration': str(duration), 'tags': {'title': title}}, 'streams': streams}


def test_verify_accepts_a_good_video_file(tmp_path):
    f = tmp_path / 'a.mkv'
    f.write_bytes(b'x')
    streams = [{'codec_type': 'video'}, {'codec_type': 'audio'}, {'codec_type': 'subtitle'}]
    result = core.verify.verify_output(f, core.models.Chapter(1, 0, 100), container='mkv', audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                             subtitle_count=1, keep_video=True, title='Song', probe=probe(101.2, streams, 'Song'))
    assert result.ok


def test_verify_reports_every_difference(tmp_path):
    f = tmp_path / 'a.mkv'
    f.write_bytes(b'x')
    result = core.verify.verify_output(f, core.models.Chapter(1, 0, 100), container='mkv',
                             audio_tracks=[core.models.Track(1, 'audio', 'PCM'), core.models.Track(2, 'audio', 'AC-3')],
                             subtitle_count=1, keep_video=True, title='Song',
                             probe=probe(90, [{'codec_type': 'audio'}], 'Other'))
    assert [i.code for i in result.issues] == ['duration', 'audio', 'video', 'subtitles', 'title']
    missing = core.verify.verify_output(tmp_path / 'none.mkv', core.models.Chapter(1, 0, 100), container='mkv', audio_tracks=[],
                              subtitle_count=0, keep_video=False, title='')
    assert [i.code for i in missing.issues] == ['missing']


def test_verify_flac_ignores_cover_art_and_checks_the_codec(tmp_path):
    f = tmp_path / 'a.flac'
    f.write_bytes(b'x')
    streams = [{'codec_type': 'audio', 'codec_name': 'flac'}, {'codec_type': 'video', 'disposition': {'attached_pic': 1}}]
    result = core.verify.verify_output(f, core.models.Chapter(1, 0, 100), container='flac', audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                             subtitle_count=0, keep_video=False, title='Song',
                             probe=lambda p: {'format': {'duration': '100.1', 'tags': {'TITLE': 'Song'}}, 'streams': streams})
    assert result.ok


def test_sound_that_ends_before_the_picture_is_not_a_short_file(tmp_path):
    # A DVD's last chapter ran 361.7 s, its sound 353.1 s: a closing screen with no sound. The FLAC was right.
    f = tmp_path / 'a.flac'
    f.write_bytes(b'x')
    chapter = core.models.Chapter(7, 1414.6, 1776.3)
    streams = [{'codec_type': 'audio', 'codec_name': 'flac'}]

    def check(length, sound_left, container='flac', keep_video=False):
        result = core.verify.verify_output(f, chapter, container=container, audio_tracks=[core.models.Track(1, 'audio', 'PCM')],
                                           subtitle_count=0, keep_video=keep_video, title='',
                                           probe=lambda p: {'format': {'duration': str(length)}, 'streams': streams})
        asked = []

        def sound(start, span):
            asked.append((round(start, 2), round(span, 2)))
            return sound_left
        return core.verify.excuse_silent_end(result, chapter, container=container, keep_video=keep_video,
                                             sound=sound, slack=1.0), result, asked

    excused, result, asked = check(353.1, 1.1)
    assert excused and result.ok
    assert asked == [(1765.7, 10.6)]            # read from 2 s before the file ends to the chapter's end
    excused, result, _ = check(341.7, 22.0)    # the source still has sound there: the file was cut short
    assert not excused and [i.code for i in result.issues] == ['duration']
    assert not check(359.7, 4.0)[0]            # even 2 s short is caught
    assert not check(353.1, None)[0]           # the source could not be read: the issue stands
    assert not check(353.1, 1.1, container='mkv', keep_video=True)[0]     # a picture copy runs as long as the picture


def test_failed_checks_are_shown_and_can_be_exported_again(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    output = Path(tmp_path) / 'Album'

    def pipeline(*a, **kw):
        files = [kw['output_folder'] / f'Track {i:02d}.mkv' for i in (1, 2, 3)]
        for f in files:
            f.write_bytes(b'x')
        calls.append(kw)
        return files
    calls = []
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', pipeline)
    bad = {'Track 02.mkv'}
    def verify(path, chapter, **kw):
        result = core.verify.VerifyResult(path, chapter.index)
        if path.name in bad:
            result.issues.append(core.verify.VerifyIssue('duration', '100.00', '97.00'))
        return result
    monkeypatch.setattr(core.verify, 'verify_output', verify)
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    rows = backend.disc.chapter_model.rows
    assert [r['verify'] for r in rows] == ['ok', 'warn', 'ok']
    assert '1:37.0' in rows[1]['verifyText'] and '1:40.0' in rows[1]['verifyText']
    assert (backend.state['verified'], backend.state['verifyIssues']) == (2, 1)

    bad.clear()
    backend.exporter.reexportFlagged()
    wait_idle(backend, qt_app)
    assert calls[1]['overwrite'] == {output / 'Track 02.mkv'}
    assert calls[1]['skip_existing'] == {output / 'Track 01.mkv', output / 'Track 03.mkv'}
    assert backend.state['verifyIssues'] == 0
