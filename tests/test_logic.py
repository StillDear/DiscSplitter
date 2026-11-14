from pathlib import Path
import json
import pytest
import extractor
import settings
from gui import logic
from gui.i18n import ZH, EN


@pytest.mark.parametrize('event,text,stage,chapter,status', [
    (extractor.splitting(5, 'Why Worry'), 'Splitting chapter 5: Why Worry', 'splitting', 5, 'running'),
    (extractor.already_done(2, 'Already'), 'Chapter 2 (Already) already done - skipping.', 'splitting', 2, 'done'),
    (extractor.extracting('Extracting audio'), 'Extracting audio', 'extracting', None, ''),
    (extractor.cleaning_up(), 'Cleaning up temporary files...', 'cleanup', None, ''),
    (extractor.job_failed(RuntimeError('ffmpeg failed on chapter 7:')), 'Failed: ffmpeg failed on chapter 7:', '', None, 'failed'),
    (extractor.job_cancelled(), 'Cancelled.', '', None, 'cancelled'),
])
def test_progress_events_carry_their_meaning(event, text, stage, chapter, status):
    assert event == text                       # still the same log line
    assert logic.progress_event(event) == logic.Progress(stage, chapter, status)


@pytest.mark.parametrize('text', ['Splitting chapter 5: Why Worry', 'Cancelled.', 'mkvmerge: warning'])
def test_plain_text_is_never_parsed(text):
    # A wording change (or a song titled like a log line) cannot move the progress display.
    assert logic.progress_event(text) == logic.Progress()


def test_paste_numbers_unicode_and_empty_lines():
    result = extractor.parse_plain_text_tracklist('01. 第一曲\r\n\n02 - Why Worry\n3) One World\nUnnumbered')
    assert [x.name for x in result] == ['第一曲', 'Why Worry', 'One World', 'Unnumbered']
    assert extractor.strip_leading_number('01 - Track') == 'Track'
    assert extractor.parse_plain_text_tracklist(' \n\n') == []


def manifest(output, status='splitting'):
    return extractor.JobManifest(source_playlist='disc/BDMV/PLAYLIST/00001.mpls', audio_track_id=1,
        audio_track_label='Atmos', video_track_id=0, output_folder=str(output), container='mkv',
        track_names={'1': 'One'}, tool_versions={}, created_at='', status=status)


def test_resume_discovery_and_complete(tmp_path):
    assert logic.resumable_job(tmp_path) is None
    m = manifest(tmp_path)
    extractor.write_manifest(tmp_path / '_work', m)
    assert logic.resumable_job(tmp_path).status == 'splitting'
    m.status = 'complete'
    extractor.write_manifest(tmp_path / '_work', m)
    assert logic.resumable_job(tmp_path) is None
    (tmp_path / '_work' / extractor.MANIFEST_FILENAME).write_text('{broken')
    assert logic.resumable_job(tmp_path) is None


def test_output_plan_detects_duplicates_and_existing_without_writes(tmp_path):
    existing = tmp_path / 'Song.mkv'
    existing.write_bytes(b'keep')
    plan = logic.collision_plan(tmp_path, 5, {1: 'Song', 2: 'song', 3: 'Three/Unsafe', 4: 'Song (2)', 5: 'CON.txt'})
    assert [p.path for p in plan.collisions] == [existing]
    assert [p.chapter.index for p in plan.duplicates] == [1, 2]
    assert [p.path.name for p in plan.items] == ['Song.mkv', 'song (3).mkv', 'ThreeUnsafe.mkv',
                                                'Song (2).mkv', '_CON.txt.mkv']
    assert plan.items[2].path.parent == tmp_path
    assert existing.read_bytes() == b'keep'
    assert len(list(tmp_path.iterdir())) == 1


def test_resume_only_exempts_checkpoint_owned_collisions(tmp_path):
    first = tmp_path / '01 - One.mkv'
    second = tmp_path / '02 - Two.mkv'
    first.write_bytes(b'one')
    second.write_bytes(b'two')
    m = manifest(tmp_path)
    m.completed_outputs = [str(first)]
    legacy_data = json.loads(m.to_json())
    del legacy_data['number_filenames']
    m = extractor.JobManifest.from_json(json.dumps(legacy_data))
    plan = logic.collision_plan(tmp_path, 2, {1: 'One', 2: 'Two'}, manifest=m)
    assert [p.path for p in plan.collisions] == [second]


def test_album_derivation_and_work_folder(tmp_path):
    assert logic.album_output('', str(tmp_path)) is None
    output = logic.album_output('Artist - Album (1975) [Blu-ray]', str(tmp_path))
    assert output == tmp_path / 'Artist - Album (1975)'
    assert logic.safe_work_folder(output) == output.resolve() / '_work'


def test_settings_defaults_merge_old_and_unknown_keys(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'SETTINGS_PATH', path)
    assert settings.load() == settings.DEFAULTS
    path.write_text('{"mkvmerge_path":"custom.exe", "future":42}', encoding='utf-8')
    result = settings.load()
    assert result['mkvmerge_path'] == 'custom.exe'
    assert result['future'] == 42
    assert result['theme'] == 'dark'
    assert result['language'] == 'zh'
    assert result['filename_template'] == 'title'
    assert result['collision_policy'] == 'ask'
    assert result['accent'] == '#F2A33A'
    result['theme'] = 'light'
    assert settings.DEFAULTS['theme'] == 'dark'
    path.write_text('broken', encoding='utf-8')
    assert settings.load() == settings.DEFAULTS


def test_language_key_parity_and_nonempty_values():
    assert set(ZH) == set(EN)
    assert all(isinstance(s, str) and s.strip() for language in (ZH, EN) for s in language.values())


def test_qml_literal_translation_keys_exist():
    import re
    for path in Path('qml').glob('*.qml'):
        for key in re.findall(r'\.tr\("([A-Za-z_]+)"\)', path.read_text(encoding='utf-8-sig')):
            assert key in ZH, (path, key)


def test_scoring_reasons_translate_without_changing_extractor():
    from gui.i18n import localize_reason
    playlist = extractor.Playlist(Path('00001.mpls'),
        [extractor.Track(0, 'video', 'AVC'), extractor.Track(1, 'audio', 'TrueHD Atmos')], 9, 3600)
    for reason in extractor.score_playlists([playlist])[0].reasons:
        assert localize_reason(reason, 'en') == reason
        assert localize_reason(reason, 'zh') != reason
