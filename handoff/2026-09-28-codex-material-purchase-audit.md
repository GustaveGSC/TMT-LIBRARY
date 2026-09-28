# 物料库与采购工具实现审计（只读）

> 日期：2026-09-28  
> 范围：`backend/services/product/material*`、`backend/routes/product/material.py`、`backend/services/purchase/price_import.py`、采购/物料前端及相关测试。  
> 本轮只审计，没有修改运行时代码，没有连接或写入生产数据库。

## 结论摘要

物料库的基础清单、分类缓存、研发 BOM 导入、覆盖事务和权限分域整体结构合理；当前最需要优先修复的不是 CRUD，而是“采购导入 → 价格批次 → 研发 BOM 历史计价”链路。

发现 3 项高优先级正确性问题、3 项中优先级问题、2 项低优先级/工程质量问题。尤其要注意：界面虽然按“采购订单批次”展示计价依据，但实际仍只把日期传给后端，同一天多个订单无法区分，展示出的历史成本可能不是所选订单当时的成本。

## P1：优先修复

### 1. 选择“采购订单批次”时实际只按日期计价，同日多订单结果错误

**证据**

- `src/components/material/PriceBatchSelect.vue:18` 明确用批次 ID 区分同日订单；
- 但 `PriceBatchSelect.vue:52-56` 选择后只向父组件发送 `batch.price_date`；
- `GET /api/material/boms/:id/tree` 也只接受 `price_date`；
- `backend/services/product/material_bom_price.py:20-52` 的价格历史不带 `snapshot_id`，只按日期判断 `day <= as_of`。

**影响**

同一天导入两个采购订单时，两个下拉项虽然显示不同订单号，但得到完全相同的计价结果。由于同日价格再按 `created_at/id` 取最新，选择当天较早订单时也可能使用当天较晚订单才出现的价格。物料卡片的“按采购订单逐单重算”历史同样按日期计算，因此同日多个批次无法还原各自时点。

**建议**

- 前后端以 `batch_id` 作为计价游标，不再把订单批次降维成日期；
- 价格查询需按 `(price_date, snapshot/order sequence)` 截止，手工价格另定明确的排序规则；
- 增加“同一天两个批次、第二批修改其中一个物料价格”的端到端测试，断言选择两个批次得到不同结果。

### 2. 同一物料在文件中出现多个单价时仍允许导入，并静默采用首次出现值

**证据**

- `backend/services/purchase/price_import.py:123-126` 遇到后续不同价格只记录 `conflicts`，保留第一个价格；
- `src/components/purchaseTools/PriceImport.vue:27-28` 的 `canImport` 不考虑 `preview.conflicts`；
- `PriceImport.vue:209-215` 仅提示“导入第一个出现的”，用户仍可直接确认导入。

**影响**

价格结果由 Excel Sheet/行顺序决定。调整工作表顺序或导出顺序即可改变入库价格，而不是由明确业务规则决定，属于成本数据的静默不确定性。

**建议**

首选：存在冲突时禁止导入，要求用户修正源文件。若业务确实允许冲突，则必须让用户逐项选择或明确采用可解释规则，并把决策写入导入结果；不能继续“取第一个”。

### 3. 无日期的人工价格会反向应用到所有历史日期

**证据**

- `MaterialPriceService._date()` 允许空日期，人工价格可以保存 `price_date=NULL`；
- `material_bom_price.price_as_of()` 在任何历史 `as_of` 下都接受 `day is None`；
- 模块注释把 NULL 价格定义为“最早”。

**影响**

今天新增一条无日期人工价格，可能让几个月前本来缺价的 BOM 突然变成“当时已齐全”，并改变“开始计价日期”和全部历史曲线。这不是历史重放，而是用当前录入值回填整个过去。

**建议**

- 成本价格强制要求日期；或给无日期价格定义 `effective_from=created_at.date()`，不得早于创建时间生效；
- 对现有 NULL 日期价格先只读盘点，再决定回填日期，不能直接批量猜测。

## P2：应在下一批收口

### 4. 全部价格均被跳过时仍创建空导入批次

**证据**

`PurchasePriceImportService.import_prices()` 在判断同日同价之前就创建并 flush `CostSnapshot`、写入 `CostSnapshotSku`；即使最终 `created == 0` 也照常 commit。`history()` 只按 `notes='采购导入价格'` 查询，不过滤价格数量为 0。

**影响**

重复导入会产生没有任何价格的“成功批次”，污染采购工具的最近导入记录。物料价格批次接口由于 INNER JOIN 价格表碰巧过滤了它，但两个历史入口的口径因此不一致。

**建议**

先算出真正需要新增的 items；为 0 时直接返回成功/无变更，不创建快照。并补测试断言 `CostSnapshot` 数量不增加、采购历史不出现空批次。

### 5. “特例半成品”识别会把没有自身有效采购价的部件也当成覆盖边界

**证据**

`extract_prices():92-105` 只要某父件的所有直接子件价格为空/0，就把父件加入 `special` 并递归把下级加入 `covered`；代码没有验证该父件自身是否作为子件出现且具有正价格。后续虽然不会凭空导入该父件，但其下级会从 `zero_items` 警告中消失。

**影响**

文件中某个无价部件及其无价下级可能被预览误报成“已由半成品价格覆盖”，实际却没有任何半成品价格可导入，降低缺价提示的可信度。

**建议**

只有“父件存在一条正价采购行”且“其直接下级均无价”时才认定 special；补一个根节点/孤立部件没有自身价格的反例测试。

### 6. BOM Excel 导出未防公式注入

**证据**

`material_bom.export_xlsx()` 把名称、规格、编码等数据库/导入文本直接传给 openpyxl。以 `= + - @` 开头的字符串会被 Excel 识别为公式；项目中未找到统一的 Excel 文本转义函数。

**影响**

如果 ERP 名称或导入字段含公式前缀，用户打开导出的 BOM 时会执行/解析公式。内部系统风险低于公网输入，但仍属于可避免的导出安全问题。

**建议**

增加统一 `safe_excel_text()`，对外部文本强制作为字符串写入（前置单引号或设置字符串类型），并覆盖名称、规格、编码、导入人等所有非数值列。

## P3：工程质量与体验

### 7. 预览接口对非法价格日期静默回退，导入接口却报错

`preview()` 使用 `_parse_date(price_date) or suggested_date`；调用方传入非法非空日期时会静默采用订单号日期，而 `import_prices()` 会明确拒绝。两个接口契约不一致。建议非法非空值直接 400，只有“未传/空值”才使用建议日期。

### 8. 相关后端测试集当前有 4 个失败，权限迁移后测试未同步

执行：

```text
python -m pytest backend/tests/test_material_library.py backend/tests/test_material_bom.py
backend/tests/test_material_prices.py backend/tests/test_material_combos.py
backend/tests/test_purchase_price_import.py -q
```

结果：81 通过、4 失败（另有 10 个 SQLAlchemy `Query.get()` 弃用警告）。失败均因测试账号仍只授予旧的 `product:view`，而运行时蓝图已切换为 `material:view`：

- `test_material_route_rejects_invalid_sort_field`
- `test_material_route_returns_expression_error_as_400`
- `test_price_routes_enforce_rd_permissions_without_requiring_product_edit`
- `test_combo_routes_enforce_view_and_edit_permissions`

这不一定代表生产权限错误（迁移脚本会给旧角色补新权限），但意味着当前测试门禁不是绿的，新回归可能被这 4 个已知失败掩盖。应同步测试身份，并新增 `material:view/material:edit/material:price/purchase:view` 的矩阵测试。

## 已核对且暂未发现问题的部分

- 研发 BOM 导入在异常时 rollback，覆盖已有 BOM 明细也处于同一事务内；
- BOM 导入已处理大小写归一、重复层次、父级缺失、同父同子冲突、数量精度和行数上限；
- ERP 重导后会调用未匹配 BOM 编码补关联，不再永久固定为空；
- BOM 删除已有被引用保护和二次 force 语义；
- 成本字段按 `material:price` 权限裁剪，物料基础查看/编辑与采购入口权限已分域；
- 物料列表分类筛选仍在 SQL 层分页，没有退回 8,000+ 行全量内存分页；
- 采购导入按事务提交，异常会 rollback；同日同价跳过和不同日期保留历史的基本行为有测试覆盖。

## 建议实施顺序

1. 先修批次游标（问题 1）与冲突单价门禁（问题 2），这两项直接影响成本正确性；
2. 明确无日期价格业务口径并盘点存量（问题 3）；
3. 一批收口空批次、special 判定和日期校验（问题 4/5/7）；
4. 补 Excel 安全转义与权限测试门禁（问题 6/8）；
5. 上线前用真实 MySQL 做至少一组“同日两订单、同物料价格变化”的只读/回滚验证，SQLite 无法覆盖排序规则及 MySQL 行为差异。
