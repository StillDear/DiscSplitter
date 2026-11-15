"""
Cutting a source into one file per chapter.

    FLAC  ffmpeg encodes each chapter from an MKV holding the chosen audio track (extract_audio_mkv,
          or for a Blu-ray read by the engine extract_audio_engine)
    MKV   mkvmerge cuts every chapter straight from the source in one pass, nothing re-encoded
    M2TS  the built-in engine cuts every run of chapters straight from the disc, the streams as they are
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from . import dvd
from . import engine
from . import tagging
from . import tools
from .jobs import Failure, JobCancelled, already_done, extracting, splitting, tool_failed
from .models import Chapter, Playlist, Track
from .naming import OutputCollisionError, PlannedOutput, plan_output_files
from .tools import TOOL_PATHS, mkvpropedit_path, probe_duration_seconds


def _planned(chapters: list[Chapter], output_folder: Path, container: str, overwrite: Optional[set[Path]],
             skip_paths: Optional[set[Path]], **naming) -> tuple[list[PlannedOutput], set[Path]]:
    """
    The files this cut will write, and the ones it leaves alone (skip_paths: finished by the run
    being resumed, or kept by the user). A planned file that already exists and is neither approved
    for overwrite nor skipped raises OutputCollisionError: nothing is ever overwritten silently.
    """
    output_folder.mkdir(parents=True, exist_ok=True)
    planned = plan_output_files(chapters, output_folder, container=container, **naming)
    overwrite, skip_paths = overwrite or set(), skip_paths or set()
    colliding = [p for p in planned if p.exists and p.path not in overwrite and p.path not in skip_paths]
    if colliding:
        raise OutputCollisionError(colliding)
    return planned, skip_paths


# ---------------------------------------------------------------------------
# FLAC: one audio track to a standalone MKV, then one encode per chapter
# ---------------------------------------------------------------------------

def extract_audio_mkv(
    playlist: Playlist,
    output_path: Path,
    audio_track: Track,
    progress_cb: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Path:
    """Remux one audio track, with the source's chapters, into a standalone MKV."""
    if audio_track.kind != "audio":
        raise ValueError("Select a valid audio track.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if dvd.is_title(playlist.path):
        return dvd.remux(playlist.path, output_path, tracks=[audio_track],
                         progress_cb=progress_cb, cancel_event=cancel_event)

    args = [TOOL_PATHS["mkvmerge"], "-o", str(output_path), "--no-video", "-a", str(audio_track.track_id),
            "--no-subtitles", str(playlist.path)]
    if progress_cb:
        progress_cb(extracting(f"Extracting audio track {audio_track.track_id} -> {output_path.name}"))
    result = tools.run(args, timeout=7200, cancel_event=cancel_event)  # 2 hours - full-disc extraction can be slow
    if result.returncode != 0:
        raise tool_failed("mkvmerge", f"{result.stdout}\n{result.stderr}")
    return output_path


def extract_audio_engine(
    source: str,
    output_path: Path,
    audio_track: Track,
    *,
    start: float = 0.0,
    end: Optional[float] = None,
    duration: float = 0.0,
    progress_cb: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> float:
    """
    One audio track of a Blu-ray playlist, from `start` to `end` only, into a Matroska audio file, read by
    the engine straight from the disc (an image is not mounted). TrueHD is kept without its AC-3 core.
    Returns where the file's timeline begins on the playlist's: a playlist time t is at t - offset in it.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    options = ["MUXOPT", "--no-chapters"]
    offset = 0.0
    if start > CUT_SLACK:
        offset = start
        options.append(f"--cut-start={engine.clock(start)}")
    if end is not None and (not duration or end < duration - CUT_SLACK):
        options.append(f"--cut-end={engine.clock(end)}")
    meta = [" ".join(options), engine.track_line(source, audio_track, matroska=True, drop_core=True)]
    if progress_cb:
        progress_cb(extracting(f"Extracting audio track {audio_track.track_id} -> {output_path.name}"))
    partial = output_path.with_name(output_path.stem + ".partial.mka")
    partial.unlink(missing_ok=True)
    try:
        engine.run_meta(meta, output_path.with_suffix(".meta"), partial, on_message=progress_cb,
                        cancel_event=cancel_event)
        os.replace(partial, output_path)
    finally:
        partial.unlink(missing_ok=True)
        output_path.with_suffix(".meta").unlink(missing_ok=True)
    return offset


def split_flac(
    audio_mkv: Path,
    chapters: list[Chapter],
    output_folder: Path,
    *,
    metadata: Optional[dict] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    overwrite: Optional[set[Path]] = None,
    cancel_event: Optional[threading.Event] = None,
    skip_paths: Optional[set[Path]] = None,
    on_output_written: Optional[Callable[[Path], None]] = None,
    source_chapter_count: Optional[int] = None,
    number_filenames: bool = False,
    renumber_tracks: bool = True,
    filename_template: str = "",
) -> list[Path]:
    """
    Encode each supplied chapter of the extracted MKV's audio to a tagged FLAC file.

    overwrite / skip_paths: see _planned().
    cancel_event: checked before each chapter and passed down into the ffmpeg call itself, so
    cancelling stops the chapter in progress rather than only stopping between chapters.
    on_output_written: called with each output path right after it is finalised, so a caller can
    persist progress (the job manifest) as it goes instead of only at the very end.
    renumber_tracks: track tags count the exported files (1, 2, 3...); otherwise they keep the
    source's chapter numbers out of source_chapter_count (checkpoints made before renumbering).
    """
    if not chapters:
        raise Failure("no_chapters", "No chapters found - this playlist has no chapter markers, "
                                     "so it can't be split into individual songs.")
    # Collisions are checked before the (comparatively expensive) duration probe below.
    planned, skip_paths = _planned(chapters, output_folder, "flac", overwrite, skip_paths,
                                   number_filenames=number_filenames, filename_template=filename_template,
                                   metadata=metadata)
    if chapters[-1].end_seconds is None:
        chapters[-1].end_seconds = probe_duration_seconds(audio_mkv)

    cover = tagging.embedded_cover(metadata)
    stream_args = ["-map", "0:a:0", "-c:a", "flac"]
    if cover is not None:
        stream_args += ["-map", "1:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]

    output_paths: list[Path] = []
    track_total = len(planned) if renumber_tracks else source_chapter_count or len(chapters)

    for track_number, item in enumerate(planned, start=1):
        ch = item.chapter
        out_path = item.path

        if out_path in skip_paths and out_path.is_file():
            if progress_cb:
                progress_cb(already_done(ch.index, ch.title))
            output_paths.append(out_path)
            continue

        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("Cancelled by user.")

        # Write to a temp file in the same folder (so the final rename is on the same filesystem
        # and therefore atomic) and only move it to the real name once ffmpeg has produced a
        # non-empty file. A crash or a killed process mid-chapter then leaves a stray ".partial-*"
        # file instead of a truncated file at the real track name looking like a finished song.
        tmp_path = out_path.with_name(f".partial-{uuid.uuid4().hex}-{out_path.name}")

        # -ss before -i seeks in the input instead of decoding from the start of the file for
        # every chapter; ffmpeg still decodes from the seek point, so the cut is sample accurate.
        args = [
            TOOL_PATHS["ffmpeg"],
            "-y",  # only ever overwrites our own freshly-named temp file
            "-ss", str(ch.start_seconds),
            "-i", str(audio_mkv),
        ]
        if cover is not None:
            args += ["-i", str(cover)]
        if ch.end_seconds is not None:
            # With -ss before -i the output timeline starts at the seek point, so the cut is
            # given as the chapter's length (-t), not its absolute end time.
            args += ["-t", str(ch.duration)]
        args += stream_args
        args += tagging.flac_tag_args(metadata, ch.index, track_total, ch.title,
                                      track_number=track_number if renumber_tracks else None)
        args += [str(tmp_path)]

        if progress_cb:
            progress_cb(splitting(ch.index, ch.title))

        try:
            # 30 min per chapter: a safety net, an encode takes seconds
            result = tools.run(args, timeout=1800, cancel_event=cancel_event)
            if result.returncode != 0:
                raise tool_failed("ffmpeg", result.stderr, f"on chapter {ch.index}")
            if not tmp_path.is_file() or tmp_path.stat().st_size == 0:
                raise RuntimeError(
                    f"ffmpeg reported success on chapter {ch.index} ({ch.title}) "
                    f"but produced no output file, or an empty one."
                )
            os.replace(tmp_path, out_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        output_paths.append(out_path)
        if on_output_written:
            on_output_written(out_path)

    return output_paths


# ---------------------------------------------------------------------------
# MKV: straight from the source (mkvmerge chapter split)
# ---------------------------------------------------------------------------

def _mkv_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:012.9f}"


def split_mkv_direct(
    source: Path,
    chapters: list[Chapter],
    output_folder: Path,
    *,
    audio_tracks: list[Track],
    subtitle_tracks: list[Track],
    video_track: Optional[Track],
    metadata: Optional[dict] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    overwrite: Optional[set[Path]] = None,
    cancel_event: Optional[threading.Event] = None,
    skip_paths: Optional[set[Path]] = None,
    on_output_written: Optional[Callable[[Path], None]] = None,
    number_filenames: bool = False,
    filename_template: str = "",
) -> list[Path]:
    """
    Cut the given chapters out of a playlist / MKV in ONE mkvmerge pass, with
    no intermediate copy of the disc. Cuts land exactly on the chapter marks
    (Blu-ray chapters sit on keyframes), every file starts on a keyframe and
    nothing is re-encoded. Each file's title is set afterwards with
    mkvpropedit; video files carry no album tags or cover (metadata is only
    used for file names).

    Finished parts are moved into place as soon as mkvmerge has moved on to
    the next one, so a cancelled or failed job resumes after the last
    complete song.
    """
    if not chapters:
        raise ValueError("No chapters selected.")
    planned, skip_paths = _planned(chapters, output_folder, "mkv", overwrite, skip_paths,
                                   number_filenames=number_filenames, filename_template=filename_template,
                                   metadata=metadata)

    def log(message: str) -> None:
        if progress_cb:
            progress_cb(message)

    results: list[Path] = []
    pending = []
    for item in planned:
        if item.path in skip_paths and item.path.is_file():
            log(already_done(item.chapter.index, item.chapter.title))
            results.append(item.path)
        else:
            pending.append(item)
    if not pending:
        return results

    propedit = mkvpropedit_path()
    if not Path(propedit).is_file() and shutil.which(propedit) is None:
        # Checked up front: otherwise the whole disc is read before tagging fails.
        raise Failure("tool_missing", "mkvpropedit was not found. It is part of MKVToolNix and should sit next "
                                      "to mkvmerge.", tool="mkvpropedit")
    work = output_folder / f".split-{uuid.uuid4().hex[:8]}"
    work.mkdir()

    def finalize(item: PlannedOutput, part: Path) -> None:
        ch = item.chapter
        result = tools.run([propedit, "--ui-language", "en", str(part), "--edit", "info", "--set",
                            f"title={ch.title}"], timeout=600)
        if result.returncode not in (0, 1):
            raise Failure("tool_failed", f"mkvpropedit could not tag chapter {ch.index}:\n{result.stdout}{result.stderr}",
                          detail=f"{result.stdout}{result.stderr}", tool="mkvpropedit")
        os.replace(part, item.path)
        results.append(item.path)
        if on_output_written:
            on_output_written(item.path)

    def parts_on_disk() -> list[Path]:
        return sorted(work.glob("part*.mkv"))

    # One part per pending chapter; the last chapter of a disc may have no end mark.
    ranges = []
    for item in pending:
        ch = item.chapter
        end = f"-{_mkv_timestamp(ch.end_seconds)}" if ch.end_seconds is not None else "-"
        ranges.append(f"{_mkv_timestamp(ch.start_seconds)}{end}")
    args = [TOOL_PATHS["mkvmerge"], "--ui-language", "en", "--gui-mode", "-o", str(work / "part.mkv")]
    args += ["-d", str(video_track.track_id)] if video_track is not None else ["--no-video"]
    args += ["-a", ",".join(str(t.track_id) for t in audio_tracks)]
    args += ["-s", ",".join(str(t.track_id) for t in subtitle_tracks)] if subtitle_tracks else ["--no-subtitles"]
    args += ["--no-chapters", "--no-global-tags", "--split", "parts:" + ",".join(ranges), str(source)]

    # Map mkvmerge's overall progress to the chapter being written.
    done = 0
    current: Optional[PlannedOutput] = None
    messages: list[str] = []

    def on_line(line: str) -> None:
        nonlocal done, current
        if line.startswith("#GUI#progress"):
            # mkvmerge opens part N+1 only after closing part N, so the files in the work
            # folder say exactly which chapter is being written (its percentage does not).
            parts = parts_on_disk()
            for part in parts[:-1]:            # complete: tag and move them now
                if done >= len(pending):
                    break
                finalize(pending[done], part)
                done += 1
            if parts and done < len(pending) and current is not pending[done]:
                current = pending[done]
                log(splitting(current.chapter.index, current.chapter.title))
        elif line.startswith(("#GUI#warning", "#GUI#error")):
            text = line.split(" ", 1)[-1]
            messages.append(text)
            log(f"mkvmerge: {text}")

    try:
        log(extracting(f"Extracting {len(pending)} chapter(s) directly from the disc with mkvmerge (no intermediate file)..."))
        # run_streaming stops mkvmerge before an error from on_line (a part that could not be
        # tagged or moved) gets here, so the work folder below is free to be removed.
        code = tools.run_streaming(args, on_line, cancel_event)
        if code not in (0, 1):   # 1 = finished with warnings
            raise tool_failed("mkvmerge", "\n".join(messages[-10:]))
        parts = parts_on_disk()
        remaining = pending[done:]
        if len(parts) != len(remaining):
            raise RuntimeError(f"mkvmerge wrote {len(parts) + done} file(s) for {len(pending)} chapter(s).")
        for item, part in zip(remaining, parts):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("Cancelled by user.")
            finalize(item, part)
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# M2TS: straight from the disc with the built-in engine, the streams as the disc has them
# ---------------------------------------------------------------------------

# Chapter marks are listed to the millisecond, so a mark may read up to half a millisecond off the key
# picture it sits on. Cuts are nudged by this much towards that picture: a start a little after it (the
# engine starts at the key picture at or before), a split a little before it (at or after).
CUT_SLACK = 0.0005


def chapter_runs(items: list[PlannedOutput]) -> list[list[PlannedOutput]]:
    """Planned chapters grouped into runs that follow one another without a gap: one engine pass per run."""
    runs: list[list[PlannedOutput]] = []
    for item in items:
        last = runs[-1][-1].chapter if runs else None
        if last is not None and last.end_seconds is not None and \
                abs(last.end_seconds - item.chapter.start_seconds) < 2 * CUT_SLACK:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def m2ts_meta(source: str, run: list[Chapter], *, video_tracks: list[Track], audio_tracks: list[Track],
              subtitle_tracks: list[Track], duration: float) -> list[str]:
    """The meta file of one run: its streams, where it starts and ends, and a file per chapter."""
    first, last = run[0], run[-1]
    options = ["MUXOPT", "--no-pcr-on-video-pid", "--new-audio-pes", "--vbr", "--vbv-len=500"]
    start = first.start_seconds + CUT_SLACK if first.start_seconds > CUT_SLACK else 0.0
    if start:
        options.append(f"--cut-start={engine.clock(start)}")
    if last.end_seconds is not None and (not duration or last.end_seconds < duration - CUT_SLACK):
        options.append(f"--cut-end={engine.clock(last.end_seconds)}")
    if len(run) > 1:
        marks = [start] + [ch.start_seconds - CUT_SLACK for ch in run[1:]]
        options += ["--split-chapters", "--custom-chapters=" + ";".join(engine.clock(m) for m in marks)]
    lines = [" ".join(options)]
    lines += [engine.track_line(source, t) for t in (*video_tracks, *audio_tracks, *subtitle_tracks)]
    return lines


def split_m2ts(
    source: str,
    chapters: list[Chapter],
    output_folder: Path,
    *,
    video_tracks: list[Track],
    audio_tracks: list[Track],
    subtitle_tracks: list[Track],
    duration: float,
    metadata: Optional[dict] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    overwrite: Optional[set[Path]] = None,
    cancel_event: Optional[threading.Event] = None,
    skip_paths: Optional[set[Path]] = None,
    on_output_written: Optional[Callable[[Path], None]] = None,
    number_filenames: bool = False,
    filename_template: str = "",
) -> list[Path]:
    """
    Cut the given chapters of a Blu-ray playlist into one .m2ts each, read by the engine straight from the
    disc (an image is not mounted). Video, audio and subtitles are copied as the disc has them: TrueHD keeps
    its AC-3 core, DTS-HD its extensions, PGS subtitles their pictures, and the timestamps stay those of the
    disc, so sound and picture stay in step exactly as on the disc.

    Chapters that follow one another are cut in one pass, split at the chapter marks (which sit on key
    pictures). A file is moved to its final name as soon as the engine has moved on to the next one, so a
    cancelled or failed job resumes after the last complete chapter.
    """
    if not chapters:
        raise ValueError("No chapters selected.")
    planned, skip_paths = _planned(chapters, output_folder, "m2ts", overwrite, skip_paths,
                                   number_filenames=number_filenames, filename_template=filename_template,
                                   metadata=metadata)

    def log(message: str) -> None:
        if progress_cb:
            progress_cb(message)

    results: list[Path] = []
    pending = []
    for item in planned:
        if item.path in skip_paths and item.path.is_file():
            log(already_done(item.chapter.index, item.chapter.title))
            results.append(item.path)
        else:
            pending.append(item)
    if not pending:
        return results

    engine.require()
    work = output_folder / f".split-{uuid.uuid4().hex[:8]}"
    work.mkdir()
    try:
        runs = chapter_runs(pending)
        log(extracting(f"Cutting {len(pending)} chapter(s) in {len(runs)} pass(es) straight from the disc "
                       f"with the built-in engine (no intermediate file)..."))
        for number, run in enumerate(runs, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("Cancelled by user.")
            results += _cut_run(source, run, work / f"run{number}", video_tracks=video_tracks,
                                audio_tracks=audio_tracks, subtitle_tracks=subtitle_tracks, duration=duration,
                                log=log, cancel_event=cancel_event, on_output_written=on_output_written)
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _cut_run(source: str, run: list[PlannedOutput], stem: Path, *, video_tracks, audio_tracks, subtitle_tracks,
             duration: float, log: Callable[[str], None], cancel_event, on_output_written) -> list[Path]:
    """One engine pass over chapters that follow one another; each part is moved into place once complete."""
    output = stem.with_suffix(".m2ts")
    meta = m2ts_meta(source, [item.chapter for item in run], video_tracks=video_tracks, audio_tracks=audio_tracks,
                     subtitle_tracks=subtitle_tracks, duration=duration)
    done: list[Path] = []
    announced = -1

    def parts() -> list[Path]:
        """The parts still in the work folder (finished ones are moved out), oldest first."""
        if len(run) == 1:
            return [output] if output.is_file() else []
        found = stem.parent.glob(f"{stem.name}.split.*.m2ts")
        return sorted(found, key=lambda p: int(p.name.rsplit(".", 2)[-2]))

    def finalize(item: PlannedOutput, part: Path) -> bool:
        try:
            os.replace(part, item.path)
        except PermissionError:      # still open: the engine has not closed it yet
            return False
        done.append(item.path)
        if on_output_written:
            on_output_written(item.path)
        return True

    def on_tick() -> None:
        nonlocal announced
        written = parts()
        # The engine opens part N+1 only after closing part N: every part but the newest is complete.
        while len(written) > 1 and len(done) < len(run) and finalize(run[len(done)], written[0]):
            written = written[1:]
        current = len(done)
        if current < len(run) and current != announced:
            announced = current
            log(splitting(run[current].chapter.index, run[current].chapter.title))

    engine.run_meta(meta, stem.with_suffix(".meta"), output, on_tick=on_tick, on_message=log,
                    cancel_event=cancel_event)
    remaining = parts()
    if len(remaining) != len(run) - len(done):
        raise RuntimeError(f"The engine wrote {len(remaining) + len(done)} file(s) for {len(run)} chapter(s).")
    for item, part in zip(run[len(done):], remaining):
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("Cancelled by user.")
        if not finalize(item, part):
            raise RuntimeError(f"{part.name} could not be moved to {item.path.name}.")
    return done


def mkvmerge_track_ids(source: Path, tracks: list[Track]) -> list[Track]:
    """
    The same tracks with mkvmerge's own numbers, for cutting with mkvmerge a playlist the engine read (the
    engine numbers tracks by their PID). Matched by PID, which mkvmerge reports as each track's stream_id.
    """
    if not tracks:
        return []
    result = tools.run([TOOL_PATHS["mkvmerge"], "-J", str(source)], timeout=120)
    if result.returncode >= 2:
        raise tool_failed("mkvmerge", result.stderr or result.stdout)
    by_pid = {}
    for entry in json.loads(result.stdout).get("tracks", []):
        pid = (entry.get("properties") or {}).get("stream_id")
        if pid is not None:
            by_pid[int(pid)] = entry.get("id")
    mapped = []
    for track in tracks:
        number = by_pid.get(track.stream_id or track.track_id)
        if number is None:
            raise Failure("tracks_unavailable", f"mkvmerge does not list the track with PID {track.stream_id}.")
        mapped.append(replace(track, track_id=number))
    return mapped
