# 部署记录 · 账号安全加固（密码规则统一 + 时序侧信道修复 + 登录注册限流）

日期：2026-07-23

## 背景

延续登录/注册模块审查（`handoff/2026-07-23-codex-login-registration-review.md`）和限流方案定案（`handoff/2026-07-23-codex-handoff-19.md`），Codex 一次性完成三项加固：密码规则统一、登录时序侧信道修复、登录/注册限流。交接文档：`handoff/2026-07-23-codex-account-security-hardening-handoff.md`（提交 `d0a7a12`，直接提交在 master 上，无独立分支）。

## 审查结论

审查通过：

- **密码规则统一**：新增 `_password_error`/`_username_error`/`_display_name_error` 服务层校验函数，`create_user`/`update_user`/`change_password`/`reset_password` 全部统一走 6 位下限 + 72 字节上限（bcrypt 截断边界）。`create_user`/`update_user` 新增 `IntegrityError` 捕获转换为业务错误（并发同名建号场景）。
- **时序侧信道修复**：`verify_password` 在用户名不存在时，也对固定 dummy hash 执行一次 `bcrypt.checkpw`，让"不存在"和"存在但密码错"两条路径耗时接近；顺带处理了超长密码（>72字节）直接判定不匹配前也先执行一次 dummy checkpw，避免因为跳过 bcrypt 而产生新的耗时差异。
- **限流实现**：`backend/rate_limit.py` 用 `Flask-Limiter` + 内存存储，`get_client_ip()` 优先读 `X-Real-IP`（回退 `remote_addr`），登录按账号（5分钟5次）和IP（5分钟20次）双维度限流，注册按IP（1小时5次，且仅在 `ALLOW_REGISTER=true` 时计数），成功登录清零该账号失败计数（不影响IP维度），429 走标准 `Result.fail().to_response(429)`。
- 新增 `test_account_security_hardening.py` 12 个测试，覆盖全部密码入口、并发唯一键异常转换、时序侧信道（断言两条路径都执行了 bcrypt 调用）、账号/IP双维度限流触发、成功登录后限流清零、`X-Real-IP` 缺失回退、注册限流与"注册关闭时豁免计数"。
- 本地复跑：`pytest` 152 passed，`compileall` 通过。`git diff --check` 对新增文档有 markdown 行尾双空格（软换行语法）提示，非代码问题，忽略。Alembic 单头确认（`20260721_04`）。

## 发现并修正的问题：依赖锁文件版本不实

Codex 提交的 `requirements-lock-py311-linux.txt` 里 `rich==15.0.0`，但这是在**未实际执行过 `pip install Flask-Limiter`** 的环境生成的。`Flask-Limiter` 的依赖链约束 `rich<14`，真正在生产 Python 3.11 环境安装后，`rich` 会被降级到 `13.9.4`。

处理过程：

1. 在服务器执行 `pip install 'Flask-Limiter>=3.12,<4.0'`，观察到 pip 主动把已安装的 `rich 15.0.0` 卸载并装回 `13.9.4`（`Flask-Limiter` 依赖约束触发）。
2. 确认 `rich` 不是后端代码直接 import 的依赖（只在 `requirements-lock` 里作为传递依赖出现），`typer`/`alembic` 降级后仍正常 import，无功能影响。
3. 第一次运行 `capture_requirements_lock.py` 生成的锁文件缺失 `Flask-Limiter`/`limits`/`Deprecated`/`ordered-set`/`wrapt` 全部5个新依赖——原因是脚本从 `requirements.txt` 的直接依赖出发做闭包搜索，而当时服务器上的 `requirements.txt` 还是旧版本（没有 `Flask-Limiter` 那行），我在此之前忘记先上传 `requirements.txt`。
4. 补传 `requirements.txt` 后重新运行脚本，正确生成 66 个包的锁文件，`rich==13.9.4` 与本地 diff 后确认这是唯一差异，其余全部一致。
5. 把 `rich==15.0.0` 改回 `rich==13.9.4` 提交到仓库（`d5de3e1`），本地重跑 `test_dependency_locking.py` 4 项通过。

这个问题印证了 Codex 交接里"生产环境安装后必须重新生成锁文件快照"这条提醒是必要的——锁文件本该反映真实解析结果，而不是开发环境里孤立跑一遍 pip 得到的理论值。

## 部署

1. 确认服务器无导入/resolve 任务在跑。
2. **先装依赖**：`pip install 'Flask-Limiter>=3.12,<4.0'`（观察到 `rich` 联动降级）。
3. 上传 `requirements.txt`，md5 核对一致。
4. 在服务器重新运行 `capture_requirements_lock.py`，与本地生成结果 diff，发现并修正 `rich` 版本差异，提交修正。
5. 上传代码文件：`app.py`、`rate_limit.py`（新文件）、`routes/account/__init__.py`、`services/account/__init__.py`，md5 逐一核对一致。
6. 上传修正后的 `requirements-lock-py311-linux.txt`，md5 核对一致。
7. `systemctl reload gunicorn`；8秒后复查：master pid 2151 未变，新 worker（10810）干净启动，无崩溃记录（确认 `flask_limiter` import 成功，否则 worker 会直接启动失败）。
8. `/health`、`/ready` 均 200。
9. **端到端功能验证**：对不存在的用户名 `__ratelimit_probe_claude__` 连续发起6次错误密码登录请求，前5次均返回 400（"用户名或密码错误"），第6次返回 429（"尝试次数过多，请稍后重试"），限流规则确认生效。

## 影响说明

- 无数据库结构变更、无前端接口契约变更（429 响应格式已被 `http.js` 提前适配，见 `b3c2917`）。
- 密码规则收紧：6位以下密码此后在任何入口（注册/管理员创建/修改/重置）都会被拒绝，此前部分入口无此限制。
- 登录/注册新增限流，正常使用不受影响（阈值远高于误操作场景），但需留意如果有自动化脚本/集成测试频繁调用登录接口，可能触发限流。
- `rich` 版本从（理论上的）15.0.0 变为实际的 13.9.4，仅影响 CLI 富文本渲染这类边缘功能（如果有的话），未在项目代码中发现直接依赖。

## 未处理项

- 注册后角色语义（自动给 guest vs 待审批空账号）仍待决策，本批未改动，`api.md` 与实现的契约冲突继续存在。
