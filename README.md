# DiscSplitter

**Losslessly split Blu-ray, DVD and MKV chapters into named audio or video tracks, with titles matched for you.**

把蓝光、DVD、MKV 按章节无损拆成带曲名的音频或视频，曲名自动对上章节。

<p align="center">
  <img src="screenshot.png" alt="DiscSplitter" width="900">
</p>

A Windows desktop app (PySide6 / Qt Quick). Open a disc or an MKV, pick the chapters, audio and subtitle tracks you want, get the titles in, and export one file per chapter. Nothing is re-encoded unless you ask for FLAC.

## Features

- **Sources:** unencrypted Blu-ray ISOs and `BDMV` folders, DVD ISOs and `VIDEO_TS` folders, MKV files with chapters, or a folder of MKVs. Playlists are scored and the main feature is picked for you, with the reasons shown.
- **Tracks:** every audio track the playlist has (Atmos, TrueHD, DTS-HD MA, LPCM, ...) with codec, channels, sample rate and bit depth; the best lossless one is preselected. Subtitles can be kept too.
- **Titles:** from the disc's own chapter names, a pasted or photographed tracklist (OCR), an imported file (`.txt`, `.cue`, `.json`, `.nfo`), or an online search (MusicBrainz, Discogs) by title or barcode. Titles are matched to chapters by length, and every match can be checked and changed on a review page before it is applied.
- **Content guess:** from the waveform, each chapter is marked as music, interlude, talk or unsure, so MCs and interludes can be taken out of the list. It is a guess and can be changed by hand.
- **Chapters:** merge, split at the playhead, or move a boundary; a built-in preview player with waveform shows where you are.
- **Export:** MKV with video, MKV audio-only, or FLAC with tags and cover art. Files are named after the titles, each disc goes into its own album folder, free space is checked first, and every file is read back and verified afterwards.
- **Resumable:** progress is saved as it goes; a cancelled or crashed export picks up where it stopped.
- Chinese and English interface; dark, light or system theme.

## Install

Download `DiscSplitter-Setup-<version>.exe` from the releases page and run it. The installer includes everything the app needs, MKVToolNix and ffmpeg among them, so nothing else has to be installed.

## Run from source

Python 3.10 or newer on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Running from source uses MKVToolNix (`mkvmerge`, `mkvextract`, `mkvpropedit`) and ffmpeg (`ffmpeg`, `ffprobe`) from your `PATH`, or from paths set in the app (Settings → External tools). DVD sources need an ffmpeg build with `dvdvideo` support.

Settings, logs and caches are kept in `%USERPROFILE%\.disc_splitter`.

## Development

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python.exe app.py --smoke-test
```

The smoke test runs every screen with fake disc data in both languages and all themes, and fails on any Qt/QML warning. `--smoke-screenshots <folder>` also saves an image of each screen.

Build the installer (needs Inno Setup 6; writes `dist\DiscSplitter-Setup-<version>.exe`):

```powershell
packaging\build_installer.bat
```

`build_exe.bat` builds a single portable `DiscSplitter.exe` instead; that one does not include MKVToolNix or ffmpeg.

| Path | What is there |
|---|---|
| `app.py` | Entry point |
| `gui/` | The bridge between Python and QML: backend, controllers (`disc`, `preview`, `names`, `metadata`, `exporter`), models, texts |
| `qml/` | Screens and components |
| `core/` | Everything without a GUI: sources, tracklists, online lookups, naming, splitting, checks, the export pipeline |
| `setlist.py`, `ocr.py` | Tracklist parsing and matching; OCR of tracklist images |
| `split_now.py` | Command-line splitter for an already-extracted file |
| `packaging/` | Installer build |
| `tests/` | Unit, integration and smoke tests |

## Limitations

- Not a ripper: encrypted discs have to be decrypted first.
- Cuts with video kept land on a keyframe (usually well under a second away on Blu-ray); audio-only exports cut exactly.
- Built and tested on Windows only.

## License

MIT, see [LICENSE](LICENSE). The installer bundles third-party tools (MKVToolNix, ffmpeg) under their own licenses, which are installed next to them in `tools\licenses`.
