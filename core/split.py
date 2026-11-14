"""Cutting a source into one file per chapter: the ffmpeg path (via an extracted MKV) and the direct mkvmerge path."""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

import tagging

from . import dvd
from . import tools
from .jobs import JobCancelled, already_done, extracting, splitting
from .models import Chapter, Playlist, Track
from .naming import OutputCollisionError, plan_output_files
from .tools import TOOL_PATHS, mkvpropedit_path, probe_duration_seconds


# ---------------------------------------------------------------------------
# Extraction: playlist -> standalone MKV with selected tracks and chapters
# ---------------------------------------------------------------------------

def extract_audio_mkv(
    playlist: Playlist,
    output_path: Path,
    audio_track: Track,
    progress_cb: Optional[Callable[[str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    *,
    audio_tracks: Optional[list[Track]] = None,
    subtitle_tracks: Optional[list[Track]] = None,
    keep_video: bool = True,
) -> Path:
    """Remux the selected streams with the source chapters."""
    audio_tracks = [audio_track] if audio_tracks is None else audio_tracks
    subtitle_tracks = subtitle_tracks or []
    if not audio_tracks or any(t.kind != "audio" for t in audio_tracks):
        raise ValueError("Select at least one valid audio track.")
    if any(t.kind != "subtitles" for t in subtitle_tracks):
        raise ValueError("Select valid subtitle tracks.")

    video_track = playlist.video_track if keep_video else None
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if dvd.is_title(playlist.path):
        return dvd.remux(playlist.path, output_path, tracks=[*filter(None, [video_track]), *audio_tracks,
                                                              *subtitle_tracks],
                         progress_cb=progress_cb, cancel_event=cancel_event)

    args = [TOOL_PATHS["mkvmerge"], "-o", str(output_path)]

    if video_track is not None:
        args += ["-d", str(video_track.track_id)]
    else:
        args += ["--no-video"]

    args += ["-a", ",".join(str(t.track_id) for t in audio_tracks)]
    args += (["-s", ",".join(str(t.track_id) for t in subtitle_tracks)]
             if subtitle_tracks else ["--no-subtitles"])
    args.append(str(playlist.path))

    if progress_cb:
        target = f"video track {video_track.track_id} + " if video_track else ""
        audio_ids = ", ".join(str(t.track_id) for t in audio_tracks)
        progress_cb(extracting(f"Extracting {target}audio tracks {audio_ids} + "
                                f"{len(subtitle_tracks)} subtitle tracks -> {output_path.name}"))

    result = tools.run(args, timeout=7200, cancel_event=cancel_event)  # 2 hours - full-disc extraction can be slow
    if result.returncode != 0:
        raise RuntimeError(f"mkvmerge failed:\n{result.stdout}\n{result.stderr}")

    return output_path


def split_chapters(
    audio_mkv: Path,
    chapters: list[Chapter],
    output_folder: Path,
    container: str = "mkv",
    progress_cb: Optional[Callable[[str], None]] = None,
    overwrite: Optional[set[Path]] = None,
    cancel_event: Optional[threading.Event] = None,
    skip_paths: Optional[set[Path]] = None,
    on_output_written: Optional[Callable[[Path], None]] = None,
    metadata: Optional[dict] = None,
    *,
    source_chapter_count: Optional[int] = None,
    audio_tracks: Optional[list[Track]] = None,
    subtitle_tracks: Optional[list[Track]] = None,
    keep_video: bool = True,
    number_filenames: bool = False,
    renumber_tracks: bool = True,
    filename_template: str = "",
) -> list[Path]:
    """
    Split the extracted MKV into one file per supplied chapter.
    FLAC encodes the first audio stream. MKV stream-copies the selected streams.

    overwrite: set of specific output paths the caller has already gotten
    user approval to overwrite (normally via preflight_check() plus a
    confirmation dialog). Any planned path that already exists and isn't
    in this set raises OutputCollisionError instead of overwriting it -
    ffmpeg's own -y flag is never allowed to make that decision silently.

    cancel_event: checked before each chapter and passed down into the
    ffmpeg call itself, so cancelling actually stops the in-progress
    chapter rather than only stopping between chapters.

    skip_paths: output paths already known-complete from a previous run
    of this same job (see run_full_pipeline's resume support) - these are
    left untouched and reported as already done, rather than re-split.

    on_output_written: called with each output path immediately after
    it's finalised, so a caller can persist progress (e.g. to the job
    manifest) incrementally instead of only at the very end.
    """
    if not chapters:
        raise ValueError(
            "No chapters found - this playlist has no chapter markers, "
            "so it can't be split into individual songs."
        )

    output_folder.mkdir(parents=True, exist_ok=True)

    # Check for collisions before the (comparatively expensive) duration
    # probe below, so a caller that skipped preflight_check still fails
    # fast instead of waiting on ffprobe first.
    planned = plan_output_files(chapters, output_folder, container=container, number_filenames=number_filenames,
                                filename_template=filename_template, metadata=metadata)
    overwrite = overwrite or set()
    skip_paths = skip_paths or set()
    colliding = [
        p for p in planned if p.exists and p.path not in overwrite and p.path not in skip_paths
    ]
    if colliding:
        raise OutputCollisionError(colliding)

    if chapters[-1].end_seconds is None:
        chapters[-1].end_seconds = probe_duration_seconds(audio_mkv)

    flac = container.lower() == "flac"
    cover = tagging.embedded_cover(metadata) if flac else None
    stream_args = []
    if flac:
        stream_args += ["-map", "0:a:0", "-c:a", "flac"]
        if cover is not None:
            stream_args += ["-map", "1:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    elif container.lower() == "mkv":
        stream_args += ["-map", "0:V?", "-map", "0:a?", "-map", "0:s?",
                        "-default_mode", "passthrough"]
        audio_override = (metadata or {}).get("audio") or {}
        for specifier, tracks in (("a", audio_tracks), ("s", subtitle_tracks)):
            for i, track in enumerate(tracks or []):
                if track.default_track is not None and not (specifier == "a" and i == 0 and "default" in audio_override):
                    flag = "+default" if track.default_track else "-default"
                    stream_args += [f"-disposition:{specifier}:{i}", flag]

    output_paths: list[Path] = []
    track_total = len(planned) if renumber_tracks else source_chapter_count or len(chapters)

    for track_number, item in enumerate(planned, start=1):
        ch = item.chapter
        out_path = item.path
        track_name = ch.name or f"Track {ch.index:02d}"

        if out_path in skip_paths and out_path.is_file():
            if progress_cb:
                progress_cb(already_done(ch.index, track_name))
            output_paths.append(out_path)
            continue

        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled("Cancelled by user.")

        # Write to a temp file in the same folder (so the final rename is
        # on the same filesystem and therefore atomic) and only move it to
        # the real name once ffmpeg has produced a non-empty file. A crash,
        # Ctrl+C, or killed process mid-chapter then leaves a stray
        # ".partial-*" file instead of a truncated file sitting at the
        # real track name looking like a finished, playable song.
        tmp_path = out_path.with_name(f".partial-{uuid.uuid4().hex}-{out_path.name}")

        # -ss before -i does a fast keyframe seek in the input instead of
        # decoding from the start of the file on every single chapter
        # (which is what -ss after -i would do). Since we're stream-copying,
        # the cut still snaps to the nearest keyframe either way - you can't
        # cut mid-GOP without re-encoding - so accuracy is the same, but this
        # is dramatically faster, especially for later chapters in a long file.
        args = [
            TOOL_PATHS["ffmpeg"],
            "-y",  # only ever overwrites our own freshly-named temp file
            "-ss", str(ch.start_seconds),
            "-i", str(audio_mkv),
        ]
        if cover is not None:
            args += ["-i", str(cover)]
        if not keep_video and not flac:
            # Input seeking can land on an earlier MKV cluster. Drop the
            # audio-only preroll before the requested chapter boundary.
            args += ["-ss", "0"]
        if ch.end_seconds is not None:
            # -to is relative to the original input timeline when placed
            # after -i, but ffmpeg re-bases it to the seek point when -ss
            # comes before -i - so we need the chapter's duration, not its
            # absolute end time, to get the correct cut point.
            args += ["-t", str(ch.end_seconds - ch.start_seconds)]
        args += stream_args
        if not flac:
            args += ["-c", "copy"]
        args += tagging.chapter_args(metadata, ch.index, track_total, track_name, container=container.lower(),
                                     track_number=track_number if renumber_tracks else None)
        args += [str(tmp_path)]

        if progress_cb:
            progress_cb(splitting(ch.index, track_name))

        try:
            # 30 min per chapter - stream-copy is fast, this is just a safety net
            result = tools.run(args, timeout=1800, cancel_event=cancel_event)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed on chapter {ch.index}:\n{result.stderr}")
            if not tmp_path.is_file() or tmp_path.stat().st_size == 0:
                raise RuntimeError(
                    f"ffmpeg reported success on chapter {ch.index} ({track_name}) "
                    f"but produced no output file, or an empty one."
                )
            os.replace(tmp_path, out_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        output_paths.append(out_path)
        if on_output_written:
            on_output_written(out_path)

    return output_paths


# ---------------------------------------------------------------------------
# Lossless MKV export straight from the disc (mkvmerge chapter split)
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
    source_chapter_count: Optional[int] = None,
    number_filenames: bool = False,
    renumber_tracks: bool = True,
    filename_template: str = "",
    embed_metadata: bool = True,
) -> list[Path]:
    """
    Cut the given chapters out of a playlist / MKV in ONE mkvmerge pass, with
    no intermediate copy of the disc. Cuts land exactly on the chapter marks
    (Blu-ray chapters sit on keyframes), every file starts on a keyframe and
    nothing is re-encoded. Each file's title is set afterwards with
    mkvpropedit; with embed_metadata, album tags, the cover and the audio
    track's name/language are written too (metadata is still used for file
    names either way).

    Finished parts are moved into place as soon as mkvmerge has moved on to
    the next one, so a cancelled or failed job resumes after the last
    complete song.
    """
    if not chapters:
        raise ValueError("No chapters selected.")
    output_folder.mkdir(parents=True, exist_ok=True)
    planned = plan_output_files(chapters, output_folder, container="mkv", number_filenames=number_filenames,
                                filename_template=filename_template, metadata=metadata)
    overwrite, skip_paths = overwrite or set(), skip_paths or set()
    colliding = [p for p in planned if p.exists and p.path not in overwrite and p.path not in skip_paths]
    if colliding:
        raise OutputCollisionError(colliding)

    def log(message: str) -> None:
        if progress_cb:
            progress_cb(message)

    track_total = len(planned) if renumber_tracks else source_chapter_count or len(chapters)
    numbers = {id(item): n for n, item in enumerate(planned, start=1)}
    results: list[Path] = []
    pending = []
    for item in planned:
        name = item.chapter.name or f"Track {item.chapter.index:02d}"
        if item.path in skip_paths and item.path.is_file():
            log(already_done(item.chapter.index, name))
            results.append(item.path)
        else:
            pending.append(item)
    if not pending:
        return results

    propedit = mkvpropedit_path()
    if not Path(propedit).is_file() and shutil.which(propedit) is None:
        # Checked up front: otherwise the whole disc is read before tagging fails.
        raise RuntimeError("mkvpropedit was not found. It is part of MKVToolNix and should sit next to mkvmerge.")
    work = output_folder / f".dts-split-{uuid.uuid4().hex[:8]}"
    work.mkdir()

    def finalize(item: "PlannedOutput", part: Path) -> None:
        ch = item.chapter
        title = ch.name or f"Track {ch.index:02d}"
        command = [propedit, "--ui-language", "en", str(part), "--edit", "info", "--set", f"title={title}"]
        if embed_metadata:
            tags = work / f"tags-{ch.index}.xml"
            tags.write_text(tagging.tags_xml(tagging.file_tags(
                metadata, ch.index, track_total, title, numbers[id(item)] if renumber_tracks else None)),
                encoding="utf-8")
            command += ["--tags", f"global:{tags}"]
        result = tools.run(command, timeout=600)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"mkvpropedit could not tag chapter {ch.index}:\n{result.stdout}{result.stderr}")
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
    audio_meta = ((metadata or {}).get("audio") or {}) if embed_metadata else {}
    if audio_tracks and audio_meta:
        first = audio_tracks[0].track_id
        if tagging._clean(audio_meta.get("title")):
            args += ["--track-name", f"{first}:{tagging._clean(audio_meta['title'])}"]
        if tagging._clean(audio_meta.get("language")):
            args += ["--language", f"{first}:{tagging._clean(audio_meta['language'])}"]
        if "default" in audio_meta:
            args += ["--default-track-flag", f"{first}:{1 if audio_meta.get('default') else 0}"]
    cover = tagging.embedded_cover(metadata) if embed_metadata else None
    if cover is not None:
        args += ["--attachment-mime-type", tagging.COVER_TYPES[cover.suffix.lower()],
                 "--attachment-name", f"cover{cover.suffix.lower()}", "--attach-file", str(cover)]
    args += ["--no-chapters", "--no-global-tags", "--split", "parts:" + ",".join(ranges), str(source)]

    # Map mkvmerge's overall progress to the chapter being written.
    current = {"item": None, "done": 0}
    messages: list[str] = []

    def on_line(line: str) -> None:
        if line.startswith("#GUI#progress"):
            # mkvmerge opens part N+1 only after closing part N, so the files in the work
            # folder say exactly which chapter is being written (its percentage does not).
            parts = parts_on_disk()
            for part in parts[:-1]:            # complete: tag and move them now
                if current["done"] >= len(pending):
                    break
                finalize(pending[current["done"]], part)
                current["done"] += 1
            if parts and current["done"] < len(pending) and current["item"] is not pending[current["done"]]:
                item = current["item"] = pending[current["done"]]
                ch = item.chapter
                log(splitting(ch.index, ch.name or f"Track {ch.index:02d}"))
        elif line.startswith(("#GUI#warning", "#GUI#error")):
            text = line.split(" ", 1)[-1]
            messages.append(text)
            log(f"mkvmerge: {text}")

    try:
        log(extracting(f"Extracting {len(pending)} chapter(s) directly from the disc with mkvmerge (no intermediate file)..."))
        code = tools.run_streaming(args, on_line, cancel_event)
        if code not in (0, 1):   # 1 = finished with warnings
            raise RuntimeError("mkvmerge failed:\n" + "\n".join(messages[-10:]))
        parts = parts_on_disk()
        remaining = pending[current["done"]:]
        if len(parts) != len(remaining):
            raise RuntimeError(f"mkvmerge wrote {len(parts) + current['done']} file(s) for {len(pending)} chapter(s).")
        for item, part in zip(remaining, parts):
            if cancel_event is not None and cancel_event.is_set():
                raise JobCancelled("Cancelled by user.")
            finalize(item, part)
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)
