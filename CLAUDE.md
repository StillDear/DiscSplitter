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

## 打包命名

| 用途 | 版本号 | 安装包文件名 | 标签 | Release 标题 |
|---|---|---|---|---|
| 正式版 | `<主>.<次>[.<修订>]`，例如 `1.1`、`1.1.1`（见「版本迭代」） | `DiscSplitter_1.1_Windows_x64_Setup.exe` | `v1.1` | `DiscSplitter 1.1` |
| 测试包 | 当天日期 `YYYY.MM.DD` | `DiscSplitter_2026.11.16_Windows_x64_Setup.exe` | 不打标签 | 不发布 |

- 文件名的格式是 `DiscSplitter_<版本号>_Windows_x64_Setup.exe`，各部分之间用下划线 `_`，由 `packaging/DiscSplitter.iss` 生成，不要手动改名。
- 我只说「打包」时，打测试包：不传 `--version`，脚本会默认用当天日期。
- 我说「发布」「正式版」或者给了版本号时，用 `--version <x.y>` 打正式版。版本号没说清楚就先问我。
- 上传到 Release 的附件名和打包出来的文件名保持一致。

## 版本迭代

| 改动 | 升哪一段 | 例子 |
|---|---|---|
| 只修 bug，没有新功能 | 修订号 | `1.1` → `1.1.1` → `1.1.2` |
| 有新功能或明显的界面变化 | 次版本号，修订号归零 | `1.1.2` → `1.2` |
| 大改版，或旧设置、输出方式不再兼容 | 主版本号，后面归零；先问我 | `1.4` → `2.0` |

- 修订号是 0 时不写：写 `1.2`，不写 `1.2.0`。
- 上一个正式版之后在 `main` 上的提交，都算下一个版本的内容。
- 发版前，用 `git log v<上一版>..HEAD` 看这段时间的提交，按上表判断该升哪一段，再写中英文发布说明（新功能、修复、附带工具版本、SHA-256）。版本号和说明先给我看，确认后再打包发布。
- 版本号不写死在代码里，只由打包时的 `--version` 决定；程序在「关于」里读到的就是它。
- 标签发布后不移动、不重用。发错了就发下一个修订号。

## 发布

- 正式发版的步骤：
  1. 用 `--version` 打包；
  2. 对打包后的程序跑 `--smoke-test`；
  3. 打标签 `v<x.y>`，问过我再推送；
  4. 在 GitHub 上建 Release，附上安装包，说明里写 SHA-256 和附带工具（tsMuxeR、FFmpeg、MKVToolNix）的版本和源码链接；
  5. 更新两个 README 顶部下载按钮和版本徽章里的版本号。

## 文档

- `README.md`（英文）和 `README.zh-CN.md`（中文）一起改，内容保持一致；`docs/development.md` 和 `docs/development.zh-CN.md` 也一样。
- README 截图放在 `docs/images/en/` 和 `docs/images/zh/`，两边文件名相同，说明见 `docs/images/SHOTS.md`。
