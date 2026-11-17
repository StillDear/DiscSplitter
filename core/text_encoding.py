"""
text_encoding.py

Text files people keep beside their music (CUE sheets, tracklists) are often not UTF-8: older
Chinese rips use GBK, Japanese ones Shift-JIS, Taiwanese and Hong Kong ones Big5. decode_text()
picks the encoding that gives the most believable text, without any extra package.

How it scores: every legacy encoding decodes most byte strings without error, so each result is
judged by its characters. Common characters of that encoding's own script count for it (simplified
characters in GB2312's set for GBK, kana and level-1 kanji for Shift-JIS, level-1 hanzi for Big5,
Hangul for EUC-KR); rare characters, half-width katakana, private-use characters and controls
count against it. Western text in Windows-1252 is the fallback when no Asian reading is believable.

EUC-KR's Hangul block lies on the same bytes as GB2312's everyday hanzi, so short Korean text made
of less common syllables can come out as Chinese; on such a tie Chinese (the likelier case) wins.
"""
from __future__ import annotations

_CANDIDATES = ("gb18030", "cp932", "big5", "euc_kr")
# EUC-KR's Hangul block sits on the same bytes as GB2312's everyday hanzi, so Chinese text read as
# EUC-KR is all Hangul too - but random syllables. Korean words lean on a small set of syllables.
_COMMON_HANGUL = set(
    "이의는다에하고을로한지가기사서도리자나어인대스아수일니정우해주시오전라보요들소내상게제그러마부구조여만"
    "성신무원세유경동비장미모연중화문르위트바날야음말계개면식적관물생과래임히할있되던것안없된를은와까께럼랑"
    "밤편좋랑노별꿈눈빛너난우랑사람운명처럼너무좋아해줘봐같이두번째첫눈물꽃잎바람하늘사랑해가요곡집앨범"
    "라이브콘서트투어버전리믹스인트로아웃드레몬불새벽달밤길집손맘속곳때줄수뿐더또왜넌네내게날널")


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def _common_in(ch: str, encoding: str) -> bool:
    """Whether a CJK character is among the everyday ones of that encoding's own region."""
    try:
        raw = ch.encode(encoding)
    except UnicodeEncodeError:
        return False
    if encoding == "gb18030":
        try:
            ch.encode("gb2312")          # GB2312: the 6,763 everyday simplified characters
            return True
        except UnicodeEncodeError:
            return False
    if len(raw) != 2:
        return False
    code = raw[0] << 8 | raw[1]
    if encoding == "cp932":
        return 0x889F <= code <= 0x9872      # JIS level 1 kanji
    if encoding == "big5":
        return 0xA440 <= code <= 0xC67E      # Big5 level 1 hanzi
    return False


def _score(text: str, encoding: str) -> float:
    score = 0.0
    for ch in text:
        if ch < " " and ch not in "\r\n\t":
            score -= 3
        elif ch < "\x80":
            continue
        elif "぀" <= ch <= "ヿ":                    # hiragana, full-width katakana
            score += 2 if encoding == "cp932" else -1
        elif "가" <= ch <= "힣":                    # Hangul syllables
            score += (2 if ch in _COMMON_HANGUL else 0.3) if encoding == "euc_kr" else -1
        elif _is_cjk(ch):
            score += 1 if _common_in(ch, encoding) else -1
        elif "｡" <= ch <= "ﾟ" or "" <= ch <= "" or ch == "�":
            score -= 3                                       # half-width katakana, private use
        elif "　" <= ch <= "〿" or "！" <= ch <= "～":
            score += 0.5                                     # CJK punctuation, full-width forms
        else:
            score -= 1
    return score


def decode_text(data: bytes) -> str:
    """Bytes of a small text file -> text, in whatever encoding it was most likely written."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    best, best_score = None, 0.0
    for encoding in _CANDIDATES:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = _score(text, encoding)
        if score > best_score:
            best, best_score = text, score
    return best if best is not None else data.decode("cp1252", errors="replace")
