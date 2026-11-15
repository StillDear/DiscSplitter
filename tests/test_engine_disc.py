"""
End to end with the built-in engine on a small Blu-ray made here: ffmpeg encodes 30 seconds of picture
and two sound tracks (AC-3 5.1 and 24-bit LPCM), and the engine authors them into a Blu-ray folder and an
ISO image with four chapters. Then the app's own code scans the disc, reads its chapters and exports them
as M2TS and FLAC, and every file is checked: its length, its streams, and that sound and picture start
together. Skipped when the engine has not been built or ffmpeg is missing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from core import engine, pipeline, sources, verify
from core import chapter_marks

pytestmark = pytest.mark.engine

CHAPTERS = [0.0, 7.007, 15.015, 22.022]      # on key pictures: one every 24 frames (1.001 s)
LENGTH = 30.0


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        pytest.skip("ffmpeg is not on PATH")
    return found


@pytest.fixture(scope="session")
def disc(tmp_path_factory) -> dict:
    root = Path(__file__).resolve().parent / "runtime" / "_engine_disc"
    folder, image = root / "disc", root / "disc.iso"
    if not (folder / "BDMV" / "PLAYLIST").is_dir() or not image.is_file():
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True)
        ffmpeg = _ffmpeg()
        subprocess.run([ffmpeg, "-v", "error", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24000/1001",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000",
                        "-map", "0:v", "-t", str(LENGTH), "-c:v", "libx264", "-preset", "ultrafast",
                        "-profile:v", "high", "-level", "4.1", "-g", "24", "-keyint_min", "24", "-sc_threshold", "0",
                        "-bsf:v", "h264_mp4toannexb", "-f", "h264", str(root / "v.h264"),
                        "-map", "1:a", "-t", str(LENGTH), "-ac", "6", "-c:a", "ac3", "-b:a", "448k",
                        str(root / "a.ac3"),
                        "-map", "2:a", "-t", str(LENGTH), "-ac", "2", "-c:a", "pcm_s24le", str(root / "a.wav")],
                       check=True, timeout=300)
        marks = ";".join(engine.clock(c) for c in CHAPTERS)
        meta = root / "disc.meta"
        meta.write_text(f"MUXOPT --blu-ray --custom-chapters={marks}\n"
                        f'V_MPEG4/ISO/AVC, "{root / "v.h264"}", fps=23.976\n'
                        f'A_AC3, "{root / "a.ac3"}", lang=eng\n'
                        f'A_LPCM, "{root / "a.wav"}", lang=jpn\n', encoding="utf-8")
        for target in (folder, image):
            result = subprocess.run([engine.path(), str(meta), str(target)], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=300)
            assert result.returncode == 0, result.stdout[-2000:]
    return dict(folder=folder, image=image)


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60)
    return json.loads(out.stdout)


@pytest.mark.parametrize("kind", ["folder", "image"])
def test_engine_scans_the_disc_without_mounting(disc, kind):
    found = sources.scan_source(disc[kind])
    assert len(found) == 1
    playlist = found[0]
    assert playlist.by_engine and playlist.main_title
    assert playlist.iso_image == (disc["image"].resolve() if kind == "image" else None)
    assert [t.kind for t in playlist.tracks] == ["video", "audio", "audio"]
    ac3, pcm = playlist.audio_tracks
    assert (ac3.codec, ac3.channels, ac3.language) == ("AC-3", 6, "eng")
    assert (pcm.codec, pcm.channels, pcm.bits_per_sample, pcm.language) == ("PCM", 2, 24, "jpn")
    assert pcm.is_lossless and pcm.bitrate_kbps == 2304
    assert playlist.chapter_count == 4
    assert playlist.marks_exact                             # from the marks' 45 kHz ticks
    assert playlist.marks == pytest.approx(CHAPTERS, abs=5e-5)     # a mark may sit one tick before its picture
    assert playlist.duration_seconds == pytest.approx(LENGTH, abs=0.2)
    chapters = chapter_marks.playlist_chapters(playlist)
    assert chapters[-1].end_seconds == pytest.approx(playlist.duration_seconds)
    best = sources.score_playlists(found)[0]
    assert "main_title" in [r.code for r in best.reasons]


@pytest.mark.parametrize("kind", ["folder", "image"])
def test_m2ts_export_keeps_every_stream_and_the_timing(disc, kind, tmp_path):
    playlist = sources.scan_source(disc[kind])[0]
    out = tmp_path / "Album"
    picked = [2, 3, 4]          # a run of chapters that ends where the disc ends
    names = {2: "Second", 3: "Third", 4: "Fourth"}
    results = pipeline.run_full_pipeline(
        playlist, playlist.audio_tracks[0], names, work_folder=out / "_work", output_folder=out, container="m2ts",
        audio_track_ids=[t.track_id for t in playlist.audio_tracks], chapter_indices=picked)
    assert [p.name for p in results] == ["Second.m2ts", "Third.m2ts", "Fourth.m2ts"]
    assert not (out / "_work").exists() and not list(out.glob(".split-*"))
    chapters = {c.index: c for c in chapter_marks.playlist_chapters(playlist)}
    total = 0.0
    for number, path in zip(picked, results):
        check = verify.verify_output(path, chapters[number], container="m2ts", audio_tracks=playlist.audio_tracks,
                                     subtitle_count=0, keep_video=True, title=names[number])
        assert check.ok, check.issues
        info = _probe(path)
        codecs = [s["codec_name"] for s in info["streams"]]
        assert codecs == ["h264", "ac3", "pcm_bluray"]
        length = float(info["format"]["duration"])
        # The cut lands on the chapter's key picture; a file may run one picture past the next one.
        assert chapters[number].duration - 0.01 <= length <= chapters[number].duration + 0.1
        total += length
    assert total == pytest.approx(LENGTH - CHAPTERS[1], abs=0.25)


def test_chapters_apart_are_cut_in_one_pass_and_the_one_between_thrown_away(disc, tmp_path):
    playlist = sources.scan_source(disc["image"])[0]
    out = tmp_path / "Album"
    events = []
    results = pipeline.run_full_pipeline(
        playlist, playlist.audio_tracks[0], {1: "One", 3: "Three"}, work_folder=out / "_work", output_folder=out,
        container="m2ts", chapter_indices=[1, 3], progress_cb=events.append)
    assert [p.name for p in results] == ["One.m2ts", "Three.m2ts"]
    assert sorted(p.name for p in out.iterdir()) == ["One.m2ts", "Three.m2ts"]      # chapter 2 is gone
    assert any("in 1 pass(es)" in str(e) for e in events)
    shares = [e for e in events if getattr(e, "fraction", None) is not None]
    assert all(0 <= e.fraction < 1 for e in shares)          # a disc this short may finish before any
    chapters = {c.index: c for c in chapter_marks.playlist_chapters(playlist)}
    for number, path in zip((1, 3), results):
        info = _probe(path)
        assert chapters[number].duration - 0.01 <= float(info["format"]["duration"]) <= chapters[number].duration + 0.1
        first = float(info["streams"][0]["start_time"]) - 600.0        # an M2TS clock starts at 600 s here
        assert first == pytest.approx(chapters[number].start_seconds, abs=1e-4)


def test_previews_and_outlines_read_an_image_without_mounting_it(disc, tmp_path, monkeypatch):
    from core import bluray_iso, preview, space

    def no_mounting(*_, **__):
        raise AssertionError("the image was mounted")
    monkeypatch.setattr(bluray_iso, "mounted", no_mounting)
    playlist = sources.scan_source(disc["image"])[0]
    keeper = preview.MountKeeper()
    audio = playlist.audio_tracks[1]
    with keeper.use(playlist.path, playlist.iso_image) as path:
        assert not keeper.mounted and engine.image_of(path) is not None
        assert space.source_size_bytes(path) > 1_000_000
        clip = preview.render(path, audio, 1, CHAPTERS[2], CHAPTERS[3], tmp_path / "clip.flac")
        assert float(_probe(clip)["format"]["duration"]) == pytest.approx(CHAPTERS[3] - CHAPTERS[2], abs=0.1)
        assert preview.probe_stream(path, playlist.video_track, 0, "video")["codec_name"] == "h264"
        assert preview.sample_bitrate(path, playlist.video_track, 0, "video", seconds=10, share=0.3)
        peaks = preview.disc_peaks(path, audio, 1, playlist.duration_seconds)
        assert len(peaks) == pytest.approx(LENGTH * preview.DISC_PER_SECOND, abs=3)
    # The engine's own naming of files inside an image
    inside = Path(f"{disc['image'].resolve()}/BDMV/PLAYLIST/00000.mpls")
    assert engine.read_file(inside)[:4] == b"MPLS"
    assert engine.media_input(inside.parent.parent / "STREAM" / "00000.m2ts").startswith("subfile,,start,")


def test_key_pictures_come_from_the_clip_information(disc):
    for root in (disc["folder"], Path(f"{disc['image'].resolve()}")):
        stream = root / "BDMV" / "STREAM"
        pictures = sources.read_key_pictures(sources.clip_info_file(stream, "00000"))
        assert len(pictures) == pytest.approx(LENGTH / 1.001, abs=2)
        assert pictures[0][0] == pytest.approx(600.0, abs=0.01)                 # the clip's clock starts at 600 s
        steps = [b[0] - a[0] for a, b in zip(pictures, pictures[1:])]
        assert all(s == pytest.approx(1.001, abs=0.006) for s in steps)   # one every 24 frames, to 512/90000 s
        assert all(b[1] > a[1] for a, b in zip(pictures, pictures[1:]))
    data = (disc["folder"] / "BDMV" / "STREAM" / "00000.m2ts").read_bytes()
    for _, offset in pictures:
        # A source packet: 4 bytes of arrival time, then a TS packet starting the video's PES.
        assert data[offset + 4] == 0x47
        assert (int.from_bytes(data[offset + 5:offset + 7], "big") & 0x1FFF) == 0x1011
        assert data[offset + 5] & 0x40                                    # payload unit start


@pytest.mark.parametrize("chapter", [1, 2, 3])
def test_previews_from_an_image_start_at_their_chapter(disc, tmp_path, chapter):
    """ffmpeg cannot seek by time through a clip read from an image; the preview opens it at a key picture."""
    from core import preview

    def first_pictures(path):
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-frames:v", "3",
                              "-f", "framemd5", "-"], capture_output=True, text=True, timeout=120).stdout
        return [line.split(",")[-1].strip() for line in out.splitlines() if not line.startswith("#")]

    clips = []
    for kind in ("folder", "image"):
        playlist = sources.scan_source(disc[kind])[0]
        path = disc["image"].resolve() / playlist.path if kind == "image" else playlist.path
        clips.append(preview.render_video(path, playlist.audio_tracks[1], 1, playlist.video_track,
                                          CHAPTERS[chapter], CHAPTERS[chapter] + 3, tmp_path / f"{kind}.mkv"))
    folder, image = map(first_pictures, clips)
    assert len(image) == 3 and image == folder
    # Opened at the chapter's key picture, not at the start of the clip (with a long clip, as on a real disc,
    # ffmpeg's seek fails there and the preview would start at the beginning: this disc is too short to show it).
    playlist = sources.scan_source(disc["image"])[0]
    path = disc["image"].resolve() / playlist.path
    args, _ = preview.clip_input(path, playlist.audio_tracks[1], 1, CHAPTERS[chapter], 3)
    whole = engine.media_input(path.parent.parent / "STREAM" / "00000.m2ts")
    opened, clip_start = (int(url.split(",")[3]) for url in (args[args.index("-i") + 1], whole))
    key = sources.read_key_pictures(sources.clip_info_file(path.parent.parent / "STREAM", "00000"))
    assert opened - clip_start == next(b for t, b in key if t == pytest.approx(600 + CHAPTERS[chapter], abs=0.006))
    assert float(args[args.index("-ss") + 1]) < 0.01
    assert float(_probe(clips[1])["format"]["duration"]) == pytest.approx(3, abs=0.1)


def test_m2ts_export_resumes_after_the_last_finished_chapter(disc, tmp_path):
    playlist = sources.scan_source(disc["folder"])[0]
    out = tmp_path / "Album"
    names = {1: "One", 2: "Two"}
    first = pipeline.run_full_pipeline(playlist, playlist.audio_tracks[1], names, work_folder=out / "_work",
                                       output_folder=out, container="m2ts", chapter_indices=[1],
                                       audio_track_ids=[playlist.audio_tracks[1].track_id], cleanup_work_folder=False)
    assert [p.name for p in first] == ["One.m2ts"]
    stamp = first[0].stat().st_mtime_ns
    # A job saved with these numbers resumes; the finished file is left alone.
    again = pipeline.run_full_pipeline(playlist, playlist.audio_tracks[1], names, work_folder=out / "_work",
                                       output_folder=out, container="m2ts", resume=True)
    assert [p.name for p in again] == ["One.m2ts"]
    assert first[0].stat().st_mtime_ns == stamp


def test_flac_export_reads_only_the_chosen_span_and_cuts_to_the_sample(disc, tmp_path):
    playlist = sources.scan_source(disc["image"])[0]
    pcm = playlist.audio_tracks[1]
    out = tmp_path / "Album"
    results = pipeline.run_full_pipeline(playlist, pcm, {2: "Two", 3: "Three"}, work_folder=out / "_work",
                                         output_folder=out, container="flac", chapter_indices=[2, 3],
                                         audio_track_ids=[pcm.track_id])
    chapters = {c.index: c for c in chapter_marks.playlist_chapters(playlist)}
    for number, path in zip((2, 3), results):
        info = _probe(path)
        assert info["streams"][0]["codec_name"] == "flac"
        assert info["streams"][0]["bits_per_raw_sample"] == "24"
        assert float(info["format"]["duration"]) == pytest.approx(chapters[number].duration, abs=0.03)


@pytest.mark.parametrize("kind", ["folder", "image"])
def test_mkv_export_of_an_engine_read_disc_needs_no_mkvtoolnix(disc, kind, tmp_path, monkeypatch):
    from core import bluray_iso, tools

    def missing(*_, **__):
        raise AssertionError("MKVToolNix or a mount was used")
    monkeypatch.setitem(tools.TOOL_PATHS, "mkvmerge", "no-mkvmerge-here")
    monkeypatch.setattr(tools, "mkvpropedit_path", missing)
    monkeypatch.setattr(bluray_iso, "mounted", missing)
    playlist = sources.scan_source(disc[kind])[0]
    out = tmp_path / "Album"
    names = {2: "Second · 第二", 4: "Fourth"}
    results = pipeline.run_full_pipeline(playlist, playlist.audio_tracks[0], names, work_folder=out / "_work",
                                         output_folder=out, container="mkv", chapter_indices=[2, 4],
                                         audio_track_ids=[t.track_id for t in playlist.audio_tracks])
    assert [p.suffix for p in results] == [".mkv", ".mkv"]
    assert sorted(p.name for p in out.iterdir()) == sorted(p.name for p in results)     # the gap is gone
    chapters = {c.index: c for c in chapter_marks.playlist_chapters(playlist)}
    for number, path in zip((2, 4), results):
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-show_chapters",
                                          "-of", "json", str(path)], capture_output=True, timeout=60).stdout)
        assert [s["codec_type"] for s in info["streams"]] == ["video", "audio", "audio"]    # no attachment
        assert [s["codec_name"] for s in info["streams"]] == ["h264", "ac3", "pcm_s24le"]
        assert info["format"]["tags"]["title"] == names[number]
        assert info["chapters"] == []
        assert chapters[number].duration - 0.01 <= float(info["format"]["duration"]) <= chapters[number].duration + 0.1
        check = verify.verify_output(path, chapters[number], container="mkv", audio_tracks=playlist.audio_tracks,
                                     subtitle_count=0, keep_video=True, title=names[number])
        assert check.ok, check.issues


def test_a_cut_reads_the_disc_from_its_chapter_mark_and_gives_the_same_sound(disc, tmp_path):
    import dataclasses
    playlist = sources.scan_source(disc["image"])[0]
    pcm = playlist.audio_tracks[1]
    chapters = {c.index: c for c in chapter_marks.playlist_chapters(playlist)}
    events = []
    m2ts = pipeline.run_full_pipeline(playlist, pcm, {3: "Three"}, work_folder=tmp_path / "a" / "_work",
                                      output_folder=tmp_path / "a", container="m2ts", chapter_indices=[3],
                                      audio_track_ids=[pcm.track_id], progress_cb=events.append)
    assert not any("instead" in str(e) for e in events)          # the window opened where it was asked to
    info = _probe(m2ts[0])
    assert float(info["streams"][0]["start_time"]) == pytest.approx(600.0, abs=1e-4)   # time 0 is the mark
    assert chapters[3].duration - 0.01 <= float(info["format"]["duration"]) <= chapters[3].duration + 0.1

    def samples(path):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-f", "s32le", "-ac", "2", "-"],
                              capture_output=True, timeout=60).stdout
    flac = pipeline.run_full_pipeline(playlist, pcm, {3: "Three"}, work_folder=tmp_path / "b" / "_work",
                                      output_folder=tmp_path / "b", container="flac", chapter_indices=[3],
                                      audio_track_ids=[pcm.track_id])
    # The FLAC holds exactly the chapter's sound as the M2TS has it beside its picture, to the sample
    sound, beside_picture = samples(flac[0]), samples(m2ts[0])
    common = min(len(sound), len(beside_picture))
    assert common > 6 * 48000 * 8 and sound[:common] == beside_picture[:common]
    assert len(sound) // 8 == round(chapters[3].duration * 48000)      # and the whole chapter, to the sample
