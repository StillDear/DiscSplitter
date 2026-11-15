import time

import core.models
from core import preview
from gui import track_info
from gui.i18n import CATALOGUES


def tr(key):
    return CATALOGUES['zh'].get(key, key)


def sheet_dict(sheet):
    return {section['title']: [(r['label'], r['value']) for r in section['rows']] for section in sheet}


def test_audio_sheet_order_and_formatting():
    track = core.models.Track(2, 'audio', 'TrueHD Atmos', 'A_TRUEHD', 'jpn', 8, 'Main', 48000, 24, default_track=True,
                    stream_id=0x1100, properties={'language_ietf': 'ja-JP', 'forced_track': False})
    probe = {'codec_long_name': 'TrueHD', 'channel_layout': '7.1', 'sample_fmt': 's32', 'bit_rate': '4560000'}
    sheet = sheet_dict(track_info.sections(track, 'audio', 8133, probe, tr, 'zh'))
    assert list(sheet) == ['概览', '标记', '技术信息']
    assert [label for label, _ in sheet['概览']] == ['名称', '编码', '沉浸式音频', '语言', '声道', '采样率', '位深', '码率', '时长']
    overview = dict(sheet['概览'])
    assert overview['沉浸式音频'] == 'Dolby Atmos'
    assert overview['语言'] == '日语 (jpn / ja-JP)'
    assert overview['声道'] == '7.1 · 8 声道'
    assert (overview['采样率'], overview['位深'], overview['码率'], overview['时长']) == ('48 kHz', '24-bit', '4,560 kbps', '2:15:33')
    assert dict(sheet['标记']) == {'默认轨道': '是', '强制显示': '否'}
    assert dict(sheet['技术信息'])['流 PID'] == '0x1100 (4352)'


def test_missing_values_are_left_out_and_text_export():
    track = core.models.Track(5, 'subtitles', 'HDMV PGS', language='')
    sheet = track_info.sections(track, 'subtitle', 0, None, tr, 'en')
    flat = [row['label'] for section in sheet for row in section['rows']]
    assert flat == ['编码', '轨道编号']                    # nothing blank, no audio-only rows
    text = track_info.as_text('T', 'H', sheet)
    assert 'HDMV PGS' in text and '#5' in text
    assert track_info.sample_rate(44100) == '44.1 kHz' and track_info.bitrate(12500) == '12.50 Mbps'
    assert track_info.immersive('DTS-HD Master Audio', 'DTS-HD MA + DTS:X') == 'DTS:X'


def test_backend_fills_decoder_details_in_the_background(backend, qt_app, monkeypatch):
    from test_backend import setup_disc
    setup_disc(backend)
    backend.smoke = False          # smoke mode never probes; settings already point at tmp_path
    monkeypatch.setattr(preview, 'probe_stream', lambda *a, **kw: {'codec_long_name': 'Decoder X', 'channel_layout': '5.1(side)'})
    backend.disc.showTrackInfo('audio', 0)
    assert backend.state['trackInfo']['probing']
    end = time.time() + 5
    while backend.state['trackInfo']['probing'] and time.time() < end:
        qt_app.processEvents()
        time.sleep(0.01)
    info = backend.state['trackInfo']
    assert not info['probing'] and info['error'] == ''
    assert 'Decoder X' in info['text'] and '5.1(side)' in info['text']
    assert backend.disc.copyTrackInfo()


def test_probe_failure_keeps_the_basic_sheet(backend, qt_app, monkeypatch):
    from test_backend import setup_disc
    setup_disc(backend)
    backend.smoke = False

    def broken(*_a, **_kw):
        raise RuntimeError('ffprobe failed\nNo such file')

    monkeypatch.setattr(preview, 'probe_stream', broken)
    backend.disc.showTrackInfo('audio', 0)
    end = time.time() + 5
    while backend.state['trackInfo']['probing'] and time.time() < end:
        qt_app.processEvents()
        time.sleep(0.01)
    info = backend.state['trackInfo']
    assert info['error'] == 'No such file' and info['sections']
