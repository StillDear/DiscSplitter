# Development

English | [简体中文](development.zh-CN.md)

## Run from source

Python 3.10 or newer on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe engine\build_engine.py
.venv\Scripts\python.exe app.py
```

### The Blu-ray engine

`engine\build_engine.py` compiles the Blu-ray engine (tsMuxeR) into `engine\bin\tsMuxeR.exe`. It needs Visual Studio 2022 or its Build Tools with the C++ workload. Without it, Blu-rays are read with MKVToolNix instead and M2TS export is not offered. The upstream version, local patches and how to update them are in [engine/UPSTREAM.md](../engine/UPSTREAM.md).

### External tools

Running from source uses these tools from your `PATH`, or from paths set in the app (**Settings → External tools**):

| Tool | Programs | Needed for |
|---|---|---|
| ffmpeg | `ffmpeg`, `ffprobe` | Previews, waveforms, FLAC, DVD sources (needs a build with `dvdvideo` support) |
| MKVToolNix | `mkvmerge`, `mkvextract`, `mkvpropedit` (all from the same folder) | MKV sources and MKV from a DVD. With the engine built, Blu-rays do not need it |

Settings, logs and caches are kept in `%USERPROFILE%\.disc_splitter`.

## Tests

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python.exe app.py --smoke-test
```

The smoke test runs every screen with fake disc data in both languages and all themes, and fails on any Qt/QML warning. `--smoke-screenshots <folder>` also saves an image of each screen. Tests marked `engine` build a small Blu-ray with ffmpeg and the engine and export it end to end; they are skipped while the engine is not built.

## Packaging

Build the installer (needs Inno Setup 6; writes `dist\DiscSplitter-Setup-<version>.exe`, where the version defaults to today's date as `YYYY.MM.DD`):

```powershell
packaging\build_installer.bat
```

`build_exe.bat` builds a single portable `DiscSplitter.exe` instead (same `packaging/installer.spec`, one-file mode). That one includes the Blu-ray engine but not MKVToolNix or ffmpeg.

Release builds are attached to [GitHub Releases](https://github.com/StillDear/DiscSplitter/releases), not committed.

## Command line

`split_now.py` splits an MKV that has chapters into named files without the GUI, using the same code as the app. Run it with `--help` for the options.

## Project layout

| Path | What is there |
|---|---|
| `app.py` | Entry point |
| `gui/` | The bridge between Python and QML: backend, controllers (`disc`, `preview`, `names`, `metadata`, `exporter`), models, texts |
| `qml/` | Screens and components |
| `core/` | Everything without a GUI: sources, tracklists and pasted set lists, online lookups, OCR, previews, naming, tags, splitting, checks, the export pipeline (layers are listed in `core/__init__.py`); `core/engine.py` drives the Blu-ray engine |
| `engine/` | The Blu-ray engine: tsMuxeR source snapshot, zlib, its CMake build and `build_engine.py` ([UPSTREAM.md](../engine/UPSTREAM.md)) |
| `split_now.py` | Command-line splitter for an MKV that has chapters |
| `packaging/` | Installer build |
| `tests/` | Unit, integration and smoke tests |
| `docs/` | This page and the README's images |
