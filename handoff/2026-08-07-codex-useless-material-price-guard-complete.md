# “无用物料”价格写入门禁完成

日期：2026-08-07  
对象：Claude Code

## 完成内容

- `MaterialPriceService.add_price()` 在任何成本节点查询/惰性创建之前检查物料大类。
- `categories` 只要包含 `useless`，立即返回：`无用物料不支持维护价格`。
- 多标签场景同样执行拒绝，不要求 `useless` 是唯一大类。
- 详情的研发成本字段新增 `can_add_price`：
  - 包含 `useless` → `false`；
  - 其他物料 → `true`。
- `can_add_price` 与其他成本字段一样，仅在调用者具备 `rd:view` 时出现。
- PATCH 供应商与 DELETE 既有价格不增加该限制，保留历史脏数据的维护和清理能力。
- API 文档已同步。

## 自动化验证

新增回归场景：物料同时属于 `material + useless`，尝试新增价格后断言：

- 返回 `无用物料不支持维护价格`；
- `cost_bom_node` 行数仍为 0；
- `cost_material_price` 行数仍为 0；
- 详情返回 `can_add_price:false`。

验证结果：

- `pytest -q tests/test_material_prices.py`：5 项通过。
- 全量 `pytest -q`：305 项通过，2 项跳过。
- `git diff --check`：通过。
- 本批无数据库迁移。

## 部署门禁

- 未部署。
- 部署后用一条实际 `useless` 物料直接 POST 价格接口，确认返回 400；随后查询
  `cost_bom_node`，确认该物料基础码没有产生空节点。
- 再用一条正常物料确认新增价格仍成功。
- 验证已有无用物料价格（若存在）仍可修改供应商和删除。

## 未纳入本批

交接文档同时记录的单数字版本/变体后缀（如 `-S1/-C1`）归约问题尚未获得用户业务确认，
本批没有修改 `_strip_version()` 或研发 BOM 节点身份规则。
