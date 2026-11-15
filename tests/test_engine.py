"""The built-in engine's wrapper without running it: listings, codec names, meta files, cuts, checks."""
from __future__ import annotations

from pathlib import Path

import pytest

from core import engine, split, verify
from core.chapter_marks import chapters_from_marks
from core.jobs import Failure
from core.models import Chapter, Playlist, Track
from core.naming import PlannedOutput

TITLES = """tsMuxeR version 3.1.0 (DiscSplitter, ea5b37f). github.com/teaching-droid/tsMuxer
Title 1  00800.mpls    2:03:47   36 chapters     2 clips  jpn  SDR  (main film)
Title 2  00012.mpls    2:21:47   64 chapters    31 clips  eng deu fra  SDR  (version of title 1, 2 of 31 clips differ)
Title 3  00000.mpls    0:00:30    1 chapter      1 clip   jpn  SDR  (under 2 minutes)

Left out:
  2 playlists under 2 minutes: 00000 00003
"""

LISTING = """tsMuxeR version 3.1.0 (DiscSplitter, ea5b37f). github.com/teaching-droid/tsMuxer
Track ID:    4113
Stream type: HEVC
Stream ID:   V_MPEGH/ISO/HEVC
Stream info: Profile: Main 10@5.1  Resolution: 3840:2160p  Frame rate: 23.976
Stream lang:
Stream order: playlist 1, clip 1

Track ID:    4117
Stream type: HEVC
Stream ID:   V_MPEGH/ISO/HEVC
Stream info: Dolby Vision enhancement layer
Stream lang:

Track ID:    4352
Stream type: TRUE-HD
Stream ID:   A_AC3
Stream info: AC3 core + TRUE-HD + ATMOS. Peak bitrate: 7224Kbps (core 640Kbps) Sample Rate: 48KHz Channels: 7.1
Stream lang: eng

Track ID:    4353
Stream type: DTS-HD
Stream ID:   A_DTS
Stream info: Bitrate: 1509Kbps  core + MLP data.Sample Rate: 96KHz  Channels: 5.1 (DTS Master Audio)
Stream lang: jpn

Track ID:    4354
Stream type: E-AC3 (DD+)
Stream ID:   A_AC3
Stream info: EAC3 Bitrate: 768Kbps Sample Rate: 48KHz Channels: 5.1
Stream lang: deu
Secondary: 1

Track ID:    4608
Stream type: PGS
Stream ID:   S_HDMV/PGS
Stream info: Presentation Graphic Stream
Stream lang: chi

Track ID:    4609
Stream type: PGS
Stream ID:   S_HDMV/PGS
Stream info: Presentation Graphic Stream
Stream lang: eng
Unselected: 1

Track ID:    6144
Stream type: SRT
Stream ID:   S_TEXT/UTF8
Stream info: TextST text subtitles
Stream lang: fra
Stream delay: -10000
Stream file: 00013.m2ts

File #00000 name=D:\\discs\\film.iso\\BDMV\\STREAM\\00001.m2ts
Duration: 01:00:00.000
start-time: 188955000
Marks: 00:00:00.000 00:02:07.336 00:06:47.991 00:09:01.541 00:11:42.118
Marks: 00:16:33.618

File #00001 name=D:\\discs\\film.iso\\BDMV\\STREAM\\00002.m2ts
Duration: 00:30:00.500
start-time: 188955000
Marks: 01:10:00.000
"""


def tracks():
    listing = engine.parse_listing(LISTING)
    return [t for t in (engine.to_track(b, i) for i, b in enumerate(listing.tracks)) if t is not None]


def test_the_disc_listing_names_its_titles_and_the_main_one():
    found = engine.parse_titles(TITLES)
    assert [(t.number, t.playlist, t.chapters, t.main) for t in found] == [
        (1, "00800.mpls", 36, True), (2, "00012.mpls", 64, False), (3, "00000.mpls", 1, False)]
    assert found[0].seconds == 2 * 3600 + 3 * 60 + 47
    assert found[1].note.startswith("version of title 1")


def test_a_playlist_listing_gives_length_and_marks_on_the_playlist_timeline():
    listing = engine.parse_listing(LISTING)
    assert listing.duration == pytest.approx(5400.5)
    assert listing.marks[:3] == [0.0, 127.336, 407.991]
    assert listing.marks[-1] == 4200.0           # a mark in the second clip, counted from the playlist's start
    assert len(listing.clips) == 2


def test_engine_codecs_are_named_as_the_rest_of_the_app_expects():
    by_pid = {t.track_id: t for t in tracks()}
    assert 4609 not in by_pid                     # a stream the playlist does not play is left out
    hevc, layer = by_pid[4113], by_pid[4117]
    assert (hevc.kind, hevc.codec_id, hevc.properties["pixel_dimensions"]) == ("video", "V_MPEGH/ISO/HEVC", "3840x2160")
    truehd = by_pid[4352]
    assert (truehd.codec, truehd.codec_id, truehd.channels, truehd.sample_rate) == ("TrueHD Atmos", "A_TRUEHD", 8, 48000)
    assert truehd.is_atmos and truehd.is_lossless and truehd.bitrate_kbps is None    # a peak rate is no average
    dts = by_pid[4353]
    assert (dts.codec, dts.channels, dts.sample_rate, dts.bitrate_kbps) == ("DTS-HD Master Audio", 6, 96000, 1509)
    assert dts.is_lossless
    eac3 = by_pid[4354]
    assert (eac3.codec, eac3.title, eac3.properties["secondary"]) == ("E-AC-3", "Secondary", "1")
    assert by_pid[4608].codec == "HDMV PGS" and by_pid[4608].language == "chi"
    textst = by_pid[6144]
    assert (textst.kind, textst.codec, textst.properties["stream_file"]) == ("subtitles", "HDMV TextST", "00013.m2ts")
    assert all(t.stream_id == t.track_id for t in by_pid.values())


def test_a_dolby_vision_layer_goes_with_the_picture():
    playlist = Playlist(Path("BDMV/PLAYLIST/00800.mpls"), tracks=tracks(), reader="engine")
    assert [t.track_id for t in playlist.picture_tracks] == [4113, 4117]
    assert playlist.best_default_audio_track().track_id == 4352


def test_meta_lines_name_each_track_by_pid():
    by_pid = {t.track_id: t for t in tracks()}
    source = "D:/discs/film.iso/BDMV/PLAYLIST/00800.mpls"
    assert engine.track_line(source, by_pid[4352]) == f'A_AC3, "{source}", track=4352, lang=eng'
    assert engine.track_line(source, by_pid[4352], matroska=True, drop_core=True).endswith("drop-ac3-core")
    assert engine.track_line(source, by_pid[4354]).endswith("lang=deu, secondary")
    textst = engine.track_line(source, by_pid[6144])
    assert '00013.m2ts"' in textst and "STREAM" in textst and "timeshift=-10000ms" in textst
    assert engine.source_of(Path("BDMV/PLAYLIST/00001.mpls"), Path("D:/x/disc.iso")) == \
        "D:/x/disc.iso/BDMV/PLAYLIST/00001.mpls"


def test_clock_keeps_microseconds():
    assert engine.clock(407.9915) == "00:06:47.991500"
    assert engine.clock(3723.000001) == "01:02:03.000001"
    assert engine.seconds_of("01:02:03.456") == pytest.approx(3723.456)


def planned(*spans):
    return [PlannedOutput(Chapter(i, s, e), Path(f"{i}.m2ts")) for i, (s, e) in enumerate(spans, start=1)]


def test_chapters_that_follow_one_another_are_cut_in_one_pass():
    items = planned((0, 10), (10, 20), (30, 40), (40, None))
    assert [[p.chapter.index for p in run] for run in split.chapter_runs(items)] == [[1, 2], [3, 4]]


def test_a_run_starts_at_its_key_picture_and_splits_at_each_mark():
    by_pid = {t.track_id: t for t in tracks()}
    run = [Chapter(3, 407.991, 541.541), Chapter(4, 541.541, 702.118)]
    lines = split.m2ts_meta("src.mpls", run, video_tracks=[by_pid[4113]], audio_tracks=[by_pid[4352]],
                            subtitle_tracks=[by_pid[4608]], duration=5400.5)
    options = lines[0].split()
    assert "--cut-start=00:06:47.991500" in options          # just after the mark: the key picture at or before
    assert "--cut-end=00:11:42.118000" in options
    assert "--split-chapters" in options
    assert "--custom-chapters=00:06:47.991500;00:09:01.540500" in options    # just before: at or after
    assert lines[1:] == ['V_MPEGH/ISO/HEVC, "src.mpls", track=4113', 'A_AC3, "src.mpls", track=4352, lang=eng',
                         'S_HDMV/PGS, "src.mpls", track=4608, lang=chi']


def test_a_single_chapter_at_the_ends_of_the_disc_needs_no_cut():
    lines = split.m2ts_meta("src.mpls", [Chapter(1, 0.0, 5400.5)], video_tracks=[], audio_tracks=[],
                            subtitle_tracks=[], duration=5400.5)
    assert lines[0] == "MUXOPT --no-pcr-on-video-pid --new-audio-pes --vbr --vbv-len=500"


def test_chapters_from_marks_end_with_the_playlist():
    chapters = chapters_from_marks([0.0, 10.0, 25.5], 40.0)
    assert [(c.index, c.start_seconds, c.end_seconds) for c in chapters] == [(1, 0.0, 10.0), (2, 10.0, 25.5),
                                                                              (3, 25.5, 40.0)]


def _info(video_start, audio_start, duration=10.0, title=None):
    streams = [dict(codec_type="video", start_time=str(video_start)), dict(codec_type="audio", start_time=str(audio_start))]
    return dict(streams=streams, format=dict(duration=str(duration), tags={"title": title} if title else {}))


def test_verify_m2ts_checks_sync_and_skips_the_title_tag(tmp_path):
    path = tmp_path / "a.m2ts"
    path.write_bytes(b"x")
    audio = [Track(1, "audio", "AC-3")]
    chapter = Chapter(1, 0.0, 10.0)
    ok = verify.verify_output(path, chapter, container="m2ts", audio_tracks=audio, subtitle_count=0, keep_video=True,
                              title="Song", probe=lambda p: _info(600.0, 599.959))
    assert ok.ok
    late = verify.verify_output(path, chapter, container="m2ts", audio_tracks=audio, subtitle_count=0,
                                keep_video=True, title="Song", probe=lambda p: _info(600.0, 600.5))
    assert [i.code for i in late.issues] == ["sync"]
    mkv = verify.verify_output(path, chapter, container="mkv", audio_tracks=audio, subtitle_count=0, keep_video=True,
                               title="Song", probe=lambda p: _info(0.0, 0.0))
    assert [i.code for i in mkv.issues] == ["title"]


def test_a_job_is_never_resumed_with_other_track_numbers(tmp_path):
    from core import manifest as job_manifest, pipeline
    audio = Track(4352, "audio", "PCM", stream_id=4352)
    playlist = Playlist(Path("BDMV/PLAYLIST/00001.mpls"), [audio], 2, 60.0, reader="engine", marks=[0.0, 30.0])
    m = job_manifest.JobManifest("BDMV/PLAYLIST/00001.mpls", 4352, "PCM", None, str(tmp_path), "m2ts", {}, {}, "now",
                                 status="cancelled")        # saved before the engine: mkvmerge's numbers
    job_manifest.write_manifest(tmp_path / "_work", m)
    with pytest.raises(Failure) as caught:
        pipeline.run_full_pipeline(playlist, audio, {}, tmp_path / "_work", tmp_path, container="m2ts", resume=True)
    assert caught.value.code == "tracks_unavailable"


def test_m2ts_needs_a_disc_the_engine_read(tmp_path):
    from core import pipeline
    audio = Track(1, "audio", "PCM")
    with pytest.raises(Failure):
        pipeline.run_full_pipeline(Playlist(Path("x.mkv"), [audio], 1, 10.0), audio, {}, tmp_path / "_work",
                                   tmp_path, container="m2ts")


def test_the_engine_route_hands_the_chosen_streams_to_the_cutter(tmp_path, monkeypatch):
    from core import pipeline
    by_pid = {t.track_id: t for t in tracks()}
    playlist = Playlist(Path("BDMV/PLAYLIST/00800.mpls"), tracks=tracks(), chapter_count=3, duration_seconds=90.0,
                        iso_image=Path("D:/discs/film.iso"), reader="engine", marks=[0.0, 30.0, 60.0])
    seen = {}

    def fake(source, chapters, output_folder, **kw):
        seen.update(source=source, chapters=[(c.index, c.start_seconds, c.end_seconds, c.name) for c in chapters], **kw)
        return [output_folder / "x.m2ts"]
    monkeypatch.setattr(split, "split_m2ts", fake)
    monkeypatch.setattr(engine, "version", lambda: "tsMuxeR version test")
    pipeline.run_full_pipeline(playlist, by_pid[4352], {2: "Two"}, tmp_path / "_work", tmp_path, container="m2ts",
                               audio_track_ids=[4352, 4353], subtitle_track_ids=[4608], chapter_indices=[2, 3])
    assert seen["source"] == "D:/discs/film.iso/BDMV/PLAYLIST/00800.mpls"
    assert seen["chapters"] == [(2, 30.0, 60.0, "Two"), (3, 60.0, 90.0, "")]
    assert [t.track_id for t in seen["video_tracks"]] == [4113, 4117]
    assert [t.track_id for t in seen["audio_tracks"]] == [4352, 4353]
    assert [t.track_id for t in seen["subtitle_tracks"]] == [4608]
    assert seen["duration"] == 90.0


def test_disc_view_offers_m2ts_only_for_an_engine_read_bluray(backend, qt_app, monkeypatch):
    from test_backend import wait_idle
    from core import space
    monkeypatch.setattr(space, 'source_size_bytes', lambda path: None)
    disc = backend.disc
    by_pid = {t.track_id: t for t in tracks()}
    playlist = Playlist(Path("D:/disc/BDMV/PLAYLIST/00800.mpls"), tracks=tracks(), chapter_count=2,
                        duration_seconds=60.0, reader="engine", marks=[0.0, 30.0], measured=True)
    from core import sources
    disc.playlists = sources.score_playlists([playlist])
    disc.selectPlaylist(0)
    wait_idle(backend, qt_app)
    assert disc.state['canM2ts']
    disc.setOutputFormat('m2ts')
    assert disc.state['outputFormat'] == 'm2ts'
    assert disc.selected_ids('audio') == [4352, 4353, 4354]       # a disc copy keeps every track
    assert disc.selected_ids('subtitle') == [4608, 6144]
    assert backend.names.fileNamePreview(1, 'Song').endswith('.m2ts')
    mkv = Playlist(Path("D:/a.mkv"), tracks=[by_pid[4352]], chapter_count=1, duration_seconds=10.0)
    disc.playlists = sources.score_playlists([mkv])
    disc.selectPlaylist(0)
    wait_idle(backend, qt_app)
    assert not disc.state['canM2ts'] and disc.state['outputFormat'] == 'mkv'
