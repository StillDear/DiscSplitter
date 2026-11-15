"""Texts on the workspace's stream cards (video / audio / subtitles)."""
import core.models
from gui import i18n, track_info


def tr(key):
    return i18n.ZH[key]


def test_audio_card_chips_and_extra():
    t = core.models.Track(1, 'audio', 'TrueHD Atmos', 'A_TRUEHD', 'eng', 8, 'Dolby Atmos 7.1', 48000, 24,
                        bitrate_kbps=5200, default_track=True)
    card = track_info.audio_card(t, 'zh', tr)
    assert card['title'] == 'TrueHD Atmos'
    assert card['chips'] == ['7.1', '48kHz', '24-bit', '英语']
    # The track name only repeats the format, so it is left out
    assert 'Dolby' not in card['extra'] and card['extra'].endswith('默认')


def test_audio_card_keeps_a_real_track_name():
    t = core.models.Track(2, 'audio', 'AC-3', 'A_AC3', 'eng', 2, 'Commentary', 48000)
    assert 'Commentary' in track_info.audio_card(t, 'en', tr)['extra']


def test_subtitle_card():
    t = core.models.Track(3, 'subtitles', 'HDMV PGS', 'S_HDMV/PGS', 'jpn', properties={'forced_track': True})
    card = track_info.subtitle_card(t, 'zh', tr)
    # Like an audio card: the format as the title, the language as a chip (no raw "jpn" repeat)
    assert card['title'] == 'PGS' and card['chips'] == ['日语'] and card['extra'] == '强制'
    blank = track_info.subtitle_card(core.models.Track(4, 'subtitles', 'HDMV PGS', 'S_HDMV/PGS', 'und'), 'zh', tr)
    assert blank['title'] == 'PGS' and blank['chips'] == ['未标语言']


def test_ocr_joins_split_track_numbers():
    from core import ocr
    lines = ['08 愛のかたまり', '09 Secret -short-', '1 0 ONLYONE -short-', '1 1 MAYBE -short-', '1 2 もっと…']
    assert ocr.join_split_numbers(lines)[2:] == ['10 ONLYONE -short-', '11 MAYBE -short-', '12 もっと…']
    # Not a continuation of the numbering: left alone
    assert ocr.join_split_numbers(['03 Intro', '1 2 Step']) == ['03 Intro', '1 2 Step']


def test_plan_stops_at_end_chapter():
    from core import setlist
    chapters = [core.models.Chapter(i, (i - 1) * 300.0, i * 300.0) for i in range(1, 7)]
    parsed = setlist.parse('A\nB\nC\nD')
    result = setlist.plan(parsed, chapters, start=2, mode='order', end=4)
    assert [p.chapter for p in result.placements] == [2, 3, 4, None]
