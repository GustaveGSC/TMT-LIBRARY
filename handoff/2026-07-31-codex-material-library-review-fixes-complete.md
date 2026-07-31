# 物料库后端审查返工完成，交接 Claude

日期：2026-07-31  
基线：`b0ea8f4`  
状态：代码完成、本地验证通过、**未部署**

## 修复内容

### P0/P1：ERP 导入

- 真实表头优先支持 `品号群组`、`群组名称`，保留旧别名。
- `_HEADER_ALIASES` 全部改为有序 tuple，消除同文件多别名时的随机匹配。
- 新增 `状态` 列解析并写入 `import_product_raw.status`。
- 差异 UPSERT 同步比较/更新 status。

### P1：列表性能

- 无大类/未分类筛选的常见路径改为数据库 `COUNT + LIMIT/OFFSET`。
- `product_material` 只按当页 code 做一次 IN 查询。
- `is_disabled` 用 LEFT JOIN + CASE 在数据库过滤，不再为过滤状态加载全量人工属性。
- 大类筛选路径只全量取 `code/group_code` 两列做内存判定，再回查当页完整行。
- 未在保存规则时触发任何 8,000 行同步重算。

### P2：特殊 ERP 编码

- 详情、保存、图片路由改为 `<path:code>`，已测试包含 `/` 的编码。
- OSS 文件名不再直接拼 ERP 编码，改用 `SHA-256(code)`，避免斜杠生成额外目录。

### P3：停用规则

- `product_material.is_disabled` 改为三态：
  - `NULL`：跟随 ERP/关键词默认
  - `true`：人工强制停用
  - `false`：人工强制启用
- API 同时返回最终 `is_disabled` 与 `is_disabled_override`。
- 新增 `material_disable_keyword`；迁移明确预置启用的“停用”“作废”两条规则。
- 因既有 `name` 会移除“（已停用）”且其组成禁止改变，新增 `import_product_raw.raw_name`
  保存 ERP 原始品名；关键词匹配 raw_name，旧行未回填时才回退到 name。
- 关键词使用模块级缓存，增删改/启停后主动失效；空表时只看 `status=失效`。
- 新增接口：
  - `GET/POST /api/material/disable-keywords`
  - `PUT/DELETE /api/material/disable-keywords/<id>`
  - `GET /api/material/disable-preview`
- preview 用一条聚合 SQL 同时计算
  `{status_inactive,keyword_hit,union}`，不会逐关键词查询。

## 验证

- 全量 `pytest -q`：通过，2 项既有环境测试 skipped。
- 新增/加强测试：
  - 真实 ERP 表头和 status 解析
  - 别名顺序
  - 默认 SQL 分页仅批量加载当页人工属性
  - ERP/关键词默认停用与人工 false 覆盖
  - preview 并集去重
  - 含斜杠 code 的详情和图片路由匹配
  - Alembic 预置关键词精确为“停用”“作废”
- `compileall`、`git diff --check` 通过。
- `alembic heads`：`20260731_01 (head)`。

## 部署门禁

仍由 Claude 部署。除上一份交接步骤外，请特别核对：

1. 迁移后 `product_material.is_disabled` nullable 且无 server default。
2. `material_disable_keyword` 恰有两条启用种子：“停用”“作废”。
3. 用真实 `123.xlsx` preview，确认 `品号群组/群组名称/状态` 正确。
4. 首次正式重导预计会更新约 8,000 行（raw_name/spec/status 首次回填），先备份并避开使用时段。
5. 真实 MySQL 验证默认列表、停用筛选、preview SQL；本地 SQLite 已覆盖语义，
   但部署前仍应检查 MySQL 的 CASE/LIKE 执行与耗时。
6. 验证一个含 `/` 的编码可读取、保存；图片对象 key 应为 64 位哈希文件名。

## 前端契约提醒

- 保存人工覆盖：`is_disabled` 传 `null|true|false`；返回看
  `is_disabled_override` 区分跟随默认和人工覆盖。
- 关键词规则的 `is_disabled=true` 表示“该关键词规则停用”。
- 图片响应形状没有变化。
