# 物料库后端实施完成，交接 Claude

日期：2026-07-31  
状态：代码已完成并通过本地验证；**未部署**

## 已完成

### 数据库与模型

- Alembic `20260731_01`：
  - 新建 `erp_group_category`
  - 新建 `product_material`
  - `import_product_raw` 新增 nullable `spec`
- `backend/migrations/env.py` 已显式导入 material 模型，autogenerate/metadata 能看到新表。
- 两个新模型均带设计原因 docstring 和 `to_dict()`；`product_material` 不复制 ERP 的
  `name/group_code/group_name`，人工维护时才按需创建。
- `erp_code_rules` 新增 `useless` 类型；`material` 展示名统一为“原材料”。

### 物料库 API

统一使用 `product:view` / `product:edit`：

- `GET /api/material/group-categories`
- `PUT /api/material/group-categories/<group_code>`
- `GET /api/material/items`
- `GET /api/material/items/<code>`
- `PUT /api/material/items/<code>`
- `POST /api/material/items/<code>/image`

列表、分组统计均使用固定数量批量查询，没有逐物料/逐分组查询。大类在请求时由内存中的
规则集判定，不在保存配置时同步重算 8,089 条。前缀规则增删改、启停后会主动失效缓存。

判定规则为：只要存在启用的前缀例外，就返回所有命中的类型集合；否则使用分组默认。
这会保留 `finished + packaged` 多标签。

### 图片接口契约（前端待接）

请求沿用成品封面图：

```json
{
  "data_url": "data:image/webp;base64,...",
  "orig_data_url": "data:image/jpeg;base64,..."
}
```

`orig_data_url` 可省略。仅 PNG/JPEG/WebP，单张解码后最大 10MB。成功响应 data：

```json
{
  "url": "https://.../materials/<code>.<ext>",
  "orig_url": "https://.../materials/<code>_orig.<ext>",
  "img_updated_at": 1780000000,
  "cover_image": "https://...",
  "cover_image_original": "https://..."
}
```

### ERP 导入正确性修复

- 不再依赖固定列号，改为表头名称映射；缺少品号、品名、分组编码、分组名称时整单 400。
- `spec` 独立保存，同时保持现有 `name = 清理后的品名 + 规格` 语义不变。
- 原实现是 insert-only，导致修正表头后重导也无法纠正历史脏行。本批改为按 `code`
  批量差异更新：
  - 新编码 INSERT
  - ERP 字段有变化才 UPDATE
  - 完全相同不写库
- 返回新增 `updated/unchanged`；保留旧 `skipped_dup`，其值等于 `unchanged`，避免旧前端中断。
- 因此 34 条 `PCS` 错位数据和 `13100` 分组问题应通过正确源文件重导纠正，不在迁移里
  静默修改生产数据。部署后请在实际导入前后单独核对这两组数据。

## 本地验证

- `pytest -q`：全量通过，2 项既有环境相关测试 skipped
- `python -m compileall -q backend`：通过
- `git diff --check`：通过
- `alembic heads`：`20260731_01 (head)`
- 新增测试覆盖：
  - Excel 列顺序变化仍按表头正确解析
  - 缺少必需表头明确拒绝
  - 重导可更新错误 ERP 分组，完全相同重导不写库
  - 成品 + 产成品多前缀类型同时保留
  - 人工属性按需建行、停用筛选
  - Alembic 新表与单 head

## 部署与生产验收建议

由 Claude 按项目纪律执行：

1. 全库备份。
2. 上传后端文件，运行 `alembic upgrade head`。
3. 核对两个新表及 `import_product_raw.spec`。
4. reload（禁止 restart / preload），检查日志、`/health`、`/ready`。
5. 用真实 Cookie 会话验证 viewer 只读、editor 可写。
6. 抽查一个内部混合分组，确认前缀例外和多标签结果。
7. 用列顺序变化的真实 ERP 文件先 preview，再正式重导；核对 `inserted/updated/unchanged`，
   并单独验证原 `PCS` 34 行和 `13100` 数据是否按源文件纠正。
8. 用生产数据观察列表与分组接口耗时/查询数；当前实现无 N+1，但列表在大类过滤时会
   对最多约 8,089 条候选做内存判定，这是有意的低风险首版取舍。

## 暂未包含

- 前端图片上传按钮（等 Claude 按上述契约接线）
- ProductImport 页面迁移（Claude 已说明与新错误提示一起处理）
- BOM 价格/供应商迁移
- 任何生产部署或数据写入
