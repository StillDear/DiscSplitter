"""What the app is called, where it lives, and which build is running."""

from __future__ import annotations

import sys
from pathlib import Path

NAME = "DiscSplitter"
REPOSITORY = "https://github.com/StillDear/DiscSplitter"
VERSION_FILE = "version.txt"      # written next to the program by packaging/build_installer.py


def version() -> str:
    """The installed build's version; "dev" when run from source (or a build that carries none)."""
    if getattr(sys, "frozen", False):
        try:
            text = (Path(sys.executable).resolve().parent / VERSION_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            return text
    return "dev"


def user_agent() -> str:
    """Identifies the app to web services (MusicBrainz asks for a name and a contact point)."""
    return f"{NAME}/{version()} (+{REPOSITORY})"
