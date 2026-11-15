import core.models
from core import setlist
from core.setlist import SONG, EXTRA, SKIP, HEADER, DISC, NOTE, OFF, MERGED


def kinds(parsed):
    return [(l.kind, l.title if l.kind in (SONG, EXTRA) else '') for l in parsed.lines if l.kind not in ('blank',)]


def chapters(lengths):
    out, t = [], 0.0
    for i, n in enumerate(lengths, 1):
        out.append(core.models.Chapter(i, t, t + n))
        t += n
    return out


def test_japanese_setlist_with_headings_mc_and_encore_numbers():
    text = """＜収録内容＞
M1. Opening Song
M2. 会いたくて 会いたくて
-MC-
M3. Darling
ENCORE
EN1. Best Friend
EN2. 1/3の純情な感情
"""
    p = setlist.parse(text)
    assert kinds(p) == [(HEADER, ''), (SONG, 'Opening Song'), (SONG, '会いたくて 会いたくて'), (EXTRA, 'MC'),
                        (SONG, 'Darling'), (EXTRA, 'ENCORE'), (SONG, 'Best Friend'), (SONG, '1/3の純情な感情')]


def test_plain_numbers_stripped_only_when_the_list_is_numbered():
    numbered = setlist.parse("01. Intro Song\n02) Second\n3 Third\n4\tFourth")
    assert [l.title for l in numbered.items()] == ['Intro Song', 'Second', 'Third', 'Fourth']
    titles = setlist.parse("99 Luftballons\nYesterday\nHey Jude")
    assert [l.title for l in titles.items()] == ['99 Luftballons', 'Yesterday', 'Hey Jude']


def test_circled_hash_and_track_numbering_and_bullets():
    p = setlist.parse("①Song A\n#2 Song B\nTrack 3: Song C\n・Song D\nTr.5 Song E")
    assert [l.title for l in p.items()] == ['Song A', 'Song B', 'Song C', 'Song D', 'Song E']


def test_durations_in_several_styles():
    p = setlist.parse("1. Alpha 4:32\n2. Beta (5:01)\n3. Gamma - 3'45\"\n4. Delta\t1:02:03\n5. 24:00")
    items = p.items()
    assert [(l.title, l.seconds) for l in items] == [('Alpha', 272), ('Beta', 301), ('Gamma', 225),
                                                     ('Delta', 3723), ('24:00', None)]


def test_disc_sections_and_guess_from_the_image_name():
    text = "Disc 1\n1. A\n2. B\n\n【DISC 2】\n1. C\n2. D\n3. E"
    p = setlist.parse(text)
    assert p.discs == [1, 2]
    assert [l.title for l in p.items(2)] == ['C', 'D', 'E']
    assert setlist.guess_disc('Kana Tour 2025 DISC 2.iso', p.discs) == 2
    assert setlist.guess_disc('Live.iso', p.discs) == 1


def test_songs_before_a_disc_2_heading_belong_to_disc_1():
    p = setlist.parse("1. A\n2. B\nDisc 2\n1. C")
    assert p.discs == [1, 2]
    assert [l.title for l in p.items(1)] == ['A', 'B']


def test_placeholders_and_decoration():
    p = setlist.parse("1. A\n-\n×\n------\n2. B")
    assert kinds(p) == [(SONG, 'A'), (SKIP, ''), (SKIP, ''), (HEADER, ''), (SONG, 'B')]


def test_cleanup_options():
    p = setlist.parse("1. Ｓｏｎｇ　Ａ (Live)\n2. Song B【Encore】", halfwidth=True, suffixes=True)
    assert [l.title for l in p.items()] == ['Song A', 'Song B']
    plain = setlist.parse("1. Song B (Live)")
    assert plain.items()[0].title == 'Song B (Live)'


def test_order_plan_with_start_chapter_extras_and_placeholders():
    p = setlist.parse("1. A\nMC\n-\n2. B\n3. C\n4. D")
    chs = chapters([60] * 6)
    plan = setlist.plan(p, chs, start=2)
    assert plan.mode == 'order'
    assert [pl.chapter for pl in plan.placements] == [2, 3, 4, 5, 6, None]
    assert [(e.index, e.name) for e in plan.entries] == [(2, 'A'), (3, 'MC'), (5, 'B'), (6, 'C')]
    assert plan.extra_chapters == {3: 'MC'}
    ignored = setlist.plan(p, chs, start=1, extras_take_chapter=False)
    assert [(e.index, e.name) for e in ignored.entries] == [(1, 'A'), (3, 'B'), (4, 'C'), (5, 'D')]


def test_duration_plan_skips_talk_chapters():
    p = setlist.parse("1. A 4:00\n2. B 5:00\n3. C 3:00")
    chs = chapters([240, 90, 300, 180])          # chapter 2 is talk
    plan = setlist.plan(p, chs)
    assert plan.mode == 'duration' and plan.can_duration
    assert [pl.chapter for pl in plan.placements] == [1, 3, 4]
    assert setlist.plan(p, chs, mode='order').mode == 'order'


def test_plan_uses_only_the_chosen_disc():
    p = setlist.parse("Disc 1\n1. A\nDisc 2\n1. B\n2. C")
    plan = setlist.plan(p, chapters([60, 60]), disc=2)
    assert [(e.index, e.name) for e in plan.entries] == [(1, 'B'), (2, 'C')]


def test_backend_applies_a_set_list_with_non_song_chapters_unticked(backend, qt_app):
    backend.disc.chapters = chapters([60] * 5)
    backend.disc.rebuild_chapters({})
    backend.put(source='D:/Live DISC 2.iso')
    text = "Disc 1\n1. Other\nDisc 2\nOpening\n1. A\n-MC-\n2. B\n3. C\n4. D"
    backend.names.previewPaste(text, {'skip': 'lines'})
    pv = backend.state['pastePreview']
    assert pv['disc'] == 2 and pv['discs'] == [1, 2]
    assert (pv['songs'], pv['extras'], pv['used'], pv['overflow']) == (4, 2, 5, 1)
    assert backend.state['pasteDraft'] == text
    backend.names.applyPaste(text, {'skip': 'lines'})
    rows = {r['number']: r for r in backend.names.review_model.rows}
    assert [rows[n]['proposed'] for n in range(1, 6)] == ['Opening', 'A', '-MC-'.strip('-'), 'B', 'C']
    assert rows[1]['confidence'] == 'extra' and not rows[1]['checked']
    assert rows[2]['checked'] and rows[3]['confidence'] == 'extra'
    assert any(p['name'] == 'D' for p in backend.state['reviewPool'])     # past the last chapter, still pickable
    assert backend.state['reviewChecked'] == 3


def test_backend_start_chapter_shifts_the_list(backend, qt_app):
    backend.disc.chapters = chapters([60] * 4)
    backend.disc.rebuild_chapters({})
    backend.names.applyPaste("1. A\n2. B", {'start': 3})
    rows = {r['number']: r['proposed'] for r in backend.names.review_model.rows}
    assert rows == {1: '', 2: '', 3: 'A', 4: 'B'}


def test_backend_unticked_lines_leave_their_chapters_alone(backend, qt_app):
    backend.disc.chapters = chapters([60] * 4)
    backend.disc.rebuild_chapters({})
    text = "1. A\n2. B\n3. C\n4. D"
    backend.names.previewPaste(text, {'excluded': ['2. B']})
    pv = backend.state['pastePreview']
    assert pv['kept'] == 3 and pv['used'] == 4
    assert [r['excluded'] for r in pv['rows']] == [False, True, False, False]
    backend.names.applyPaste(text, {'excluded': ['2. B']})
    checked = {r['number']: r['checked'] for r in backend.names.review_model.rows}
    assert checked == {1: True, 2: False, 3: True, 4: True}
    assert backend.state['reviewChecked'] == 3


def test_backend_end_chapter_limits_the_range(backend, qt_app):
    backend.disc.chapters = chapters([60] * 4)
    backend.disc.rebuild_chapters({})
    backend.names.previewPaste("1. A\n2. B\n3. C", {'end': 2})
    pv = backend.state['pastePreview']
    assert pv['end'] == 2 and pv['overflow'] == 1
    assert [c['before'] for c in pv['strip']] == [False, False, True, True]


def test_backend_removed_chapters_stay_out_of_matching(backend, qt_app):
    backend.disc.chapters = chapters([60] * 4)
    backend.disc.rebuild_chapters({})
    backend.names.applyPaste("1. A\n2. B\n3. C", {'mode': 'order'})
    backend.names.removeChapter(1, True)
    rows = {r['number']: (r['proposed'], r['confidence'], r['checked']) for r in backend.names.review_model.rows}
    assert rows[1] == ('', 'removed', False)
    assert [rows[n][0] for n in (2, 3, 4)] == ['A', 'B', 'C']
    assert backend.state['reviewCounts']['removed'] == 1
    backend.names.restoreRemoved()
    assert backend.names.review_model.rows[0]['proposed'] == 'A'
    # A file name preview follows the output format
    name = backend.names.fileNamePreview(2, 'B / x')
    assert name.endswith(('.mkv', '.flac')) and '/' not in name


def test_backend_chapter_kind_set_by_hand(backend, qt_app):
    backend.disc.chapters = chapters([60] * 4)
    backend.disc.rebuild_chapters({})
    backend.disc.setChapterKind(1, 'talk')
    assert backend.disc.state['chapterKinds']['2'] == 'talk'
    assert backend.disc.state['chapterKindsManual'] == [2]
    kinds, _ = backend.names.chapter_kinds()
    assert kinds[2] == 'talk'                    # the paste dialog and review page see it too
    backend.disc.setChapterKind(1, '')
    assert backend.disc.state['chapterKindsManual'] == []
