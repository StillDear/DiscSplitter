"""
settings.py

Small JSON-backed settings store: tool paths, the last-used source and
output folders, and the preferences from the Settings page.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path.home() / ".disc_splitter" / "settings.json"

DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "language": "zh",
    "accent": "#F2A33A",
    "interface_scale": "system",   # "system" or an absolute factor such as "1.25"
    "font_scale": "1",
    "density": "comfortable",
    "motion": "full",
    "proxy_mode": "system",       # "system" | "none" | "custom"
    "proxy_url": "",
    "net_timeout": "15",
    "meta_source": "musicbrainz",
    "itunes_country": "US",
    "cover_size": "large",         # "standard" | "large" | "original"
    "cover_target": "both",        # "both" | "embed" | "folder"
    "meta_auto_search": False,
    "discogs_token": "",          # optional Discogs personal access token
    "mkvmerge_path": "mkvmerge",
    "mkvextract_path": "mkvextract",
    "ffmpeg_path": "ffmpeg",
    "ffprobe_path": "ffprobe",
    "last_source_folder": "",
    "last_output_folder": "",
    "output_container": "mkv",
    "filename_template": "title",  # core.naming.FILENAME_TEMPLATES key
    "collision_policy": "ask",     # "ask" | "skip" | "overwrite" when output files already exist
    "chapter_language": "eng",     # preferred language of names stored on the disc, or "first"
    "duration_tolerance": "20",    # seconds a song may differ from its chapter and still be checked
    "window_geometry": [],         # [x, y, width, height, maximized]
    "waveform": True,             # draw loudness outlines on the timeline and the preview bar
    "crop_backdrop": "dark",      # backdrop behind the cover-crop previews: "dark" | "light" | "checker"
    "kind_column": "show",        # music/talk column: "show" | "auto" (only once talk is found) | "hide"
    "layout": {},                  # dragged panel sizes (gui.backend.LAYOUT_LIMITS); empty = defaults
}


LEGACY_FOLDER = ".disc_track_splitter"     # the app's folder under its first name


def adopt_legacy_folder() -> None:
    """
    First start after the rename: take over the old folder (settings, logs, waveform and cover
    caches) so nothing has to be set up again. Only ever looks next to the current folder.
    """
    folder = SETTINGS_PATH.parent
    legacy = folder.with_name(LEGACY_FOLDER)
    if folder.name == LEGACY_FOLDER or folder.exists() or not legacy.is_dir():
        return
    try:
        legacy.rename(folder)
    except OSError:
        try:        # in use or not movable: at least bring the settings along
            folder.mkdir(parents=True, exist_ok=True)
            (folder / SETTINGS_PATH.name).write_bytes((legacy / SETTINGS_PATH.name).read_bytes())
        except OSError:
            pass


def load() -> dict[str, Any]:
    adopt_legacy_folder()
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(settings: dict[str, Any]) -> None:
    """Write atomically: a crash mid-write keeps the previous file instead of leaving a broken one."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)
