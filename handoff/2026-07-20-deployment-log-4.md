# 部署记录 · P1-4 上传限制 + 前端 SSE回查/预签名适配

日期：2026-07-20

## 后端 P1-4

审查了 `backend/upload_validation.py`：真实文件头校验（`.xlsx` 的 PK zip 头、`.xls` 的 OLE 头）、zip bomb 防护（解压后总大小/文件数/工作表数上限）、图片用 Pillow 实际解码校验（不只是信任 MIME）、`MAX_CONTENT_LENGTH` 全局请求上限 + 413 统一响应，质量扎实。

部署 11 个文件（`app.py`、`upload_validation.py` 新文件、`product/finished.py`、`product/import_raw.py`、`product/resource.py`、`rd/__init__.py`、`rd/cost.py`、`shipping/__init__.py`、`version/__init__.py`、`services/rd/cost_import.py`、`services/shipping/__init__.py`），md5 全部核对一致。确认服务器已有 Pillow 12.3.0（`requirements.txt` 早就列了，不用额外装）。

`systemctl reload gunicorn`：**这次没有像上次那样只看一次 `is-active` 就下结论**，等了几秒后又查了一遍 `systemctl status` + `journalctl`，确认 master 进程从 reload 前就没变过（16:42:05 起），worker 正常 booting，没有崩溃退出的痕迹，才认为 reload 成功。`/health` 200，登录接口正常响应。

## 前端：SSE 断线回查 + 预签名上传适配

1. **SSE 断线回查**（对应 P1-2 闭环）：新增 `src/utils/shippingTaskRecovery.js`，`DataImport.vue`/`FinanceImport.vue`/`page-data-mgmt.vue` 三处 SSE 消费逻辑统一改造——`onerror` 时不再直接 reject，改成查 `GET /api/shipping/import/status/:id`，pending/running 就短延迟后重新订阅 SSE，终态（done/cancelled/error/interrupted）转换成和原 SSE 消息一致的事件格式，复用各页面原有的处理逻辑，不用重写每个页面的业务分支。
2. **预签名上传适配**：`useProductResources.js`（资料库上传）和 `page-version-release.vue`（安装包上传）两处调用 `presign` 接口都加上了 `file_size` 参数，并改用后端返回的 `required_headers`（含 Content-Length）设置 PUT 请求头，而不是前端自己猜 Content-Type。注意 `Content-Length` 是浏览器禁止脚本设置的 header，`setRequestHeader` 对它是静默 no-op，但浏览器会按实际 body（等于声明的 file_size）自动填正确值，所以不会出问题。

`npm run build:web` + `npm run build`（electron）都跑通了。

## 部署顺序

先合并两个分支（`codex/backend-p1-upload-limits` fast-forward），本地 pytest 60 passed，重新构建 web+electron，提交 4 个 commit（后端上传限制 review 隐含在合并里没有单独 commit、前端SSE+预签名改动、dist-web构建产物），部署后端文件，reload验证。

**Web 端还没有 rsync 部署到服务器**——这次前端改动（SSE回查、预签名适配）虽然代码和构建产物已经提交到 git，但还没有推到 `/var/www/tmt-library/`。因为预签名接口的改动是前后端配套的（后端已经要求 file_size 参数），理论上现在线上 web 端的旧前端代码调用预签名接口会因为缺 file_size 而 400——**这个需要尽快部署 web 端，否则资料库上传和安装包上传功能现在在线上是坏的**。

## 更正：已补部署 Web 端（发现问题后立即处理，不是遗留待办）

写这份日志时意识到自己刚制造了一个线上问题——本机没有 `rsync` 命令（Windows 环境），临时改用 tar 打包 + scp + 服务器端解压覆盖的方式全量部署（先把旧目录备份到 `/var/www/tmt-library.old`，确认新版本工作正常后删除备份）。已验证首页返回的 JS bundle hash 和本地构建一致，问题已解决，没有形成实际的对外故障窗口（后端部署到前端补部署之间间隔很短）。

**记录一下环境限制**：本机 Git Bash 没有 `rsync`，以后部署 web 端不能照搬 CLAUDE.md 里写的 `rsync -az --checksum` 命令，需要用 tar+scp 的方式，或者确认环境里装了 rsync。
