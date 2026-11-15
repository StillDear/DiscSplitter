"""
Build DiscSplitter's Blu-ray engine (tsMuxeR, from the source in engine/tsmuxer) into engine/bin/tsMuxeR.exe.

    python engine/build_engine.py [--clean] [--debug]

Needs Visual Studio 2022 (or its Build Tools) with the C++ workload; its own CMake and Ninja are used,
so nothing else has to be installed. Takes a few minutes the first time, seconds after that.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
BUILD = ENGINE / "build"
BIN = ENGINE / "bin"
EXE = BIN / "tsMuxeR.exe"


def fail(message: str) -> None:
    print(f"\nEngine build FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def visual_studio() -> Path:
    """The newest Visual Studio installation with the C++ tools."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / \
        "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        fail("Visual Studio 2022 (or Build Tools) with the C++ workload is needed: vswhere.exe was not found")
    out = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                          "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-format", "json", "-utf8"],
                         capture_output=True, text=True, encoding="utf-8")
    found = json.loads(out.stdout or "[]")
    if not found:
        fail("no Visual Studio installation with the C++ tools (MSVC x64) was found")
    return Path(found[0]["installationPath"])


def msvc_environment(vs: Path) -> dict[str, str]:
    """The environment vcvars64.bat sets up, so cl, link, cmake and ninja are all found."""
    vcvars = vs / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    out = subprocess.run(f'"{vcvars}" >nul && set', shell=True, capture_output=True, text=True,
                         encoding="mbcs", errors="replace")
    env = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)
    if "VCToolsInstallDir" not in env:
        fail(f"{vcvars} did not set up the compiler")
    path = next((v for k, v in env.items() if k.upper() == "PATH"), "")
    env = {k: v for k, v in env.items() if k.upper() != "PATH"}     # Windows spells it "Path"
    bundled = vs / "Common7" / "IDE" / "CommonExtensions" / "Microsoft" / "CMake"
    env["PATH"] = os.pathsep.join([str(bundled / "CMake" / "bin"), str(bundled / "Ninja"), path])
    return env


def run(command: list[str], env: dict[str, str]) -> None:
    print(">", " ".join(command), flush=True)
    # The child is looked up on this process's PATH, not on the one handed to it.
    exe = shutil.which(command[0], path=env["PATH"]) or command[0]
    if subprocess.run([exe, *command[1:]], env=env, cwd=ENGINE).returncode:
        fail(f"{command[0]} returned an error (see above)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clean", action="store_true", help="start from an empty build folder")
    parser.add_argument("--debug", action="store_true", help="build without optimisation")
    args = parser.parse_args()

    env = msvc_environment(visual_studio())
    if args.clean:
        shutil.rmtree(BUILD, ignore_errors=True)
    kind = "Debug" if args.debug else "Release"
    run(["cmake", "-S", str(ENGINE), "-B", str(BUILD), "-G", "Ninja", f"-DCMAKE_BUILD_TYPE={kind}"], env)
    run(["cmake", "--build", str(BUILD), "--target", "tsmuxer"], env)
    built = BUILD / "tsMuxer" / "tsMuxeR.exe"
    if not built.is_file():
        fail(f"the build finished without {built}")
    BIN.mkdir(exist_ok=True)
    shutil.copy2(built, EXE)
    print(f"\nEngine: {EXE}  ({EXE.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
