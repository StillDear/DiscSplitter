import core.models
import core.chapter_marks
import core.sources
from test_backend import wait_idle


def titles(backend):
    return [r['title'] for r in backend.disc.chapter_model.rows]


def test_new_disc_starts_without_the_last_discs_titles(backend, qt_app, tmp_path, monkeypatch):
    first, second = tmp_path / 'Artist - First Live.mkv', tmp_path / 'Artist - Second Live.mkv'
    first.touch()
    second.touch()
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda p, **_: core.models.Playlist(p, chapter_count=3))
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: [
        core.models.Chapter(1, 0, 60), core.models.Chapter(2, 60, 120), core.models.Chapter(3, 120, 180)])

    backend.disc.setSource(str(first))
    wait_idle(backend, qt_app)
    backend.disc.editTitle(0, 'Opening Song')
    backend.disc.editTitle(1, 'Second Song')
    assert titles(backend)[:2] == ['Opening Song', 'Second Song']

    backend.disc.setSource(str(second))         # the next disc: nothing carried over
    wait_idle(backend, qt_app)
    assert titles(backend) == ['', '', '']
    assert backend.disc.disc_baselines == {}

    backend.disc.editTitle(2, 'Kept')
    backend.disc.scan()                         # rescanning the same disc keeps what was typed
    wait_idle(backend, qt_app)
    assert titles(backend) == ['', '', 'Kept']
