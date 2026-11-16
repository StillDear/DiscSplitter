"""
The built-in help page's text, in both interface languages.

Each section is a list of entries, {title, body}; the Chinese and English lists run in the same
order, one entry for one entry (a test holds them to that). Button names are written the way the
interface shows them, so a reader can find what an entry talks about. Keep bodies to a few short
sentences and out of internal terms (playlist IDs, PIDs, tool names where the user never meets them).
"""
from __future__ import annotations

SECTIONS = ('guide', 'tips', 'faq', 'troubleshoot')

ZH = {
    'guide': [
        dict(title='打开光盘',
             body='把蓝光或 DVD 的文件夹、ISO 镜像，或者带章节的 MKV 拖进窗口，也可以点「选择文件夹」「选择 ISO / MKV」。'
                  '软件会自动选出正片，并在左侧说明为什么选它。'),
        dict(title='选章节和音轨',
             body='勾选要导出的章节、音轨和字幕。音质最好的无损音轨已经默认选好；「内容」列会标出哪些章节是 MC 或过场，方便去掉。'),
        dict(title='获取曲名',
             body='点「获取曲名」，可以用光盘自带的名字、在线搜索、粘贴曲目，或者原盘同目录下的曲目表文件。软件按时长把歌曲对到章节上，'
                  '你在核对页逐条确认后再应用。'),
        dict(title='导出',
             body='在左上角选 M2TS、MKV 或 FLAC，然后导出。导出前会检查剩余空间，导出后逐个检查文件；'
                  '中途取消或意外关闭，下次打开会提示从停下的地方继续。'),
    ],
    'tips': [
        dict(title='随时试听',
             body='点章节前面的播放按钮就能试听；双击时间轴上的一段，从那里开始播放。双击画面可以放大。'),
        dict(title='一键去掉 MC',
             body='获取曲名后，用「只选已改名」或「不选未命名」，没有曲名的 MC 和过场就不会被导出。'),
        dict(title='调整章节',
             body='点章节行最右边的三个点，可以与上一章或下一章合并，或在当前播放位置拆分。改乱了可以点「恢复原始章节」。'),
        dict(title='条码搜索最准',
             body='在线搜索时点「按条码搜索」，填封底的 UPC / EAN 条码，比按名字搜准确得多。'),
        dict(title='网页和截图也能当曲目表',
             body='在「粘贴曲目」里可以直接输入官网、维基百科等网页地址，或者用「识别截图…」读取封底照片或网页截图。'),
        dict(title='整理曲名',
             body='核对页的「去掉括号」可以一次清掉曲名里的 (Live)、[Remaster] 之类的附注。'),
        dict(title='搜索结果带封面',
             body='在 设置 → 在线元数据 里填一个免费的 Discogs 个人令牌，Discogs 的搜索结果会带封面，次数限制也更宽。'),
        dict(title='界面太小或太大',
             body='在 设置 → 外观 里可以调整界面缩放和字体大小，深色、浅色主题和强调色也在那里。'),
    ],
    'faq': [
        dict(title='为什么打不开我的蓝光？',
             body='DiscSplitter 不能读取加密的光盘。请先用其他工具解密，再打开解密后的文件夹或 ISO。'),
        dict(title='自动选的不是正片怎么办？',
             body='左侧「播放列表」里列出了所有候选，点另一个就能切换。每个候选下面写了时长、章节数和音轨，方便比较。'),
        dict(title='会重新编码、损失音质吗？',
             body='不会。M2TS 和 MKV 都是原样复制画面和声音。只有 FLAC 需要编码，而 FLAC 本身也是无损的。'),
        dict(title='为什么没有 M2TS 选项？',
             body='M2TS 只能从蓝光导出，DVD 和 MKV 来源只能导出 MKV 或 FLAC。'),
        dict(title='带视频的文件为什么比章节长一点？',
             body='视频只能在关键帧处切开。蓝光自带的章节点就在关键帧上，所以切得很准；手动挪过的分界会对齐到下一个关键帧，'
                  '通常不到一秒。只导出音频时可以精确切。'),
        dict(title='在线搜索什么都没找到',
             body='小众或地区性的版本经常查不到。可以只填专辑名、改用条码，或者把官网的曲目表粘贴进来、给封底拍照识别。'
                  '连不上网时，在搜索页点「检查连接」，或在 设置 → 在线元数据 里设置代理。'),
        dict(title='提示缺少工具',
             body='安装版已经自带全部工具，一般不会出现。如果出现了，到 设置 → 外部工具 点「重新检测」，'
                  '或者点「浏览」找到工具所在的位置。'),
        dict(title='文件、设置和日志存在哪？',
             body='导出的文件在你选的输出文件夹里，每张光盘一个专辑文件夹。设置和日志在 %USERPROFILE%\\.disc_splitter，'
                  '可以在下面「问题排查与反馈」里直接打开。'),
    ],
    'troubleshoot': [
        dict(title='先检查外部工具',
             body='很多问题来自工具没找到。点下面的「重新检测」，看看是不是都显示「已找到」。'),
        dict(title='再看看日志',
             body='导出时出的问题会写进日志。导出页的「实时日志」可以看当前这次，日志文件夹里有之前的。'),
        dict(title='还是不行，就告诉我们',
             body='点「复制诊断信息」，再点「报告问题」，把诊断信息粘贴进去，写清楚做了什么、看到了什么。'
                  '诊断信息只有版本号、系统版本和工具状态，不含文件路径。'),
    ],
}

EN = {
    'guide': [
        dict(title='Open a disc',
             body='Drop a Blu-ray or DVD folder, an ISO image, or an MKV with chapters onto the window, or use '
                  'Choose folder / Choose ISO / MKV. The main feature is picked for you, with the reasons shown on the left.'),
        dict(title='Pick chapters and tracks',
             body='Tick the chapters, audio and subtitles to export. The best lossless audio is already chosen, and the '
                  'Content column marks MCs and interludes so they are easy to leave out.'),
        dict(title='Get titles',
             body='Click Get titles and use the disc\'s own names, an online search, a pasted list, or a tracklist file next to the disc. Songs are '
                  'matched to chapters by length, and you check each one on the review page before applying.'),
        dict(title='Export',
             body='Pick M2TS, MKV or FLAC at the top left and export. Free space is checked first and every file is '
                  'checked afterwards. If an export is cancelled or the app closes, you can resume where it stopped.'),
    ],
    'tips': [
        dict(title='Listen any time',
             body='Click the play button in front of a chapter to listen, or double-click a stretch of the timeline to play from '
                  'there. Double-click the picture to enlarge it.'),
        dict(title='Drop the MCs in one click',
             body='After getting titles, use Only renamed or Skip unnamed so chapters without a song are not exported.'),
        dict(title='Adjust chapters',
             body='The three-dot button at the end of a chapter row merges it with the previous or next one, or splits it at the playback '
                  'position. Restore original chapters undoes it all.'),
        dict(title='A barcode finds the right release',
             body='In an online search, click Search by barcode and enter the UPC / EAN from the back cover. It is far '
                  'more precise than a name.'),
        dict(title='Web pages and screenshots work too',
             body='In Paste list you can enter a web address (official site, Wikipedia…) or use Read a screenshot… on a '
                  'photo of the back cover or a screenshot of a page.'),
        dict(title='Tidy the titles',
             body='Remove brackets on the review page clears notes like (Live) or [Remaster] from every title at once.'),
        dict(title='Covers in search results',
             body='Add a free Discogs personal token in Settings → Online metadata to get covers in Discogs results and a '
                  'higher rate limit.'),
        dict(title='Text too small or too large',
             body='Settings → Appearance has interface scale and text size, as well as dark and light themes and the accent colour.'),
    ],
    'faq': [
        dict(title='Why won\'t my Blu-ray open?',
             body='DiscSplitter cannot read encrypted discs. Decrypt the disc with another tool first, then open the '
                  'decrypted folder or ISO.'),
        dict(title='The wrong title was picked',
             body='Every candidate is listed under Playlist on the left; click another to switch. Each one shows its '
                  'length, chapters and audio so you can compare.'),
        dict(title='Is anything re-encoded?',
             body='No. M2TS and MKV copy picture and sound as they are. Only FLAC encodes, and FLAC is lossless.'),
        dict(title='Why is there no M2TS option?',
             body='M2TS is only offered for Blu-rays. DVD and MKV sources export to MKV or FLAC.'),
        dict(title='Why does a file with video run slightly long?',
             body='Video can only be cut on a keyframe. A Blu-ray\'s own chapter marks sit on keyframes, so those cuts '
                  'are exact; a boundary you moved snaps to the next keyframe, usually well under a second away. '
                  'Audio-only exports cut exactly.'),
        dict(title='The online search found nothing',
             body='Small or regional releases are often missing. Try the album alone or the barcode, paste the list from '
                  'the official site, or photograph the back cover. If you are offline, use Check connection on the '
                  'search page, or set a proxy in Settings → Online metadata.'),
        dict(title='It says tools are missing',
             body='The installer includes every tool, so this is rare. If it happens, click Check again in Settings → '
                  'External tools, or use Browse to point at the tool.'),
        dict(title='Where are my files, settings and logs?',
             body='Exports go to the output folder you chose, one album folder per disc. Settings and logs are in '
                  '%USERPROFILE%\\.disc_splitter; you can open it under Troubleshooting below.'),
    ],
    'troubleshoot': [
        dict(title='Check the tools first',
             body='Many problems come from a tool that was not found. Click Check again below and see that each one says Available.'),
        dict(title='Then look at the log',
             body='Export problems are written to the log. Live log on the export page shows the current one; earlier '
                  'ones are in the log folder.'),
        dict(title='Still stuck? Tell us',
             body='Click Copy diagnostics, then Report issue, and paste them in with what you did and what you saw. '
                  'Diagnostics hold only the version, Windows version and tool status, no file paths.'),
    ],
}

CONTENT = {'zh': ZH, 'en': EN}


def content(language: str) -> dict:
    return CONTENT.get(language, ZH)
