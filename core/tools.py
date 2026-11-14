"""External tools (MKVToolNix, ffmpeg): configured paths, identity checks and cancellable runs."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .jobs import JobCancelled


# ---------------------------------------------------------------------------
# Tool paths - overridden by settings.py if the user configures custom paths
# ---------------------------------------------------------------------------

TOOL_PATHS = {
    "mkvmerge": "mkvmerge",
    "mkvextract": "mkvextract",
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
}

# Where to point people if a required tool isn't found. mkvmerge/mkvextract
# both ship in the same MKVToolNix install; ffmpeg/ffprobe both ship in the
# same ffmpeg download.
TOOL_DOWNLOAD_URLS = {
    "mkvmerge": "https://mkvtoolnix.download/downloads.html",
    "mkvextract": "https://mkvtoolnix.download/downloads.html",
    "ffmpeg": "https://ffmpeg.org/download.html",
    "ffprobe": "https://ffmpeg.org/download.html",
}


def bundled_tool(tool: str) -> Optional[str]:
    """The copy shipped with the installed app (<app folder>/tools/<tool>.exe), if there is one."""
    import sys
    if not getattr(sys, "frozen", False):
        return None
    path = Path(sys.executable).resolve().parent / "tools" / f"{tool}.exe"
    return str(path) if path.is_file() else None


def default_tool_path(tool: str, configured: Optional[str]) -> str:
    """A path the user set wins; a bare name ("ffmpeg", the default) prefers the bundled copy."""
    if configured and configured != tool:
        return configured
    return bundled_tool(tool) or configured or tool


def set_tool_path(tool: str, path: str) -> None:
    if tool not in TOOL_PATHS:
        raise KeyError(f"Unknown tool '{tool}'")
    TOOL_PATHS[tool] = path


def check_tools() -> dict[str, bool]:
    """
    Check whether each configured tool is actually runnable and actually
    the right tool. See verify_tool_at_path() for why - existence alone
    doesn't prove much, and neither does exit code alone.

    Returns {tool_name: True/False}.
    """
    return {name: verify_tool_at_path(path, name)[0] for name, path in TOOL_PATHS.items()}


# ffmpeg/ffprobe use a single-dash "-version" - "--version" (GNU style) is
# NOT a recognised option for them. mkvmerge/mkvextract do use GNU-style
# "--version". Using the wrong flag doesn't necessarily fail cleanly: ffmpeg
# prints its full version banner to stderr unconditionally at startup,
# *before* it even parses arguments, so an unrecognised "--version" still
# produces a perfectly legible banner followed by an "Unrecognized option"
# error and a nonzero exit - which looks exactly like a real failure if
# you're only checking the exit code.
_VERSION_FLAGS = {
    "mkvmerge": "--version",
    "mkvextract": "--version",
    "ffmpeg": "-version",
    "ffprobe": "-version",
}

# Text each tool prints about itself, used to confirm a binary's actual
# identity rather than just trusting that "something ran successfully".
_IDENTIFYING_TEXT = {
    "mkvmerge": "mkvmerge v",
    "mkvextract": "mkvextract v",
    "ffmpeg": "ffmpeg version",
    "ffprobe": "ffprobe version",
}


def verify_tool_at_path(path: str, tool_name: str, timeout: float = 10.0) -> tuple[bool, str]:
    """
    Check whether a specific path is actually a working copy of tool_name -
    usable directly against a path the user just picked in a file browser,
    before it's saved to settings at all.

    This checks the tool's own self-identifying banner text in its output
    (e.g. "ffmpeg version") rather than trusting the exit code alone, for
    two reasons that both showed up in practice:

    - ffmpeg/ffprobe print their version banner to stderr unconditionally
      at startup, before parsing arguments - so a genuinely-working binary
      given the wrong flag can still exit nonzero after having already
      printed a perfectly valid banner. Checking only the exit code would
      wrongly reject it and show that banner back as if it were an error.
    - A file that runs fine and exits 0 isn't necessarily the *right*
      tool - ffmpeg.exe and ffprobe.exe sit right next to each other in
      every install, and it's an easy misclick to pick one while browsing
      for the other. Checking identity catches that with a clear message
      instead of a false pass.

    Returns (True, first line of version output) on success, or
    (False, a short human-readable reason - naming what it actually looks
    like, if it's recognisably one of our *other* tools) on failure.
    """
    flag = _VERSION_FLAGS.get(tool_name, "--version")
    try:
        result = run([path, flag], timeout=timeout)
    except (FileNotFoundError, OSError) as exc:
        return False, f"Could not run this file: {exc}"
    except RuntimeError as exc:
        # run()'s own timeout wrapper - already a clear message.
        return False, str(exc)

    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    combined_lower = combined.lower()

    expected = _IDENTIFYING_TEXT.get(tool_name, tool_name)
    if expected.lower() in combined_lower:
        first_line = next((ln.strip() for ln in combined.splitlines() if ln.strip()), "OK")
        return True, first_line

    # Not the expected tool - check whether it's recognisably one of our
    # *other* tools, so a mixed-up file gets a specific, actionable answer
    # ("this looks like ffprobe, not ffmpeg") instead of a raw dump.
    for other_name, other_text in _IDENTIFYING_TEXT.items():
        if other_name != tool_name and other_text.lower() in combined_lower:
            return False, f"This looks like {other_name}, not {tool_name}."

    if result.returncode != 0:
        detail_lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
        detail = detail_lines[0] if detail_lines else f"exited with code {result.returncode}"
        return False, detail

    return False, "Ran, but didn't produce recognisable version output."


# Tools that are always installed together in the same folder, so once the
# user locates one we can offer to auto-detect the other instead of making
# them browse twice for what's really one install.
SIBLING_TOOL_NAMES = {
    "ffmpeg": "ffprobe",
    "ffprobe": "ffmpeg",
    "mkvmerge": "mkvextract",
    "mkvextract": "mkvmerge",
}


def guess_sibling_tool_path(chosen_path: str, tool_name: str) -> Optional[str]:
    """
    Given a path the user just picked for one tool (e.g. .../bin/ffmpeg.exe),
    guess the path for its usual companion in the same install (ffprobe
    next to ffmpeg, mkvextract next to mkvmerge - both pairs are always
    shipped together in the same bin/ folder). Only replaces the filename
    itself, not anything matching the tool name elsewhere in the path
    (e.g. a parent folder called "ffmpeg-8.1.2-full_build" is left alone).

    Returns the guessed path only if a file actually exists there - the
    caller still has to run it through verify_tool_at_path() before
    trusting it, since a same-named file isn't proof it's a working,
    matching-architecture binary.
    """
    sibling_name = SIBLING_TOOL_NAMES.get(tool_name)
    if sibling_name is None:
        return None

    chosen = Path(chosen_path)
    candidate = chosen.with_name(chosen.name.replace(tool_name, sibling_name))
    if candidate != chosen and candidate.is_file():
        return str(candidate)
    return None


def tool_versions() -> dict[str, str]:
    """First line of each configured tool's version output, for the job manifest."""
    versions: dict[str, str] = {}
    for name, configured_path in TOOL_PATHS.items():
        ok, message = verify_tool_at_path(configured_path, name)
        versions[name] = message if ok else "unknown"
    return versions


def run(
    args: list[str],
    timeout: Optional[float] = None,
    cancel_event: Optional[threading.Event] = None,
) -> subprocess.CompletedProcess:
    """
    Run a subprocess, hiding the console window on Windows.

    stdin is explicitly set to DEVNULL. When this app is running as a
    windowed/no-console exe (PyInstaller --windowed), there is no valid
    console handle for the process to inherit as stdin. A child process
    that inherits a broken/invalid stdin handle can hang indefinitely
    waiting on it even after the child itself has exited - this was the
    root cause of the app appearing stuck on "Working..." after mkvmerge
    had already finished/died. Explicitly redirecting stdin from DEVNULL
    avoids that inheritance entirely, regardless of how the app is launched.

    A timeout is also supported (default: no timeout) so that a genuinely
    hung external tool doesn't wedge the app forever with no feedback.

    cancel_event: if given, checked roughly twice a second while the
    process runs. If set, the process is terminated (SIGTERM, then
    SIGKILL if it hasn't exited within 5s) and JobCancelled is raised
    instead of waiting for it to finish naturally. Omitted entirely for
    calls that don't need to be cancellable (quick --version checks etc),
    which keeps using the simpler non-polling subprocess.run path.
    """
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    if cancel_event is None:
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            tool = Path(args[0]).name if args else "process"
            raise RuntimeError(
                f"{tool} timed out after {timeout} seconds and was killed. "
                f"Command: {' '.join(args)}"
            ) from exc

    # Cancellable path: subprocess.run() blocks until the process exits
    # with no way to interrupt it early, so use Popen + a short-timeout
    # communicate() loop instead, checking cancel_event between polls.
    # Retrying communicate() after a TimeoutExpired is explicitly
    # supported and doesn't lose any output (per the subprocess docs).
    if cancel_event.is_set():
        raise JobCancelled("Cancelled by user.")
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    started = time.monotonic()
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
            return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if cancel_event.is_set():
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                raise JobCancelled("Cancelled by user.")
            if timeout is not None and (time.monotonic() - started) > timeout:
                proc.kill()
                proc.communicate()
                tool = Path(args[0]).name if args else "process"
                raise RuntimeError(
                    f"{tool} timed out after {timeout} seconds and was killed. "
                    f"Command: {' '.join(args)}"
                )


def probe_duration_seconds(media_path: Path) -> float:
    """Get total duration of a media file via ffprobe (used for the last chapter)."""
    args = [
        TOOL_PATHS["ffprobe"],
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    result = run(args, timeout=60)
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Could not determine duration of {media_path}")


def mkvpropedit_path() -> str:
    """mkvpropedit ships next to mkvmerge in every MKVToolNix install."""
    mkvmerge = Path(TOOL_PATHS["mkvmerge"])
    if mkvmerge.parent != Path("."):
        sibling = mkvmerge.with_name("mkvpropedit" + mkvmerge.suffix)
        if sibling.is_file():
            return str(sibling)
    return "mkvpropedit"


def run_streaming(args: list[str], on_line: Callable[[str], None],
                   cancel_event: Optional[threading.Event] = None) -> int:
    """Run a tool, handing each output line to on_line as it arrives; cancellable like run()."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                               text=True, encoding="utf-8", errors="replace", creationflags=creationflags)
    lines: "list[str]" = []
    reader = threading.Thread(target=lambda: [lines.append(line.rstrip("\r\n")) for line in process.stdout], daemon=True)
    reader.start()
    seen = 0
    while True:
        while seen < len(lines):
            on_line(lines[seen])
            seen += 1
        if process.poll() is not None:
            reader.join(timeout=5)
            for line in lines[seen:]:
                on_line(line)
            return process.returncode
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise JobCancelled("Cancelled by user.")
        time.sleep(0.2)
