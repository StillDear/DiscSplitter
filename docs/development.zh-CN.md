# 开发

[English](development.md) | 简体中文

## 从源码运行

Windows 上需要 Python 3.10 或更高版本：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe engine\build_engine.py
.venv\Scripts\python.exe app.py
```

### 蓝光引擎

`engine\build_engine.py` 会把蓝光引擎（tsMuxeR）编译成 `engine\bin\tsMuxeR.exe`，需要 Visual Studio 2022 或它的生成工具（Build Tools），并装好 C++ 工作负载。没有编译引擎时，蓝光改用 MKVToolNix 读取（ISO 镜像这时由 Windows 挂载），也不提供 M2TS 导出。上游版本、本地补丁和更新方法见 [engine/UPSTREAM.md](../engine/UPSTREAM.md)（英文）。

### 外部工具

从源码运行时，下面这些工具从 `PATH` 里找，或者用软件里设置的路径（**设置 → 外部工具**）：

| 工具 | 程序 | 用途 |
|---|---|---|
| ffmpeg | `ffmpeg`、`ffprobe` | 预览、波形、FLAC、DVD 来源（需要支持 `dvdvideo` 的版本） |
| MKVToolNix | `mkvmerge`、`mkvextract`、`mkvpropedit`（三个要在同一个文件夹） | MKV 来源，以及从 DVD 导出 MKV。编译好引擎后，蓝光不需要它 |

设置、日志和缓存放在 `%USERPROFILE%\.disc_splitter`。

## 测试

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python.exe app.py --smoke-test
```

冒烟测试会用模拟的光盘数据，在两种语言、所有主题下把每个页面跑一遍，出现任何 Qt/QML 警告就算失败。加上 `--smoke-screenshots <文件夹>` 还会给每个页面存一张截图。标记为 `engine` 的测试会用 ffmpeg 和引擎做一张小蓝光，从头到尾导出一遍；没编译引擎时这些测试会跳过。

## 打包

制作安装包（需要 Inno Setup 6；生成 `dist\DiscSplitter_<版本号>_Windows_x64_Setup.exe`，不传 `--version` 时是测试包，版本号取上一个正式版标签加当前提交号，例如 `1.0-16dd782`）：

```powershell
packaging\build_installer.bat
```

`build_exe.bat` 则生成一个单文件的便携版 `DiscSplitter.exe`（同样用 `packaging/installer.spec`，单文件模式）。便携版带蓝光引擎，但不带 MKVToolNix 和 ffmpeg。

发布的安装包上传到 [GitHub Releases](https://github.com/StillDear/DiscSplitter/releases)，不提交进仓库。发新版本时运行 `packaging\build_installer.bat --version <x.y>`。两个 README 顶部的下载徽章和版本徽章会从 GitHub 读取最新 Release 的版本，不用手动改。

## 命令行

`split_now.py` 不打开界面，直接把带章节的 MKV 拆成带曲名的文件，用的是和软件相同的代码。用 `--help` 查看参数。

## 目录结构

| 路径 | 内容 |
|---|---|
| `app.py` | 程序入口 |
| `gui/` | Python 和 QML 之间的桥：backend、控制器（`disc`、`preview`、`names`、`metadata`、`exporter`）、模型、界面文字 |
| `qml/` | 页面和组件 |
| `core/` | 所有和界面无关的部分：来源、曲目表和粘贴的歌单、在线查询、OCR、预览、命名、标签、切分、校验、导出流程（分层见 `core/__init__.py`）；`core/engine.py` 负责调用蓝光引擎 |
| `engine/` | 蓝光引擎：tsMuxeR 源码快照、zlib、CMake 构建和 `build_engine.py`（[UPSTREAM.md](../engine/UPSTREAM.md)） |
| `split_now.py` | 拆分带章节 MKV 的命令行工具 |
| `packaging/` | 安装包构建 |
| `tests/` | 单元测试、集成测试和冒烟测试 |
| `docs/` | 本页和 README 用到的图片 |
