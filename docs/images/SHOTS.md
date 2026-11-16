# Screenshots for the README / README 截图清单

The READMEs already contain the markup for these images inside HTML comments. Drop the files here with the exact names below, then delete the comment's opening `<!--` and closing `-->` lines in both `README.md` and `README.zh-CN.md`.

README 里已经写好了这些图片的代码，放在 HTML 注释里。按下面的文件名把图片放进本文件夹，再把 `README.md` 和 `README.zh-CN.md` 里对应注释开头的 `<!--` 和结尾的 `-->` 两行删掉即可。

| File / 文件 | Screen / 页面 | What to show / 拍摄内容 | Required / 必需 |
|---|---|---|:---:|
| `workspace-light.png` | Workspace, light theme / 工作区，浅色 | A real Blu-ray open, titles filled in, a frame visible in the preview, one row selected / 打开一张真实蓝光，曲名已填好，预览区有画面，选中一行 | ✓ |
| `workspace-dark.png` | Workspace, dark theme / 工作区，深色 | Same scene as above / 和上面同一画面 | ✓ |
| `review.png` | Review titles / 核对曲名 | An online search result matched to chapters / 在线搜索结果已对到章节上 | |
| `done.png` | Export finished / 导出完成 | Files written and verified / 文件已写出并校验通过 | |

Tips / 拍摄建议

- Window size 1280 × 800 at 100 % scale, so every image has the same width and text stays readable on GitHub. / 窗口 1280 × 800，缩放 100%，所有图宽度一致，在 GitHub 上文字清晰。
- Use the English interface for `README.md` images if you want separate sets; otherwise one set is fine for both. / 如果想中英文各一套，可以另存 `*-zh.png`；否则一套图两个 README 共用。
- Hide personal details: user name in paths, drive letters you would rather not show. / 遮掉路径里的用户名等个人信息。
- Save as PNG; keep each file under about 500 KB (e.g. run it through an optimiser). / 存为 PNG，每张尽量控制在 500 KB 以内。
- `app.py --smoke-screenshots <folder>` renders every screen with demo data; useful for checking layout, but the README should show a real disc. / `app.py --smoke-screenshots <文件夹>` 能用演示数据导出所有页面，可用来检查布局，但 README 里应该放真实光盘的截图。
