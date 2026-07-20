# Codex 后端进度 · 废弃接口清理与 P0 安全配置

日期：2026-07-20
分支：`codex/backend-p0`

## 已完成

### 1. 独立销退导入清理

- 删除 `POST /api/shipping/import/return`。
- 删除仅供该接口使用的 `ShippingService.import_return()`、专用解析器和序列化函数。
- 保留财务清单导入使用的销退写入、合并和 repository 公共能力。
- `.claude/modules/api.md` 明确：销退数据统一通过 `/api/shipping/import/finance` 的负数量行导入。

提交：`4cf5953 refactor(backend): 移除独立销退导入接口并补测试`

### 2. 自动化测试基础设施

- 新增 `pytest.ini`、`backend/requirements-dev.txt`、`backend/tests/`。
- 测试不连接 MySQL、不访问真实 OSS、不启动模型下载。
- 覆盖废弃路由/服务不存在，以及财务 CSV 正负数量分流和售后组过滤。

### 3. P0 安全配置

- `APP_ENV` 默认为 `production`。
- 生产环境缺少强 `JWT_SECRET` 或 `SHARE_SECRET` 时，应用在初始化数据库和蓝图前拒绝启动。
- `ALLOW_REGISTER` 改为默认关闭，只在显式设置 `true` / `1` / `yes` 时开启。
- `/api/resources/:id/og-image` 必须验证分享链接的 `key` 和 `exp`。
- 分享页面生成的 Open Graph 图片地址会携带相同分享凭证。

## 部署前置条件（必须先做）

在部署或 reload 前，先确认 Gunicorn 实际加载的环境文件包含：

```dotenv
APP_ENV=production
JWT_SECRET=<非默认强随机值>
SHARE_SECRET=<非默认强随机值>
ALLOW_REGISTER=false
```

如果生产环境没有上述两个密钥，直接 reload 会导致新 worker 因 fail-fast 拒绝启动。不要先部署代码再补环境变量。

如果更换现有 `JWT_SECRET`，所有当前登录 token 会立即失效，用户需要重新登录；如果更换现有 `SHARE_SECRET`，既有资料分享链接会立即失效，需要重新生成。

## 验证

```text
python -m pytest
python -m compileall -q backend
git diff --check
```

当前结果：全部 pytest 通过；未连接生产环境、未部署、未 push。

## 尚未处理

- 账号禁用、改密、撤权后的旧 JWT 失效机制。
- 全局上传大小与文件内容校验。
- 生产连接池实际配置核验。
- 进程内后台任务、多 worker/reload 可靠性。
- Alembic 迁移和依赖锁定。
