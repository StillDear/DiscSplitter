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
    "disc_colors": "replace",       # M2TS mode: "replace" (blue accent) | "tint" (blue over frames and selections)
    "proxy_mode": "system",       # "system" | "none" | "custom"
    "proxy_url": "",
    "net_timeout": "15",
    "meta_source": "musicbrainz",
    "itunes_country": "US",
    "cover_size": "large",         # "standard" | "large" | "original"
    "cover_target": "both",        # "both" | "embed" | "folder"
    "meta_auto_search": False,
    "local_cover": "embedded",     # cover from local music files: "embedded" picture first, or the "folder" image
    "last_music_folder": "",       # where the local-files picker on the tags page last read
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


def system_language() -> str:
    """The interface language for a first start: Chinese when Windows shows Chinese, English otherwise."""
    try:
        import ctypes
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF     # LANG_CHINESE = 0x04
        return "zh" if primary == 0x04 else "en"
    except (AttributeError, OSError):       # not Windows
        import locale
        name = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
        return "zh" if name.startswith(("zh", "chinese")) else "en"


def load() -> dict[str, Any]:
    adopt_legacy_folder()
    if not SETTINGS_PATH.exists():
        # First start: speak the language Windows shows. Settings saved by earlier versions keep theirs.
        return dict(DEFAULTS, language=system_language())
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update({key: value for key, value in data.items() if _usable(key, value)})
    return merged


NUMBERS = ("net_timeout", "duration_tolerance", "font_scale")     # read with float()


def _usable(key: str, value: Any) -> bool:
    """A hand-edited or damaged value falls back to its default instead of failing at start-up."""
    default = DEFAULTS.get(key)
    if default is not None and not isinstance(value, type(default)):
        return False
    if key in NUMBERS:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False
    return True


def save(settings: dict[str, Any]) -> None:
    """Write atomically: a crash mid-write keeps the previous file instead of leaving a broken one."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)
