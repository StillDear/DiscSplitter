import core.models
import core.tracklist


def chapters(lengths):
    out, t = [], 0
    for i, length in enumerate(lengths, 1):
        out.append(core.models.Chapter(i, t, t + length))
        t += length
    return out


def entries(pairs):
    return [core.tracklist.TracklistEntry(name, index=i, duration_seconds=d) for i, (name, d) in enumerate(pairs, 1)]


def names(result):
    return [m.name or None for m in result.matches]


def test_concert_disc_skips_talk_chapters():
    # intro, song, MC, song, song, MC, song, encore talk, song, outro
    ch = chapters([7, 219, 100, 275, 319, 80, 181, 60, 340, 20])
    tl = entries([('A', 214), ('B', 280), ('C', 316), ('D', 185), ('E', 336)])
    result = core.tracklist.match_tracklist_to_chapters(ch, tl)
    assert names(result) == [None, 'A', None, 'B', 'C', None, 'D', None, 'E', None]
    assert [m.entry_index for m in result.matches if m.name] == [0, 1, 2, 3, 4]


def test_album_songs_missing_from_disc_are_skipped():
    ch = chapters([200, 300, 250])
    tl = entries([('A', 201), ('Bonus', 420), ('B', 298), ('C', 251)])
    assert names(core.tracklist.match_tracklist_to_chapters(ch, tl)) == ['A', 'B', 'C']


def test_order_is_never_shuffled():
    # Durations would fit better swapped, but alignment must stay monotonic.
    ch = chapters([300, 200])
    tl = entries([('First', 200), ('Second', 300)])
    result = names(core.tracklist.match_tracklist_to_chapters(ch, tl))
    assert result != ['Second', 'First']           # never reordered
    assert sum(n is not None for n in result) == 1  # only one in-order pairing fits


def test_loose_lengths_are_flagged_not_checked():
    ch = chapters([300])
    result = core.tracklist.match_tracklist_to_chapters(ch, entries([('A', 330)]))
    assert result.matches[0].confidence == 'duration_mismatch'


def test_order_mode_and_name_only_lists_stay_positional():
    ch = chapters([7, 219, 100])
    tl = entries([('A', 214), ('B', 280)])
    assert names(core.tracklist.match_tracklist_to_chapters(ch, tl, mode='order')) == ['A', 'B', None]
    plain = [core.tracklist.TracklistEntry('A'), core.tracklist.TracklistEntry('B')]
    assert names(core.tracklist.match_tracklist_to_chapters(ch, plain)) == ['A', 'B', None]


def test_backend_realign_and_manual_assignment(backend):
    backend.disc.chapters = chapters([7, 219, 100, 275])
    backend.disc.rebuild_chapters({})
    backend.names.review_entries(entries([('A', 214), ('B', 280)]))
    assert backend.state['reviewCanAlign'] and backend.state['reviewMode'] == 'duration'
    assert [r['proposed'] for r in backend.names.review_model.rows] == ['', 'A', '', 'B']
    assert [r['entryLabel'] for r in backend.names.review_model.rows] == ['', '01', '', '02']
    backend.names.realignReview('order')
    assert backend.state['reviewMode'] == 'order'
    assert [r['proposed'] for r in backend.names.review_model.rows] == ['A', 'B', '', '']
    backend.names.realignReview('duration')
    backend.names.assignReview(2, 0)                     # put "A" on the MC chapter by hand
    row = backend.names.review_model.rows[2]
    assert (row['proposed'], row['confidence'], row['checked'], row['entryLabel']) == ('A', 'manual', True, '01')
    assert backend.state['reviewPool'][0]['used'] is True
    backend.names.assignReview(2, -1)                    # and clear it again
    row = backend.names.review_model.rows[2]
    assert (row['proposed'], row['checked'], row['entry']) == ('', False, -1)


def test_open_ended_last_chapter_still_aligns_by_duration():
    # Real playlists leave the last chapter without an end time ("runs to end of file").
    ch = chapters([7, 219, 319])
    ch.append(core.models.Chapter(4, ch[-1].end_seconds, None))
    tl = entries([('A', 221), ('B', 321), ('C', 250)])
    assert core.tracklist.can_align_by_duration(ch, tl)
    assert names(core.tracklist.match_tracklist_to_chapters(ch, tl)) == [None, 'A', 'B', None]


def test_does_not_leap_ahead_past_songs_for_a_slightly_closer_length():
    # Real case: after song 6, chapter lengths 177 s / 106 s fit songs 7 (187 s) and 9 (121 s)
    # reasonably, and songs 16 (181 s) / 19 (97 s) slightly better. Jumping would drop songs 7-15.
    album = [221, 321, 340, 255, 106, 102, 187, 73, 121, 187, 246, 248, 285, 276, 339, 181, 132, 97, 97]
    tl = entries([(f'S{i}', d) for i, d in enumerate(album, 1)])
    ch = chapters([7, 108, 219, 319, 181, 340, 260, 88, 177, 106])
    used = [m.entry_index + 1 for m in core.tracklist.match_tracklist_to_chapters(ch, tl).matches if m.entry_index is not None]
    assert used == sorted(used) and max(used) <= 9


def test_order_mode_flags_clear_length_mismatches():
    ch = chapters([7, 219])
    result = core.tracklist.match_tracklist_to_chapters(ch, entries([('A', 221), ('B', 321)]), mode='order')
    assert [m.confidence for m in result.matches] == ['duration_mismatch', 'duration_mismatch']


def test_review_page_knows_which_source_it_shows(backend, qt_app):
    backend.disc.chapters = chapters([60, 60])
    for c in backend.disc.chapters:
        c.embedded_name = f'Chapter {c.index:02d}'
    backend.disc.rebuild_chapters({})
    backend.names.reviewEmbedded()
    assert (backend.state['reviewSource'], backend.state['reviewCount']) == ('disc', 2)
    assert backend.state['mbRelease'] == backend.tr('srcDiscBadge')
    backend.names.reviewPaste('One\nTwo\nThree')
    assert (backend.state['reviewSource'], backend.state['reviewCount']) == ('paste', 3)
    backend.names.openOnline()
    # Waiting for a release: every chapter is listed, nothing proposed or ticked.
    assert backend.state['reviewSource'] == 'online'
    assert [r['confidence'] for r in backend.names.review_model.rows] == ['waiting'] * len(backend.disc.chapters)
    assert not any(r['proposed'] or r['checked'] for r in backend.names.review_model.rows)


def test_get_titles_reopens_the_last_used_source(backend, qt_app):
    backend.disc.chapters = chapters([60, 60])
    for c in backend.disc.chapters:
        c.embedded_name = f'Chapter {c.index:02d}'
    backend.disc.rebuild_chapters({})
    backend.names.reviewEmbedded()
    backend.navigate('main')
    backend.names.openTitles()                      # disc: re-read straight away
    assert (backend.state['page'], backend.state['reviewSource'], backend.state['reviewCount']) == ('review', 'disc', 2)
    backend.names.reviewPaste('One\nTwo')
    backend.navigate('main')
    backend.names.openTitles()                      # paste: open that tab empty, waiting for a new paste
    assert (backend.state['reviewSource'], backend.state['reviewCount'], backend.state['reviewCanAlign']) == ('paste', 0, False)
    assert {r['confidence'] for r in backend.names.review_model.rows} == {'waiting'} and backend.state['reviewChecked'] == 0


def test_back_from_review_returns_to_the_workspace(backend, qt_app):
    """The review page is opened by the names controller, not navigate(); Back must still lead to the workspace
    (it used to follow a stale return page, e.g. the start page the app opened on, or settings opened from there)."""
    backend.navigate('settings')                    # from the start page: Back would lead there
    backend.back()
    backend.disc.chapters = chapters([60, 60])
    backend.disc.rebuild_chapters({})
    backend.navigate('main')
    backend.names.openOnline()
    assert backend.state['page'] == 'review'
    backend.back()
    assert backend.state['page'] == 'main'
    backend.names.reviewPaste('One\nTwo')
    assert backend.state['page'] == 'review'        # a paste from the workspace opens the review too
    backend.back()
    assert backend.state['page'] == 'main'
