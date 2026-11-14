"""
Compatibility facade: the engine now lives in the core package (see core/__init__.py).

`extractor.X` looks X up in the core module that defines it at the moment of access, so
replacing a function there (for example in a test) is seen by callers using either name.
New code should import from core directly.
"""
from __future__ import annotations

# Static imports, so PyInstaller bundles every module. Lower layers first: a name a module
# merely imported from below is found in the module that defines it.
from core import (models, jobs, tools, manifest, chapter_marks, naming, sources, tracklist, musicbrainz,
                  split, space, verify, pipeline)

_MODULES = (models, jobs, tools, manifest, chapter_marks, naming, sources, tracklist, musicbrainz,
            split, space, verify, pipeline)
_MISSING = object()


def __getattr__(name: str):
    if not name.startswith("__"):
        for module in _MODULES:
            found = getattr(module, name, _MISSING)
            if found is not _MISSING:
                return found
    raise AttributeError(f"module 'extractor' has no attribute {name!r}")


def __dir__():
    return sorted({name for module in _MODULES for name in vars(module) if not name.startswith("_")})
