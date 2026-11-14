import setlist
from setlist import SONG, EXTRA, HEADER, NOTE, OFF, MERGED

NL, TAB, Q = "\n", "\t", '"'


def test_squeezed_line_is_split_on_running_numbers():
    p = setlist.parse("M1. Alpha M2. Beta Gamma M3. Delta EN1. Encore Song")
    assert [l.title for l in p.items()] == ['Alpha', 'Beta Gamma', 'Delta', 'Encore Song']
    assert [l.title for l in setlist.parse("1. Vol. 2. Song").items()] == ['Vol. 2. Song']
    assert [l.title for l in setlist.parse("①Song A ②Song B ③Song C").items()] == ['Song A', 'Song B', 'Song C']


def test_single_line_list_with_separators():
    p = setlist.parse("Song A／Song B／Song C")
    assert [l.title for l in p.items()] == ['Song A', 'Song B', 'Song C']
    kept = setlist.parse("会いたくて、会いたくて" + NL + "Next" + NL + "Third")
    assert [l.title for l in kept.items()] == ['会いたくて、会いたくて', 'Next', 'Third']


def test_pasted_table_uses_the_title_and_length_columns():
    rows = [["No.", "タイトル", "作詞", "作曲", "時間"],
            ["1.", "会いたくて", "西野カナ", "Yum-Yum", "5:01"],
            ["2.", "Darling", "西野カナ", "Carlos K.", "4:12"],
            ["3.", "Best Friend", "西野カナ", "Carlos K.", "4:30"]]
    text = NL.join(TAB.join(r) for r in rows)
    p = setlist.parse(text)
    assert p.table.title == 1 and p.table.kinds == ['number', 'text', 'text', 'text', 'duration']
    assert p.table.columns[1] == 'タイトル'
    assert [(l.title, l.seconds) for l in p.items()] == [('会いたくて', 301), ('Darling', 252), ('Best Friend', 270)]
    assert p.lines[0].kind == HEADER
    other = setlist.parse(text, column=3)
    assert [l.title for l in other.items()] == ['Yum-Yum', 'Carlos K.', 'Carlos K.']


def test_table_without_header_takes_the_first_text_column():
    text = NL.join(["1" + TAB + "Alpha" + TAB + "3:10", "2" + TAB + "Beta" + TAB + "4:00", "3" + TAB + "Gamma" + TAB + "2:59"])
    p = setlist.parse(text)
    assert [(l.title, l.seconds) for l in p.items()] == [('Alpha', 190), ('Beta', 240), ('Gamma', 179)]


def test_credits_notes_and_quotes():
    text = NL.join(["1. 「Song A」", "作詞：someone 作曲：other", "2. Song B 作詞:X", "※ 一部映像は収録されません",
                    "3. " + Q + "Song C" + Q + " (Original)"])
    p = setlist.parse(text)
    assert [(l.kind, l.title) for l in p.lines] == [
        (SONG, 'Song A'), (NOTE, '作詞：someone 作曲：other'), (SONG, 'Song B'), (NOTE, '※ 一部映像は収録されません'),
        (SONG, 'Song C (Original)')]
    assert setlist.unquote('「A」のB') == '「A」のB'


def test_prefer_original_script():
    text = NL.join(["1. " + Q + "Aitakute Aitakute" + Q + " (会いたくて 会いたくて)", "2. 恋をして / Koi wo Shite"])
    p = setlist.parse(text, original=True)
    assert [l.title for l in p.items()] == ['会いたくて 会いたくて', '恋をして']
    plain = setlist.parse(text)
    assert plain.items()[0].title == 'Aitakute Aitakute (会いたくて 会いたくて)'


def test_manual_overrides_and_merging_wrapped_titles():
    text = NL.join(["1. A long title that", "wrapped onto a second line", "2. Talk with band", "3. B"])
    p = setlist.parse(text, overrides={'wrapped onto a second line': MERGED, '2. Talk with band': EXTRA, '3. B': OFF})
    assert [(l.kind, l.title) for l in p.lines] == [
        (SONG, 'A long title that wrapped onto a second line'), (MERGED, 'wrapped onto a second line'),
        (EXTRA, 'Talk with band'), (OFF, 'B')]
    assert p.lines[2].auto == SONG
    assert [l.title for l in p.items()] == ['A long title that wrapped onto a second line', 'Talk with band']
