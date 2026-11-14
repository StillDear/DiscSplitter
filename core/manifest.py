"""The job manifest: lets an interrupted export resume instead of starting over."""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Job manifest - lets an interrupted job be resumed instead of redone from
# scratch, and gives "Open log" / crash diagnosis something concrete to
# point at.
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "manifest.json"


@dataclass
class JobManifest:
    source_playlist: str
    audio_track_id: int
    audio_track_label: str           # human-readable description of the chosen track, for the resume banner
    video_track_id: Optional[int]
    output_folder: str
    container: str
    track_names: dict[str, str]      # chapter index (as string, for JSON) -> name
    tool_versions: dict[str, str]
    created_at: str
    status: str = "pending"          # pending -> extracting -> splitting -> complete | failed | cancelled
    audio_extracted: bool = False    # True once extract_audio_mkv has succeeded - independent of status,
                                      # since status becomes "failed"/"cancelled" regardless of which stage failed
    chapters: list[dict] = field(default_factory=list)             # [{index, start_seconds, end_seconds, name}]
    completed_outputs: list[str] = field(default_factory=list)     # output paths already written, in order
    source_iso: Optional[str] = None
    metadata: dict = field(default_factory=dict)   # tags for the split files (see tagging.py)
    audio_track_ids: Optional[list[int]] = None   # None means a legacy single-track job
    subtitle_track_ids: list[int] = field(default_factory=list)
    chapter_indices: Optional[list[int]] = None   # None means all original chapters
    number_filenames: bool = True  # Checkpoints without this field used numbered filenames.
    renumber_tracks: bool = False  # Existing checkpoints used original chapter numbers in track tags.
    filename_template: str = ""   # FILENAME_TEMPLATES key; empty for checkpoints made before presets.
    chapter_layout: Optional[list[float]] = None   # edited chapter start times; None keeps the source's chapters

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "JobManifest":
        data = json.loads(text)
        known_fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known_fields})


def write_manifest(work_folder: Path, manifest: JobManifest) -> None:
    """Write the manifest atomically - a crash mid-write must never leave a corrupt manifest behind."""
    work_folder.mkdir(parents=True, exist_ok=True)
    path = work_folder / MANIFEST_FILENAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(manifest.to_json(), encoding="utf-8")
    os.replace(tmp, path)


def read_manifest(work_folder: Path) -> Optional[JobManifest]:
    """
    Read a previous job's manifest from work_folder, or None if there
    isn't one (fresh job) or it's unreadable (treated the same as "no
    manifest" - a corrupt manifest shouldn't block starting a new job,
    it just means resume isn't available for whatever was there before).
    """
    path = work_folder / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        return JobManifest.from_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, KeyError, OSError):
        return None
