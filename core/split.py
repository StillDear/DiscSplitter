"""
Cutting a source into one file per chapter.

    FLAC  ffmpeg encodes each chapter from an MKV holding the chosen audio track (extract_audio_mkv,
          or for a Blu-ray read by the engine extract_audio_engine)
    MKV   a Blu-ray read by the engine: cut by the engine as M2TS is; anything else: mkvmerge cuts every
          chapter straight from the source in one pass, nothing re-encoded
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
from .jobs import Failure, JobCancelled, already_done, chapter_progress, extracting, splitting, tool_failed
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
    marks: Optional[list[float]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> float:
    """
    One audio track of a Blu-ray playlist, from `start` to `end` only, into a Matroska audio file, read by
    the engine straight from the disc (an image is not mounted). TrueHD is kept without its AC-3 core.
    With the playlist's exact marks the disc is read from the mark at or before the start (window_for).
    Returns where the file's timeline begins on the playlist's: a playlist time t is at t - offset in it.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if progress_cb:
        progress_cb(extracting(f"Extracting audio track {audio_track.track_id} -> {output_path.name}"))
    window = window_for(source, start, end, marks, [audio_track])
    if window is not None and window[1] is not None:
        # Closed a mark further on: the sound that runs past the end mark is kept, for ffmpeg to cut to the sample
        later = [m for m in marks if m > window[1] + 0.5]
        window = (window[0], later[0] if later else None)
    if window is not None:
        try:
            return _extract_audio(source, output_path, audio_track, start, end, duration, window, progress_cb,
                                  cancel_event)
        except engine.WindowMoved as moved:
            if progress_cb:
                progress_cb(f"tsMuxeR: {moved}; reading the audio from the start of the disc instead.")
    return _extract_audio(source, output_path, audio_track, start, end, duration, None, progress_cb, cancel_event)


def _extract_audio(source: str, output_path: Path, audio_track: Track, start: float, end: Optional[float],
                   duration: float, window, progress_cb, cancel_event) -> float:
    options = ["MUXOPT", "--no-chapters"]
    origin, closing = window if window is not None else (0.0, None)
    opened = [origin]
    if window is not None:
        options.append(f"--playlist-window={origin:.6f}" + (f",{closing:.6f}" if closing is not None else ""))
    # Inside a window nothing is cut: the file starts at the mark (time 0) and runs to the mark at or after the
    # end, and ffmpeg cuts the chapters from it to the sample. A --cut-start would drop the frame of sound that
    # begins right on the cut, 5 ms of LPCM. Without a window the cut is needed to keep the file small.
    cut = 0.0
    if window is None:
        if start > CUT_SLACK:
            cut = start
            options.append(f"--cut-start={engine.clock(cut)}")
        if end is not None and (not duration or end < duration - CUT_SLACK):
            options.append(f"--cut-end={engine.clock(end)}")
    meta = [" ".join(options), engine.track_line(source, audio_track, matroska=True, drop_core=True)]

    def on_window(at: float) -> None:
        if abs(at - origin) > WINDOW_TOLERANCE:
            raise engine.WindowMoved(f"the window opened at {at:.6f} s, not at the mark at {origin:.6f} s")
        opened[0] = at                  # the file's time 0, to the tick

    partial = output_path.with_name(output_path.stem + ".partial.mka")
    partial.unlink(missing_ok=True)
    try:
        engine.run_meta(meta, output_path.with_suffix(".meta"), partial, on_message=progress_cb,
                        on_window=on_window if window is not None else None, cancel_event=cancel_event)
        os.replace(partial, output_path)
    finally:
        partial.unlink(missing_ok=True)
        output_path.with_suffix(".meta").unlink(missing_ok=True)
    return opened[0] + cut


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
    stream: str = "0:a:0",
) -> list[Path]:
    """
    Encode each supplied chapter of the extracted MKV's audio to a tagged FLAC file.

    stream: the audio to encode, as ffmpeg maps it: the first audio track of an extracted copy, or a chosen
    track of a Matroska source read as it is ("0:<track number>").

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
    stream_args = ["-map", stream, "-c:a", "flac"]
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


def _is_flac(track: Track) -> bool:
    return (track.codec_id or "").upper() == "A_FLAC" or (track.codec or "").upper() == "FLAC"


# Within this of the requested time, a key picture counts as at it (Matroska times are kept to the millisecond).
_KEY_TOLERANCE = 0.0005


def _key_picture_at_or_after(source: Path, stream: int, seconds: float) -> Optional[float]:
    """The first key picture of the stream at or after `seconds`, where mkvmerge splits; None past the last one."""
    for reach in (30, 600, None):              # a short look first: reading packets reads the file
        interval = f"{max(0.0, seconds - 1):.6f}" + (f"%+{reach}" if reach else "")
        result = tools.run([TOOL_PATHS["ffprobe"], "-v", "error", "-select_streams", str(stream), "-read_intervals",
                            interval, "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", str(source)],
                           timeout=600)
        if result.returncode != 0:
            raise tool_failed("ffprobe", result.stderr, f"looking for the key picture at {seconds:.3f}s")
        times = []
        for line in result.stdout.splitlines():
            pts, _, flags = line.partition(",")
            try:
                if "K" in flags and float(pts) >= seconds - _KEY_TOLERANCE:
                    times.append(float(pts))
            except ValueError:
                continue
        if times:
            return min(times)
    return None


def _start_time(source: Path) -> float:
    """Where the file's timeline starts: ffmpeg's -ss counts from it, Matroska and ffprobe's packet times do not."""
    result = tools.run([TOOL_PATHS["ffprobe"], "-v", "error", "-show_entries", "format=start_time", "-of",
                        "csv=p=0", str(source)], timeout=120)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _flac_cut(source: Path, track: Track, start: float, end: Optional[float], offset: float, out: Path,
              cancel_event: Optional[threading.Event]) -> Path:
    """One FLAC track from start to end (source times), decoded and encoded again: FLAC is lossless, so the samples
    are the source's own, cut to the sample (mkvmerge cannot split a FLAC track)."""
    args = [TOOL_PATHS["ffmpeg"], "-v", "error", "-y", "-ss", f"{max(0.0, start - offset):.6f}", "-i", str(source)]
    if end is not None:
        args += ["-t", f"{end - start:.6f}"]
    args += ["-map", f"0:{track.track_id}", "-c:a", "flac", "-map_metadata", "-1", "-map_chapters", "-1", str(out)]
    result = tools.run(args, timeout=1800, cancel_event=cancel_event)
    if result.returncode != 0 or not out.is_file():
        raise tool_failed("ffmpeg", result.stderr, f"cutting FLAC track {track.track_id}")
    return out


def _track_options(track: Track) -> list[str]:
    """mkvmerge options giving a FLAC track cut on its own the properties it has in the source."""
    props = track.properties or {}
    options = ["--default-track-flag", f"0:{1 if track.default_track else 0}",
               "--forced-display-flag", f"0:{1 if props.get('forced_track') else 0}"]
    if track.language:
        options += ["--language", f"0:{track.language}"]
    if track.title:
        options += ["--track-name", f"0:{track.title}"]
    return options


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
    slack: float = 0.0,
    duration: Optional[float] = None,
) -> list[Path]:
    """
    slack: how far before each chapter time to cut (see CUT_SLACK), for chapter times that may sit a hair after
    their key picture (marks listed by the engine); mkvmerge's own chapters need none.
    duration: the source's length, to tell how far into each chapter the cut is (ChapterMeter).

    Cut the given chapters out of a playlist / MKV in ONE mkvmerge pass, with
    no intermediate copy of the disc. Cuts land exactly on the chapter marks
    (Blu-ray chapters sit on keyframes), every file starts on a keyframe and
    nothing is re-encoded. Each file's title is set afterwards with
    mkvpropedit; video files carry no album tags or cover (metadata is only
    used for file names).

    FLAC tracks, which mkvmerge cannot split, are cut by ffmpeg over the span mkvmerge gave each part and
    added to it (the samples are the source's own: FLAC is lossless).

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
    # One part per pending chapter; the last chapter of a disc may have no end mark.
    spans: list[tuple[float, Optional[float]]] = []
    for item in pending:
        ch = item.chapter
        spans.append((ch.start_seconds - slack if ch.start_seconds > slack else 0.0,
                      ch.end_seconds - slack if ch.end_seconds is not None else None))

    # mkvmerge cannot split a FLAC track: those are cut by ffmpeg over the span mkvmerge gave each part (from the
    # key picture at or after the chapter's start to the one at or after its end) and added to the part.
    flac = sorted((t for t in audio_tracks if _is_flac(t)), key=lambda t: t.track_id)
    audio_tracks = [t for t in audio_tracks if not _is_flac(t)]
    flac_spans: list[tuple[float, Optional[float]]] = []
    offset = 0.0
    if flac:
        offset = _start_time(source)
        for start, end in spans:
            if video_track is not None:
                start = _key_picture_at_or_after(source, video_track.track_id, start) or start
                end = _key_picture_at_or_after(source, video_track.track_id, end) if end is not None else None
            flac_spans.append((start, end))
    work = output_folder / f".split-{uuid.uuid4().hex[:8]}"
    work.mkdir()

    def with_flac(item: PlannedOutput, part: Optional[Path]) -> Path:
        """The part with its FLAC tracks added, in the source's track order (part None: there is nothing else)."""
        number = pending.index(item)
        start, end = flac_spans[number]
        if part is not None and video_track is not None and end is not None:
            length = probe_duration_seconds(part)
            if abs(length - (end - start)) > 0.25:      # the split did not land where it was looked for
                raise RuntimeError(f"mkvmerge cut chapter {item.chapter.index} to {length:.3f}s, but its FLAC "
                                   f"tracks would be {end - start:.3f}s long.")
        made: list[Path] = []
        if part is None and subtitle_tracks:
            # Nothing for mkvmerge to split by: the subtitles are copied over the same span by ffmpeg.
            part = work / f"subs-{number:03d}.mks"
            args = [TOOL_PATHS["ffmpeg"], "-v", "error", "-y", "-ss", f"{max(0.0, start - offset):.6f}",
                    "-i", str(source)]
            args += ["-t", f"{end - start:.6f}"] if end is not None else []
            for t in subtitle_tracks:
                args += ["-map", f"0:{t.track_id}"]
            args += ["-c", "copy", "-map_metadata:g", "-1", "-map_chapters", "-1", "-f", "matroska", str(part)]
            result = tools.run(args, timeout=1800, cancel_event=cancel_event)
            if result.returncode != 0 or not part.is_file():
                raise tool_failed("ffmpeg", result.stderr, f"cutting the subtitles of chapter {item.chapter.index}")
            kept = sorted(subtitle_tracks, key=lambda t: t.track_id)
        elif part is not None:
            kept = sorted([*([video_track] if video_track is not None else []), *audio_tracks, *subtitle_tracks],
                          key=lambda t: t.track_id)
        else:
            kept = []
        made += [_flac_cut(source, t, start, end, offset, work / f"flac-{number:03d}-{i}.mka", cancel_event)
                 for i, t in enumerate(flac)]
        first = 1 if part is not None else 0
        files = {t.track_id: f"0:{i}" for i, t in enumerate(kept)}
        files.update({t.track_id: f"{first + i}:0" for i, t in enumerate(flac)})
        merged = work / f"full-{number:03d}.mkv"
        args = [TOOL_PATHS["mkvmerge"], "--ui-language", "en", "-q", "-o", str(merged)]
        if part is not None:
            args.append(str(part))
        for t, cut in zip(flac, made):
            args += [*_track_options(t), str(cut)]
        args += ["--track-order", ",".join(files[k] for k in sorted(files))]
        result = tools.run(args, timeout=1800, cancel_event=cancel_event)
        if result.returncode not in (0, 1):
            raise tool_failed("mkvmerge", f"{result.stdout}{result.stderr}", f"adding the FLAC tracks of chapter "
                                                                              f"{item.chapter.index}")
        for path in (part, *made):
            if path is not None:
                path.unlink(missing_ok=True)
        return merged

    def finalize(item: PlannedOutput, part: Optional[Path]) -> None:
        ch = item.chapter
        if flac:
            part = with_flac(item, part)
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

    if video_track is None and not audio_tracks:
        # Only FLAC sound (and maybe subtitles): nothing for mkvmerge to split, ffmpeg cuts each chapter.
        try:
            log(extracting(f"Cutting {len(pending)} chapter(s) from the file..."))
            for item in pending:
                if cancel_event is not None and cancel_event.is_set():
                    raise JobCancelled("Cancelled by user.")
                log(splitting(item.chapter.index, item.chapter.title))
                finalize(item, None)
            return results
        finally:
            shutil.rmtree(work, ignore_errors=True)

    ranges = [f"{_mkv_timestamp(start)}-{_mkv_timestamp(end) if end is not None else ''}" for start, end in spans]
    args = [TOOL_PATHS["mkvmerge"], "--ui-language", "en", "--gui-mode", "-o", str(work / "part.mkv")]
    args += ["-d", str(video_track.track_id)] if video_track is not None else ["--no-video"]
    args += ["-a", ",".join(str(t.track_id) for t in audio_tracks)] if audio_tracks else ["--no-audio"]
    args += ["-s", ",".join(str(t.track_id) for t in subtitle_tracks)] if subtitle_tracks else ["--no-subtitles"]
    args += ["--no-chapters", "--no-global-tags", "--split", "parts:" + ",".join(ranges), str(source)]

    # Map mkvmerge's overall progress to the chapter being written.
    done = 0
    current: Optional[PlannedOutput] = None
    messages: list[str] = []
    meter = ChapterMeter(duration, log)

    def on_line(line: str) -> None:
        nonlocal done, current
        if line.startswith("#GUI#progress"):
            # mkvmerge opens part N+1 only after closing part N, so the files in the work
            # folder say which chapter is being written; its percentage says how far into it.
            parts = parts_on_disk()
            for part in parts[:-1]:            # complete: tag and move them now
                if done >= len(pending):
                    break
                finalize(pending[done], part)
                done += 1
            if done < len(pending) and current is not pending[done]:
                current = pending[done]
                log(splitting(current.chapter.index, current.chapter.title))
                meter.begin(current.chapter)
            try:
                meter.update(float(line.split()[-1].rstrip("%")))
            except ValueError:
                pass
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

# A chapter mark may sit a hair off the key picture it belongs to: by up to half a millisecond when the engine
# lists marks only to the millisecond, and even in its 45 kHz ticks (Playlist.marks_exact) by one tick of the
# picture's 90 kHz clock. Cuts are nudged by this much towards that picture: a start a little after it (the engine
# starts at the key picture at or before), a split a little before it (the engine and mkvmerge split at the key
# picture at or after). Sound and subtitles are cut at the time itself, so the smaller the nudge, the closer they
# start to the picture: with exact marks, within a 48 kHz sample and a half.
CUT_SLACK = 0.0005
EXACT_CUT_SLACK = 0.00003

# Reaching a chapter costs the engine a read of the disc from its start, twice (to find the key picture, then to
# mux). Chapters a short way apart are therefore cut in one pass, the footage between them written and thrown
# away; a longer gap starts a pass of its own instead, so a gap never needs much free space.
MAX_GAP_SECONDS = 20 * 60


def cut_slack(playlist: Optional[Playlist]) -> float:
    return EXACT_CUT_SLACK if playlist is not None and playlist.marks_exact else CUT_SLACK


# One piece of a pass: (the planned chapter, its span), or (None, span) for a gap that is cut and thrown away.
Piece = tuple


def cut_passes(items: list[PlannedOutput], *, slack: float = CUT_SLACK,
               max_gap: float = MAX_GAP_SECONDS) -> list[list[Piece]]:
    """
    Planned chapters grouped into engine passes. Chapters that follow one another share a pass; so do chapters
    with a gap of up to max_gap between them, the gap cut as a piece of its own and thrown away.
    """
    passes: list[list[Piece]] = []
    for item in items:
        ch = item.chapter
        last = passes[-1][-1][1] if passes else None
        if last is not None and last.end_seconds is not None:
            gap = ch.start_seconds - last.end_seconds
            if abs(gap) < 2 * slack:
                passes[-1].append((item, ch))
                continue
            if 0 < gap <= max_gap:
                passes[-1] += [(None, Chapter(0, last.end_seconds, ch.start_seconds)), (item, ch)]
                continue
        passes.append([(item, ch)])
    return passes


WINDOW_TOLERANCE = 0.001     # how far the engine may open a window from the mark it was asked for (a tick or two)


def window_for(source: str, start: float, end: Optional[float], marks: Optional[list[float]],
               tracks: list[Track], slack: float = CUT_SLACK) -> Optional[tuple[float, Optional[float]]]:
    """
    Where to open a --playlist-window for a cut from start to end, so the engine reads the disc from there (by the
    clip's entry point map) rather than from its start: at the last chapter mark at or before the start (a key
    picture, whose exact time the times of the cut are counted from), to the first mark at or after the end. None
    where there is nothing to gain or it cannot be done: a cut from the start, no exact marks, a source that is no
    playlist, or a track the playlist plays from a sub path (TextST subtitles, secondary audio).
    """
    if not marks or not source.lower().endswith(".mpls"):
        return None
    if any((t.properties or {}).get(k) for t in tracks for k in ("stream_file", "secondary", "sub_track")):
        return None
    opening = max((m for m in marks if m <= start + slack), default=0.0)
    if opening <= slack:
        return None
    closing = None
    if end is not None:
        closing = min((m for m in marks if m >= end - slack), default=None)
    return opening, closing


def engine_meta(source: str, run: list[Chapter], *, video_tracks: list[Track], audio_tracks: list[Track],
                subtitle_tracks: list[Track], duration: float, slack: float = CUT_SLACK,
                container: str = "m2ts", window: Optional[tuple[float, Optional[float]]] = None) -> list[str]:
    """
    The meta file of one pass: its streams, where it starts and ends, and a file per piece. With a window
    (window_for), the playlist is narrowed to it and every time is counted from its opening.
    """
    first, last = run[0], run[-1]
    if container == "mkv":
        # Every part gets the placeholder title, written over with its own (tagging.set_matroska_title).
        options = ["MUXOPT", "--no-chapters", f"--title={tagging.TITLE_PLACEHOLDER}"]
    else:
        options = ["MUXOPT", "--no-pcr-on-video-pid", "--new-audio-pes", "--vbr", "--vbv-len=500"]
    origin, closing = 0.0, None
    if window is not None:
        origin, closing = window
        options.append(f"--playlist-window={origin:.6f}" + (f",{closing:.6f}" if closing is not None else ""))
    first_start = first.start_seconds - origin
    start = first_start + slack if first_start > slack else 0.0
    if start:
        options.append(f"--cut-start={engine.clock(start)}")
    if last.end_seconds is not None:
        stop = closing if closing is not None else duration
        if not stop or last.end_seconds < stop - slack:
            options.append(f"--cut-end={engine.clock(last.end_seconds - origin)}")
    if len(run) > 1:
        marks = [start] + [ch.start_seconds - origin - slack for ch in run[1:]]
        options += ["--split-chapters", "--custom-chapters=" + ";".join(engine.clock(m) for m in marks)]
    lines = [" ".join(options)]
    lines += [engine.track_line(source, t, matroska=container == "mkv")
              for t in (*video_tracks, *audio_tracks, *subtitle_tracks)]
    return lines


m2ts_meta = engine_meta


class ChapterMeter:
    """
    How far into the chapter being written a pass is. The engine says the time it has reached (at(): on the
    source's timeline, from the window's opening when there is one); mkvmerge only a percentage of the bytes it
    has read of its source (update()), which reads from the source's start, so a percentage is a place on the
    timeline near enough (bytes are not spread evenly over time). A time, once given, is used from then on.
    """

    def __init__(self, duration: Optional[float], log: Callable[[str], None]):
        self.duration = duration or 0.0
        self.log = log
        self.chapter: Optional[Chapter] = None
        self.shown = 0.0
        self.origin = 0.0
        self.timed = False

    def begin(self, chapter: Optional[Chapter]) -> None:
        self.chapter, self.shown = chapter, 0.0

    def update(self, percent: float) -> None:
        if not self.timed and self.duration > 0:
            self._place(percent / 100 * self.duration)

    def at(self, seconds: float) -> None:
        self.timed = True
        self._place(self.origin + seconds)

    def _place(self, position: float) -> None:
        ch = self.chapter
        if ch is None:
            return
        end = ch.end_seconds if ch.end_seconds is not None else self.duration
        if not end or end <= ch.start_seconds:
            return
        fraction = (position - ch.start_seconds) / (end - ch.start_seconds)
        fraction = min(0.99, max(0.0, fraction))        # done is said by the file being in place
        if fraction >= self.shown + 0.01:
            self.shown = fraction
            self.log(chapter_progress(ch.index, fraction))


def split_with_engine(
    source: str,
    chapters: list[Chapter],
    output_folder: Path,
    *,
    video_tracks: list[Track],
    audio_tracks: list[Track],
    subtitle_tracks: list[Track],
    duration: float,
    slack: float = CUT_SLACK,
    marks: Optional[list[float]] = None,
    metadata: Optional[dict] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    overwrite: Optional[set[Path]] = None,
    cancel_event: Optional[threading.Event] = None,
    skip_paths: Optional[set[Path]] = None,
    on_output_written: Optional[Callable[[Path], None]] = None,
    number_filenames: bool = False,
    filename_template: str = "",
    container: str = "m2ts",
) -> list[Path]:
    """
    Cut the given chapters of a Blu-ray playlist into one file each, read by the engine straight from the disc
    (an image is not mounted), nothing re-encoded.

    m2ts: video, audio and subtitles as the disc has them: TrueHD keeps its AC-3 core, DTS-HD its extensions,
          PGS subtitles their pictures, and the timestamps stay those of the disc.
    mkv:  the same streams in Matroska, each file titled with its song (no chapters, no attachments), as
          mkvmerge made them before; no MKVToolNix needed.

    Chapters near one another are cut in one pass (cut_passes), split at the chapter marks (which sit on key
    pictures). With the playlist's exact marks, each pass reads the disc from the mark it starts at (window_for)
    instead of from the start of the disc. A file is moved to its final name as soon as the engine has moved on to
    the next one, so a cancelled or failed job resumes after the last complete chapter.
    """
    if not chapters:
        raise ValueError("No chapters selected.")
    planned, skip_paths = _planned(chapters, output_folder, container, overwrite, skip_paths,
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
    meter = ChapterMeter(duration, log)
    try:
        passes = cut_passes(pending, slack=slack)
        log(extracting(f"Cutting {len(pending)} chapter(s) in {len(passes)} pass(es) straight from the disc "
                       f"with the built-in engine (no intermediate file)..."))
        for number, pieces in enumerate(passes, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("Cancelled by user.")
            results += _cut_pass(source, pieces, work / f"pass{number}", video_tracks=video_tracks,
                                 audio_tracks=audio_tracks, subtitle_tracks=subtitle_tracks, duration=duration,
                                 slack=slack, log=log, meter=meter, cancel_event=cancel_event,
                                 on_output_written=on_output_written, container=container, marks=marks)
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


def split_m2ts(source: str, chapters: list[Chapter], output_folder: Path, **options) -> list[Path]:
    return split_with_engine(source, chapters, output_folder, container="m2ts", **options)


def _cut_pass(source: str, pieces: list[Piece], stem: Path, *, video_tracks, audio_tracks, subtitle_tracks,
              duration: float, slack: float, log: Callable[[str], None], meter: ChapterMeter, cancel_event,
              on_output_written, container: str = "m2ts", marks: Optional[list[float]] = None) -> list[Path]:
    """
    One engine pass; each piece is moved into place (a gap: removed) once complete. A pass opened at a chapter mark
    (window_for) that the engine opens elsewhere is stopped at once and run again from the start of the disc.
    """
    spans = [ch for _, ch in pieces]
    window = window_for(source, spans[0].start_seconds, spans[-1].end_seconds, marks,
                        [*video_tracks, *audio_tracks, *subtitle_tracks], slack)
    if window is not None:
        try:
            return _run_pass(source, pieces, stem, window, video_tracks=video_tracks, audio_tracks=audio_tracks,
                             subtitle_tracks=subtitle_tracks, duration=duration, slack=slack, log=log, meter=meter,
                             cancel_event=cancel_event, on_output_written=on_output_written, container=container)
        except engine.WindowMoved as moved:
            log(f"tsMuxeR: {moved}; reading this pass from the start of the disc instead.")
            for leftover in stem.parent.glob(f"{stem.name}*"):
                leftover.unlink(missing_ok=True)
    return _run_pass(source, pieces, stem, None, video_tracks=video_tracks, audio_tracks=audio_tracks,
                     subtitle_tracks=subtitle_tracks, duration=duration, slack=slack, log=log, meter=meter,
                     cancel_event=cancel_event, on_output_written=on_output_written, container=container)


def _run_pass(source: str, pieces: list[Piece], stem: Path, window, *, video_tracks, audio_tracks, subtitle_tracks,
              duration: float, slack: float, log: Callable[[str], None], meter: ChapterMeter, cancel_event,
              on_output_written, container: str) -> list[Path]:
    output = stem.with_suffix(f".{container}")
    meta = engine_meta(source, [ch for _, ch in pieces], video_tracks=video_tracks, audio_tracks=audio_tracks,
                       subtitle_tracks=subtitle_tracks, duration=duration, slack=slack, container=container,
                       window=window)
    meter.origin = window[0] if window is not None else 0.0

    def opened(at: float) -> None:
        if window is not None and abs(at - window[0]) > WINDOW_TOLERANCE:
            raise engine.WindowMoved(f"the window opened at {at:.6f} s, not at the mark at {window[0]:.6f} s")

    written: list[Path] = []
    settled = 0                 # pieces finished: moved into place, or thrown away
    announced: Optional[PlannedOutput] = None

    def parts() -> list[Path]:
        """The parts still in the work folder (finished ones are moved out), oldest first."""
        if len(pieces) == 1:
            return [output] if output.is_file() else []
        found = stem.parent.glob(f"{stem.name}.split.*.{container}")
        return sorted(found, key=lambda p: int(p.name.rsplit(".", 2)[-2]))

    def settle(piece: Piece, part: Path) -> bool:
        nonlocal settled
        item = piece[0]
        try:
            if item is None:
                part.unlink()
            else:
                if container == "mkv":
                    tagging.set_matroska_title(part, item.chapter.title)
                    tagging.blank_matroska_elements(part)
                os.replace(part, item.path)
        except PermissionError:      # still open: the engine has not closed it yet
            return False
        settled += 1
        if item is not None:
            written.append(item.path)
            if on_output_written:
                on_output_written(item.path)
        return True

    def announce() -> None:
        nonlocal announced
        # Through a gap, the chapter after it is the one being worked towards.
        upcoming = next((item for item, _ in pieces[settled:] if item is not None), None)
        if upcoming is not None and upcoming is not announced:
            announced = upcoming
            log(splitting(upcoming.chapter.index, upcoming.chapter.title))
            meter.begin(upcoming.chapter)

    def on_tick() -> None:
        found = parts()
        # The engine opens part N+1 only after closing part N: every part but the newest is complete.
        while len(found) > 1 and settled < len(pieces) and settle(pieces[settled], found[0]):
            found = found[1:]
        announce()

    announce()
    engine.run_meta(meta, stem.with_suffix(".meta"), output, on_tick=on_tick, on_progress=meter.update,
                    on_position=meter.at, on_window=opened, on_message=log, cancel_event=cancel_event)
    remaining = parts()
    if len(remaining) != len(pieces) - settled:
        raise RuntimeError(f"The engine wrote {len(remaining) + settled} file(s) for {len(pieces)} piece(s).")
    for piece, part in zip(pieces[settled:], remaining):
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("Cancelled by user.")
        if not settle(piece, part):
            raise RuntimeError(f"{part.name} could not be moved to its place.")
    return written
