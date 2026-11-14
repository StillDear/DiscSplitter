import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QWindow

import extractor as x
from gui import desktop
import core.pipeline


def chapters(names):
    return [x.Chapter(i, (i - 1) * 60.0, i * 60.0, name=n) for i, n in enumerate(names, 1)]


def stems(planned):
    return [p.path.stem for p in planned]


def test_filename_presets_number_the_exported_songs(tmp_path):
    ch = chapters(['Intro', 'Song A', 'Song B'])[1:]           # chapter 1 is not exported
    meta = {'album': {'artist': 'Kana'}, 'track_artists': {'3': 'Guest: X'}}
    assert stems(x.plan_output_files(ch, tmp_path)) == ['Song A', 'Song B']
    assert stems(x.plan_output_files(ch, tmp_path, filename_template='nn_title')) == ['01 - Song A', '02 - Song B']
    assert stems(x.plan_output_files(ch, tmp_path, filename_template='nn_dot_title')) == ['01. Song A', '02. Song B']
    # per-track artist wins and is made filename-safe; no artist at all falls back to the title
    assert stems(x.plan_output_files(ch, tmp_path, filename_template='artist_title', metadata=meta)) == \
        ['Kana - Song A', 'Guest X - Song B']
    assert stems(x.plan_output_files(ch, tmp_path, filename_template='artist_title')) == ['Song A', 'Song B']


def test_numbered_presets_do_not_flag_equal_titles_as_duplicates(tmp_path):
    ch = chapters(['Encore', 'Encore'])
    assert all(p.duplicate_name for p in x.plan_output_files(ch, tmp_path))
    numbered = x.plan_output_files(ch, tmp_path, filename_template='nn_title')
    assert not any(p.duplicate_name for p in numbered)
    assert stems(numbered) == ['01 - Encore', '02 - Encore']


def test_chapter_language_accepts_two_and_three_letter_codes():
    atom = ET.fromstring(
        '<ChapterAtom>'
        '<ChapterDisplay><ChapterString>Chapter 1</ChapterString><ChapterLanguage>eng</ChapterLanguage></ChapterDisplay>'
        '<ChapterDisplay><ChapterString>第1章</ChapterString><ChapterLanguage>und</ChapterLanguage>'
        '<ChapLanguageIETF>ja</ChapLanguageIETF></ChapterDisplay>'
        '</ChapterAtom>')
    assert x._pick_chapter_display(atom, 'jpn')[0] == '第1章'
    assert x._pick_chapter_display(atom, 'eng')[0] == 'Chapter 1'
    assert x._pick_chapter_display(atom, 'first')[0] == 'Chapter 1'
    assert x._pick_chapter_display(atom, 'kor')[0] == 'Chapter 1'       # missing language falls back


def test_tolerance_decides_what_counts_as_a_length_match():
    ch = [x.Chapter(1, 0, 300)]
    entry = [x.TracklistEntry('A', index=1, duration_seconds=330)]
    assert x.match_tracklist_to_chapters(ch, entry).matches[0].confidence == 'duration_mismatch'
    loose = x.match_tracklist_to_chapters(ch, entry, duration_tolerance_seconds=40)
    assert loose.matches[0].confidence != 'duration_mismatch'


def test_collision_policy_skip_and_overwrite(backend, qt_app, monkeypatch, tmp_path):
    from test_backend import setup_disc, wait_idle
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    output = tmp_path / 'Album'
    output.mkdir()
    (output / 'Track 01.mkv').write_bytes(b'existing')
    calls = []
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **kw: calls.append(kw) or [])
    dialogs = []
    backend.dialogRequested.connect(lambda kind, text: dialogs.append(kind))

    backend.cfg['collision_policy'] = 'skip'
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    assert dialogs == [] and calls[-1]['overwrite'] == set()
    assert calls[-1]['skip_existing'] == {output / 'Track 01.mkv'}

    backend.cfg['collision_policy'] = 'overwrite'
    backend.cfg['filename_template'] = 'title'
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    assert dialogs == [] and calls[-1]['overwrite'] == {output / 'Track 01.mkv'}

    backend.cfg['collision_policy'] = 'ask'
    backend.exporter.startExport()
    assert dialogs == ['collision']


def test_window_geometry_is_restored_only_when_visible_on_a_screen(qt_app):
    window = QWindow()
    window.setMinimumWidth(400)
    window.setMinimumHeight(300)
    screen = qt_app.primaryScreen().availableGeometry()
    assert desktop.restore_geometry(window, [screen.x() + 20, screen.y() + 20, 500, 350, False])
    assert window.geometry().size().width() == 500
    assert not desktop.restore_geometry(window, [screen.right() + 5000, screen.y(), 500, 350, False])
    assert not desktop.restore_geometry(window, None)
    assert not desktop.restore_geometry(window, ['bad'])


def test_taskbar_follows_export_progress(backend, qt_app):
    window = QWindow()
    calls = []

    class FakeTaskbar:
        def state(self, flag):
            calls.append(('state', flag))

        def value(self, done, total):
            calls.append(('value', done, total))

    d = desktop.Desktop.__new__(desktop.Desktop)
    d.backend, d.window, d.taskbar = backend, window, FakeTaskbar()
    d.running, d.total, d.error_shown, d.tray = False, 0, False, None
    d.notify = lambda *a, **kw: calls.append(('notify',) + a)
    backend.put(pipeline=True, result='running', stage='extracting', remaining=4, completed=0)
    d.sync()
    assert calls[-1] == ('state', desktop._Taskbar.INDETERMINATE)
    backend.put(stage='splitting', completed=2)
    d.sync()
    assert calls[-1] == ('value', 2, 4)
    backend.put(pipeline=False, result='failed', page='done')
    d.sync()
    assert ('state', desktop._Taskbar.ERROR) in calls
    assert calls[-1][0] == 'notify'          # the test window is never active
    backend.put(page='main')
    d.sync()
    assert calls[-1] == ('state', desktop._Taskbar.NONE)
