import json
import shutil
import subprocess
from pathlib import Path

import pytest

import core.manifest
import core.models
import core.split
from core import metadata_sources
from core import tagging
import core.musicbrainz


def sample_meta(tmp_path=None):
    meta = tagging.empty_metadata()
    meta['album'].update(artist='Dire Straits', album='Brothers In Arms', date='1985', genre='Rock')
    meta['track_artists'] = {'2': 'Dire Straits feat. Sting'}
    return meta


def pairs(args):
    """['-metadata', 'k=v', ...] -> {(flag, k): v}"""
    out = {}
    for flag, value in zip(args[::2], args[1::2]):
        if '=' in value:
            key, _, v = value.partition('=')
            out[(flag, key)] = v
    return out


def test_flac_tags_album_and_track():
    args = pairs(tagging.flac_tag_args(sample_meta(), 1, 9, 'So Far Away'))
    assert args[('-metadata', 'title')] == 'So Far Away'
    assert args[('-metadata', 'track')] == '1/9'
    assert args[('-metadata', 'artist')] == 'Dire Straits'
    assert args[('-metadata', 'album_artist')] == 'Dire Straits'   # falls back to artist
    assert args[('-metadata', 'album')] == 'Brothers In Arms'


def test_track_artist_override():
    raw = tagging.flac_tag_args(sample_meta(), 2, 9, 'Money For Nothing')
    assert pairs(raw)[('-metadata', 'artist')] == 'Dire Straits feat. Sting'


def test_empty_values_are_skipped_and_no_metadata_means_no_args():
    assert tagging.flac_tag_args(None, 1, 2, 'x') == []
    args = pairs(tagging.flac_tag_args(tagging.empty_metadata(), 3, 0, 'Song'))
    assert ('-metadata', 'album') not in args and ('-metadata', 'artist') not in args
    assert args[('-metadata', 'track')] == '3'


def test_cover_only_from_an_existing_jpeg_or_png(tmp_path):
    meta = sample_meta()
    meta['cover'] = str(tmp_path / 'missing.jpg')
    assert tagging.embedded_cover(meta) is None
    gif = tmp_path / 'cover.gif'; gif.write_bytes(b'GIF89a')
    meta['cover'] = str(gif)
    assert tagging.embedded_cover(meta) is None
    png = tmp_path / 'art.png'; png.write_bytes(b'\x89PNG\r\n\x1a\n')
    meta['cover'] = str(png)
    assert tagging.embedded_cover(meta) == png
    out = tmp_path / 'album'
    assert tagging.write_folder_cover(meta, out) == out / 'cover.png'
    assert (out / 'cover.png').read_bytes() == png.read_bytes()


def test_cover_crop_suggests_paired_borders_and_preserves_original(backend, qt_app, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QImage, QPainter
    from gui import cover_crop

    original = QImage(320, 320, QImage.Format_RGB32)
    original.fill(QColor('white'))
    with QPainter(original) as painter:
        painter.fillRect(46, 0, 228, 320, QColor('#835878'))
    assert cover_crop.suggest_crop(original) == dict(left=46, right=46, top=0, bottom=0)

    white_design = original.copy()
    with QPainter(white_design) as painter:
        painter.fillRect(274, 0, 46, 320, QColor('#835878'))
    assert not any(cover_crop.suggest_crop(white_design).values())
    white_design.fill(QColor('white'))
    assert not any(cover_crop.suggest_crop(white_design).values())

    path = tmp_path / 'original.png'
    assert original.save(str(path))
    original_data = path.read_bytes()
    monkeypatch.setattr(backend.metadata, 'COVER_CACHE', tmp_path / 'cache')
    backend.metadata.chooseCover(str(path))
    assert backend.metadata.coverCropInfo()['left'] == 46
    assert backend.metadata.export_metadata()['cover'] == str(path)
    assert backend.metadata.applyCoverCrop(46, 46, 0, 0)
    metadata = backend.metadata.export_metadata()
    cropped = Path(metadata['cover'])
    assert cover_crop.read_cover(str(cropped)).size().width() == 228
    assert path.read_bytes() == original_data
    assert tagging.embedded_cover(metadata) == cropped

    # Reapplying online metadata can download the same image to another path.
    download = tmp_path / 'download.png'
    download.write_bytes(original_data)
    info = metadata_sources.AlbumInfo('itunes', cover_url='https://x/cover.png')
    monkeypatch.setattr(metadata_sources, 'fetch', lambda *_args: info)
    monkeypatch.setattr(metadata_sources, 'download_cover', lambda *_args: download)
    backend.metadata.reset_metadata('another session')
    backend.metadata.meta_candidates = [metadata_sources.Candidate('itunes', '7', 'Album', 'Band')]
    backend.put(metaChosen=0)
    backend.metadata.metaApply(False, True, False, False)
    backend.pool.waitForDone(5000)
    qt_app.processEvents()
    metadata = backend.metadata.export_metadata()
    assert metadata['cover'] == str(cropped)
    assert backend.metadata.coverCropInfo()['left'] == 46
    assert tagging.embedded_cover(metadata) == cropped

    output = tmp_path / 'out'
    output.mkdir()
    (output / 'cover.png').write_bytes(original_data)
    assert tagging.write_folder_cover(metadata, output).read_bytes() == cropped.read_bytes()
    backend.metadata.restoreCover()
    assert tagging.write_folder_cover(backend.metadata.export_metadata(), output).read_bytes() == original_data
    backend.metadata.chooseCover(str(path))
    assert backend.metadata.export_metadata()['cover'] == str(path)


def test_control_characters_are_stripped():
    meta = sample_meta()
    meta['album']['album'] = 'Bad\nName\x00'
    assert pairs(tagging.flac_tag_args(meta, 1, 1, 'x'))[('-metadata', 'album')] == 'BadName'


def test_manifest_keeps_metadata_and_reads_old_manifests():
    manifest = core.manifest.JobManifest('p', 1, 'a', None, 'o', 'mkv', {}, {}, 'now', metadata=sample_meta())
    again = core.manifest.JobManifest.from_json(manifest.to_json())
    assert again.metadata['album']['album'] == 'Brothers In Arms'
    old = json.loads(manifest.to_json()); old.pop('metadata')
    assert core.manifest.JobManifest.from_json(json.dumps(old)).metadata == {}


# ------------------------------------------------------------ online sources (network mocked)

def test_itunes_search_and_fetch(monkeypatch):
    def fake(url):
        if 'search' in url:
            return {'results': [{'wrapperType': 'collection', 'collectionId': 7, 'collectionName': 'Album',
                                 'artistName': 'Band', 'releaseDate': '1985-05-13T07:00:00Z', 'trackCount': 2,
                                 'primaryGenreName': 'Rock', 'artworkUrl100': 'https://x/100x100bb.jpg'}]}
        return {'results': [
            {'wrapperType': 'collection', 'collectionName': 'Album', 'artistName': 'Band', 'releaseDate': '1985-05-13T07:00:00Z',
             'primaryGenreName': 'Rock', 'artworkUrl100': 'https://x/100x100bb.jpg'},
            {'wrapperType': 'track', 'trackNumber': 2, 'trackName': 'Two', 'artistName': 'Band & Guest', 'trackTimeMillis': 2000},
            {'wrapperType': 'track', 'trackNumber': 1, 'trackName': 'One', 'artistName': 'Band', 'trackTimeMillis': 1000}]}
    monkeypatch.setattr(metadata_sources, '_get_json', fake)
    found = metadata_sources.search('itunes', 'Band', 'Album')
    assert found[0].id == '7' and found[0].date == '1985-05-13'
    info = metadata_sources.fetch('itunes', '7')
    assert (info.album, info.genre, info.date) == ('Album', 'Rock', '1985-05-13')
    assert info.cover_url == 'https://x/1200x1200bb.jpg'   # default cover size is "large"
    assert [t.title for t in info.tracks] == ['One', 'Two'] and info.tracks[1].artist == 'Band & Guest'


def test_deezer_region_block_is_reported(monkeypatch):
    monkeypatch.setattr(metadata_sources, '_get_json', lambda url: {'data': [], 'total': 16})
    with pytest.raises(RuntimeError, match='REGION_BLOCKED'):
        metadata_sources.search('deezer', 'Band', 'Album')


def test_musicbrainz_fetch_uses_release_group_genres(monkeypatch):
    calls = []
    def fake(path, params):
        calls.append(path)
        if path.startswith('release-group/'):
            return {'genres': [{'name': 'rock', 'count': 3}, {'name': 'classic rock', 'count': 5}]}
        return {'title': 'Album', 'date': '1985', 'genres': [], 'release-group': {'id': 'rg'},
                'artist-credit': [{'name': 'Band', 'joinphrase': ''}],
                'media': [{'tracks': [{'title': 'One', 'length': 1000, 'artist-credit': [{'name': 'Band', 'joinphrase': ' feat. '}, {'name': 'Guest'}]}]}]}
    monkeypatch.setattr(core.musicbrainz, 'api_get', fake)
    info = metadata_sources.fetch('musicbrainz', 'id1')
    assert info.genre == 'Classic Rock, Rock'
    assert info.tracks[0].artist == 'Band feat. Guest' and info.tracks[0].seconds == 1.0
    assert calls == ['release/id1', 'release-group/rg']


def test_cover_download_rejects_non_images(tmp_path, monkeypatch):
    class Response:
        def __init__(self, data): self.data = data
        def read(self, n=-1): return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(metadata_sources.urllib.request, 'urlopen', lambda req, timeout: Response(b'<html>'))
    with pytest.raises(RuntimeError):
        metadata_sources.download_cover('https://x/c', tmp_path, 'k')
    monkeypatch.setattr(metadata_sources.urllib.request, 'urlopen', lambda req, timeout: Response(b'\xff\xd8\xff\xe0data'))
    assert metadata_sources.download_cover('https://x/c', tmp_path, 'k').suffix == '.jpg'


# ------------------------------------------------------------ backend

def test_backend_apply_fills_album_cover_and_track_artists(backend, qt_app, tmp_path, monkeypatch):
    backend.disc.chapters = [core.models.Chapter(i, (i - 1) * 60, i * 60) for i in (1, 2)]
    backend.disc.rebuild_chapters({1: 'One', 2: 'Two'})
    backend.metadata.meta_candidates = [metadata_sources.Candidate('itunes', '7', 'Album', 'Band')]
    backend.put(metaChosen=0)
    info = metadata_sources.AlbumInfo('itunes', 'Album', 'Band', 'Band', '1985', 'Rock', 'https://x/c.jpg',
                                      [metadata_sources.TrackInfo('One', 'Band'), metadata_sources.TrackInfo('Two', 'Band & Guest')])
    cover = tmp_path / 'c.jpg'; cover.write_bytes(b'\xff\xd8\xff')
    monkeypatch.setattr(metadata_sources, 'fetch', lambda s, i: info)
    monkeypatch.setattr(metadata_sources, 'download_cover', lambda url, d, k: cover)
    backend.metadata.metaApply(True, True, True, False)
    backend.pool.waitForDone(5000); qt_app.processEvents()
    meta = backend.metadata.export_metadata()
    assert meta['album']['album'] == 'Album' and meta['album']['genre'] == 'Rock'
    assert meta['cover'] == str(cover)
    assert meta['track_artists'] == {'2': 'Band & Guest'}      # same-as-album artists are left empty
    assert backend.disc.chapter_model.rows[1]['artist'] == 'Band & Guest'


def test_backend_manual_edits(backend):
    backend.disc.chapters = [core.models.Chapter(1, 0, 60)]
    backend.disc.rebuild_chapters({1: 'One'})
    backend.metadata.setMeta('album.album', 'Live')
    backend.metadata.setMeta('nonsense.key', 'x')
    backend.metadata.setTrackArtist(0, 'Guest')
    meta = backend.metadata.export_metadata()
    assert meta['album']['album'] == 'Live' and meta['track_artists'] == {'1': 'Guest'}


# ------------------------------------------------------------ real ffmpeg round trip

@pytest.mark.skipif(not (shutil.which('ffmpeg') and shutil.which('ffprobe')), reason='ffmpeg not installed')
def test_flac_chapter_preserves_24_bit_pcm_and_embeds_cover(tmp_path):
    def run(*args):
        return subprocess.check_output(args)

    source = tmp_path / 'source.mkv'
    cover = tmp_path / 'cover.png'
    run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
        'aevalsrc=0.1*sin(2*PI*997*t)|0.09*sin(2*PI*731*t):s=48000:d=3',
        '-af', 'asetnsamples=n=960:p=0', '-c:a', 'pcm_s24le', str(source))
    run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=orange:s=64x64', '-frames:v', '1', str(cover))
    metadata = sample_meta()
    metadata['cover'] = str(cover)
    result, = core.split.split_flac(source, [core.models.Chapter(2, 1, 2, name='Two')],
                                  tmp_path / 'out', metadata=metadata)
    assert result.name == 'Two.flac'
    probe = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(result)))
    audio, picture = probe['streams']
    assert (audio['codec_name'], audio['sample_rate'], audio['channels'], audio['bits_per_raw_sample']) == (
        'flac', '48000', 2, '24')
    assert picture['disposition']['attached_pic'] == 1
    tags = {k.lower(): v for k, v in probe['format']['tags'].items()}
    assert (tags['title'], tags['track'], tags['artist']) == ('Two', '1/1', 'Dire Straits feat. Sting')
    pcm_args = ('-map', '0:a:0', '-c:a', 'pcm_s24le', '-f', 's24le', '-')
    source_samples = run('ffmpeg', '-v', 'error', '-i', str(source), *pcm_args)
    chapter_samples = run('ffmpeg', '-v', 'error', '-i', str(result), *pcm_args)
    bytes_per_second = 48000 * 2 * 3
    assert chapter_samples == source_samples[bytes_per_second:2 * bytes_per_second]


def test_review_search_other_source_ranks_by_fit_and_feeds_review(backend, qt_app, monkeypatch):
    backend.disc.chapters = [core.models.Chapter(i, (i - 1) * 60, i * 60) for i in (1, 2, 3)]
    backend.disc.rebuild_chapters({})
    found = [metadata_sources.Candidate('itunes', 'a', 'Single', 'Band', track_count=1, thumb='https://x/a.jpg'),
             metadata_sources.Candidate('itunes', 'b', 'Live', 'Band', track_count=3, thumb='https://x/b.jpg')]
    monkeypatch.setattr(metadata_sources, 'search', lambda *a: found)
    monkeypatch.setattr(metadata_sources, 'fetch', lambda s, i, tracks_only=False: metadata_sources.AlbumInfo(
        'itunes', tracks=[metadata_sources.TrackInfo(t, seconds=60) for t in ('One', 'Two', 'Three')]))
    backend.names.setTitleSource('itunes')
    assert backend.state['titleSource'] == 'itunes'
    backend.names.search('Band', 'Live', '')
    backend.pool.waitForDone(5000); qt_app.processEvents()
    rows = backend.names.release_model.rows
    assert [r['fit'] for r in rows] == ['exact', 'close'] and rows[0]['thumb'] == 'https://x/b.jpg'
    backend.names.selectRelease(0)
    backend.pool.waitForDone(5000); qt_app.processEvents()
    assert [r['proposed'] for r in backend.names.review_model.rows] == ['One', 'Two', 'Three']
    backend.names.setTitleSource('musicbrainz')
    assert backend.names.release_model.rows == [] and backend.state['mb'] == 'idle'
