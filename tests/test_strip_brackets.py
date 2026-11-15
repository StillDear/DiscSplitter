import core.models
import core.tracklist
from core import setlist

LIVE = '(Live on Special Live "Christmas Magic")'


def test_only_the_shared_note_is_dropped():
    titles = [f'Christmas Love {LIVE}', f'Merry Christmas {LIVE}', f'Secret -short- {LIVE}',
              f'SongA (Acoustic Ver.) {LIVE}', 'Intro']
    assert setlist.drop_shared_suffixes(titles) == [
        'Christmas Love', 'Merry Christmas', 'Secret -short-', 'SongA (Acoustic Ver.)', 'Intro']


def test_notes_on_few_titles_stay():
    titles = ['A (Remix)', 'B', 'C', 'D (feat. X)']
    assert setlist.drop_shared_suffixes(titles) == titles


def test_matching_ignores_width_case_and_spacing():
    titles = ['A（Live 2025）', 'B (live  2025)', 'C [LIVE 2025]']
    assert setlist.drop_shared_suffixes(titles) == ['A', 'B', 'C']


def test_a_title_is_never_emptied():
    assert setlist.drop_shared_suffixes(['(Live)', 'B (Live)', 'C (Live)']) == ['(Live)', 'B', 'C']


def test_review_button_strips_rows_and_tracklist(backend):
    backend.disc.chapters = [core.models.Chapter(i, (i - 1) * 300, i * 300) for i in range(1, 5)]
    backend.disc.rebuild_chapters({})
    names = backend.names
    entries = [core.tracklist.TracklistEntry(f'Song {i} (Live on Tour)', index=i, duration_seconds=300) for i in range(1, 4)]
    entries.append(core.tracklist.TracklistEntry('Song 4 (Acoustic) (Live on Tour)', index=4, duration_seconds=300))
    names.review_entries(entries)
    assert names.state['reviewStrippable'] is True

    names.editReview(0, 'My Own (Live on Tour)')         # a typed title loses only the shared note too
    names.stripReviewBrackets()
    assert [r['proposed'] for r in names.review_model.rows] == ['My Own', 'Song 2', 'Song 3', 'Song 4 (Acoustic)']
    assert [p['name'] for p in names.state['reviewPool']] == ['Song 1', 'Song 2', 'Song 3', 'Song 4 (Acoustic)']
    assert names.state['reviewStrippable'] is False

    names.realignReview('order')                          # re-matching keeps the cleaned names
    assert names.review_model.rows[0]['proposed'] == 'Song 1'
