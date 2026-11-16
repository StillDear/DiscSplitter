<div align="center">

<img src="docs/images/logo.png" width="112" alt="DiscSplitter 图标">

# DiscSplitter

**把演唱会蓝光、DVD 或 MKV 按歌曲无损拆成单独的文件，曲名自动配好。**

[**下载 Windows 版**](https://github.com/StillDear/DiscSplitter/releases/latest) &nbsp;·&nbsp; [使用流程](#使用流程) &nbsp;·&nbsp; [功能](#功能) &nbsp;·&nbsp; [常见问题](#常见问题)

[English](README.md) &nbsp;|&nbsp; 简体中文

![Windows 10/11 x64](https://img.shields.io/badge/Windows-10%20%7C%2011%20x64-0078D4?style=flat-square) ![License: MIT](https://img.shields.io/badge/license-MIT-3DA639?style=flat-square) ![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square)

</div>

<!--
  首屏截图。把 docs/images/workspace-light.png 和 workspace-dark.png 放好
  （见 docs/images/SHOTS.md），再删掉这段注释的开头和结尾两行。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/workspace-dark.png">
    <img src="docs/images/workspace-light.png" width="860" alt="DiscSplitter 工作区：带曲名的章节、波形、预览和音轨列表">
  </picture>
</p>
-->

一张演唱会光盘就是一段带章节标记、没有曲名的长视频。DiscSplitter 打开光盘后会自动找到正片，再从光盘、网上或一张照片里拿到歌单，把歌曲和章节对上，然后一首歌切出一个文件。画面和声音都原样复制，除非你选 FLAC，否则不会重新编码。

<table>
<tr>
<td width="33%" valign="top">

**真正无损**

TrueHD Atmos、DTS-HD MA、LPCM 和 PGS 字幕逐位复制。M2TS 按光盘自己的章节点直接从盘上切出。

</td>
<td width="33%" valign="top">

**曲名自动对齐**

可以搜索 MusicBrainz、Apple Music、Deezer、Discogs，也能读粘贴的歌单、网页或照片。按时长把歌曲对到章节上，每一条都可以核对。

</td>
<td width="33%" valign="top">

**ISO 直接读**

内置 tsMuxeR 引擎，蓝光 ISO 和文件夹都不用挂载。一个安装包装好就能用，不用另外装工具。

</td>
</tr>
</table>

## 使用流程

| 步骤 | 你要做的 | DiscSplitter 做的 |
|:---:|---|---|
| **1** | 打开光盘镜像、`BDMV` / `VIDEO_TS` 文件夹或 MKV | 给每个播放列表打分，选出正片，并说明理由 |
| **2** | 勾选要的章节、音轨和字幕 | 默认选好最好的无损音轨，并判断每个章节是音乐、说话还是过场 |
| **3** | 点 **获取曲名** | 找到歌单，按时长对到章节上，交给你核对 |
| **4** | 选 M2TS、MKV 或 FLAC，导出 | 先检查剩余空间，再一首歌一个文件放进专辑文件夹，逐个校验 |

<!--
  步骤截图。把 docs/images/review.png 和 docs/images/done.png 放好
  （见 docs/images/SHOTS.md），再删掉这段注释的开头和结尾两行。

<p align="center">
  <img src="docs/images/review.png" width="49%" alt="核对曲名页：按时长把候选曲名对到章节上">
  <img src="docs/images/done.png" width="49%" alt="导出完成：文件已写出并校验">
</p>
-->

## 功能

**来源**
- 蓝光：ISO 镜像和 `BDMV` 文件夹（不用挂载），也可以只打开一个 `.mpls` 播放列表或 `.m2ts` 流。光盘需要是未加密的。
- DVD：ISO 镜像和 `VIDEO_TS` 文件夹。
- 带章节的 MKV 文件，或者一整个文件夹的 MKV。

**曲名**
- 用光盘自带的章节名。
- 按艺人、专辑或条形码在线搜索：MusicBrainz、Apple Music、Deezer、Discogs（填一个免费的 Discogs 令牌后，搜索结果带封面）。
- 从粘贴的歌单、网页链接（官网、维基百科、商店页）、照片或截图（用 Windows 自带的 OCR 识别），或 `.txt`、`.cue`、`.nfo`、`.json` 文件读取。
- 按时长或按顺序对到章节上，每个候选曲名在应用前都可以核对和修改。

**章节与音轨**
- 列出播放列表里的全部音轨，带编码、声道、采样率和位深；也可以保留字幕。
- 根据波形把每个章节标成音乐、过场、说话或不确定，方便去掉 MC。
- 可以合并章节、在播放位置拆分、挪动分界，配有内置播放器和波形。

**导出**
- 从蓝光直接切 **M2TS**，带视频的 **MKV**，只有音频的 **MKV**，或者带标签和封面的 **FLAC**。
- 文件按曲名命名，每张盘单独一个专辑文件夹。
- 导出前先检查剩余空间；导出后逐个读回校验（时长、流、音画同步）。
- 导出中断了，下次从停下的地方继续。

**界面**
- 中文和英文界面；浅色、深色或跟随系统。

<details>
<summary><b>M2TS 导出是怎么做的</b></summary>
<br>

每个章节都直接从光盘上切出来，画面、全部音轨（TrueHD 连同 AC-3 内核、DTS-HD 连同扩展、LPCM）和 PGS 字幕都和盘上一模一样，杜比视界增强层也在，时间戳也沿用光盘自己的，所以音画同步和原盘一致。

切点落在光盘精确的章节点上（按 45 kHz 刻度）。引擎从第一个选中的章节开始读，而不是从盘头读起，所以靠近结尾的章节几秒就能切完，相邻的章节一次切出。从蓝光导出 MKV 用的是同样的方式；从蓝光导出 FLAC 时，只读选中章节覆盖的那一段。

</details>

### 支持的格式

| 来源 | M2TS | MKV（带视频） | MKV（仅音频） | FLAC |
|---|:---:|:---:|:---:|:---:|
| 蓝光（ISO、`BDMV`、`.mpls`、`.m2ts`） | ✓ | ✓ | ✓ | ✓ |
| DVD（ISO、`VIDEO_TS`） | | ✓ | ✓ | ✓ |
| 带章节的 MKV | | ✓ | ✓ | ✓ |

## 下载安装

1. 从 [最新版本](https://github.com/StillDear/DiscSplitter/releases/latest) 下载 `DiscSplitter-Setup-<版本号>.exe`。
2. 运行安装包，按提示完成安装。
3. 从开始菜单打开 **DiscSplitter**，然后打开一张光盘。

| | |
|---|---|
| **系统** | Windows 10 或 11，64 位 |
| **已包含** | 蓝光引擎（tsMuxeR）、MKVToolNix、ffmpeg，不用另外安装 |
| **设置和日志** | `%USERPROFILE%\.disc_splitter` |

> [!NOTE]
> DiscSplitter 不是抓轨/解密工具。加密的光盘要先用别的工具解密。

## 常见问题

<details>
<summary><b>音频会被重新编码吗？</b></summary>
<br>

不会。导出 M2TS 和 MKV 时所有流都原样复制。只有 FLAC 需要编码，而 FLAC 本身也是无损的。

</details>

<details>
<summary><b>为什么带视频的文件有时会比章节稍长一点？</b></summary>
<br>

视频只能在关键帧处切。蓝光自带的章节点本来就在关键帧上，所以按原章节切是精确的（文件末尾可能多出一个画面组）。手动挪过的分界会对齐到下一个关键帧，通常不到一秒。只导出音频时可以精确切。

</details>

<details>
<summary><b>在线搜索什么都没找到怎么办？</b></summary>
<br>

小众或地区性的版本经常查不到。可以从演唱会的网页上复制歌单粘贴进来，或者直接填网页链接，也可以给封底拍张照让软件识别。**设置 → 在线元数据** 里可以设置代理和超时，搜索页上也能检查网络连接。

</details>

<details>
<summary><b>支持 macOS 或 Linux 吗？</b></summary>
<br>

暂时不支持，目前只在 Windows 上开发和测试。

</details>

## 局限

- 不支持加密光盘，需要先解密。
- 保留视频时切点落在关键帧上（见 [常见问题](#常见问题)）。
- 仅支持 Windows。

## 从源码运行

Windows 上需要 Python 3.10 或更高版本：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

编译蓝光引擎、运行测试和制作安装包，见 [docs/development.zh-CN.md](docs/development.zh-CN.md)。

## 许可证与致谢

DiscSplitter 以 [MIT 许可证](LICENSE) 发布。

- 蓝光引擎：[tsMuxeR](https://github.com/teaching-droid/tsMuxer)，Apache License 2.0（[许可证](engine/tsmuxer/LICENSE)、[NOTICE](engine/tsmuxer/NOTICE)），用 zlib 编译。
- 安装包还附带了 [MKVToolNix](https://mkvtoolnix.download/) 和 [ffmpeg](https://ffmpeg.org/)，它们各自的许可证随程序装在 `tools\licenses` 里。
- 曲目数据来自 [MusicBrainz](https://musicbrainz.org/)、Apple Music、[Deezer](https://www.deezer.com/) 和 [Discogs](https://www.discogs.com/)。
