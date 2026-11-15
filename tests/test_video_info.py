import core.models
from core import preview
from gui import track_info
import core.tools

BD_PROBE = dict(codec_name='h264', codec_long_name='H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10', profile='High',
                width=1920, height=1080, coded_width=1920, coded_height=1088, has_b_frames=1, sample_aspect_ratio='1:1',
                display_aspect_ratio='16:9', pix_fmt='yuv420p', level=41, chroma_location='left',
                field_order='progressive', refs=2, mime_codec_string='avc1.640029', r_frame_rate='24000/1001',
                avg_frame_rate='24000/1001', bits_per_raw_sample='8', start_time='4200.000000',
                frame=dict(interlaced_frame=0, top_field_first=0, tags=dict(timecode='01:00:00:00')))
UHD_PROBE = dict(codec_name='hevc', profile='Main 10', width=3840, height=2160, pix_fmt='yuv420p10le', level=153,
                 color_range='tv', color_primaries='bt2020', color_transfer='smpte2084', color_space='bt2020nc',
                 r_frame_rate='24000/1001', avg_frame_rate='24000/1001',
                 frame=dict(side_data_list=[
                     dict(side_data_type='Mastering display metadata', min_luminance='50/10000', max_luminance='10000000/10000'),
                     dict(side_data_type='Content light level metadata', max_content=1000, max_average=400),
                     dict(side_data_type='Dolby Vision RPU Data')]))
DVD_PROBE = dict(codec_name='mpeg2video', width=720, height=480, sample_aspect_ratio='32:27', display_aspect_ratio='16:9',
                 pix_fmt='yuv420p', level=-99, color_range='tv', field_order='tt', r_frame_rate='30000/1001',
                 avg_frame_rate='30000/1001', max_bit_rate='7900000', frame=dict(interlaced_frame=1, top_field_first=1))


def sheet(probe, sampled=None, track=None):
    track = track or core.models.Track(0, 'video', 'AVC/H.264/MPEG-4p10', 'V_MPEG4/ISO/AVC', stream_id=0x1011,
                                     properties={'pixel_dimensions': '1920x1080'})
    out = track_info.sections(track, 'video', 8988, probe, lambda k: k, 'zh', sampled_kbps=sampled)
    return {row['label']: row['value'] for section in out for row in section['rows']}, [s['title'] for s in out]


def test_blu_ray_video_sheet():
    rows, titles = sheet(BD_PROBE, sampled=23914.5)
    assert titles[:2] == ['tiOverview', 'tiColour'] and titles[-1] == 'tiTechnical'
    assert rows['tiCodec'] == 'H.264 / AVC · High@L4.1'
    assert rows['tiResolution'] == '1920 × 1080' and rows['tiAspect'] == '16:9'
    assert rows['tiFrameRate'] == '23.976 fps (24000/1001)'
    assert rows['tiScan'] == 'tiProgressive'
    assert rows['tiBitrate'] == '≈ 23.91 Mbps tiSampled'
    assert rows['tiDynamicRange'] == 'SDR' and rows['tiBitDepth'] == '8-bit' and rows['tiChroma'] == '4:2:0'
    assert rows['tiCodedSize'] == '1920 × 1088' and rows['tiTimecode'] == '01:00:00:00' and rows['tiPid'] == '0x1011 (4113)'
    assert track_info.video_summary(core.models.Track(0, 'video', 'AVC', 'V_MPEG4/ISO/AVC'), BD_PROBE) == \
        'H.264 · 1920×1080 · 23.976p · SDR'


def test_hdr_and_dolby_vision_are_named():
    rows, _ = sheet(UHD_PROBE)
    assert rows['tiDynamicRange'] == 'Dolby Vision + HDR10'
    assert rows['tiBitDepth'] == '10-bit' and rows['tiPrimaries'] == 'BT.2020' and rows['tiTransfer'] == 'PQ (SMPTE ST 2084)'
    assert rows['tiMastering'] == '0.005 – 1000 nits' and rows['tiLightLevel'] == 'MaxCLL 1000 / MaxFALL 400 nits'
    assert rows['tiCodec'] == 'H.265 / HEVC · Main 10@L5.1'


def test_dvd_video_sheet():
    track = core.models.Track(0, 'video', 'MPEG-2', 'mpeg2video', properties=dict(width=720, height=480))
    rows, _ = sheet(DVD_PROBE, track=track)
    assert rows['tiAspect'] == '16:9 (tiPixelAspect 32:27)'
    assert rows['tiScan'] == 'tiInterlaced · tiTopFirst'
    assert rows['tiFrameRate'] == '29.97 fps (30000/1001)'
    assert rows['tiMaxBitrate'] == '7,900 kbps' and rows['tiColorRange'] == 'tiRangeLimited'
    assert track_info.video_summary(track, DVD_PROBE) == 'MPEG-2 · 720×480 · 29.97i · SDR'
    # before ffprobe answers, the card still names the codec and size
    assert track_info.video_summary(track, None) == 'MPEG-2'
    assert track_info.video_summary(core.models.Track(0, 'video', 'AVC/H.264/MPEG-4p10', 'V_MPEG4/ISO/AVC',
                                                    properties={'pixel_dimensions': '1920x1080'}), None) == 'H.264 · 1920×1080'


def test_bitrate_is_measured_from_packets(monkeypatch, tmp_path):
    import json, subprocess
    packets = [dict(size=100_000, dts_time=f'{t / 24:.4f}') for t in range(24 * 10 + 1)]
    seen = []
    monkeypatch.setattr(core.tools, 'run', lambda args, timeout=None: seen.append(args) or
                        subprocess.CompletedProcess(args, 0, json.dumps(dict(packets=packets)), ''))
    source = tmp_path / 'movie.mkv'
    rate = preview.sample_bitrate(source, core.models.Track(0, 'video', 'AVC'), 0, at=300)
    assert round(rate) == round(241 * 100_000 * 8 / 10 / 1000)
    assert seen[0][seen[0].index('-read_intervals') + 1] == '300.000%+60'


def test_backend_sheet_for_the_video_track(backend):
    backend.disc.playlist = core.models.Playlist(path=core.models.Path('movie.mkv'), tracks=[
        core.models.Track(0, 'video', 'AVC/H.264/MPEG-4p10', 'V_MPEG4/ISO/AVC', properties={'pixel_dimensions': '1920x1080'}),
        core.models.Track(1, 'audio', 'FLAC', 'A_FLAC', channels=2)], duration_seconds=60)
    backend.disc.showTrackInfo('video', 0)
    info = backend.state['trackInfo']
    assert info['title'] == backend.tr('tiVideoTitle') and info['heading'] == 'H.264 · 1920×1080'
    backend.disc.info_done(dict(BD_PROBE, sampled_kbps=24000.0))
    info = backend.state['trackInfo']
    assert info['heading'] == 'H.264 · 1920×1080 · 23.976p · SDR'
    assert backend.state['videoSummary'] == info['heading']
    assert '24.00 Mbps' in info['text']
