import urllib.request
from pathlib import Path

import pytest

import extractor
import metadata_sources as ms
import settings
import tagging
from gui import logic
import core.musicbrainz


@pytest.fixture(autouse=True)
def restore_network():
    yield
    ms.configure()  # back to system proxy / defaults for other tests


@pytest.mark.parametrize('value, expected', [
    ('127.0.0.1:7890', 'http://127.0.0.1:7890'),
    ('https://proxy.lan:8443', 'https://proxy.lan:8443'),
    ('  ', ''),
    ('socks5://127.0.0.1:1080', None),   # urllib cannot speak SOCKS without extra packages
    ('http://host-without-port', None),
    ('127.0.0.1:notaport', None),
])
def test_normalize_proxy(value, expected):
    assert logic.normalize_proxy(value) == expected


def proxies_of_installed_opener():
    # An empty ProxyHandler registers no protocol handlers, so urllib leaves it out of the
    # opener entirely; build_opener also skips its default (system) ProxyHandler. No handler = no proxy.
    opener = urllib.request._opener
    return next((h.proxies for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)), {})


def test_configure_proxy_modes_and_timeout():
    ms.configure('custom', 'http://127.0.0.1:7890', 30)
    assert proxies_of_installed_opener() == {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
    assert extractor.MUSICBRAINZ_TIMEOUT == 30.0
    ms.configure('none')
    assert proxies_of_installed_opener() == {}


def test_itunes_country_and_cover_size(monkeypatch):
    urls = []
    def fake(url):
        urls.append(url)
        return {'results': [{'wrapperType': 'collection', 'collectionName': 'A', 'artistName': 'B',
                             'artworkUrl100': 'https://x/100x100bb.jpg'}]}
    monkeypatch.setattr(ms, '_get_json', fake)
    ms.configure(country='jp', cover_size='original')
    info = ms.fetch('itunes', '1')
    assert 'country=JP' in urls[0]
    assert info.cover_url.endswith('3000x3000bb.jpg')
    ms.configure(cover_size='standard')
    assert ms.fetch('itunes', '1').cover_url.endswith('600x600bb.jpg')


def test_musicbrainz_cover_size_and_503_retry(monkeypatch):
    calls = []
    def flaky(path, params):
        calls.append(path)
        if len(calls) == 1:
            raise RuntimeError('MusicBrainz returned an error (503): Service Temporarily Unavailable')
        return {'title': 'A', 'genres': [{'name': 'rock', 'count': 1}], 'media': []}
    monkeypatch.setattr(core.musicbrainz, 'api_get', flaky)
    monkeypatch.setattr(ms.time, 'sleep', lambda s: None)
    ms.configure(cover_size='original')
    info = ms.fetch('musicbrainz', 'rid')
    assert calls == ['release/rid', 'release/rid']
    assert info.cover_url.endswith('/rid/front')


def test_check_reports_states(monkeypatch):
    monkeypatch.setattr(ms, '_get_json', lambda url: {'data': [], 'total': 5})
    assert ms.check('deezer')[0] == 'blocked'
    def fail(url):
        raise RuntimeError('Could not reach host')
    monkeypatch.setattr(ms, '_get_json', fail)
    state, ms_, detail = ms.check('itunes')
    assert state == 'error' and 'Could not reach' in detail


@pytest.mark.parametrize('mode, embedded, folder', [('both', True, True), ('embed', True, False), ('folder', False, True)])
def test_cover_mode(tmp_path, mode, embedded, folder):
    cover = tmp_path / 'c.jpg'; cover.write_bytes(b'\xff\xd8\xff')
    meta = tagging.empty_metadata(); meta['cover'] = str(cover); meta['cover_mode'] = mode
    assert ('-attach' in tagging.chapter_args(meta, 1, 1, 'x')) is embedded
    assert (tagging.write_folder_cover(meta, tmp_path / 'out') is not None) is folder


def test_defaults():
    d = settings.DEFAULTS
    assert (d['proxy_mode'], d['net_timeout'], d['meta_source'], d['itunes_country'],
            d['cover_size'], d['cover_target'], d['meta_auto_search']) == ('system', '15', 'musicbrainz', 'US', 'large', 'both', False)


def test_backend_network_preferences(backend):
    backend.setPreference('meta_auto_search', 'true')
    assert backend.config['meta_auto_search'] is True
    backend.setPreference('itunes_country', 'CN')
    backend.setPreference('itunes_country', 'XX')
    assert backend.config['itunes_country'] == 'CN'
    backend.setPreference('cover_target', 'folder')
    assert backend.metadata.export_metadata()['cover_mode'] == 'folder'
    messages = []
    backend.dialogRequested.connect(lambda kind, text: messages.append(text))
    backend.setProxyUrl('socks5://x:1')
    assert messages and backend.config.get('proxy_url', '') == ''
    backend.setProxyUrl('127.0.0.1:7890')
    assert backend.config['proxy_url'] == 'http://127.0.0.1:7890'


def test_clear_cover_cache_keeps_current_cover(backend, tmp_path, monkeypatch):
    cache = tmp_path / 'covers'; cache.mkdir()
    keep = cache / 'keep.jpg'; keep.write_bytes(b'1' * 10)
    (cache / 'old.jpg').write_bytes(b'2' * 2000)
    monkeypatch.setattr(type(backend.metadata), 'COVER_CACHE', cache)
    backend.metadata.meta['cover'] = str(keep)
    backend.metadata.refresh_cover_cache()
    assert backend.state['coverCache'] == '2.0 KB'
    backend.metadata.clearCoverCache()
    assert sorted(p.name for p in cache.iterdir()) == ['keep.jpg']


def test_discogs_search_and_fetch_parsing(monkeypatch):
    seen = []
    def fake(url, headers=None):
        seen.append((url, headers or {}))
        if '/database/search' in url:
            return {'results': [{'id': 42, 'title': 'Kana Nishino (2) - Live Tour', 'year': '2025', 'country': 'Japan',
                                 'format': ['Blu-ray', 'Album'], 'thumb': 'https://i/t.jpg'}]}
        return {'title': 'Live Tour', 'released': '2025-10-00', 'styles': ['J-pop'], 'genres': ['Pop'],
                'artists': [{'name': 'Kana Nishino (2)', 'join': ''}],
                'images': [{'type': 'secondary', 'uri': 'https://i/back.jpg'}, {'type': 'primary', 'uri': 'https://i/front.jpg'}],
                'tracklist': [{'type_': 'heading', 'title': 'Disc 1'},
                              {'type_': 'track', 'title': 'Opening', 'duration': '1:05'},
                              {'type_': 'index', 'title': 'Medley', 'sub_tracks': [
                                  {'type_': 'track', 'title': 'Part A', 'duration': '2:00'},
                                  {'type_': 'track', 'title': 'Part B', 'duration': '', 'artists': [{'name': 'Guest', 'join': ''}]}]},
                              {'type_': 'track', 'title': 'Long Jam', 'duration': '1:02:03'}]}
    monkeypatch.setattr(ms, '_get_json', fake)
    ms.configure(discogs_token='abc')
    found = ms.search('discogs', 'Kana Nishino', 'Live Tour')
    assert (found[0].artist, found[0].title, found[0].thumb) == ('Kana Nishino', 'Live Tour', 'https://i/t.jpg')
    assert 'artist=Kana+Nishino' in seen[0][0] and seen[0][1] == {'Authorization': 'Discogs token=abc'}
    info = ms.fetch('discogs', '42')
    assert (info.artist, info.date, info.genre, info.cover_url) == ('Kana Nishino', '2025-10', 'J-pop', 'https://i/front.jpg')
    assert [(t.title, t.artist, t.seconds) for t in info.tracks] == [
        ('Opening', 'Kana Nishino', 65.0), ('Part A', 'Kana Nishino', 120.0), ('Part B', 'Guest', None), ('Long Jam', 'Kana Nishino', 3723.0)]


def test_discogs_works_without_token(monkeypatch):
    seen = []
    monkeypatch.setattr(ms, '_get_json', lambda url, headers=None: seen.append(headers) or {'results': []})
    ms.configure(discogs_token='')
    ms.search('discogs', '', '', '4988005123456')
    assert seen == [{}]


def test_backend_discogs_token(backend):
    backend.setDiscogsToken('  ab c  ')
    assert backend.config['discogs_token'] == 'abc'
    assert ms._config['discogs_token'] == 'abc'
