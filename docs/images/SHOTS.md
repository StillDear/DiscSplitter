# README screenshots / README 截图

`README.md` uses the English set in `en/`, `README.zh-CN.md` the Chinese set in `zh/`. Both sets have the same file names, so a screenshot is replaced by saving the new one over the old.

`README.md` 用 `en/` 里的英文界面截图，`README.zh-CN.md` 用 `zh/` 里的中文界面截图。两套文件名相同，替换时直接用新图覆盖旧图即可。

| File / 文件 | Screen / 页面 | Where in the README / 用在哪里 |
|---|---|---|
| `workspace-light.webp` | Workspace, light theme / 工作区，浅色 | Top of the page, for readers in light mode / 首屏，浅色模式的访客看到 |
| `workspace-dark.webp` | Workspace, dark theme / 工作区，深色 | Top of the page, for readers in dark mode / 首屏，深色模式的访客看到 |
| `review.webp` | Review titles / 确认曲名 | Under "How it works" / 「使用流程」下方 |
| `done.webp` | Export finished / 导出完成 | Under "How it works" / 「使用流程」下方 |
| `metadata.webp` | Metadata / 元数据 | "More screenshots" / 「更多截图」 |
| `export.webp` | Export in progress / 导出进行中 | "More screenshots" / 「更多截图」 |

`social-preview.png` (1280 × 640) is the repository's social preview, shown when a link to it is shared. It is built from `logo.png` and `en/workspace-dark.webp`, and is uploaded by hand in the repository's **Settings → General → Social preview**.

`social-preview.png`（1280 × 640）是仓库的社交预览图，分享仓库链接时显示。它由 `logo.png` 和 `en/workspace-dark.webp` 合成，需要在仓库 **Settings → General → Social preview** 里手动上传。

Taking new ones / 重新拍摄时

- Same window size for every shot (the current set is 2000 × 1194), so the images line up. / 每张窗口大小一致（现在这套是 2000 × 1194），排版才整齐。
- WebP keeps each file around 60–170 KB. / 存成 WebP，每张大约 60–170 KB。
- Check the paths shown on screen for anything you would rather not publish. / 检查画面里显示的路径，有不想公开的信息先遮掉。
- `app.py --smoke-screenshots <folder>` renders every screen with demo data, useful for checking layout, not for the README. / `app.py --smoke-screenshots <文件夹>` 能用演示数据导出所有页面，适合检查布局，不用于 README。
