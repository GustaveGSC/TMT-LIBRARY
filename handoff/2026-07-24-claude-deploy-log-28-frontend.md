# Claude 部署记录：前端批次合并部署（仓库过滤权限 / 分类树共享缓存 / 409任务冲突）

日期：2026-07-24

## 合并

`worktree-frontend-viewer-tree-409` 分支（commit `ea80e99`）以 `--no-ff` 合并进 `master`，
与售后正确性批次（`b06150b`/`59945ea`）无文件重叠，合并无冲突。

## 验证

- `npm run build:web`：通过。
- 全量 Playwright（46 用例，含 5 个本批新增 + 41 个既有响应式回归）：全部通过，无回归。

## 部署

`tar` 打包 `dist-web/` → `scp` → 服务器端解压覆盖 `/var/www/tmt-library/`，部署后比对线上
`index.html` 引用的 `assets/index-*.js` hash 与本地构建一致（`index-OiChdwnH.js`），确认后删除
`.old` 备份目录。`https://tmt-library.cn/` 返回 200。

本批为纯前端静态资源，无需重启/reload 后端。
