# The built-in Blu-ray engine

`engine/` holds DiscSplitter's Blu-ray engine: **tsMuxeR**, compiled from source and shipped with the app.
It reads Blu-ray folders and ISO images without mounting them, lists a disc's titles with the main one marked,
lists a playlist's tracks (by PID) and chapter marks, and cuts a playlist into M2TS or Matroska files.

| Path | What is there |
|---|---|
| `tsmuxer/` | Snapshot of the upstream source: `tsMuxer/`, `libmediation/`, `LICENSE`, `NOTICE`, `THIRD-PARTY-NOTICES.txt` |
| `third_party/zlib/` | zlib 1.3.1, the engine's only library on Windows (official release, SHA-256 `9a93b2b7…df23` of the tarball) |
| `CMakeLists.txt`, `cmake/` | DiscSplitter's own build: static (`/MT`), zlib compiled in, command line program only |
| `build_engine.py` | Builds `bin/tsMuxeR.exe` with Visual Studio 2022's compiler, CMake and Ninja |

## Upstream

- Repository: <https://github.com/teaching-droid/tsMuxer> (fork of jaminmc/tsMuxer and justdan96/tsMuxer)
- Commit: `ea5b37fa905c927da9f5d78a013106805e886d1e` (version 3.1.0)
- Licence: Apache 2.0 (`tsmuxer/LICENSE`, `tsmuxer/NOTICE`). The GUI (Qt), documentation and packaging of
  upstream are not included; nothing here links Qt, libass or libdovi (the last two are only loaded at run time
  when present, and are not shipped).
- Local changes to the upstream sources: two. The first, `patches/0001-discsplitter-listings.patch` (in `tsMuxer/main.cpp`,
  `metaDemuxer.cpp/.h`, `muxerManager.cpp` and `tsPacket.h`, already applied to the snapshot). It adds output
  and one opt-in option; without that option nothing upstream does changes:
  - a playlist listing adds `Mark ticks (45 kHz): …` after each clip's `Marks:` lines: the same marks unrounded,
    so chapters are cut at the disc's own times rather than at times rounded to the millisecond;
  - `tsMuxeR --extents <image.iso/path> …` prints where the bytes of files inside an image are
    (`File: … size=…`, `Extent: offset=… length=…`, `Data: <hex>` for a small file kept in its entry), so the
    app's previews, probes and outlines read a disc image with ffmpeg's subfile protocol instead of mounting it;
  - `MUXOPT --playlist-window=<start>[,<end>]` (seconds or `H:MM:SS.sss` on the playlist's timeline, both at
    chapter marks) keeps only that stretch of a `.mpls` input: play items outside it are dropped and the first
    one starts at the key picture of the mark, found in the clip's EP map. The engine then starts reading there
    instead of from the start of the disc (a `--cut-start` deep into a disc reads everything before it twice).
    The muxer prints `Playlist window: start=<s> ticks=<t>` with where the stretch really starts, and times in
    the meta (`--cut-*`, `--custom-chapters`) are counted from it. Refused for 3D playlists;
  - every progress report is followed by `Position: <seconds>`, the timestamp the muxer has reached (from the
    window start when there is one), so the app shows progress by time instead of by bytes read.
- The second, `patches/0002-key-pictures-carry-parameter-sets.patch` (in `tsMuxer/h264StreamReader.cpp`), widens
  `contSPS`: an H.264 I picture that carries no SPS and PPS of its own now gets them, also in a stream that repeats
  them elsewhere. Upstream did so only for a stream that holds them once. Some discs open an IDR picture at a cut in
  the middle of a group without sending the sets again; a cut of such a chapter decoded from its start but not
  after a seek, and Windows drew its thumbnail green. Only output with `contSPS` changes, which is Blu-ray output
  and, from the app, every H.264 track cut to M2TS.

  Any further change goes into `patches/` as a `git diff` against the upstream snapshot and is listed here, so
  that an update can re-apply it.

## Building

```powershell
python engine\build_engine.py           # -> engine\bin\tsMuxeR.exe (about 6 MB, no DLLs)
python engine\build_engine.py --clean   # from an empty build folder
```

Needs Visual Studio 2022 or its Build Tools with the "Desktop development with C++" workload. The installer
build (`packaging\build_installer.py`) and `build_exe.bat` run it first when the engine is missing.

## How the app uses it (`core/engine.py`)

The engine runs as a child process, never in-process: a crash or a cancel never takes the app with it, and its
global state is reset with every run. The app depends on these outputs, all of which tsMuxeR's own GUI parses
too:

- `tsMuxeR <disc folder or image>`: `Title N  00001.mpls  H:MM:SS  N chapters … (main film)` lines
- `tsMuxeR <playlist>`: `Track ID / Stream type / Stream ID / Stream info / Stream lang` blocks,
  `Duration:` per clip and `Marks:` on the playlist's own timeline (milliseconds), with `Mark ticks (45 kHz):`
  from the local patch (the app falls back to `Marks:` when an engine without it is used)
- `tsMuxeR --extents …` (local patch): files inside an image, for ffmpeg's subfile protocol
- muxing: `tsMuxeR <file.meta> <output>`, `NN.N% complete` progress lines, exit code 0 on success,
  split parts named `<output>.split.N.m2ts`; with the local patch, `Playlist window:` and `Position:` lines
  (the app needs an engine built with the patch for `--playlist-window`; without `Position:` lines it falls back
  to the percentage)

`tests/test_engine.py` checks the parsers against recorded listings; `tests/test_engine_disc.py` builds a small
Blu-ray with ffmpeg and the engine and runs the whole export on it (skipped when the engine is not built).

## Updating the snapshot

1. Download the new upstream commit, replace `tsmuxer/tsMuxer`, `tsmuxer/libmediation` and the three licence files.
2. Compare upstream's `tsMuxer/CMakeLists.txt` source list with the old one; `engine/CMakeLists.txt` only adds
   the subdirectories, so new sources are picked up as long as upstream lists them.
3. Re-apply `patches/` (`git apply --directory=engine/tsmuxer engine/patches/*.patch`), set `UPSTREAM_COMMIT`
   in `CMakeLists.txt`, update the commit above.
4. `python engine\build_engine.py --clean`, then `pytest -q` (the engine tests run against the new build).
