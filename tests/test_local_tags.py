"""Tags read from music files the user already has: parsing ffprobe's answer, sorting files into albums,
choosing the cover, and the tags page applying the result."""
import shutil
import subprocess
from pathlib import Path

import pytest

import core.models
from core import local_tags, metadata_sources, tools
from core.jobs import Failure


def probe_json(tags=None, stream_tags=None, duration='200.5', codec='flac', pictures=()):
    streams = [dict(index=0, codec_type='audio', codec_name=codec, tags=stream_tags or {})]
    for i, comment in enumerate(pictures, start=1):
        streams.append(dict(index=i, codec_type='video', codec_name='mjpeg', disposition=dict(attached_pic=1),
                            tags=dict(comment=comment)))
    return dict(format=dict(duration=duration, tags=tags or {}), streams=streams)


def touch(path: Path, data=b'x') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ------------------------------------------------------------ one file

def test_tags_from_any_format_are_read_by_their_usual_names():
    data = probe_json(tags={'TITLE': 'So Far Away', 'ARTIST': 'Dire Straits', 'ALBUM': 'Brothers In Arms',
                            'ALBUMARTIST': 'Dire Straits', 'DATE': '1985', 'GENRE': 'Rock',
                            'track': '01/09', 'disc': '1/1', 'MUSICBRAINZ_ALBUMID': 'abc-123'})
    item = local_tags.read_file(Path('a.flac'), data)
    assert (item.title, item.artist, item.album, item.album_artist) == ('So Far Away', 'Dire Straits', 'Brothers In Arms', 'Dire Straits')
    assert (item.date, item.genre, item.track, item.disc, item.mb_album) == ('1985', 'Rock', 1, 1, 'abc-123')
    assert item.seconds == pytest.approx(200.5) and item.codec == 'FLAC' and not item.named_from_file


def test_ogg_tags_on_the_stream_and_id3_album_artist_names():
    item = local_tags.read_file(Path('a.opus'), probe_json(stream_tags={'title': 'Song', 'album artist': 'Band',
                                                                        'TRACKNUMBER': '7'}, codec='opus'))
    assert (item.title, item.album_artist, item.track) == ('Song', 'Band', 7)


def test_untagged_files_are_named_from_the_file_name():
    item = local_tags.read_file(Path('Album/1-03 Some Song.flac'), probe_json())
    assert (item.disc, item.track, item.title) == (1, 3, 'Some Song') and item.named_from_file
    item = local_tags.read_file(Path('Album/05. Another One.mp3'), probe_json())
    assert (item.track, item.title) == (5, 'Another One')
    item = local_tags.read_file(Path('Album/Intro.flac'), probe_json())
    assert (item.track, item.title) == (None, 'Intro')


def test_disc_folder_gives_the_disc_number():
    item = local_tags.read_file(Path('Album/Disc 2/01 - Song.flac'), probe_json(tags={'title': 'Song'}))
    assert item.disc == 2


def test_the_front_cover_is_chosen_among_embedded_pictures():
    item = local_tags.read_file(Path('a.flac'), probe_json(pictures=('Cover (back)', 'Cover (front)')))
    assert item.picture == 2
    assert local_tags.read_file(Path('a.flac'), probe_json(pictures=('Other',))).picture == 1
    assert local_tags.read_file(Path('a.flac'), probe_json()).picture is None


# ------------------------------------------------------------ albums

def file(path, **tags):
    return local_tags.LocalFile(Path(path), **tags)


def test_files_are_grouped_by_album_and_sorted_by_disc_and_track(tmp_path):
    a = tmp_path / 'A'
    albums = local_tags.group([
        file(a / 'x.flac', title='Two', album='Live', artist='Band', track=2, disc=1),
        file(a / 'y.flac', title='Three', album='Live', artist='Band', track=1, disc=2),
        file(a / 'z.flac', title='One', album='Live', artist='Band', track=1, disc=1),
        file(a / 'w.flac', title='Other', album='Hits', artist='Someone', track=1),
    ])
    assert sorted(x.album for x in albums) == ['Hits', 'Live']
    live = next(x for x in albums if x.album == 'Live')
    assert [[f.title for f in d] for d in live.discs] == [['One', 'Two'], ['Three']]
    info = local_tags.album_info(live)
    assert [t.title for t in info.disc_tracks(disc_number=2)] == ['Three']
    assert local_tags.candidate(live, 0).disc_track_counts == [2, 1]


def test_untagged_files_group_by_folder_across_disc_subfolders(tmp_path):
    root = tmp_path / 'Concert'
    albums = local_tags.group([file(root / 'CD1' / '01.flac', title='A', named_from_file=True),
                               file(root / 'CD2' / '01.flac', title='B', named_from_file=True, disc=2)])
    assert len(albums) == 1 and albums[0].album == 'Concert'
    assert [[f.title for f in d] for d in albums[0].discs] == [['A'], ['B']]


def test_album_fields_follow_the_majority_and_say_when_files_disagree(tmp_path):
    files = [file(tmp_path / f'{i}.flac', title=str(i), album='Live', album_artist='Band', date=d, track=i)
             for i, d in enumerate(['2001', '2001', '1999'], start=1)]
    album = local_tags.group(files)[0]
    assert album.date == '2001' and album.mixed == ['date']


def test_a_shared_artist_prefix_in_file_names_is_the_artist(tmp_path):
    files = [file(tmp_path / 'a.flac', title='Band - One', named_from_file=True, track=1),
             file(tmp_path / 'b.flac', title='Band - Two - Live', named_from_file=True, track=2)]
    album = local_tags.group(files)[0]
    assert [(f.artist, f.title) for f in album.files] == [('Band', 'One'), ('Band', 'Two - Live')]
    # Only one file, or different prefixes: titles are left as they are
    lone = local_tags.group([file(tmp_path / 'c' / 'a.flac', title='X - Y', named_from_file=True)])[0]
    assert lone.files[0].title == 'X - Y'


def test_collect_reads_one_level_of_subfolders_and_refuses_too_many(tmp_path, monkeypatch):
    touch(tmp_path / 'Album' / '02.flac'); touch(tmp_path / 'Album' / '10.flac'); touch(tmp_path / 'Album' / 'notes.txt')
    touch(tmp_path / 'Album' / 'CD2' / '01.mp3'); touch(tmp_path / 'Album' / 'CD2' / 'deep' / '01.mp3')
    found = local_tags.collect([tmp_path / 'Album'])
    assert [p.relative_to(tmp_path / 'Album').as_posix() for p in found] == ['02.flac', '10.flac', 'CD2/01.mp3']
    with pytest.raises(Failure) as err:
        local_tags.collect([tmp_path / 'Album' / 'notes.txt'])
    assert err.value.code == 'local_none'
    monkeypatch.setattr(local_tags, 'MAX_FILES', 2)
    with pytest.raises(Failure) as err:
        local_tags.collect([tmp_path / 'Album'])
    assert err.value.code == 'local_too_many'


def test_folder_image_prefers_cover_names_then_a_lone_image(tmp_path):
    touch(tmp_path / 'a' / 'back.jpg'); touch(tmp_path / 'a' / 'Folder.jpg')
    assert local_tags.folder_image(tmp_path / 'a').name == 'Folder.jpg'
    touch(tmp_path / 'b' / 'cover_1200.png')
    assert local_tags.folder_image(tmp_path / 'b').name == 'cover_1200.png'
    touch(tmp_path / 'c' / 'scan.jpg')
    assert local_tags.folder_image(tmp_path / 'c').name == 'scan.jpg'
    touch(tmp_path / 'd' / 'scan1.jpg'); touch(tmp_path / 'd' / 'scan2.jpg')
    assert local_tags.folder_image(tmp_path / 'd') is None


def test_cover_preference_with_fallback(tmp_path):
    embedded, folder = touch(tmp_path / 'e.jpg'), touch(tmp_path / 'cover.jpg')
    album = local_tags.LocalAlbum(embedded_cover=embedded, folder_cover=folder)
    assert local_tags.pick_cover(album, 'embedded') == embedded
    assert local_tags.pick_cover(album, 'folder') == folder
    assert local_tags.pick_cover(local_tags.LocalAlbum(folder_cover=folder), 'embedded') == folder
    assert local_tags.pick_cover(local_tags.LocalAlbum(embedded_cover=embedded), 'folder') == embedded
    assert local_tags.pick_cover(local_tags.LocalAlbum(), 'folder') is None


def test_scan_with_canned_probes(tmp_path, monkeypatch):
    one = touch(tmp_path / 'Live' / '01.flac'); two = touch(tmp_path / 'Live' / '02.flac')
    touch(tmp_path / 'Live' / 'cover.jpg', b'\xff\xd8\xff')
    answers = {one: probe_json(tags={'title': 'One', 'album': 'Live', 'artist': 'Band', 'track': '1'}),
               two: {}}   # unreadable: left out
    monkeypatch.setattr(local_tags, 'probe', lambda path: answers[path])
    albums = local_tags.scan([tmp_path / 'Live'], tmp_path / 'cache')
    assert len(albums) == 1 and [f.title for f in albums[0].files] == ['One']
    assert albums[0].folder_cover.name == 'cover.jpg' and albums[0].embedded_cover is None
    answers[one] = {}
    with pytest.raises(Failure) as err:
        local_tags.scan([tmp_path / 'Live'], tmp_path / 'cache')
    assert err.value.code == 'local_unreadable'


# ------------------------------------------------------------ the tags page

def scanned(tmp_path):
    folder = tmp_path / 'Studio'
    embedded, cover = touch(tmp_path / 'emb.jpg', b'\xff\xd8\xff'), touch(folder / 'cover.jpg', b'\xff\xd8\xff')
    album = local_tags.group([
        file(folder / '1.flac', title='One', album='Studio', album_artist='Band', artist='Band', date='2003',
             genre='Pop', track=1, seconds=60.0, mb_album='mb-1'),
        file(folder / '2.flac', title='Two', album='Studio', album_artist='Band', artist='Band & Guest',
             date='2003', genre='Pop', track=2, seconds=60.0, mb_album='mb-1'),
    ])[0]
    album.embedded_cover = embedded
    return album, embedded, cover


def read_local(backend, qt_app, monkeypatch, albums, folder):
    monkeypatch.setattr(local_tags, 'scan', lambda paths, cache: albums)
    backend.metadata.metaReadLocal([str(folder)])
    backend.pool.waitForDone(5000); qt_app.processEvents()


def test_tags_page_reads_local_files_and_applies_them(backend, qt_app, tmp_path, monkeypatch):
    backend.disc.chapters = [core.models.Chapter(i, (i - 1) * 60, i * 60) for i in (1, 2)]
    backend.disc.rebuild_chapters({1: 'Track 1', 2: 'Track 2'})
    album, embedded, cover = scanned(tmp_path)
    read_local(backend, qt_app, monkeypatch, [album], tmp_path / 'Studio')
    rows = backend.metadata.meta_model.rows
    assert len(rows) == 1 and rows[0]['source'] == 'local' and rows[0]['mbid'] == 'mb-1'
    assert rows[0]['thumb'].endswith('emb.jpg')
    assert backend.metadata.state['metaChosen'] == 0          # one album: already chosen
    assert backend.cfg['last_music_folder'] == str(tmp_path / 'Studio')

    backend.setPreference('local_cover', 'folder')
    assert backend.metadata.meta_model.rows[0]['thumb'].endswith('cover.jpg')

    backend.metadata.metaApply(True, True, True, True)
    backend.pool.waitForDone(5000); qt_app.processEvents()
    meta = backend.metadata.export_metadata()
    assert meta['album'] == dict(artist='Band', album='Studio', album_artist='Band', date='2003', genre='Pop')
    assert meta['cover'] == str(cover)
    assert meta['track_artists'] == {'2': 'Band & Guest'}
    assert backend.state['reviewSource'] == 'online'           # titles go to the review page
    assert [e.name for e in backend.names.review_pool] == ['One', 'Two']


def test_local_album_without_a_cover_says_so(backend, qt_app, tmp_path, monkeypatch):
    backend.disc.chapters = [core.models.Chapter(1, 0, 60)]
    backend.disc.rebuild_chapters({1: 'One'})
    album, _, _ = scanned(tmp_path)
    album.embedded_cover = album.folder_cover = None
    read_local(backend, qt_app, monkeypatch, [album], tmp_path / 'Studio')
    backend.metadata.metaApply(True, True, False, False)
    backend.pool.waitForDone(5000); qt_app.processEvents()
    assert backend.metadata.state['metaStatus'] == 'applied'
    assert backend.metadata.state['metaError'] == backend.tr('localNoCover')
    assert backend.metadata.export_metadata()['album']['album'] == 'Studio'


def test_musicbrainz_id_in_the_files_lists_that_release(backend, qt_app, tmp_path, monkeypatch):
    album, _, _ = scanned(tmp_path)
    second = local_tags.LocalAlbum(album='Other', artist='X', folder=tmp_path / 'Other')
    read_local(backend, qt_app, monkeypatch, [album, second], tmp_path)
    assert backend.metadata.state['metaChosen'] == -1
    backend.metadata.metaUseMusicBrainz(0)
    sources = [(c.source, c.id) for c in backend.metadata.meta_candidates]
    assert sources == [('local', '0'), ('musicbrainz', 'mb-1'), ('local', '1')]
    assert backend.metadata.state['metaChosen'] == 1
    backend.metadata.metaUseMusicBrainz(0)                      # asked again: no second copy
    assert len(backend.metadata.meta_candidates) == 3
    # The second local album still applies its own tags after the insert
    backend.metadata.metaChoose(2)
    backend.metadata.metaApply(True, False, False, False)
    backend.pool.waitForDone(5000); qt_app.processEvents()
    assert backend.metadata.export_metadata()['album']['album'] == 'Other'


def test_read_error_is_shown_in_the_users_words(backend, qt_app, tmp_path, monkeypatch):
    def fail(paths, cache):
        raise Failure('local_none', 'No music files were found there.')
    monkeypatch.setattr(local_tags, 'scan', fail)
    backend.metadata.metaReadLocal([str(tmp_path)])
    backend.pool.waitForDone(5000); qt_app.processEvents()
    assert backend.metadata.state['metaStatus'] == 'error'
    assert backend.metadata.state['metaError'] == backend.texts['err_local_none']


# ------------------------------------------------------------ real ffprobe / ffmpeg

@pytest.mark.skipif(not (shutil.which(tools.TOOL_PATHS['ffmpeg']) or tools.bundled_tool('ffmpeg')),
                    reason='ffmpeg is not available')
def test_real_files_with_an_embedded_cover(tmp_path):
    ffmpeg = tools.bundled_tool('ffmpeg') or tools.TOOL_PATHS['ffmpeg']
    ffprobe = tools.bundled_tool('ffprobe') or tools.TOOL_PATHS['ffprobe']
    old = dict(tools.TOOL_PATHS)
    tools.TOOL_PATHS.update(ffmpeg=ffmpeg, ffprobe=ffprobe)
    try:
        folder = tmp_path / 'Album'; folder.mkdir()
        art = tmp_path / 'art.jpg'
        subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=64x64', '-frames:v', '1', str(art)],
                       check=True, creationflags=tools.NO_WINDOW)
        for n, title in ((1, 'Alpha'), (2, 'Beta')):
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'sine=d=1', '-i', str(art),
                            '-map', '0', '-map', '1', '-c:a', 'flac', '-c:v', 'copy', '-disposition:v', 'attached_pic',
                            '-metadata:s:v', 'comment=Cover (front)',
                            '-metadata', f'title={title}', '-metadata', 'album=Real', '-metadata', 'artist=Band',
                            '-metadata', f'track={n}', str(folder / f'{n:02d}.flac')],
                           check=True, creationflags=tools.NO_WINDOW)
        albums = local_tags.scan([folder], tmp_path / 'cache')
        assert len(albums) == 1 and [f.title for f in albums[0].files] == ['Alpha', 'Beta']
        assert albums[0].files[0].seconds == pytest.approx(1.0, abs=0.1)
        cover = albums[0].embedded_cover
        assert cover is not None and cover.suffix == '.jpg' and cover.read_bytes()[:3] == b'\xff\xd8\xff'
        assert local_tags.scan([folder], tmp_path / 'cache')[0].embedded_cover == cover     # cached
    finally:
        tools.TOOL_PATHS.clear(); tools.TOOL_PATHS.update(old)


# ------------------------------------------------------------ CUE sheets and whole-disc images

CUE = '''REM GENRE "J-Pop"
REM DATE 2019
REM DISCNUMBER 2
PERFORMER "椎名林檎"
TITLE "三毒史"
FILE "Album.wav" WAVE
  TRACK 01 AUDIO
    TITLE "鶏と蛇と豚"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "獣ゆく細道"
    PERFORMER "椎名林檎と宮本浩次"
    INDEX 00 03:59:50
    INDEX 01 04:00:00
  TRACK 03 AUDIO
    TITLE "マ・シェリ"
    INDEX 01 08:30:37
'''


def test_cue_sheet_is_parsed():
    sheet = local_tags.parse_cue(CUE)
    assert (sheet.title, sheet.performer, sheet.date, sheet.genre, sheet.disc) == ('三毒史', '椎名林檎', '2019', 'J-Pop', 2)
    assert sheet.files == ['Album.wav']
    assert [(t.number, t.title, t.performer) for t in sheet.tracks] == [
        (1, '鶏と蛇と豚', ''), (2, '獣ゆく細道', '椎名林檎と宮本浩次'), (3, 'マ・シェリ', '')]
    assert [t.start for t in sheet.tracks] == [0.0, 240.0, pytest.approx(510 + 37 / 75)]


def test_unquoted_file_names_and_data_tracks():
    sheet = local_tags.parse_cue('FILE My Album.flac WAVE\nTRACK 01 MODE1/2352\nINDEX 01 00:00:00\n'
                                 'TRACK 02 AUDIO\nTITLE Song\nINDEX 01 00:10:00\n')
    assert sheet.files == ['My Album.flac']
    assert [(t.number, t.title) for t in sheet.tracks] == [(2, 'Song')]


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'cp932'])
def test_whole_disc_image_is_split_by_the_cue_beside_it(tmp_path, encoding):
    image = touch(tmp_path / 'Album.flac')
    (tmp_path / 'Album.cue').write_bytes(CUE.encode(encoding))
    item = local_tags.read_file(image, probe_json(tags={'album': '三毒史', 'artist': '椎名林檎'}, duration='700'))
    songs = local_tags.apply_cues([item], {tmp_path: local_tags.folder_cues(tmp_path)})
    assert [(s.track, s.title, s.artist) for s in songs] == [
        (1, '鶏と蛇と豚', '椎名林檎'), (2, '獣ゆく細道', '椎名林檎と宮本浩次'), (3, 'マ・シェリ', '椎名林檎')]
    assert [round(s.seconds, 2) for s in songs] == [240.0, 270.49, 189.51]     # the last runs to the end
    assert all(s.disc == 2 and s.genre == 'J-Pop' and s.date == '2019' for s in songs)
    album = local_tags.group(songs)[0]
    assert len(album.files) == 3 and album.album == '三毒史'


def test_embedded_cue_sheet_is_used(tmp_path):
    item = local_tags.read_file(tmp_path / 'x.flac', probe_json(tags={'CUESHEET': CUE}, duration='600'))
    songs = local_tags.apply_cues([item], {})
    assert [s.title for s in songs] == ['鶏と蛇と豚', '獣ゆく細道', 'マ・シェリ']
    assert songs[0].album == '三毒史' and songs[0].album_artist == '椎名林檎'


def test_a_sheet_for_split_files_fills_only_missing_names(tmp_path):
    cue = ('PERFORMER "Band"\nTITLE "Live"\nFILE "01 a.flac" WAVE\nTRACK 01 AUDIO\nTITLE "Opening"\nINDEX 01 00:00:00\n'
           'FILE "02 b.flac" WAVE\nTRACK 02 AUDIO\nTITLE "Encore"\nINDEX 01 00:00:00\n')
    (tmp_path / 'Live.cue').write_text(cue, encoding='utf-8')
    tagged = local_tags.read_file(touch(tmp_path / '01 a.flac'), probe_json(tags={'title': 'Own Title', 'track': '1'}))
    untagged = local_tags.read_file(touch(tmp_path / '02 b.flac'), probe_json())
    songs = local_tags.apply_cues([tagged, untagged], {tmp_path: local_tags.folder_cues(tmp_path)})
    assert [(s.title, s.artist, s.album, s.start) for s in songs] == [
        ('Own Title', 'Band', 'Live', None), ('Encore', 'Band', 'Live', None)]


def test_a_converted_image_still_matches_its_sheet_and_a_picked_cue_finds_it(tmp_path):
    image = touch(tmp_path / 'Album.ape')
    cue = touch(tmp_path / 'Album.cue', CUE.encode('utf-8'))      # the sheet still names Album.wav
    assert local_tags.collect([cue]) == [image]
    item = local_tags.read_file(image, probe_json(duration='700'))
    assert len(local_tags.apply_cues([item], {tmp_path: local_tags.folder_cues(tmp_path)})) == 3


def test_files_without_a_sheet_are_left_alone(tmp_path):
    item = local_tags.read_file(touch(tmp_path / 'song.flac'), probe_json(tags={'title': 'Song'}))
    assert local_tags.apply_cues([item], {tmp_path: local_tags.folder_cues(tmp_path)}) == [item]


@pytest.mark.skipif(not (shutil.which(tools.TOOL_PATHS['ffmpeg']) or tools.bundled_tool('ffmpeg')),
                    reason='ffmpeg is not available')
def test_real_images_with_embedded_and_gbk_sidecar_sheets(tmp_path):
    ffmpeg = tools.bundled_tool('ffmpeg') or tools.TOOL_PATHS['ffmpeg']
    ffprobe = tools.bundled_tool('ffprobe') or tools.TOOL_PATHS['ffprobe']
    old = dict(tools.TOOL_PATHS)
    tools.TOOL_PATHS.update(ffmpeg=ffmpeg, ffprobe=ffprobe)
    sheet = ('PERFORMER "陈奕迅"\nTITLE "黑白灰"\nFILE "CD.wav" WAVE\n'
             'TRACK 01 AUDIO\n  TITLE "十年"\n  INDEX 01 00:00:00\nTRACK 02 AUDIO\n  TITLE "黑白灰"\n  INDEX 01 00:02:00\n')
    try:
        embedded, sidecar = tmp_path / 'A', tmp_path / 'B'
        embedded.mkdir(); sidecar.mkdir()
        tone = ['-f', 'lavfi', '-i', 'sine=d=5', '-c:a', 'flac']
        subprocess.run([ffmpeg, '-v', 'error', *tone, '-metadata', f'CUESHEET={sheet}', str(embedded / 'CD.flac')],
                       check=True, creationflags=tools.NO_WINDOW)
        subprocess.run([ffmpeg, '-v', 'error', *tone, str(sidecar / 'CD.flac')], check=True, creationflags=tools.NO_WINDOW)
        (sidecar / 'CD.cue').write_bytes(sheet.encode('gbk'))
        for folder in (embedded, sidecar):
            albums = local_tags.scan([folder], tmp_path / 'cache')
            assert len(albums) == 1, folder
            album = albums[0]
            assert (album.album, album.artist) == ('黑白灰', '陈奕迅')
            assert [f.title for f in album.files] == ['十年', '黑白灰']
            assert [round(f.seconds or 0) for f in album.files] == [2, 3]
    finally:
        tools.TOOL_PATHS.clear(); tools.TOOL_PATHS.update(old)
