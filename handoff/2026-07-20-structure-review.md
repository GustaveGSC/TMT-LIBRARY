# 功能结构与模块划分筛查 · Claude → Codex

日期：2026-07-20
这次筛查的是"架构/分类是否合理"，不是找 bug。按 [AGENTS.md](../AGENTS.md) 边界分成后端（Codex 处理）和前端（我处理）两部分，前端部分我会陆续整理，这里先一起报上来方便你了解全貌，因为个别问题跨越前后端命名对应关系。

---

## 一、后端（backend/，Codex 负责）

1. **`routes/config` 没有对应的 `services/config` / `repository/config`**
   其他模块（account/product/version/shipping/aftersale/rd）都是 routes→services→repository 三层对应，唯独 config 只有 routes 层，业务逻辑可能直接写在路由里。要么补齐分层，要么明确这是刻意的轻量例外（比如加一行注释说明）。

2. **`rd/cost` 子模块层级不对称**
   `database/models/rd/cost.py` 内容较重（6 张表），但 `routes/rd/cost.py` 是单文件、`services/rd/cost_import.py` 命名只覆盖"导入"这一个动作，看不出和 routes 层的完整对应关系。建议统一成 `rd/cost/` 子目录，或者明确 `cost_import` 和 cost 路由各自的职责边界。

3. **backend 根目录堆积大量一次性/维护脚本**
   `create_packaged_equivalents.py`、`backfill_image_dimensions.py`、`backfill_days_since_purchase.py`、`create_cost_tables.py`、`simulate_match.py`、`seed_roles.py`、`seed_permissions.py` 等都是数据回填/建表/模拟脚本，分别归属 product、aftersale、rd/cost 等业务域，却统一堆在根目录，和 routes/services/repository 的模块划分完全脱节。建议按业务域归入各模块的 `scripts/` 子目录，或建立统一 `backend/scripts/` 按业务域分子目录。

4. **`model_manager.py`、`utils.py`、`auth.py` 定位模糊**
   `model_manager.py` 是语义模型管理，被 `app.py` 后台线程调用，更像基础设施服务而非顶层脚本；`utils.py` 是无归属的工具箱，容易变成"什么都往里塞"的杂物抽屉；`auth.py` 独立于 `services/account` 之外，认证逻辑和账号模块分离，边界不清晰。建议 `model_manager` 移入 `services/semantic/` 或 `infra/`，`auth.py` 并入 `services/account` 或建立 `backend/core/` 存放跨模块基础设施。

5. **`rd` 模块和 `product` 模块边界模糊**
   ECR（工程变更）、cost（成本/BOM）本质上都是围绕 product 展开的子领域，独立成 `rd` 顶层模块后，和已经很庞大的 `product` 模块（含 import_raw/finished/tag/param/category/lifecycle/resource 等 7+ 子文件）在业务语义上有重叠。建议写清楚 `rd` 和 `product` 的边界（比如"rd 管变更流程和成本，product 管产品数据本身"），或者考虑 `rd` 是否该做 `product` 的子命名空间。

6. **`app.py` 蓝图分组顺序未反映模块完整性**
   product 相关的多个蓝图（product_bp/finished_bp/erp_code_rules_bp/category_bp/tag_bp/param_bp/lifecycle_bp/resource_bp）分散排列，中间穿插 shipping/aftersale/rd；`resource_bp` 被拆到最后单独注册，且 `url_prefix` 是 `/api/resources` 而不是 `/api/product/resources`，和其它 product 子路由的前缀风格不一致。建议按业务域连续分组注册，统一 `resource_bp` 的 url_prefix 命名。

---

## 二、前端（src/，我这边处理，先报上来供你了解）

1. **`dataMgmtViews` 命名和实际内容不符**
   目录内混杂"数据管理"（DataImport/FinanceImport/ReturnImport/WarehouseConfig/OperatorConfig/EquivalentConfig/TagDimensionConfig/LifecycleManager）和"发货看板"（ShippingDashboard.vue），但发货已经有独立的 `shippingViews` 目录（ShippingTable.vue、page-shipping.vue）。同一业务域拆在两处。计划把 `ShippingDashboard.vue` 移入 `shippingViews`，`dataMgmtViews` 改名聚焦"数据导入/主数据配置"。**这个改动会影响 `frontend-data-mgmt.md` 的模块划分和路由，如果后端有任何按这个目录结构写死的假设（不应该有，但确认一下），提前说一声。**

2. **组件目录分类粒度不统一**：`common/update/user` 按功能类型分，`rdTools/aftersale` 按业务模块分，`product/shipping/dataMgmt` 完全没有独立 components 子目录，页面把子组件直接内嵌在 views 里。计划统一标准：views 只放路由级页面，其余拆到 `components/<module>/`。

3. **`aftersale` 模块组件重复入口**：`AftersaleCasesTable.vue` 在 `views` 和 `components/aftersale/` 两处都能找到，职责边界不清，需要合并成一处。

4. **stores 仅覆盖 product 模块**：`src/stores/` 只有 `product/`，shipping、aftersale、dataMgmt、rdTools 均无对应 store。计划评估是否给 aftersale/shipping 补 store，或者明确写进文档"只有 product 用 Pinia，其余用组件内状态"的约定。

5. **composables 与 utils 边界混淆**：`useProductResources.js`/`useFinishedParams.js`/`useFinishedImage.js` 是业务专属 composable，和 `useSortable`/`usePermission` 这类通用 composable 平铺在同一目录；`utils/image.js` 和 `useFinishedImage.js`/`useVideoCompress.js` 在图片/视频处理上可能有重叠实现，需要核对是否该合并。

这部分前端问题我会自己排期处理，不需要 Codex 动手，列出来只是让你知道 `frontend-data-mgmt.md` 未来可能会有结构调整。

---

## 三、跨边界的问题

- **命名不对称本身就是协作风险**：后端 `rd/cost` 和前端对应的 `BomCost.vue`、`page-rd-tools.vue` 之间没有统一的模块命名约定，未来新增字段/接口时容易因为双方对"这个功能算 rd 还是 product"理解不一致而导致 `api.md` 归类错放。建议下次接口设计前先在 `api.md` 里明确这个功能属于哪个业务域前缀。

---

以上都是结构性观察，不需要马上全部动手，建议你按优先级自行排期。如果某几条你认为现状是刻意设计（比如 config 模块确实很轻不需要分层），直接在这份文件下面回复说明即可，我会更新认知不再重复提。
