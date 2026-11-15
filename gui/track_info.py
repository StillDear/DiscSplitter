"""Build the "track details" sheet from mkvmerge's track data plus an optional ffprobe stream."""

from __future__ import annotations

LANGUAGES = {
    'jpn': ('日语', 'Japanese'), 'ja': ('日语', 'Japanese'),
    'eng': ('英语', 'English'), 'en': ('英语', 'English'),
    'zho': ('中文', 'Chinese'), 'chi': ('中文', 'Chinese'), 'zh': ('中文', 'Chinese'),
    'kor': ('韩语', 'Korean'), 'ko': ('韩语', 'Korean'),
    'fre': ('法语', 'French'), 'fra': ('法语', 'French'), 'fr': ('法语', 'French'),
    'ger': ('德语', 'German'), 'deu': ('德语', 'German'), 'de': ('德语', 'German'),
    'spa': ('西班牙语', 'Spanish'), 'es': ('西班牙语', 'Spanish'),
    'ita': ('意大利语', 'Italian'), 'it': ('意大利语', 'Italian'),
    'por': ('葡萄牙语', 'Portuguese'), 'rus': ('俄语', 'Russian'), 'tha': ('泰语', 'Thai'),
    'und': ('未指定', 'Undetermined'), 'mul': ('多语言', 'Multiple'), 'zxx': ('无语言内容', 'No linguistic content'),
}


def language(code: str, ietf: str, lang: str) -> str:
    code = (code or '').strip()
    names = LANGUAGES.get(code.lower()) or LANGUAGES.get((ietf or '').split('-')[0].lower())
    name = names[0 if lang == 'zh' else 1] if names else ''
    tag = ' / '.join(dict.fromkeys(filter(None, (code, ietf if ietf and ietf != code else ''))))
    return f'{name} ({tag})' if name and tag else name or tag


def sample_rate(hz) -> str:
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return ''
    if hz <= 0:
        return ''
    khz = hz / 1000
    return f'{khz:g} kHz'


def bitrate(kbps) -> str:
    try:
        kbps = float(kbps)
    except (TypeError, ValueError):
        return ''
    if kbps <= 0:
        return ''
    return f'{kbps / 1000:.2f} Mbps' if kbps >= 10_000 else f'{round(kbps):,} kbps'


def duration(seconds) -> str:
    if not seconds:
        return ''
    total = int(round(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def immersive(codec: str, profile: str) -> str:
    text = f'{codec} {profile}'.lower()
    if 'atmos' in text:
        return 'Dolby Atmos'
    if 'dts:x' in text or 'dts-x' in text:
        return 'DTS:X'
    if 'auro' in text:
        return 'Auro-3D'
    return ''


# ------------------------------------------------------------------ video
CODECS = {'h264': 'H.264 / AVC', 'hevc': 'H.265 / HEVC', 'mpeg2video': 'MPEG-2', 'mpeg1video': 'MPEG-1',
          'vc1': 'VC-1', 'av1': 'AV1', 'vp9': 'VP9'}
CODEC_IDS = {'V_MPEG4/ISO/AVC': 'h264', 'V_MPEGH/ISO/HEVC': 'hevc', 'V_MPEG2': 'mpeg2video', 'V_MPEG1': 'mpeg1video',
             'V_MS/VFW/FOURCC': 'vc1', 'V_AV1': 'av1', 'V_VP9': 'vp9', 'mpeg2video': 'mpeg2video'}
PRIMARIES = {'bt709': 'BT.709', 'bt2020': 'BT.2020', 'smpte170m': 'BT.601 NTSC', 'bt470bg': 'BT.601 PAL',
             'smpte432': 'Display P3'}
TRANSFERS = {'bt709': 'BT.709', 'smpte2084': 'PQ (SMPTE ST 2084)', 'arib-std-b67': 'HLG', 'smpte170m': 'BT.601',
             'bt2020-10': 'BT.2020'}
MATRICES = {'bt709': 'BT.709', 'bt2020nc': 'BT.2020 NCL', 'bt2020c': 'BT.2020 CL', 'smpte170m': 'BT.601',
            'bt470bg': 'BT.601'}


def _ratio(text) -> float | None:
    try:
        top, _, bottom = str(text).partition('/')
        value = float(top) / float(bottom or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def frame_rate(probe: dict, props: dict) -> str:
    rate = _ratio(probe.get('avg_frame_rate')) or _ratio(probe.get('r_frame_rate'))
    if rate is None and props.get('default_duration'):
        rate = 1e9 / float(props['default_duration'])
    if rate is None:
        return ''
    exact = probe.get('r_frame_rate') or ''
    text = f'{rate:.3f}'.rstrip('0').rstrip('.') + ' fps'
    return f'{text} ({exact})' if '/1001' in exact else text


def resolution(track, probe: dict) -> tuple[int, int] | None:
    width, height = probe.get('width'), probe.get('height')
    if not (width and height):
        dims = (track.properties or {}).get('pixel_dimensions', '')
        width, _, height = dims.partition('x')
    try:
        return int(width), int(height)
    except (TypeError, ValueError):
        return None


def scan_type(probe: dict, tr) -> str:
    frame = probe.get('frame') or {}
    order = probe.get('field_order') or ''
    if frame.get('interlaced_frame') == 1 or order in ('tt', 'bb', 'tb', 'bt'):
        top = frame.get('top_field_first') == 1 if frame else order in ('tt', 'tb')
        return tr('tiInterlaced') + ' · ' + tr('tiTopFirst' if top else 'tiBottomFirst')
    if order == 'progressive' or frame.get('interlaced_frame') == 0:
        return tr('tiProgressive')
    return ''


def dynamic_range(probe: dict) -> str:
    sides = [s.get('side_data_type', '') for s in (probe.get('side_data_list') or [])
             + ((probe.get('frame') or {}).get('side_data_list') or [])]
    names = []
    if any('DOVI' in s or 'Dolby Vision' in s for s in sides):
        names.append('Dolby Vision')
    transfer = probe.get('color_transfer') or (probe.get('frame') or {}).get('color_transfer') or ''
    if transfer == 'smpte2084':
        names.append('HDR10+' if any('HDR10+' in s or 'HDR Dynamic Metadata' in s for s in sides) else 'HDR10')
    elif transfer == 'arib-std-b67':
        names.append('HLG')
    if not names and probe:
        names.append('SDR')
    return ' + '.join(names)


def chroma(pix_fmt: str) -> str:
    if not pix_fmt:
        return ''
    for marker, name in (('444', '4:4:4'), ('422', '4:2:2'), ('420', '4:2:0'), ('411', '4:1:1')):
        if marker in pix_fmt:
            return name
    return 'YUV 4:2:0' if pix_fmt in ('nv12', 'p010le') else ''


def video_depth(probe: dict) -> str:
    raw = probe.get('bits_per_raw_sample')
    if raw and str(raw).isdigit() and int(raw) > 0:
        return f'{raw}-bit'
    pix = probe.get('pix_fmt') or ''
    for bits in ('16', '12', '10'):
        if f'p{bits}' in pix:
            return f'{bits}-bit'
    return '8-bit' if pix else ''


def _side(probe: dict, name: str) -> dict:
    for side in (probe.get('side_data_list') or []) + ((probe.get('frame') or {}).get('side_data_list') or []):
        if name in side.get('side_data_type', ''):
            return side
    return {}


def mastering(probe: dict) -> str:
    side = _side(probe, 'Mastering display')
    low, high = _ratio(side.get('min_luminance')), _ratio(side.get('max_luminance'))
    return f'{low:g} – {high:g} nits' if low is not None and high else ''


def light_level(probe: dict) -> str:
    side = _side(probe, 'Content light level')
    return f"MaxCLL {side['max_content']} / MaxFALL {side['max_average']} nits" if side.get('max_content') else ''


def codec_name(track, probe: dict) -> str:
    name = CODECS.get(probe.get('codec_name') or CODEC_IDS.get(track.codec_id, ''), track.codec)
    profile, level = probe.get('profile') or '', probe.get('level')
    if level not in (None, '', -99) and probe.get('codec_name') in ('h264', 'hevc'):
        level = f'{level / 10:g}' if probe.get('codec_name') == 'h264' else f'{level / 30:g}'
        profile = f'{profile}@L{level}' if profile else f'L{level}'
    return f'{name} · {profile}' if profile else name


def video_summary(track, probe: dict | None) -> str:
    """One line for the stream card: codec · size · frame rate · scan · range."""
    probe = probe or {}
    size = resolution(track, probe)
    rate = frame_rate(probe, track.properties or {}).split(' (')[0].replace(' fps', '')
    scan = ''
    if probe:
        frame = probe.get('frame') or {}
        interlaced = frame.get('interlaced_frame') == 1 or probe.get('field_order') in ('tt', 'bb', 'tb', 'bt')
        scan = 'i' if interlaced else 'p'
    name = probe.get('codec_name') or CODEC_IDS.get(track.codec_id, '')
    parts = [CODECS.get(name, track.codec).split(' / ')[0],
             f'{size[0]}×{size[1]}' if size else '', f'{rate}{scan}' if rate else '',
             dynamic_range(probe) if probe else '']
    return ' · '.join(p for p in parts if p)


def video_sections(track, playlist_duration, probe: dict, sampled_kbps, tr) -> tuple[list, list]:
    props = track.properties or {}
    frame = probe.get('frame') or {}
    size = resolution(track, probe)
    coded = (probe.get('coded_width'), probe.get('coded_height'))
    aspect = probe.get('display_aspect_ratio') or ''
    sar = probe.get('sample_aspect_ratio') or ''
    if aspect and sar and sar not in ('1:1', '0:1'):
        aspect = f"{aspect} ({tr('tiPixelAspect')} {sar})"
    rate = track.bitrate_kbps or sampled_kbps
    if not rate and probe.get('bit_rate') not in (None, '', 'N/A'):
        rate = float(probe['bit_rate']) / 1000
    nominal = probe.get('max_bit_rate')
    color_range = probe.get('color_range') or frame.get('color_range') or ''
    overview = [
        ('tiCodec', codec_name(track, probe)),
        ('tiResolution', f'{size[0]} × {size[1]}' if size else ''),
        ('tiAspect', aspect),
        ('tiFrameRate', frame_rate(probe, props)),
        ('tiScan', scan_type(probe, tr)),
        ('tiBitrate', (('≈ ' + bitrate(rate) + ' ' + tr('tiSampled')) if sampled_kbps and rate == sampled_kbps
                       else bitrate(rate))),
        ('tiMaxBitrate', bitrate(float(nominal) / 1000) if nominal and str(nominal).isdigit() else ''),
        ('tiDuration', duration(playlist_duration)),
    ]
    colour = [
        ('tiDynamicRange', dynamic_range(probe)),
        ('tiBitDepth', video_depth(probe)),
        ('tiChroma', chroma(probe.get('pix_fmt') or '')),
        ('tiColorRange', {'tv': tr('tiRangeLimited'), 'pc': tr('tiRangeFull')}.get(color_range, color_range)),
        ('tiPrimaries', PRIMARIES.get(probe.get('color_primaries', ''), probe.get('color_primaries', ''))),
        ('tiTransfer', TRANSFERS.get(probe.get('color_transfer', ''), probe.get('color_transfer', ''))),
        ('tiMatrix', MATRICES.get(probe.get('color_space', ''), probe.get('color_space', ''))),
        ('tiMastering', mastering(probe)),
        ('tiLightLevel', light_level(probe)),
    ]
    technical = [
        ('tiCodedSize', f'{coded[0]} × {coded[1]}' if all(coded) and size and tuple(coded) != size else ''),
        ('tiPixFmt', probe.get('pix_fmt', '')),
        ('tiChromaLoc', probe.get('chroma_location', '')),
        ('tiRefs', probe.get('refs', '') if probe.get('codec_name') in ('h264', 'hevc') else ''),
        ('tiBFrames', (tr('yes') if probe['has_b_frames'] else tr('no')) if 'has_b_frames' in probe else ''),
        ('tiMime', probe.get('mime_codec_string', '')),
        ('tiTimecode', (frame.get('tags') or {}).get('timecode', '')),
    ]
    return overview, colour, technical


def sections(track, kind: str, playlist_duration, probe: dict | None, tr, lang: str,
             sampled_kbps: float | None = None) -> list[dict]:
    """
    Ordered sheet: what you hear first (overview), then flags, then the
    technical identifiers. Rows without a value are left out.
    """
    props = track.properties or {}
    probe = probe or {}
    yes_no = lambda value: '' if value is None else tr('yes') if value else tr('no')
    channels = track.channels or probe.get('channels')
    layout = track.channel_layout if kind == 'audio' else ''
    probe_rate = probe.get('bit_rate')
    rate = track.bitrate_kbps or (float(probe_rate) / 1000 if probe_rate not in (None, '', 'N/A') else None)
    depth = track.bits_per_sample or probe.get('bits_per_raw_sample') or None
    profile = probe.get('profile') or ''

    overview = [
        ('tiName', track.title or props.get('track_name') or ''),
        ('tiCodec', track.codec),
    ]
    colour = []
    if kind == 'video':
        video, colour, video_technical = video_sections(track, playlist_duration, probe, sampled_kbps, tr)
        overview = overview[:1] + video
    elif kind == 'audio':
        overview += [
            ('tiImmersive', immersive(track.codec, profile)),
            ('tiLanguage', language(track.language, props.get('language_ietf', ''), lang)),
            ('tiChannels', (f'{layout} · ' if layout else '') + tr('tiChannelCount').format(n=channels) if channels else ''),
            ('tiSampleRate', sample_rate(track.sample_rate or probe.get('sample_rate'))),
            ('tiBitDepth', f'{depth}-bit' if depth and str(depth) != '0' else ''),
            ('tiBitrate', bitrate(rate)),
            ('tiDuration', duration(playlist_duration)),
        ]
    else:
        overview += [('tiLanguage', language(track.language, props.get('language_ietf', ''), lang))]

    flags = [
        ('tiDefault', yes_no(track.default_track if track.default_track is not None else props.get('default_track'))),
        ('tiForced', yes_no(props.get('forced_track'))),
        ('tiEnabled', yes_no(props.get('enabled_track'))),
    ]
    technical = [
        ('tiTrackId', f'#{track.track_id}'),
        ('tiPid', f'{track.stream_id:#06x} ({track.stream_id})' if track.stream_id else ''),
        ('tiCodecId', track.codec_id or props.get('codec_id', '')),
        ('tiDecoder', probe.get('codec_long_name', '')),
        ('tiProfile', profile),
        ('tiLayout', probe.get('channel_layout', '') if kind == 'audio' else ''),
        ('tiSampleFmt', probe.get('sample_fmt', '') if kind == 'audio' else ''),
    ]
    if kind == 'video':
        technical += video_technical
    out = []
    for key, rows in (('tiOverview', overview), ('tiColour', colour), ('tiFlags', flags), ('tiTechnical', technical)):
        rows = [dict(label=tr(label), value=str(value)) for label, value in rows if value not in (None, '')]
        if rows:
            out.append(dict(title=tr(key), rows=rows))
    return out


def as_text(title: str, heading: str, sheet: list[dict]) -> str:
    lines = [title, heading, '']
    for section in sheet:
        lines.append(f"[{section['title']}]")
        lines += [f"{row['label']}: {row['value']}" for row in section['rows']]
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


# ---------------------------------------------------------------- stream cards (workspace)
# Each card: a title, a row of short chips, and one muted line of extra facts.

def short_language(code: str, ietf: str, lang: str) -> str:
    """"日语" / "Japanese" for a known code, else the code itself."""
    code = (code or '').strip()
    names = LANGUAGES.get(code.lower()) or LANGUAGES.get((ietf or '').split('-')[0].lower())
    if names and code.lower() != 'und':
        return names[0 if lang == 'zh' else 1]
    return '' if code.lower() in ('', 'und') else code


def _rate_text(kbps: float | None, approximate: bool, tr) -> str:
    text = bitrate(kbps)
    return tr('streamApprox').replace('{v}', text) if text and approximate else text


def audio_card(track, lang: str, tr) -> dict:
    from core import space
    chips = [track.channel_layout, f'{track.sample_rate / 1000:g}kHz' if track.sample_rate else '',
             f'{track.bits_per_sample}-bit' if track.bits_per_sample else '',
             short_language(track.language, track.properties.get('language_ietf', ''), lang)]
    if track.bitrate_kbps:
        rate = _rate_text(track.bitrate_kbps, False, tr)
    else:
        stored = space.audio_rate_bytes(track)
        rate = _rate_text(stored * 8 / 1000 if stored else None, not track.is_pcm, tr)
    # Disc track names often just repeat the format ("Dolby Atmos 7.1" on a TrueHD Atmos track)
    codec_words = {w for w in (track.codec or '').lower().split() if len(w) > 2}
    title_words = {w for w in (track.title or '').lower().split() if len(w) > 2 and w.isalpha()}
    name = track.title if track.title and not (title_words & codec_words) else ''
    extra = [rate, name, tr('streamDefault') if track.default_track else '']
    return dict(title=track.codec or '—', chips=[c for c in chips if c], extra=' · '.join(e for e in extra if e))


def subtitle_card(track, lang: str, tr) -> dict:
    codec = (track.codec or '').replace('HDMV ', '').replace('SubRip/SRT', 'SRT')
    name = short_language(track.language, track.properties.get('language_ietf', ''), lang) or tr('streamNoLang')
    extra = [track.title, tr('streamForced') if track.properties.get('forced_track') else '',
             tr('streamDefault') if track.default_track else '']
    # Built like an audio card: the format as the title, the language as a chip.
    return dict(title=codec or name, chips=[name] if codec else [], extra=' · '.join(e for e in extra if e))


def video_extra(playlist, source_size, tr) -> str:
    """Approximate picture bitrate (the source's average rate minus its known audio) and length."""
    from core import space
    rate = ''
    seconds = playlist.duration_seconds if playlist is not None else None
    if playlist is not None and source_size and seconds:
        audio = sum(space.audio_rate_bytes(t) or 0 for t in playlist.audio_tracks)
        rest = source_size / seconds - audio
        rate = _rate_text(rest * 8 / 1000, True, tr) if rest > 0 else ''
    return ' · '.join(x for x in (rate, duration(seconds)) if x)
