"""UI-independent decisions shared by the Qt bridge and tests."""
from dataclasses import dataclass
from pathlib import Path
import re

import extractor


@dataclass(frozen=True)
class Progress:
    stage: str = ""
    chapter: int | None = None
    status: str = ""


def progress_event(message: str) -> Progress:
    """What a pipeline message means. Only extractor.ProgressEvent carries a meaning; the wording is never parsed."""
    if isinstance(message, extractor.ProgressEvent):
        return Progress(message.stage, message.chapter, message.status)
    return Progress()


def album_output(source: str, library: str) -> Path | None:
    if not source.strip() or not library.strip():
        return None
    return Path(library) / extractor.derive_album_folder_name(extractor.source_name_path(Path(source)))


def resumable_job(output: Path | None):
    manifest = extractor.read_manifest(output / "_work") if output else None
    return manifest if manifest and manifest.status != "complete" else None


@dataclass
class CollisionPlan:
    items: list
    collisions: list
    duplicates: list


def collision_plan(output: Path, count: int, names: dict, container="mkv", manifest=None, chapter_indices=None,
                   filename_template="title", metadata=None):
    # A resumed job keeps the naming and tags it started with.
    items = extractor.preflight_check(output, count, names, container=container, chapter_indices=chapter_indices,
                                      number_filenames=manifest.number_filenames if manifest else False,
                                      filename_template=manifest.filename_template if manifest else filename_template,
                                      metadata=(manifest.metadata or metadata) if manifest else metadata)
    # Only checkpoint-owned files may be skipped by a resumed job.
    completed = {Path(p) for p in manifest.completed_outputs} if manifest else set()
    return CollisionPlan(items, [p for p in items if p.exists and p.path not in completed],
                         [p for p in items if p.duplicate_name])


def safe_work_folder(output: Path) -> Path:
    """Resolve and constrain a recursive cleanup to this album's _work child."""
    parent = output.resolve()
    target = (parent / "_work").resolve()
    if target.parent != parent or target.name != "_work":
        raise ValueError("Unsafe work folder")
    return target


def format_time(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, seconds = divmod(max(0, round(seconds)), 60)
    return f"{minutes:02d}:{seconds:02d}"


def format_length(seconds: float | None) -> str:
    """Playlist lengths: m:ss under an hour, h:mm:ss above (never "137:29")."""
    if not seconds or seconds < 3600:
        return format_time(seconds or 0)
    total = round(seconds)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


_HEX_COLOR = re.compile(r"#(?:[0-9A-Fa-f]{2})?([0-9A-Fa-f]{6})")


def normalize_accent(value: str) -> str | None:
    """Accept "system" or a #RRGGBB / #AARRGGBB colour; return #RRGGBB upper-case."""
    value = str(value).strip()
    if value == "system":
        return value
    match = _HEX_COLOR.fullmatch(value)
    return "#" + match.group(1).upper() if match else None


INTERFACE_SCALES = {"system", "1", "1.25", "1.5", "1.75"}
FONT_SCALES = {"0.9", "1", "1.15", "1.3"}


def scale_factor(cfg: dict) -> str | None:
    """Absolute interface scale to force at startup, or None to follow Windows display scaling."""
    value = str(cfg.get("interface_scale", "system"))
    return value if value in INTERFACE_SCALES and value != "system" else None


def normalize_proxy(value: str) -> str | None:
    """"127.0.0.1:7890" or "http(s)://host:port" -> "http://host:port"; "" clears; None if invalid."""
    from urllib.parse import urlsplit
    value = str(value).strip()
    if not value:
        return ""
    if "://" not in value:
        value = "http://" + value
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname or port is None:
        return None
    return f"{parts.scheme}://{parts.netloc}"


ITUNES_COUNTRIES = {"US", "CN", "JP", "HK", "TW", "GB"}


def format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


# Facts the playlist card already shows elsewhere (its length · chapters line, the video panel), so they
# never make the one-line summary.
_RESTATED_REASONS = (r'\d+ chapters', r'Includes a video track \(.+\)', r'Runs .+ minutes')


def headline_reason(reasons: list[str]) -> str:
    """The one scoring reason worth showing on a playlist card: a duplicate or a disqualifier first,
    then what decided the ranking (usually the audio verdict). Empty when nothing new is left to say."""
    for reason in reasons:
        if reason.startswith('Same duration/chapters/tracks as') or reason.startswith('No audio track') \
                or reason.startswith('No chapters'):
            return reason
    for reason in reasons:
        if not any(re.fullmatch(p, reason) for p in _RESTATED_REASONS):
            return reason
    return ''
