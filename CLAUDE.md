# DiscSplitter 项目规则

所有会话都按这里的规则做。这里的规则优先于默认做法。

## 沟通

- 用中文回复。代码、提交信息、标识符保持英文。

## Git

- **直接在 `main` 上提交**，不要先建临时分支再快进。
- 只在我要求时提交。提交前用 `git add <文件>` 只加入这次任务改动的文件；工作区里别的未提交改动可能是我或其他会话的，不要夹带，也不要还原。
- **每次推送前都先问我**，包括推送标签。「提交」不等于「推送」。
- 提交信息用英文：标题写「范围: 改了什么」，例如 `Help: a built-in help page, …`，需要时正文用要点列出；结尾按系统给的 Co-Authored-By 署名。

## 测试

改了 Python 或 QML 后，提交前先跑：

```powershell
.venv\Scripts\python.exe -m pytest -q
$env:QT_QPA_PLATFORM = "offscreen"; .venv\Scripts\python.exe app.py --smoke-test
```

冒烟测试必须是零警告。

## 界面文字与帮助

- 界面上的每条文字都写在 `gui/i18n.py`，中英文成对。
- 帮助正文写在 `gui/help_content.py`，中英文条目一一对应。帮助里提到的按钮名必须和界面上的完全一致，`tests/test_help.py` 会检查。
- 不要用依赖字体的符号当图标（例如 ⋯、✓），图标都在 `qml/Icon.qml` 里画。

## 打包与发布

- 安装包文件名：`DiscSplitter_<版本号>_Windows_x64_Setup.exe`。
- 测试包不传版本号，`packaging\build_installer.bat` 默认用当天日期（`YYYY.MM.DD`）。正式版用 `--version <x.y>`，例如 `--version 1.1`。
- 正式发版的步骤：
  1. 用 `--version` 打包；
  2. 对打包后的程序跑 `--smoke-test`；
  3. 打标签 `v<x.y>`，问过我再推送；
  4. 在 GitHub 上建 Release，附上安装包，说明里写 SHA-256 和附带工具（tsMuxeR、FFmpeg、MKVToolNix）的版本和源码链接；
  5. 更新两个 README 顶部下载按钮和版本徽章里的版本号。

## 文档

- `README.md`（英文）和 `README.zh-CN.md`（中文）一起改，内容保持一致；`docs/development.md` 和 `docs/development.zh-CN.md` 也一样。
- README 截图放在 `docs/images/en/` 和 `docs/images/zh/`，两边文件名相同，说明见 `docs/images/SHOTS.md`。
