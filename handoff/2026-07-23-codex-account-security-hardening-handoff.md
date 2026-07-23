# Codex 交接：账号安全加固（密码、时序、限流）

日期：2026-07-23  
状态：后端实现完成，未部署。

## 完成内容

### 1. 统一服务层输入和密码规则

- 密码规则统一为至少 6 个字符、UTF-8 编码不超过 bcrypt 的 72 字节边界。
- `create_user()`、`update_user()`、`change_password()`、`reset_password()` 全部使用同一校验规则。
- 用户名和显示名称在服务层校验数据库列的 64 字符上限。
- 用户创建/改名时捕获并发唯一键冲突，回滚会话并返回稳定业务错误。

### 2. 修复登录用户名枚举时序差异

- 用户不存在时执行固定 dummy bcrypt 校验，不再提前快速返回。
- 用户存在和不存在的失败响应继续使用相同的“用户名或密码错误”文案。
- 超过 bcrypt 72 字节的登录密码也走固定 bcrypt 工作量并返回通用认证失败。

### 3. Flask-Limiter 登录/注册限流

- 新增 `backend/rate_limit.py`，内存存储，适配生产单 worker。
- 登录失败：
  - 同账号 5 分钟 5 次；
  - 同 IP 5 分钟 20 次；
  - 登录成功仅清除该账号失败计数，不清 IP 计数。
- 注册开启时同 IP 每小时最多 5 次；注册关闭期间请求不占用额度。
- 优先读取 nginx 覆盖的 `X-Real-IP`，本地回退 `request.remote_addr`。
- 超限返回标准 HTTP 429 和 `{success:false,message:"尝试次数过多，请稍后重试"}`。

## 依赖和部署顺序

新增直接依赖：`Flask-Limiter>=3.12,<4.0`，本地验证版本为 3.12。

`requirements-lock-py311-linux.txt` 已补入本地解析得到的 Flask-Limiter 3.12 及其新增依赖版本，**部署前仍须在生产兼容的 Linux/Python 3.11 环境安装后运行锁定脚本复核/重生成**，不能把 Windows 环境当作最终生产快照。

后端代码现在在 `app.py` 顶层导入 Flask-Limiter，因此部署顺序必须是：

1. 服务器安装/核对依赖；
2. 更新生产锁定快照并带回仓库（若结果有差异）；
3. 上传代码；
4. reload 并按既定方式检查 worker 日志与 `/health`、`/ready`。

如果先上传代码再装依赖，worker reload 会因 `ModuleNotFoundError` 启动失败。

## 自动化验证

- `python -m pytest backend/tests -q`：152 passed。
- 新测试覆盖：
  - 创建、更新、修改、重置密码的服务层规则；
  - bcrypt 多字节 72 字节边界；
  - 并发唯一键异常转换；
  - 存在/不存在用户都调用一次 bcrypt；
  - 账号失败限流、IP 轮换用户名限流；
  - 成功登录清除账号计数；
  - 标准 429 响应；
  - `X-Real-IP` 缺失时回退；
  - 注册关闭豁免及开启后的 IP 限流。
- `python -m compileall -q backend`：通过。
- `python -m pytest backend/tests/test_dependency_locking.py -q`：4 passed。
- `git diff --check`：通过。

## 明确未处理

- 注册后自动分配 `guest` 还是保持无角色账号，产品语义尚未定，本批没有修改。
- 当前 `api.md` 原有“注册后默认 guest 角色”仍与实现不一致，必须在产品决策批次统一处理。
- 登录日志保留/清理策略未在本批引入；限流已显著降低新增失败日志的速度，但不替代留存策略。

## 请 Claude 重点复核

1. Flask-Limiter 条件扣减与账号成功清零逻辑。
2. 生产依赖必须先安装再上传代码的顺序。
3. 在服务器 Python 3.11 环境重新生成依赖锁后是否与本次补入版本一致。
4. 429 响应与已部署前端的提示展示是否端到端一致。
