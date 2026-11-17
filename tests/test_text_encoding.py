"""Sidecar text files (CUE sheets, tracklists) in the legacy encodings people's rips still use."""
import pytest

from core import tracklist
from core.text_encoding import decode_text


@pytest.mark.parametrize('text, encoding', [
    ('一路向北 周杰伦 晴天 稻香 七里香', 'gbk'),
    ('王菲 红豆 传奇 匆匆那年', 'gbk'),
    ('李宗盛 山丘 当爱已成往事', 'gb18030'),
    ('夜に駆ける YOASOBI ハルジオン 群青', 'cp932'),
    ('中島みゆき 時代', 'cp932'),
    ('五月天 倔強 溫柔 知足 擁抱', 'big5'),
    ('張學友 吻別 每天愛你多一些', 'big5'),
    ('아이유 좋은 날 밤편지', 'euc_kr'),
    ('Café de Flore – Été', 'cp1252'),
    ('plain ascii', 'ascii'),
    ('UTF-8 中文 日本語', 'utf-8'),
    ('BOM 中文', 'utf-8-sig'),
    ('UTF-16 中文', 'utf-16'),
])
def test_text_is_read_in_its_own_encoding(text, encoding):
    assert decode_text(text.encode(encoding)) == text


def test_cue_sidecar_in_gbk_reads_its_titles(tmp_path):
    path = tmp_path / 'live.cue'
    path.write_bytes('TRACK 01 AUDIO\n  TITLE "晴天"\n  INDEX 01 00:00:00\n'.encode('gbk'))
    assert [e.name for e in tracklist.load_sidecar_tracklist(path)] == ['晴天']
