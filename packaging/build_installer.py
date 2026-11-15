"""
Build the Windows installer: dist/DiscSplitter-Setup-<version>.exe

    .venv\\Scripts\\python.exe packaging\\build_installer.py [--version 2026.11.13]
        [--ffmpeg-dir DIR] [--mkvtoolnix-dir DIR] [--iscc PATH] [--skip-pyinstaller]

1. PyInstaller builds the app as a folder (packaging/installer.spec -> build/installer/DiscSplitter);
   the version is written next to it (version.txt), where the app reads it.
2. ffmpeg/ffprobe and mkvmerge/mkvextract/mkvpropedit are copied into its tools\\ folder with their licences;
   the installed app uses them unless the user sets other paths in Settings. The built-in Blu-ray engine
   (tsMuxeR, compiled from engine/ by engine/build_engine.py, which runs first and rebuilds what changed) goes there too.
3. Inno Setup (packaging/DiscSplitter.iss) packs that folder into the setup wizard.

Tool folders come from the arguments, else the environment (FFMPEG_DIR, MKVTOOLNIX_DIR), else the
paths set in the app's settings, else PATH. Needs: pip install -r requirements-dev.txt, Inno Setup 6.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core import appinfo                      # noqa: E402  (the project root has to be on the path first)
from gui.settings import SETTINGS_PATH as SETTINGS   # noqa: E402

PACKAGING = ROOT / "packaging"
APP_DIR = ROOT / "build" / "installer" / "DiscSplitter"
# mkvpropedit has no setting of its own, but every MKV export needs it next to mkvmerge.
TOOLS = {"ffmpeg": ("ffmpeg", "ffprobe"), "mkvtoolnix": ("mkvmerge", "mkvextract", "mkvpropedit")}


def fail(message: str) -> None:
    print(f"\nBuild FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def configured_path(tool: str) -> str | None:
    try:
        value = json.loads(SETTINGS.read_text(encoding="utf-8")).get(f"{tool}_path")
    except (OSError, ValueError):
        return None
    return value if value and value != tool else None


def tool_folder(family: str, override: str | None) -> Path:
    """The folder holding both of a family's executables."""
    names = TOOLS[family]
    candidates = [override, os.environ.get(f"{family.upper()}_DIR")]
    for name in names:
        configured = configured_path(name)
        candidates.append(str(Path(configured).parent) if configured else None)
        found = shutil.which(name)
        candidates.append(str(Path(found).parent) if found else None)
    for folder in filter(None, candidates):
        folder = Path(folder)
        if all((folder / f"{n}.exe").is_file() for n in names):
            return folder
    fail(f"could not find {' and '.join(n + '.exe' for n in names)}; pass --{family}-dir")


def licence(family: str, folder: Path) -> Path | None:
    places = {"ffmpeg": [folder / "LICENSE", folder.parent / "LICENSE", folder / "LICENSE.txt", folder.parent / "LICENSE.txt"],
              "mkvtoolnix": [folder / "doc" / "COPYING.txt", folder / "COPYING.txt", folder / "COPYING"]}[family]
    return next((p for p in places if p.is_file()), None)


def find_iscc(override: str | None) -> Path:
    candidates = [override, shutil.which("ISCC"),
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                  Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
                  Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe"]
    for path in filter(None, candidates):
        if Path(path).is_file():
            return Path(path)
    fail("Inno Setup 6 (ISCC.exe) not found; install it (winget install JRSoftware.InnoSetup) or pass --iscc")


def run(command: list) -> None:
    print("\n>", " ".join(str(c) for c in command), flush=True)
    if subprocess.run([str(c) for c in command], cwd=ROOT).returncode:
        fail(f"{Path(str(command[0])).name} returned an error (see above)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default=date.today().strftime("%Y.%m.%d"))
    parser.add_argument("--ffmpeg-dir")
    parser.add_argument("--mkvtoolnix-dir")
    parser.add_argument("--iscc")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="reuse the last app build")
    args = parser.parse_args()

    # Find everything first, so a missing tool fails fast rather than after a long build.
    folders = {"ffmpeg": tool_folder("ffmpeg", args.ffmpeg_dir),
               "mkvtoolnix": tool_folder("mkvtoolnix", args.mkvtoolnix_dir)}
    iscc = find_iscc(args.iscc)
    engine_exe = ROOT / "engine" / "bin" / "tsMuxeR.exe"
    # Always run the engine build: it is incremental, so it is quick when nothing changed,
    # and an engine source edited since the last build is never packed stale.
    run([sys.executable, ROOT / "engine" / "build_engine.py"])

    if not args.skip_pyinstaller:
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", ROOT / "build" / "installer", "--workpath", ROOT / "build" / "installer-work",
             PACKAGING / "installer.spec"])
    if not (APP_DIR / "DiscSplitter.exe").is_file():
        fail(f"no app build in {APP_DIR}")

    # The app reads its version from here (About, and the User-Agent it sends to web services).
    (APP_DIR / appinfo.VERSION_FILE).write_text(args.version + "\n", encoding="utf-8")

    tools = APP_DIR / "tools"
    shutil.rmtree(tools, ignore_errors=True)
    (tools / "licenses").mkdir(parents=True)
    for family, folder in folders.items():
        for name in TOOLS[family]:
            shutil.copy2(folder / f"{name}.exe", tools / f"{name}.exe")
            print(f"  bundled {name}.exe  <- {folder}")
        text = licence(family, folder)
        if text:
            target = "ffmpeg-LICENSE.txt" if family == "ffmpeg" else "mkvtoolnix-COPYING.txt"
            shutil.copy2(text, tools / "licenses" / target)
        else:
            print(f"  warning: no licence file found for {family} in {folder}")

    shutil.copy2(engine_exe, tools / "tsMuxeR.exe")
    print(f"  bundled tsMuxeR.exe  <- {engine_exe.parent}")
    upstream = ROOT / "engine" / "tsmuxer"
    for source, target in ((upstream / "LICENSE", "tsMuxeR-LICENSE.txt"), (upstream / "NOTICE", "tsMuxeR-NOTICE.txt"),
                           (upstream / "THIRD-PARTY-NOTICES.txt", "tsMuxeR-THIRD-PARTY-NOTICES.txt"),
                           (ROOT / "engine" / "third_party" / "zlib" / "LICENSE", "zlib-LICENSE.txt")):
        shutil.copy2(source, tools / "licenses" / target)

    run([iscc, "/Q", f"/DAppVersion={args.version}", f"/DSourceDir={APP_DIR}", f"/DOutputDir={ROOT / 'dist'}",
         PACKAGING / "DiscSplitter.iss"])
    setup = ROOT / "dist" / f"DiscSplitter-Setup-{args.version}.exe"
    print(f"\nInstaller: {setup}  ({setup.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
