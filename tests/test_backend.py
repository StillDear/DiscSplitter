import threading
import time
from pathlib import Path

import core.jobs
import core.manifest
import core.models
from PySide6.QtCore import QThread
from gui.backend import Worker
import core.chapter_marks
import core.musicbrainz
from core import metadata_sources
import core.pipeline
import core.sources
import core.tools
import core.tracklist


def wait_idle(backend, app):
    deadline = time.monotonic() + 5
    while backend.state['working'] and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    app.processEvents()
    assert not backend.state['working'], 'worker did not finish'


def setup_disc(backend):
    audio = core.models.Track(1, 'audio', 'TrueHD Atmos', channels=8)
    stereo = core.models.Track(2, 'audio', 'LPCM', channels=2, default_track=False)
    playlist = core.models.Playlist(Path('disc/BDMV/PLAYLIST/00001.mpls'),
        [core.models.Track(0, 'video', 'AVC'), audio, stereo, core.models.Track(3, 'subtitles', 'PGS', language='eng')], 3, 300)
    backend.disc.playlist = playlist
    backend.disc.audio = audio
    backend.disc.populate_tracks([audio.track_id], [])
    backend.disc.chapters = [core.models.Chapter(i, (i-1)*100, i*100, embedded_name=f'Disc {i}') for i in range(1, 4)]
    backend.disc.rebuild_chapters()
    backend.disc.setAllChapters(True)   # discs start unchecked; these tests export everything
    return playlist


def running_export(backend, output):
    """Put the export flow where finish_export / cancel expect it: a job running for `output`."""
    assert backend.exporter.flow.prepare(dict(output=output))
    assert backend.exporter.flow.launch() is not None


def test_every_name_source_requires_review_and_only_checked_apply(backend):
    setup_disc(backend)
    backend.names.reviewEmbedded()
    assert all(r['title'] == '' for r in backend.disc.chapter_model.rows)
    assert backend.state['page'] == 'review'
    backend.names.checkReview(1, False)
    backend.names.applyReview()
    assert [r['title'] for r in backend.disc.chapter_model.rows] == ['Disc 1', '', 'Disc 3']
    assert backend.disc.chapter_model.rows[0]['origin'] == 'disc'
    backend.names.reviewPaste('1. Pasted One\n2. Pasted Two')
    assert backend.disc.chapter_model.rows[0]['title'] == 'Disc 1'
    assert backend.names.review_model.rows[2]['checked'] is False
    backend.names.editReview(0, 'Corrected')
    backend.names.applyReview()
    assert backend.disc.chapter_model.rows[0]['title'] == 'Corrected'
    assert backend.disc.chapter_model.rows[0]['origin'] == 'edited'
    backend.disc.editTitle(2, 'Manual')
    assert backend.disc.chapter_model.rows[2]['origin'] == 'edited'


def test_chapter_tracklist_round_trips_exact_titles_and_chapters(backend, qt_app, tmp_path):
    # The done page no longer writes these files, but tracklists saved earlier still import as they were.
    setup_disc(backend)
    titles = {1: ' 15 ', 3: '03 - 君に会いたくなるから / Live: "2025" ☆'}
    backend.disc.rebuild_chapters(titles)
    backend.disc.setAllChapters(True)
    backend.disc.setChapterIncluded(0, False)
    backend.disc.unselectUnnamedChapters()
    assert [row['included'] for row in backend.disc.chapter_model.rows] == [False, False, True]
    copied = core.tracklist.export_chapter_tracklist(titles)
    saved = tmp_path / 'concert.tracklist.json'
    saved.write_text(copied, encoding='utf-8')

    backend.disc.rebuild_chapters({2: 'Existing title'})
    backend.names.reviewPaste(copied)
    assert backend.state['reviewMode'] == 'chapter'
    assert [row['checked'] for row in backend.names.review_model.rows] == [True, False, True]
    backend.names.applyReview()
    assert [row['title'] for row in backend.disc.chapter_model.rows] == [titles[1], 'Existing title', titles[3]]

    backend.disc.rebuild_chapters()
    backend.names.importFile(str(saved))
    wait_idle(backend, qt_app)
    backend.names.applyReview()
    assert [row['title'] for row in backend.disc.chapter_model.rows] == [titles[1], '', titles[3]]


def test_online_entry_clears_stale_review_and_autosearches(backend, qt_app, monkeypatch):
    setup_disc(backend)
    backend.names.reviewEmbedded()
    assert backend.names.review_model.rows
    backend.put(mbArtist='', mbAlbum='Live Tour 2025')
    searched, fetched = [], []
    exact = metadata_sources.Candidate('musicbrainz', 'b', 'Live', 'A', score=80, disc_track_counts=[5, 3])
    far = metadata_sources.Candidate('musicbrainz', 'a', 'Live', 'A', score=100, disc_track_counts=[12])
    monkeypatch.setattr(metadata_sources, 'search',
                        lambda source, artist, album, barcode: searched.append((artist, album)) or [far, exact])
    track = metadata_sources.TrackInfo
    two_discs = metadata_sources.AlbumInfo('musicbrainz', discs=[[track(f'A{i}') for i in range(5)],
                                                                 [track(f'T{i}') for i in range(3)]])
    two_discs.tracks = [t for disc in two_discs.discs for t in disc]
    monkeypatch.setattr(metadata_sources, 'fetch',
                        lambda source, rid, tracks_only=False: fetched.append((rid, tracks_only)) or two_discs)
    backend.names.openOnline()
    assert backend.state['page'] == 'review'
    wait_idle(backend, qt_app)
    assert searched == [('', 'Live Tour 2025')]
    # The release whose second disc has exactly 3 tracks ranks first and is previewed, not applied.
    assert [r['fit'] for r in backend.names.release_model.rows] == ['exact', 'far']
    assert backend.names.release_model.rows[0]['chosen'] and backend.names.release_model.rows[0]['tracks'] == 3
    assert fetched == [('b', True)]
    # Only the disc that fits this playlist's chapters is laid over them.
    assert [r['proposed'] for r in backend.names.review_model.rows] == ['T0', 'T1', 'T2']
    assert backend.state['mbRelease'] == 'A — Live'
    assert backend.state['reviewChecked'] == 3
    assert backend.disc.chapter_model.rows[0]['title'] == ''
    backend.names.checkAllReview(False)
    assert backend.state['reviewChecked'] == 0
    backend.names.editReview(1, 'Typed')
    assert backend.names.review_model.rows[1]['checked'] and backend.state['reviewChecked'] == 1


def test_musicbrainz_busy_shows_friendly_hint(backend, qt_app, monkeypatch):
    import urllib.error
    import urllib.request
    setup_disc(backend)
    def busy(*a, **k):
        raise urllib.error.HTTPError('https://musicbrainz.org', 503, 'Service Temporarily Unavailable', {}, None)
    monkeypatch.setattr(urllib.request, 'urlopen', busy)
    monkeypatch.setattr(metadata_sources, 'MB_RETRY_SECONDS', 0)
    backend.names.search('Artist', 'Album', '')
    wait_idle(backend, qt_app)
    assert backend.state['mb'] == 'error'
    assert backend.state['mbError'] == backend.tr('mbBusy')


def test_online_search_requires_some_query(backend):
    setup_disc(backend)
    backend.names.search(' ', '', '')
    assert backend.state['mb'] == 'error' and not backend.state['working']


def test_disc_tag_and_medium_choice():
    assert core.musicbrainz.split_disc_tag('Fall In Love Tour 2025 DISC 1') == ('Fall In Love Tour 2025', 1)
    assert core.musicbrainz.split_disc_tag('Live [Disc 2]') == ('Live', 2)
    assert core.musicbrainz.split_disc_tag('Brothers In Arms') == ('Brothers In Arms', None)
    assert core.musicbrainz.split_disc_tag('CD 1') == ('CD 1', None)
    assert core.musicbrainz.pick_medium([10, 12], disc_number=2) == 1
    assert core.musicbrainz.pick_medium([10, 12], chapter_count=12) == 1
    assert core.musicbrainz.pick_medium([], chapter_count=12) == 0


def test_duration_mismatch_is_unchecked(backend):
    setup_disc(backend)
    backend.names.review_entries([core.tracklist.TracklistEntry('Wrong edition', start_seconds=0, duration_seconds=150)])
    assert backend.names.review_model.rows[0]['confidence'] == 'duration_mismatch'
    assert backend.names.review_model.rows[0]['checked'] is False


def test_scan_uses_worker_thread_selects_best_and_reads_chapters(backend, qt_app, monkeypatch, tmp_path):
    playlist = setup_disc(backend)
    chapters = list(backend.disc.chapters)
    calls = []
    main_thread = threading.get_ident()
    def scan(source):
        calls.append(threading.get_ident())
        return [playlist]
    monkeypatch.setattr(core.sources, 'scan_disc_folder', scan)
    monkeypatch.setattr(core.tracklist, 'find_sidecar_tracklist_files', lambda p: [tmp_path / 'names.txt'])
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: chapters)
    backend.disc.setSource(str(tmp_path))
    wait_idle(backend, qt_app)
    assert calls and calls[0] != main_thread
    assert backend.disc.playlist_model.rows[0]['chosen'] is True
    assert backend.disc.audio.track_id == 1
    assert len(backend.disc.audio_model.rows) == 2
    assert backend.disc.subtitle_model.rows[0]['label'].startswith('PGS')
    assert backend.disc.chapter_model.rows[0]['title'] == ''
    # Names stored on the disc wait behind "Get titles" instead of opening the review by themselves.
    assert backend.state['page'] != 'review' and backend.state['reviewSource'] == 'disc'
    backend.names.openTitles()
    assert backend.state['page'] == 'review'
    backend.disc.selectAudio(1)
    assert backend.disc.audio.track_id == 2
    assert [r['chosen'] for r in backend.disc.audio_model.rows] == [True, True]
    backend.disc.selectAudio(0)
    assert [r['chosen'] for r in backend.disc.audio_model.rows] == [False, True]


def test_import_and_barcode_use_existing_apis_before_review(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    tracklist = tmp_path / 'titles.txt'
    tracklist.write_text('01. One\n02. Two', encoding='utf-8')
    # On the review page an imported file waits there for confirmation.
    backend.navigate('review')
    backend.names.importFile(str(tracklist))
    wait_idle(backend, qt_app)
    assert backend.names.review_model.rows[0]['proposed'] == 'One'
    assert backend.disc.chapter_model.rows[0]['title'] == ''
    assert backend.state['page'] == 'review'
    calls = []
    candidate = core.musicbrainz.MusicBrainzCandidate('release', 'Album', 'Artist')
    monkeypatch.setattr(core.musicbrainz, 'search_musicbrainz_releases_by_barcode', lambda barcode: calls.append(barcode) or [candidate])
    monkeypatch.setattr(metadata_sources, 'fetch', lambda source, release, tracks_only=False: metadata_sources.AlbumInfo(
        'musicbrainz', tracks=[metadata_sources.TrackInfo('Online')]))
    backend.names.search('', '', '12345')
    wait_idle(backend, qt_app)
    assert calls == ['12345']
    backend.names.selectRelease(0)
    wait_idle(backend, qt_app)
    assert backend.names.review_model.rows[0]['proposed'] == 'Online'
    assert backend.disc.chapter_model.rows[0]['title'] == ''
    monkeypatch.setattr(core.musicbrainz, 'search_musicbrainz_releases', lambda artist, album: calls.append((artist, album)) or [])
    backend.names.search('Artist', 'Album', '')
    wait_idle(backend, qt_app)
    assert calls[-1] == ('Artist', 'Album')


def test_worker_result_is_delivered_on_qt_thread(backend, qt_app):
    seen = []
    backend.task(lambda p: threading.get_ident(), lambda result: seen.append((result, threading.get_ident())))
    wait_idle(backend, qt_app)
    assert seen[0][0] != threading.get_ident()
    assert seen[0][1] == threading.get_ident()


def test_export_collision_requires_approval_and_precise_overwrite(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    output = tmp_path / 'Album'
    output.mkdir()
    old = output / 'Track 01.mkv'
    old.write_bytes(b'existing')
    skipped = output / 'Track 02.mkv'
    skipped.write_bytes(b'keep')
    backend.disc.setChapterIncluded(1, False)
    backend.disc.setAllTracks('audio', True)
    backend.disc.selectSubtitle(0)
    backend.disc.setKeepVideo(False)
    assert backend.state['hasVideo'] and not backend.state['keepVideo']
    assert backend.disc.export_model.rowCount() == 2
    calls, dialogs = [], []
    backend.dialogRequested.connect(lambda kind, msg: dialogs.append(kind))
    def pipeline(*args, **kw):
        calls.append(kw)
        return []
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', pipeline)
    backend.exporter.startExport()
    assert dialogs[-1] == 'collision'
    assert calls == []
    assert old.read_bytes() == b'existing'
    backend.exporter.approveOverwrite()
    wait_idle(backend, qt_app)
    assert calls[0]['overwrite'] == {old}
    assert calls[0]['chapter_indices'] == [1, 3]
    assert calls[0]['audio_track_ids'] == [1, 2]
    assert calls[0]['subtitle_track_ids'] == [3]
    assert calls[0]['keep_video'] is False
    assert skipped.read_bytes() == b'keep'
    assert calls[0]['resume'] is False
    # The log goes to the app's own logs folder, never into the music library.
    log = calls[0]['log_path']
    assert log.parent == backend.exporter.LOG_DIR and log.suffix == '.log' and output not in log.parents
    assert isinstance(calls[0]['cancel_event'], threading.Event)


def test_flac_export_passes_one_audio_track_and_uses_flac_names(backend, qt_app, monkeypatch, tmp_path):
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    backend.disc.selectAudio(1)
    backend.disc.selectSubtitle(0)
    backend.disc.setOutputFormat('flac')
    assert backend.state['audioSelected'] == 1
    backend.disc.selectAudio(0)
    backend.disc.selectAudio(0)
    assert backend.state['audioSelected'] == 1
    backend.disc.setChapterIncluded(1, False)
    calls = []

    def pipeline(*args, **kwargs):
        calls.append(kwargs)
        return [kwargs['output_folder'] / 'Track 01.flac', kwargs['output_folder'] / 'Track 03.flac']

    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', pipeline)
    backend.exporter.startExport()
    wait_idle(backend, qt_app)
    assert calls[0]['container'] == 'flac'
    assert calls[0]['audio_track_ids'] == [1]
    assert calls[0]['subtitle_track_ids'] == []
    assert calls[0]['keep_video'] is False
    assert calls[0]['chapter_indices'] == [1, 3]
    assert backend.state['completed'] == 2


def test_progress_failure_preserves_completed_and_pending(backend, tmp_path):
    from test_logic import manifest
    setup_disc(backend)
    output = tmp_path / 'Album'
    running_export(backend, output)
    for i in range(3):
        backend.disc.chapter_model.change(i, file=f'{i+1:02d} - Track {i+1:02d}.mkv')
    backend.exporter.progress(core.jobs.extracting('Extracting audio track 1 -> _audio_extracted.mkv'))
    assert backend.state['stage'] == 'extracting'
    assert backend.state['completed'] == 0
    backend.exporter.progress(core.jobs.splitting(1, 'One'))
    backend.exporter.progress(core.jobs.splitting(2, 'Two'))
    assert backend.disc.chapter_model.rows[0]['status'] == 'done'
    m = manifest(output, 'failed')
    m.completed_outputs = [str(output / '01 - Track 01.mkv')]
    core.manifest.write_manifest(output / '_work', m)
    backend.exporter.finish_export(RuntimeError('ffmpeg failed'), [])
    assert [r['status'] for r in backend.disc.chapter_model.rows] == ['done', 'failed', 'pending']
    assert (backend.state['completed'], backend.state['failed'], backend.state['remaining']) == (1, 1, 1)


def test_resume_restores_manifest_audio_names_and_container(backend, qt_app, monkeypatch, tmp_path):
    from test_logic import manifest
    playlist = setup_disc(backend)
    output = tmp_path / 'Album'
    m = manifest(output, 'cancelled')
    m.audio_track_id = 2
    m.audio_track_ids = [1, 2]
    m.subtitle_track_ids = [3]
    m.chapter_indices = [2, 3]
    m.track_names = {'1': 'Saved title'}
    m.chapters = [{'index': i, 'start_seconds': (i-1)*100, 'end_seconds': i*100, 'name': ''} for i in range(1, 4)]
    core.manifest.write_manifest(output / '_work', m)
    backend.exporter.flow.manifest = m
    monkeypatch.setattr(core.sources, 'inspect_playlist', lambda path, **_: playlist)
    calls = []
    def pipeline(pl, audio, names, **kw):
        calls.append((audio.track_id, names, kw))
        return []
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', pipeline)
    backend.disc.setKeepVideo(False)
    backend.exporter.resume()
    wait_idle(backend, qt_app)
    assert calls[0][0] == 2
    assert calls[0][1] == {1: 'Saved title'}
    assert calls[0][2]['resume'] is True
    assert calls[0][2]['container'] == 'mkv'
    assert calls[0][2]['overwrite'] == set()
    assert calls[0][2]['audio_track_ids'] == [1, 2]
    assert calls[0][2]['subtitle_track_ids'] == [3]
    assert calls[0][2]['chapter_indices'] == [2, 3]
    assert calls[0][2]['keep_video'] is True
    assert backend.disc.export_model.rowCount() == 2


def test_tool_browse_verifies_sibling_and_refreshes(backend, qt_app, monkeypatch):
    verified = []
    monkeypatch.setattr(core.tools, 'verify_tool_at_path', lambda path, tool: verified.append(tool) or (True, 'v1'))
    monkeypatch.setattr(core.tools, 'guess_sibling_tool_path', lambda path, tool: 'C:/tools/mkvextract.exe' if tool == 'mkvextract' else None)
    monkeypatch.setattr(core.tools, 'check_tools', lambda: {t: True for t in core.tools.TOOL_PATHS})
    backend.locateTool('mkvmerge', 'C:/tools/mkvmerge.exe')
    wait_idle(backend, qt_app)
    assert verified == ['mkvmerge', 'mkvextract']
    assert backend.config['mkvextract_path'] == 'C:/tools/mkvextract.exe'
    assert all(row['available'] for row in backend.tool_model.rows)


def test_switching_playlist_preserves_edited_titles(backend, qt_app, monkeypatch):
    playlist = setup_disc(backend)
    chapters = list(backend.disc.chapters)
    backend.disc.editTitle(1, 'Keep this title')
    backend.disc.playlists = core.sources.score_playlists([playlist])
    backend.disc.playlist_model.replace([dict(label='test', detail='', tracks='', headline='', reasons='', chosen=False)])
    monkeypatch.setattr(core.chapter_marks, 'read_chapters_from_source', lambda p, **kw: chapters)
    backend.disc.selectPlaylist(0)
    wait_idle(backend, qt_app)
    assert backend.disc.chapter_model.rows[1]['title'] == 'Keep this title'
    assert backend.disc.chapter_model.rows[1]['origin'] == 'edited'


def test_cancel_sets_existing_event_and_finishes_from_checkpoint(backend, tmp_path):
    from test_logic import manifest
    setup_disc(backend)
    running_export(backend, tmp_path / 'Album')
    event = backend.exporter.flow.cancel_event
    backend.exporter.cancel()
    assert event.is_set()
    assert backend.state['result'] == 'cancelling'
    m = manifest(backend.exporter.flow.output, 'cancelled')
    core.manifest.write_manifest(backend.exporter.flow.output / '_work', m)
    backend.exporter.finish_export(core.jobs.JobCancelled('Cancelled'), [])
    assert backend.state['result'] == 'cancelled'
    assert backend.state['resume'] is True
    assert backend.state['failed'] == 0


def test_discard_deletes_only_work_preserving_exports(backend, qt_app, tmp_path):
    from test_logic import manifest
    output = tmp_path / 'Album'
    m = manifest(output, 'cancelled')
    core.manifest.write_manifest(output / '_work', m)
    (output / '_work' / '_audio_extracted.mkv').write_bytes(b'intermediate')
    exported = output / '01 - One.mkv'
    exported.write_bytes(b'keep')
    backend.exporter.flow.manifest = m
    backend.exporter.discard()
    wait_idle(backend, qt_app)
    assert not (output / '_work').exists()
    assert exported.read_bytes() == b'keep'


def test_bad_tool_path_does_not_persist(backend, qt_app, monkeypatch):
    previous = dict(backend.config)
    errors = []
    backend.dialogRequested.connect(lambda kind, text: errors.append(text))
    monkeypatch.setattr(core.tools, 'verify_tool_at_path', lambda path, tool: (False, 'invalid executable'))
    backend.locateTool('ffmpeg', 'invalid.exe')
    wait_idle(backend, qt_app)
    assert backend.config == previous
    assert errors == ['invalid executable']


def test_existing_checkpoint_requires_choice_before_start(backend, monkeypatch, tmp_path):
    from test_logic import manifest
    setup_disc(backend)
    backend.put(source='Album', output=str(tmp_path))
    output = tmp_path / 'Album'
    core.manifest.write_manifest(output / '_work', manifest(output, 'failed'))
    calls, dialogs = [], []
    monkeypatch.setattr(core.pipeline, 'run_full_pipeline', lambda *a, **kw: calls.append(kw))
    backend.dialogRequested.connect(lambda kind, text: dialogs.append(kind))
    backend.exporter.startExport()
    assert dialogs == ['resume']
    assert calls == []
    assert backend.exporter.flow.cancel_event is None


def test_preferences_switch_live_without_changing_product_defaults(backend):
    from gui.i18n import EN, ZH
    backend.setPreference('language', 'en')
    assert backend.texts == EN
    backend.setPreference('language', 'zh')
    assert backend.texts == ZH
    backend.setPreference('accent', '#60CDFF')
    backend.setPreference('theme', 'system')
    assert backend.config['accent'] == '#60CDFF'
    assert backend.config['theme'] == 'system'
    backend.setPreference('collision_policy', 'overwrite')
    assert backend.config['collision_policy'] == 'overwrite'
    backend.setPreference('collision_policy', 'delete-everything')   # unknown values are ignored
    assert backend.config['collision_policy'] == 'overwrite'
    assert backend.config['filename_template'] == 'title'


def test_new_disc_starts_unchecked_and_only_renamed_can_be_selected(backend):
    setup_disc(backend)
    backend.disc.rebuild_chapters()
    assert backend.state['chapterSelected'] == 0
    backend.disc.editTitle(0, 'Opening')
    backend.disc.chapter_model.change(1, title='Chapter 02', origin='disc')   # plain disc name: not a rename
    backend.disc.selectRenamedChapters()
    assert [row['included'] for row in backend.disc.chapter_model.rows] == [True, False, False]
    assert backend.state['chapterSelected'] == 1


def test_importing_from_the_workspace_applies_titles_without_the_review(backend, qt_app, tmp_path):
    setup_disc(backend)
    backend.navigate('main')
    tracklist = tmp_path / 'titles.txt'
    tracklist.write_text('01. One' + chr(10) + '02. Two', encoding='utf-8')
    backend.names.importFile(str(tracklist))
    wait_idle(backend, qt_app)
    assert backend.state['page'] == 'main'
    applied = {r['number']: r['title'] for r in backend.disc.chapter_model.rows}
    checked = {r['number']: r['proposed'] for r in backend.names.review_model.rows if r['checked']}
    assert checked and all(applied[n] == title for n, title in checked.items())
    # "Get titles" reopens that file's list for adjusting instead of an empty import tab.
    backend.names.openTitles()
    assert (backend.state['page'], backend.state['reviewSource'], backend.state['reviewCount']) == ('review', 'import', 2)


def test_back_from_settings_returns_to_the_page_it_was_opened_from(backend):
    backend.disc.put(source='E:/Discs/Last used')       # remembered source, nothing read yet
    backend.navigate('settings')
    backend.back()
    assert backend.state['page'] == 'start'
    backend.navigate('main')                            # no disc read: never an empty workspace
    assert backend.state['page'] == 'start'
