"""
The whole export in one call: checkpointed, resumable and cancellable.

Both routes share one skeleton (checkpoint, chapters, resume, status, cleanup); they differ only in
the file the songs are cut from and the tool that cuts it:

    MKV   cut straight from the disc in one mkvmerge pass (a DVD title is first copied to one MKV)
    FLAC  extract the chosen audio to one MKV first, then encode each chapter with ffmpeg
"""

from __future__ import annotations

import contextlib
import dataclasses
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

import tagging

from . import bluray_iso, chapter_marks, dvd, split, tools
from .chapter_marks import apply_chapter_layout
from .jobs import JobCancelled, ProgressEvent, cleaning_up, job_cancelled, job_failed
from .manifest import JobManifest, read_manifest, write_manifest
from .models import Chapter, Playlist, Track
from .naming import FILENAME_TEMPLATES


def run_full_pipeline(
    playlist: Playlist,
    audio_track: Track,
    track_names: dict[int, str],
    work_folder: Path,
    output_folder: Path,
    container: str = "mkv",
    progress_cb: Optional[Callable[[str], None]] = None,
    cleanup_work_folder: bool = True,
    overwrite: Optional[set[Path]] = None,
    cancel_event: Optional[threading.Event] = None,
    resume: bool = False,
    log_path: Optional[Path] = None,
    metadata: Optional[dict] = None,
    *,
    audio_track_ids: Optional[list[int]] = None,
    subtitle_track_ids: Optional[list[int]] = None,
    chapter_indices: Optional[list[int]] = None,
    keep_video: bool = True,
    filename_template: str = "title",
    skip_existing: Optional[set[Path]] = None,
    chapter_layout: Optional[list[float]] = None,
) -> list[Path]:
    """
    audio_track is the primary selected audio and the fallback for legacy callers.
    Track ID selections refer to the source playlist and chapter indices to its
    original chapter numbers. Omitting chapter_indices exports all chapters.
    Set keep_video to False to export only the selected audio and subtitles.
    chapter_layout: edited chapter start times (see apply_chapter_layout); chapter
    indices and track names then refer to the edited chapters.
    track_names: maps chapter index (1-based) -> song title.
    Returns list of final output file paths.

    cleanup_work_folder: if True (default), deletes work_folder (any
    intermediate copy inside it, and the job manifest) once splitting has
    finished successfully. If splitting raises - including cancellation -
    the work folder and manifest are left in place so the job can be
    resumed. Set to False to always keep the intermediate file around
    (e.g. for debugging).

    overwrite: paths pre-approved for overwrite by the caller (see
    preflight_check()). Extraction still runs even if this ends up wrong
    (e.g. the disk changed since preflight) - the collision is caught by
    the cutter afterwards rather than skipped, so nothing gets silently
    overwritten either way.

    cancel_event: if set while running, stops as soon as the current
    external-tool call can be safely terminated and raises JobCancelled.
    The manifest is updated to status "cancelled" first, so the job shows
    up as resumable rather than merely failed.

    resume: if True and work_folder already has a manifest from a
    previous run of this same job, reuse whatever it recorded as already
    done - skip re-making the intermediate file if it's already there,
    and skip re-splitting any chapter whose output file is already on
    disk. This folds "resume" and "retry failed chapters" into one
    behaviour: since progress is tracked by which output files actually
    exist, there's nothing left to distinguish a plain resume from a
    retry-what-failed - both mean "don't redo what's already done".

    log_path: if given, every progress message is also appended to this
    file (with a UTC timestamp), independent of progress_cb - this is
    what an "Open log" button in the UI can point at, and it survives
    even if the caller passes cleanup_work_folder=True.
    """
    def log(message: str) -> None:
        if progress_cb:
            progress_cb(message)
        if log_path:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{timestamp}  {message}\n")

    manifest = read_manifest(work_folder) if resume else None
    video_track = playlist.video_track
    if manifest is not None:
        # A resumed job keeps every choice it started with.
        audio_track_ids = manifest.audio_track_ids or [manifest.audio_track_id]
        subtitle_track_ids = manifest.subtitle_track_ids
        chapter_indices = manifest.chapter_indices
        track_names = {int(k): v for k, v in manifest.track_names.items()}
        container = manifest.container
        metadata = manifest.metadata or metadata
        keep_video = manifest.video_track_id is not None
        if keep_video and (video_track is None or video_track.track_id != manifest.video_track_id):
            raise ValueError("The saved video track is unavailable in this source.")
    keep_video = keep_video and video_track is not None

    audio_track_ids = [audio_track.track_id] if audio_track_ids is None else audio_track_ids
    subtitle_track_ids = subtitle_track_ids or []
    if container.lower() == "flac":
        if len(set(audio_track_ids)) != 1:
            raise ValueError("FLAC export requires exactly one audio track.")
        keep_video = False
        subtitle_track_ids = []
    audio_tracks = [t for t in playlist.audio_tracks if t.track_id in audio_track_ids]
    subtitle_tracks = [t for t in playlist.subtitle_tracks if t.track_id in subtitle_track_ids]
    if not audio_tracks or {t.track_id for t in audio_tracks} != set(audio_track_ids):
        raise ValueError("The selected audio tracks are unavailable in this source.")
    if {t.track_id for t in subtitle_tracks} != set(subtitle_track_ids):
        raise ValueError("The selected subtitle tracks are unavailable in this source.")
    if chapter_indices is not None:
        chapter_indices = sorted(set(chapter_indices))
        if not chapter_indices or chapter_indices[0] < 1:
            raise ValueError("Select at least one valid chapter.")
    if len(audio_tracks) > 1 and metadata:
        metadata = {key: value for key, value in metadata.items() if key != "audio"}

    if manifest is None:
        primary_audio = next((t for t in audio_tracks if t.track_id == audio_track.track_id), audio_tracks[0])
        manifest = JobManifest(
            source_playlist=str(playlist.path),
            source_iso=str(playlist.iso_image) if playlist.iso_image else None,
            audio_track_id=primary_audio.track_id,
            audio_track_label=primary_audio.display_label,
            audio_track_ids=[t.track_id for t in audio_tracks],
            subtitle_track_ids=[t.track_id for t in subtitle_tracks],
            chapter_indices=chapter_indices,
            number_filenames=False,
            renumber_tracks=True,
            filename_template=filename_template if filename_template in FILENAME_TEMPLATES else "title",
            video_track_id=video_track.track_id if keep_video and video_track is not None else None,
            output_folder=str(output_folder),
            container=container,
            track_names={str(k): v for k, v in track_names.items()},
            tool_versions=tools.tool_versions(),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status="extracting",
            metadata=metadata or {},
            chapter_layout=[float(s) for s in chapter_layout] if chapter_layout else None,
        )
        write_manifest(work_folder, manifest)

    direct = container.lower() == "mkv"

    def save(status: str) -> None:
        manifest.status = status
        write_manifest(work_folder, manifest)

    try:
        with _cut_source(playlist, manifest, work_folder, direct=direct, resume=resume, log=log, save=save,
                         cancel_event=cancel_event, audio_track=audio_track, audio_tracks=audio_tracks,
                         subtitle_tracks=subtitle_tracks, keep_video=keep_video) as source:
            chapters = _chapters_to_cut(source, direct, manifest, chapter_indices, track_names)
            save("splitting")
            done = _already_done(manifest, work_folder, resume, skip_existing, log)

            def on_output_written(path: Path) -> None:
                if str(path) not in manifest.completed_outputs:
                    manifest.completed_outputs.append(str(path))
                    write_manifest(work_folder, manifest)

            common = dict(progress_cb=log, overwrite=overwrite, cancel_event=cancel_event, skip_paths=done,
                          on_output_written=on_output_written, metadata=metadata,
                          source_chapter_count=len(chapters), number_filenames=manifest.number_filenames,
                          renumber_tracks=manifest.renumber_tracks, filename_template=manifest.filename_template)
            selected = [ch for ch in chapters if chapter_indices is None or ch.index in chapter_indices]
            if direct:
                # Video files carry only their song titles: no album tags, cover or folder.jpg.
                results = split.split_mkv_direct(
                    source, selected, output_folder, audio_tracks=audio_tracks, subtitle_tracks=subtitle_tracks,
                    video_track=video_track if keep_video else None, embed_metadata=False, **common)
            else:
                # A resumed job keeps the tags it started with.
                tagging.write_folder_cover(metadata, output_folder)
                results = split.split_chapters(
                    source, selected, output_folder, container=container, audio_tracks=audio_tracks,
                    subtitle_tracks=subtitle_tracks, keep_video=keep_video, **common)
        save("complete")
    except JobCancelled:
        save("cancelled")
        log(job_cancelled())
        raise
    except Exception as exc:
        save("failed")
        log(job_failed(exc))
        raise

    if cleanup_work_folder:
        log(cleaning_up())
        shutil.rmtree(work_folder, ignore_errors=True)
    return results


@contextlib.contextmanager
def _cut_source(playlist: Playlist, manifest: JobManifest, work_folder: Path, *, direct: bool, resume: bool,
                log: Callable[[str], None], save: Callable[[str], None], cancel_event: Optional[threading.Event],
                audio_track: Track, audio_tracks: list[Track], subtitle_tracks: list[Track],
                keep_video: bool) -> Iterator[Path]:
    """
    The file the songs are cut from, made first when the route needs one, and kept open (a mounted
    disc image) while it is cut. manifest.audio_extracted records that the intermediate copy is
    complete, so a resumed job reuses it instead of reading the disc again.
    """
    if direct and not dvd.is_title(playlist.path):
        with bluray_iso.playlist_file(playlist.path, playlist.iso_image) as path:
            yield path
        return
    # MKV: a DVD title is copied into one Matroska file first (all streams, so track numbers stay the same).
    copy = work_folder / ("_dvd_title.mkv" if direct else "_audio_extracted.mkv")
    if resume and manifest.audio_extracted and copy.is_file():
        if not direct:
            log(ProgressEvent(f"Resuming: {manifest.audio_track_label} already extracted, skipping re-extraction.",
                              stage="splitting"))
    else:
        manifest.audio_extracted = False
        save("extracting")
        if direct:
            dvd.remux(playlist.path, copy, progress_cb=log, cancel_event=cancel_event)
        else:
            with bluray_iso.playlist_file(playlist.path, playlist.iso_image) as path:
                split.extract_audio_mkv(dataclasses.replace(playlist, path=path), copy, audio_track,
                                        progress_cb=log, cancel_event=cancel_event, audio_tracks=audio_tracks,
                                        subtitle_tracks=subtitle_tracks, keep_video=keep_video)
        manifest.audio_extracted = True
        write_manifest(work_folder, manifest)
    yield copy


def _chapters_to_cut(source: Path, direct: bool, manifest: JobManifest, chapter_indices: Optional[list[int]],
                     track_names: dict[int, str]) -> list[Chapter]:
    """The source's chapters, edited as the job asked and named; recorded in the manifest."""
    chapters = (chapter_marks.read_chapters_from_source(source) if direct
                else chapter_marks.read_chapters(source))
    if not chapters:
        raise ValueError("No chapters found - this playlist has no chapter markers, so it can't be split into songs.")
    if manifest.chapter_layout:
        chapters = apply_chapter_layout(chapters, manifest.chapter_layout)
    if chapter_indices is not None and not set(chapter_indices).issubset(ch.index for ch in chapters):
        raise ValueError("The selected chapters are unavailable in this source.")
    for ch in chapters:
        if ch.index in track_names:
            ch.name = track_names[ch.index]
    manifest.chapters = [dict(index=ch.index, start_seconds=ch.start_seconds, end_seconds=ch.end_seconds,
                              name=ch.name) for ch in chapters]
    return chapters


def _already_done(manifest: JobManifest, work_folder: Path, resume: bool, skip_existing: Optional[set[Path]],
                  log: Callable[[str], None]) -> set[Path]:
    """Files this job will not write again: finished by the run being resumed, or kept by the user."""
    done = {Path(p) for p in manifest.completed_outputs} if resume else set()
    # Files the user chose to keep ("skip existing") count as done, also for a later resume.
    for path in skip_existing or ():
        if path not in done and path.is_file():
            done.add(path)
            manifest.completed_outputs.append(str(path))
    if done:
        log(f"Resuming: {len(done)} chapter(s) already split, skipping those.")
    return done
