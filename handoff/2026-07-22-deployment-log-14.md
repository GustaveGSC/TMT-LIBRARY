# 部署记录 · 站点配置分层（周期二 P3 第十五轮第三批）

日期：2026-07-22

## 背景

Codex 只读评估 `routes/config` 后发现：该目录只有2个接口（登录轮播语句读写），不存在"路由文件过大"问题，不值得继续拆 Blueprint；真正的问题是路由层混了 JSON 解析、默认值、ORM 查询和事务提交，且此前零测试覆盖。这一批做三层职责对齐（路由→service→repository），接口契约不变。交接文档：`handoff/2026-07-22-codex-config-layering.md`。

## 审查结论

`codex/config-layering`（`47c3655`）审查通过：

- `routes/config/__init__.py` 瘦身到只剩 HTTP 参数解析、author/admin 权限判断、`Result` 响应包装。
- 新增 `services/config.py`：`get_login_mottos()`/`update_login_mottos()`，默认语句列表、JSON 解析失败回退、输入清理（trim+过滤空值）、校验规则全部原样保留，逐行核对和重构前行为一致。
- 新增 `database/repository/config.py`：`SiteConfigRepository.get_value`/`set_value`，用 SQLAlchemy 2.0 的 `db.session.get()` 替代废弃的 `.query.get()`，是个顺手的小改进。
- `SiteConfig` 模型注释修正："自动建表"这个过期描述被替换为"生产 baseline 已有，结构变更走 Alembic"，避免以后有人真的以为这张表会自动建。
- 测试新增 `test_site_config.py`：service 层的损坏 JSON 回退、清理/持久化逐条验证；路由层用真实 Flask app + cookie 认证走一遍公开读取 200、非管理员写入 403、admin 写入 200 的完整权限契约，测试质量扎实。
- 本地复跑 `pytest`：115 passed。

## 部署

按 Codex 指定顺序（先传两个新模块，再传引用它们的路由文件，避免 reload 窗口期 import 失败）：

1. 确认无导入/resolve 任务在跑。
2. scp 上传 `database/repository/config.py`、`services/config.py`、`routes/config/__init__.py`、`database/models/account/__init__.py`（模型注释），md5 全部核对一致。
3. `systemctl reload gunicorn`；8秒后复查（master pid 2258 未变，新 worker 干净启动）。
4. `/health`/`/ready` 均 200。
5. 实测 `GET /api/config/login-mottos`：返回的是生产库里实际配置的3条自定义语句（不是内置默认值），证明新的 service+repository 分层链路端到端跑通、正确读到了真实数据。

## 影响说明

- 无接口契约变更、无数据库结构变更、无前端改动。
- `routes/config` 到此收口，不再继续拆分（Codex 明确建议不要）。

## 下一批

Codex 建议先只读梳理 `routes/rd/__init__.py`（1761行）和 `routes/rd/cost.py`（902行）的职责地图和拆分边界，输出方案后再决定要不要动，不要直接对大文件做整体搬移。
