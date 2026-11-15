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
    assert playlist.marks == pytest.approx(CHAPTERS, abs=0.002)
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


def _mkvmerge(monkeypatch) -> None:
    """mkvmerge from PATH, or where the app's settings point (as the app itself would run it)."""
    from core import tools
    from gui import settings
    try:
        configured = json.loads(settings.SETTINGS_PATH.read_text(encoding="utf-8")).get("mkvmerge_path")
    except (OSError, ValueError):
        configured = None
    for candidate in (tools.TOOL_PATHS["mkvmerge"], configured):
        if candidate and tools.verify_tool_at_path(candidate, "mkvmerge")[0]:
            monkeypatch.setitem(tools.TOOL_PATHS, "mkvmerge", candidate)
            return
    pytest.skip("mkvmerge is not available")


def test_mkv_output_maps_engine_track_numbers_for_mkvmerge(disc, tmp_path, monkeypatch):
    from core import split
    _mkvmerge(monkeypatch)
    playlist = sources.scan_source(disc["folder"])[0]
    mapped = split.mkvmerge_track_ids(disc["folder"] / "BDMV" / "PLAYLIST" / "00000.mpls", playlist.tracks)
    assert [t.track_id for t in mapped] == [0, 1, 2]
    assert [t.stream_id for t in mapped] == [t.stream_id for t in playlist.tracks]


def test_mkv_export_of_an_engine_read_disc_still_goes_through_mkvmerge(disc, tmp_path, monkeypatch):
    _mkvmerge(monkeypatch)
    playlist = sources.scan_source(disc["folder"])[0]
    out = tmp_path / "Album"
    results = pipeline.run_full_pipeline(playlist, playlist.audio_tracks[0], {2: "Two"}, work_folder=out / "_work",
                                         output_folder=out, container="mkv", chapter_indices=[2],
                                         audio_track_ids=[t.track_id for t in playlist.audio_tracks])
    info = _probe(results[0])
    assert [s["codec_name"] for s in info["streams"]] == ["h264", "ac3", "pcm_s24le"]
    assert info["format"]["tags"]["title"] == "Two"
