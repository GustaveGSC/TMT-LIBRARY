# 交接说明 · Codex → Claude（周期二 P3：RD 后端结构审计）

日期：2026-07-22

## 本轮范围与结论

本轮只读审计，没有修改运行代码。`backend/routes/rd/__init__.py` 为 1761 行、17 个端点；`backend/routes/rd/cost.py` 为 902 行、26 个端点。现有 `backend/tests` 没有 RD 功能专项测试，仅应用启动测试会间接 import 两个 Blueprint，因此当前不能安全地直接拆文件。

“rd/cost 命名不对称”只是表象：主文件把四个业务域和大量 Excel 纯逻辑塞进 `__init__.py`，cost 虽已单独成为 Blueprint，内部仍由路由直接操作 ORM。应按业务域和测试门禁逐批处理，不做一次性整体搬移。

## 职责地图

### `routes/rd/__init__.py`

1. ECR/ECN 与 BOM 比对（约 1–1298 行）
   - 端点：`ecr/export`、`ecr/parse-ecr`、`ecr/export-ecn`、`ecr/compare-bom`。
   - 大部分代码是 Excel 样式、ECR/ECN 构建、BOM 解析/比对、版本推算等纯文件逻辑，不属于 HTTP 路由。
   - 建议目标：`services/rd/change_documents.py` 承载纯逻辑，`routes/rd/change.py` 保留上传、响应和错误映射。
2. 变更提醒（约 1299–1404 行）
   - 5 个端点：公开在架列表；rd:admin 全量列表、新建、编辑、上下架。
   - 当前路由直接操作 `EcrReminder` 与 commit，并使用多处废弃 `.query.get()`。
   - 建议独立为 `routes/rd/reminders.py` + service/repository。
3. 个人笔记（约 1405–1470 行）
   - 4 个端点：按当前 username 隔离的列表、新建、编辑、删除。
   - 当前路由直接操作 `EcrNote` 与 commit；所有权校验属于 service/repository 边界。
   - 这是最小、最适合作为第一次真实拆分的域。
4. PDM 转 BOM（约 1471–1761 行）
   - 3 个端点：处理 PDM、导出 ERP、导出 BOM。
   - 包含资源模板定位、列映射和层级 BOM 生成纯逻辑。
   - 建议目标：`services/rd/pdm_to_bom.py` + `routes/rd/pdm_to_bom.py`。

### `routes/rd/cost.py`

- 已独立挂载 `/api/rd/cost`，无需为了命名统一并回主 Blueprint。
- 26 个端点可分为：
  1. 快照/导入：snapshots、preview、import、SKU/BOM（7 个）。
  2. 节点查询：nodes、详情、编辑、价格历史、使用记录（5 个）。
  3. 供应商：4 个。
  4. 物料规则：3 个。
  5. 手工价格：4 个。
  6. 列别名与估算：3 个。
- `services/rd/cost_import.py` 已存在，但除此之外路由直接查询/提交 ORM；后续应先补 cost API 测试和 repository，再考虑拆子路由。
- `col-aliases` 直接操作 SiteConfig，可在后续复用 `database/repository/config.py`，但 JSON 业务规则仍应留在 RD cost service，不能塞回通用 config 路由。

## 优先安全问题：遗留服务端路径读取

Electron 已正式停止支持，但以下接口仍接受 JSON 中的本地路径，并让服务器直接检查/读取该路径：

- `POST /api/rd/ecr/parse-ecr`：`ecr_path`
- `POST /api/rd/ecr/compare-bom`：`bom_before_path`、`bom_after_path`
- `POST /api/rd/pdm2bom/process`：`file_path`

Web 前端已有 multipart 上传路径；JSON 路径分支是旧 Electron 协议。任何拥有 RD 权限的 Web 调用方都可以让服务尝试读取服务器文件，属于不必要的服务端文件读取面。该问题应在结构拆分前单独处理：

1. 先补 multipart 成功、缺文件、大小/类型限制测试。
2. 后端拒绝非 multipart 请求，不再接受路径字段。
3. Claude 同步删除前端已暂停 Electron 分支中的路径请求或明确保持代码存档但不可调用；更新 frontend-rdtools.md 中“发送本地文件路径”的陈旧说明。
4. 独立提交、独立回归，不与文件搬移混在一起。

## 建议实施顺序

### 第 0 批：安全门禁

- 移除上述 3 个 JSON 路径读取协议，只保留受 `upload_validation` 保护的 multipart 上传。
- 为 3 个上传端点补自动化测试。

### 第 1 批：先建立行为护栏

- 增加 URL map 快照测试，固定 17 个主 RD 和 26 个 cost 路径/方法。
- 为 `_compare_bom`、ECR/ECN round-trip、`_ptb_build_erp_data`、`_ptb_build_bom_data` 建小型 fixture 测试。
- 为 notes/reminders 建真实权限与所有权测试。

### 第 2 批：拆 notes/reminders

- 先拆 4 个 notes，再拆 5 个 reminders；保持 URL、Blueprint guard、权限和响应不变。
- 引入 RD repository/service，替换 `.query.get()`，每个域单独提交和部署。

### 第 3 批：抽纯文件服务

- 把 ECR/ECN/BOM 和 PDM 转 BOM 的纯函数移动到 `services/rd/`。
- 路由仍可暂时留在原 Blueprint；先降低 `__init__.py` 体积与依赖，再决定是否拆子 Blueprint。

### 第 4 批：成本库

- 先 repository/service 分层，后按快照、节点、供应商/规则/价格拆分路由。
- 不与主 RD 路由拆分同批进行。

## 性能与兼容性要求

- URL、HTTP 方法、权限码、响应结构不得因拆分变化。
- parent Blueprint guard 是否覆盖嵌套 Blueprint 必须由测试证明；若不能明确证明，各子 Blueprint 显式配置同一 guard。
- 成本快照列表当前“全量查出后在 Python 分组分页”，数据增长后有内存风险，但属于查询优化事项，应单独评估，不能夹带在结构搬移中。
- Excel 上传仍必须走 `read_spreadsheet_upload`；临时文件必须在 finally 中清理。

## 下一步建议

下一批优先执行“第 0 批：移除遗留路径读取”，因为它是已停止 Electron 支持后的安全债，不需要等待完整结构重构。之后再补 URL map 与 notes/reminders 测试门禁。

本轮未部署、未 push、未修改任何运行代码或前端文件。
