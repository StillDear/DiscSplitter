from core import ocr
from core import setlist
from core import webpage
from core.ocr import Word

NL = "\n"


def test_ocr_rows_join_japanese_characters_and_line_up_columns():
    h = 20
    words = [
        Word("<", 30, 10, 10, h), Word("収", 40, 10, 20, h), Word("録", 60, 10, 20, h), Word(">", 80, 10, 10, h),
        Word("M", 30, 50, 12, h), Word("1", 42, 50, 10, h), Word(".", 52, 50, 4, h),
        Word("会", 120, 50, 20, h), Word("い", 140, 50, 20, h), Word("た", 160, 50, 20, h),
        Word("5", 600, 51, 10, h), Word(":", 610, 51, 4, h), Word("01", 616, 51, 20, h),
        Word("-MC-", 120, 90, 50, h),
        Word("Dar", 120, 130, 30, h), Word("Iing", 150, 130, 30, h), Word("4:12", 600, 131, 40, h),
    ]
    text = ocr.rebuild_rows(words)
    assert text.split(NL) == ["<収録>", "M1.\t会いた\t5:01", "-MC-", "\tDarling\t4:12"]
    p = setlist.parse(text)
    assert [(l.kind, l.title, l.seconds) for l in p.lines] == [
        ("header", "<収録>", None), ("song", "会いた", 301), ("extra", "MC", None), ("song", "Darling", 252)]


def test_web_page_track_table_ranks_above_other_tables():
    html = """<html><head><title>x</title><style>.a{}</style></head><body>
    <ul class="vector-menu"><li class="interlanguage-link">Deutsch</li><li class="interlanguage-link">English</li>
    <li class="interlanguage-link">Français</li></ul>
    <h2>Sales</h2><table><tr><th>Region</th><th>Certification</th></tr>
    <tr><td>Japan (RIAJ)</td><td>Gold</td></tr><tr><td>US (RIAA)</td><td>Platinum</td></tr>
    <tr><td>UK (BPI)</td><td>Gold</td></tr></table>
    <h2>Track listing</h2><table class="tracklist"><tr><th>No.</th><th>Title</th><th>Length</th></tr>
    <tr><td>1.</td><td>"So Far Away"</td><td>5:12</td></tr>
    <tr><td>2.</td><td>"Money for Nothing"<sup class="reference">[1]</sup></td><td>8:25</td></tr>
    <tr><td>3.</td><td>"Walk of Life"</td><td>4:12</td></tr>
    <tr><th colspan="2">Total length:</th><td>17:49</td></tr></table>
    <p>セットリスト<br>M1. 会いたくて<br>M2. Darling<br>-MC-<br>M3. Best Friend</p>
    </body></html>"""
    found = webpage.candidates(html)
    assert found[0].kind == "table" and found[0].tracklist
    items = setlist.parse(found[0].text).items()
    assert [(l.title, l.seconds) for l in items] == [("So Far Away", 312), ("Money for Nothing", 505), ("Walk of Life", 252)]
    texts = [c for c in found if c.kind == "text"]
    assert [l.title for l in setlist.parse(texts[0].text).items()] == ["会いたくて", "Darling", "MC", "Best Friend"]
    assert not any("Deutsch" in c.text for c in found)


def test_web_decoding_and_address_checks():
    assert webpage._decode("曲目".encode("cp932"), "shift_jis") == "曲目"
    assert webpage._decode('<meta charset="euc-jp">曲目'.encode("euc-jp"), None).endswith("曲目")
    try:
        webpage.fetch("not an address")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
