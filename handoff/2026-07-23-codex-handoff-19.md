# 交接说明 · Claude → Codex（第十九轮，登录/注册限流方案定案）

日期：2026-07-23

用户明确表示"按常规方式处理，你和 Codex 决定"，不用继续等产品侧拍板。方案定下来了，可以直接开始实现。

## 技术选型：`Flask-Limiter`，内存存储

不自己写计数器，用 Flask 生态的标准限流库 `Flask-Limiter`。存储后端选内存（`storage_uri="memory://"`），理由：

- 生产是单 Gunicorn worker（`-w 1`），不存在多进程/多机计数不一致的问题，不需要 Redis。
- 引入 Redis 是新的运维成本，这台机器目前没有，且内存本就紧张（1.675GB，MySQL 占约400MB，gunicorn 占约190MB），不建议为了限流单独起一个 Redis 进程。
- 进程重启会清零计数器，可接受（重启本来就不频繁，清零最坏情况是限流窗口提前重置，不是安全问题）。

## 真实客户端 IP 获取

我已经查过服务器 nginx 配置（`/etc/nginx/conf.d/tmt-library.conf`）：已经设置了 `proxy_set_header X-Real-IP $remote_addr;`，但后端目前完全没有读这个头，`request.remote_addr` 拿到的会是 nginx 的地址，不是真实客户端 IP。

请在配置 `Flask-Limiter` 的 `key_func` 时，用 `X-Real-IP` 头取值（没有则 fallback 到 `request.remote_addr`，兼容本地开发环境没走 nginx 的情况）。

## 限流规则

- **登录** `POST /api/account/login`：
  - 按账号（`username` 字段）维度：5分钟内失败5次 → 429；
  - 按 IP 维度：5分钟内失败20次 → 429（覆盖"同IP轮换用户名枚举"场景，正好配合这批要修的登录时序侧信道问题）；
  - 登录成功后清零该账号的失败计数（`Flask-Limiter` 有对应的 reset 机制，或者用装饰器只在失败路径计数）。
- **注册** `POST /api/account/register`：按 IP 维度，1小时内最多5次（仅在 `ALLOW_REGISTER=true` 时生效，反正接口默认关闭）。

具体阈值不是精确科学，按常规经验值定的，如果后续观察到误伤真实用户（比如公司共享出口IP），再调整，不用现在就设计成可配置项。

## 响应格式

429 时走现有 `Result.fail(...).to_response(429)`，消息文案类似"尝试次数过多，请稍后重试"。不需要额外加 `Retry-After` 头之类的精细化处理，现有错误提示模式已经够用。

## 前端已经改好，不需要你处理

我已经确认并修复了一个衔接问题：`src/api/http.js` 的响应拦截器之前只对 400 状态码做特殊处理（解析响应体让页面读 `res.message`），429 会落到默认分支被直接 reject，页面 `catch` 块只会显示笼统的"网络错误，请重试"，看不到真正的限流提示。已经把 429 加进那个特殊处理分支（和 400 一路），已构建部署到生产。你只需要保证后端 429 响应体是标准 `Result.fail()` 格式（带 `message` 字段），前端就能正确显示。

## 提交要求

- 补真实请求测试：连续失败触发 429、成功登录后计数清零、429 响应体格式正确、`X-Real-IP` 缺失时正确 fallback。
- 照例本地 `pytest`+`compileall`+`git diff --check`，写交接文档。
- 这批可以和之前交接的第1项（密码规则统一）分开提交，也可以合并，你看哪个更方便测试和回滚。

依赖变化：`Flask-Limiter` 是新增的三方库，记得更新 `requirements.txt`（如果项目用这个管理依赖）并在交接文档里注明版本号，部署时我需要在服务器上装这个包。
