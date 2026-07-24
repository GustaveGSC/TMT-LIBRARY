# 数据管理 & 发货图表前端组件说明

> 2026-07-24：数据管理入口已从独立的 `/data-mgmt` 一级页面迁移进发货数据域，
> 首页不再有独立"数据管理"卡片。见下方 `page-shipping.vue` 说明和
> `handoff/2026-07-24-claude-data-management-migration-plan.md`。原 `page-data-mgmt.vue`
> 已删除；`DataImport.vue`/`FinanceImport.vue`/`OperatorConfig.vue`/`WarehouseConfig.vue`/
> `EquivalentConfig.vue`/`TagDimensionConfig.vue`/`FinanceCustomerMapping.vue` 组件文件本身仍在
> `src/views/dataMgmtViews/`（本批未物理搬移目录，只改了路由归属），被新的
> `src/views/shippingViews/ShippingImportsPage.vue`/`ShippingSettingsPage.vue`/
> `ShippingMaintenancePage.vue` 引用组装。

## DataImport.vue 说明
- 导入发货清单（xlsx/xls/csv），固定 100px 文件拖放区，选中后显示 Excel SVG 图标
- 导入流程：上传文件获取 task_id → `pollShippingTask` 短轮询 `GET /api/shipping/tasks/:task_id`（1秒间隔，不重叠，终态立即停止）→ 展示进度条（parsing→parsed→inserting→inserted→resolving→done）。SSE 已废弃，不再创建 `EventSource`
- 遇到 409（已有发货数据任务在跑）：`getConflictTaskId()` 解析冲突响应里的 `task_id`，直接接入该任务的轮询，而非提示失败后中断
- **文件内合并**：同 `(ecommerce_order_no, line_no, product_code)` 的行 quantity 累加，被合并行记录在 `merged_away_rows`
- **DB 去重**：与库中已有记录比对，跳过的记录返回在 `skipped_rows`
- **中止导入**：中止后 rollback 已写入的 batch 数据
- **错误弹窗**：导入失败用 el-dialog 展示（不自动消失），进度条隐藏
- **结果卡片**：文件行数 / 新增记录 / 跳过重复 / 文件内合并（可点击→弹出明细 dialog）
- **跳过重复弹窗**：9列表格（电商订单号/项次/商品型号/商品名称/数量/发货日期/渠道/最近操作人/省份）
- **文件内合并弹窗**：19列完整内容
- **缺失日期日历**：自定义 7 列网格（非 el-calendar slot，绕开响应性问题）
  - `missingDates = ref([])` 数组，`calCells` computed 按年月生成 `{ d, missing }` 单元格
  - 缺失日期显示红色 32×32 圆圈（`.cal-inner--missing`）
  - 导航：年份 el-select + 月份 el-select + 上/下月按钮
- 权限：`shipping:edit` 才显示文件选择区和"开始导入"按钮，`shipping:view` 只读（不依赖后端 403 兜底）

## FinanceImport.vue 说明（财务数据导入）
- 调用 `POST /api/shipping/import/finance`
- 标题「导入财务清单」，支持 xlsx/xls/csv，同 DataImport.vue 文件选择区风格
- 导入流程：上传→ task_id → `pollShippingTask` 短轮询（同 DataImport.vue，SSE 已废弃）
- **正数量行 → 发货记录（source='finance'）**；**负数量行 → 销退记录**；**部门名称='售后组' → 跳过**
- `ecommerce_order_no` 补全：优先「平台订单」列，其次取「订单单号」中 `-` 后的部分，均空则跳过
- **增量正确性**（财务导入工作流 B 批）：重导时先批量比对既有行快照，只对新增/实际变化的行 UPSERT；完全相同的行不写库、不触发 resolve；受影响订单（含仅补充 `customer_alias` 的历史订单）在同一事务内自动增量 `_resolve_orders()`，不再需要手动执行"重建全部成品组合"
- 文件内合并：shipping 按 (order_no, product_code) 合并，return 按 (order_no, product_code, date) 合并
- **结果卡片**（3列网格）：文件总行数 / 新增发货记录（accent）/ 新增销退记录（accent）/ 跳过重复（可点击）/ 售后组过滤。`updated`/`skipped` 现在精确区分"实际变化"和"内容完全相同"
- **跳过重复弹窗**：4列（平台订单号/品号/日期/数量）
- 权限同 DataImport.vue

## OperatorConfig.vue 说明
- 展示所有「最近操作人」列出现过的人员，可设置类型：发货 / 售后 / 未分类
- 类型颜色：shipping=#c4883a，aftersale=#4a8fc0，unknown=#8a7a6a
- 右上角「刷新成品组合」按钮（`stale_count > 0` 时显示），调 `POST /api/shipping/resolve`（`resolve_stale`，只处理 `is_stale` 订单，与"重建全部成品组合"是不同范围的操作）；短轮询 `GET /api/shipping/tasks/:task_id`（原先是手写 800ms×1125次循环，已改用共享 `pollShippingTask`）
- 权限：`shipping:edit` 才显示保存/刷新按钮和分类点击交互，`shipping:view` 只读

## WarehouseConfig.vue 说明
- 展示所有在 return_record 中出现过的仓库名，可配置 is_excluded（排除/正常导入）
- 排除状态：橙红标签 + 橙红边框背景；正常状态：绿色标签
- 调 `GET /api/shipping/warehouses` 加载，`POST /api/shipping/warehouses/filter` 保存
- 权限：`shipping:edit` 才显示开关可交互和保存按钮，`shipping:view` 开关禁用、无保存按钮

## TagDimensionConfig.vue 说明
- 配置哪些标签分类可作为发货图表聚合维度（`product_tag_category.is_shipping_dim`），及分类下具体哪些标签参与统计（`product_tag.shipping_dim_enabled`）
- `onMounted` 拉取 `GET /api/product/tags/categories/`（已含每个分类的 tags[]），本地打快照用于保存时 diff
- 每个分类一行：`el-switch` 控制是否作为发货维度；分类下标签用 `el-checkbox` 勾选是否纳入统计（分类开关关闭时标签行置灰禁用，但状态仍保留）
- 「保存」仅对比初始快照后变化的行调用 `PUT /api/product/tags/categories/:id` / `PUT /api/product/tags/:id`（`Promise.all` 并发），无变化时提示"没有变更"
- 权限：`shipping:edit` 才显示保存按钮、开关/勾选框可交互，`shipping:view` 只读

## EquivalentConfig.vue 说明
- 配置产成品通用件（等效互换对），用于发货匹配时允许 A01↔B01 混用
- 列表：code_a / code_b / 备注 / 删除按钮
- 新增区：两个产成品编码输入框 + 备注 + 新增按钮
- 调 `GET /api/shipping/equivalents` 加载，`POST /api/shipping/equivalents` 新增，`DELETE /api/shipping/equivalents/<id>` 删除
- 权限：`shipping:edit` 才显示新增表单和删除按钮，`shipping:view` 只读
- 新增/删除后提示用户前往"数据维护"页执行"重建全部成品组合"更新历史数据（原文案"刷新全局数据"已随 A 批改名同步更新）

## FinanceCustomerMapping.vue 说明（页面标题「客户匹配」，原「外贸客户匹配」已改名）
- 财务原始数据"客户简称"去重列表（合并 shipping_record 与 return_record 出现次数），人工审核归类四态 + 填写国家/品牌/备注，**完全人工，不做自动解析**
- 四态：`pending`未审核（默认）/ `export`外贸客户 / `domestic`内销客户 / `non_sales`非销售客户（已审核但既不算外贸也不算内销的终态，如赠品样品，不会再被"仅看未审核"筛出来提醒处理）
- 顶部筛选：关键字输入框（默认空，400ms 防抖）+「仅看未审核」勾选（直接请求后端 `status=pending`）
- 每行草稿态存于 `drafts[customer_alias]`（status/country/brand/note/dirty），状态用 `el-select` 四选一，编辑后标记 dirty，「保存」按钮仅在 dirty 时可点，保存成功后用响应覆盖该行 `mapping` 并清 dirty
- 调 `GET /api/shipping/finance-customer-aliases`（`?keyword=&status=&page=&per_page=`，`shipping:view`）加载，`POST /api/shipping/finance-customer-aliases/mapping`（`shipping:edit`）保存单条，保存成功后后端立即失效 `chart-options` 缓存（财务导入工作流 A 批）
- 无 `shipping:edit` 权限时所有输入框/下拉/保存按钮禁用（只读展示）
- 应用到 `shipping_order_finished` 聚合表/图表分析：`export`进外贸统计+国家/品牌维度，`domestic`进内销统计，`pending`/`non_sales`/未映射均只在"全部"里出现。修改分类/国家/品牌**保存后立即生效**（`chart-data` 实时 JOIN 映射表，不经过 resolve）；财务导入工作流 B 批上线后，重导历史数据补充客户简称也会自动增量同步派生表，不再需要额外操作

## page-shipping.vue 说明（发货数据业务壳，2026-07-24 起带 5 个子路由）
- 路由 `/shipping`，`onMounted` 调用 `maximizeApp()`，返回按钮先 `unmaximizeApp()` 再 `router.push('/index')`（不用 `router.back()`，避免在子页间来回切换后被困在历史栈里）
- 顶部导航 5 项，`router.push` 明确导航（非 tab 内部状态），`<router-view>` 承载内容区，各子路由组件独立懒加载（`import()` 动态导入），切换页面不会预先加载其他页面的接口：
  | 路径 | 页面 | 内容 |
  |---|---|---|
  | `/shipping` | 分析看板 | `ShippingDashboard.vue` |
  | `/shipping/orders` | 订单明细 | `ShippingTable.vue` |
  | `/shipping/imports` | 数据接入 | `ShippingImportsPage.vue`（组装 DataImport + FinanceImport） |
  | `/shipping/settings` | 规则设置 | `ShippingSettingsPage.vue`（组装 OperatorConfig/WarehouseConfig/FinanceCustomerMapping/EquivalentConfig/TagDimensionConfig，侧边栏 Tab 分三组：来源与口径/匹配规则/分析设置） |
  | `/shipping/maintenance` | 数据维护 | `ShippingMaintenancePage.vue`（"重建全部成品组合（高级）"，即原 resolve-all，独立页面，不在日常导入/设置流程里出现） |
- 旧 `/data-mgmt` 路由改为 `redirect: '/shipping/imports'`，保留兼容跳转（计划至少保留一个发布周期）
- 子路由权限统一继承父路由 `meta.permission: 'shipping:view'`（vue-router 的 `to.meta` 会合并父子路由 meta）；各页面内部写操作再各自按 `shipping:edit` 做二次门禁（不依赖后端 403 兜底，见各组件小节）
- `ShippingSettingsPage.vue` 用 `route.query.tab` 持久化当前 Tab，刷新页面后保持在同一个 Tab（不回到默认的"操作人分类"）
- 首页 `page-index.vue` 已移除独立"数据管理"卡片，`icon_data_mgmt.png` 资源文件未删除（未使用，留作后续清理）

## ShippingDashboard.vue 说明
- 左侧筛选面板（230px）：**数据来源 segmented（发货端/财务端）**、日期范围 + 时间粒度 segmented（月/季度/半年/年）、品类/系列/型号级联选择、渠道多选、省份多选、重置按钮
  - 切换数据来源时清空渠道/省份/城市/区筛选（两端渠道名称完全不同），tradeType 重置为 'domestic'
- 右侧顶部工具栏：图表类型图标（柱/折/饼/地图）+ 分隔线 + 同比/环比按钮；最左显示下钻面包屑，最右依次为**内外销选择（all/domestic/foreign）**、数据指标选择
  - 内外销选择两端均显示，`domestic` 为默认值；`foreign` 过滤 `ProductSeries.code LIKE '%-FTP'`（后端 SQL）
  - 切换来源或内外销时重新调 `GET /api/shipping/chart-options`（更新渠道列表）和 `POST /api/shipping/chart-data`
- 右侧内容区：ECharts 图表（占满）+ 底部聚合维度切换 chip（产品/渠道/地域/时间）

### 聚合维度与图表类型
| 维度 | 可用图表 | 默认 |
|------|---------|------|
| 产品（品类→系列→型号自动下钻） | bar、pie | bar |
| 渠道（渠道→渠道商自动下钻） | bar、pie | bar |
| 地域（省份→城市→县区自动下钻） | map、bar | map |
| 时间 | 同比（yoy）、环比（mom） | 同比 |
| 标签维度（动态，见下） | bar、pie | bar |

### 标签维度 chip（动态）
- 桌面端底部维度栏固定四个 chip（产品/渠道/地域/时间，`BASE_GROUP_BY_OPTIONS`）+ 一个「标签」下拉按钮（`el-dropdown`，仅 `tagDimensions.length > 0` 时显示）：点击弹出菜单列出 `GET /api/shipping/chart-options` 返回的 `tag_dimensions`（数据管理→数据配置→「标签分析维度」面板配置的已启用标签分类），选中后 `groupBy` 设为对应 `tag:<category_id>`；按钮激活态与图标颜色跟随当前选中的标签分类（`activeTagDim` computed，用 `findTagDim(groupBy)` 判定）
- 移动端/全屏工具栏的 `el-select` 维度选择器仍用扁平列表 `GROUP_BY_OPTIONS`（`BASE_GROUP_BY_OPTIONS` + 各标签分类展开，`isTag` 标记 + `PriceTag` 图标），因为下拉列表本身已是菜单形式，无需再套一层
- `groupBy` 值为 `tag:<category_id>`；单层不可下钻（不在 `DRILLABLE_LEVELS` 集合内，`drillDown` 对其自动 no-op，与时间维度一致）
- 聚合仅统计该分类下 `shipping_dim_enabled=1` 的标签；未启用的标签、以及未打该分类任何标签的产品，不出现在该维度下（筛选性维度，非"未知"兜底分组）
- 不支持自定义分组（`customGroups`/`DIM_LABELS` 等仅覆盖产品/渠道/地域三个固定维度）
- 若某产品在同一标签分类下被打了多个标签，聚合时会在多个标签分组中重复计入该产品的发货记录（标签多对多设计的已知边界情况）
- **例外**：标签分类名恰好等于 `"地域"` 时（`REGION_TAG_DIM_ALLOWED`），额外允许 `map` 图表类型，用世界地图渲染（标签值需为国家中文名，如"美国""德国"）。通过 `COUNTRY_NAME_MAP`（国家中文名→GeoJSON英文名）转换后匹配 `src/assets/maps/world.json`（ECharts 社区标准世界地图，217国，Vite glob 懒加载，同 `ensureChinaMap` 机制）。未在映射表里的国家名会原样传给 ECharts，匹配不到对应区划则该项不显示颜色（数据仍在 Top10 表格里）。这个"地域"标签维度和固定维度里同样叫"地域"的省份维度是两个独立概念，只是恰好同名，UI 上会出现两个都显示"地域"的选项，是已知的命名交叉，不是 bug。
  - 台湾/香港/澳门单独着色：从 `china-map.json`（省级地图）里抠出这三个区划叠加进 world 地图注册，不跟 world.json 原生的"China"整体轮廓混在一起。
  - 国家定位点（详情面板连线起点）：`featureLargestRingCentroid` 取"面积最大子多边形的真实几何中心"，不能用外接矩形中心（美国/俄罗斯这类有海外飞地或跨很大经度的国家，外接矩形中心会算到国土外面）。
  - "显示详细数据"开关（`showDetailPanels`）：默认只有 hover tooltip，开启后为每个有数据国家常驻一个可拖拽面板+连线，用普通 DOM 元素叠层实现（不是 ECharts `graphic`——canvas 内 zlevel 分层在 roam 时不可靠，实测面板会被地图盖住）。
  - tooltip/面板内容模式（`tooltipMode`：默认/按系列/按品牌）：非默认模式下，对地图上每个有数据的国家分别用该国家的标签 id 作为 `tag_filters` 调一次 `chart-data`（`group_by=series` 或 `group_by=tag:<品牌分类id>`），批量预取后本地渲染，不是每次 hover 都发请求。按系列模式下用已加载的 `categoryTree` 反查每个系列所属品类做分组排序。品牌细分依赖"品牌"标签分类已配置为发货维度（`is_shipping_dim=1`），否则该模式不可用。

### 标签筛选（左侧筛选面板）
- 左侧筛选面板新增「标签筛选」分组（`sections.tag`），与聚合维度无关，独立生效——不管当前按什么维度聚合，选中的标签都会过滤底层数据
- 每个已启用的标签分类渲染一个多选下拉（选项为该分类下 `shipping_dim_enabled=1` 的标签），绑定 `filters.tagFilters[category_id]`
- 请求体新增 `tag_filters: [{category_id, tag_ids}]`（`buildTagFilters()` 生成，跳过未选择的分类）；同一分类内多个标签为 OR，不同分类之间为 AND
- 后端用"先查出符合条件的 finished_code 集合再 IN 过滤"而非 JOIN，避免同一产品命中同分类下多个标签时 JOIN fan-out 导致数量重复计入

### 自定义分组支持标签维度
- 自定义分组（`customGroups`）的 `dimension` 除 `product`/`channel`/`region` 外，还支持动态的 `tag:<category_id>`；标签维度单层（无层级/无 parent_context），`level` 恒等于 `dimension` 本身
- 分组项 `items` 结构为 `{value: tag_id, code: tag_name, name: tag_name, label: tag_name}`：`value` 供 `tagFilters`/`tag_filters` 用 id 过滤，`code` 供 `mergeGroupedItems` 按后端返回的标签名 label 匹配合并
- 「标签筛选」区每个分类上方显示该分类的分组芯片（`tagGroupsFor(categoryId)`），激活后隐藏被合并的原始标签、下拉里出现合并后的分组选项（`tagOptsFor`）
- `dimLabel()`/`dimColor()`/`defaultLevelFor()` 是兼容固定维度与动态标签维度的通用 helper，管理弹窗（分组列表标签色块、新建分组表单）均已改用这三个函数而非旧的 `DIM_LABELS`/`DIM_COLORS`/`DIM_DEFAULT_LEVEL` 直接取值

### 时间维度
- 切换到时间维度自动激活「同比」；可手动切换为「环比」
- 时间粒度（月/季度/半年/年）绑定左侧 segmented，切换后重新请求数据
- **同比（buildYoyOption）**：X 轴为完整一年期号（月 01-12 / Q1-Q4 / 上下半年），每年一个柱状系列；缺失期号显示 0
- **环比（buildMomOption）**：上下双 grid 布局（与同比一致）——上图：环比增长率折线（rich text 标签：▲红/▼蓝/0%灰），下图：数量柱状图；X 轴通过 `axisPointer.link` 联动，dataZoom 同时绑定两轴；tooltip 合并显示数量+增长率
- title 末尾追加「· 同比」或「· 环比」
- 后端 `POST /api/shipping/chart-data` 时额外传 `period`（month/quarter/halfyear/year），后端对应使用不同 `DATE_FORMAT` / `QUARTER()` / CASE 表达式

### 工具区（toolbox）
- 所有图表均含 ECharts toolbox（右上角），统一由 `makeToolbox(withZoom)` 生成
- 直角坐标系（bar/line/yoy/mom）：区域缩放 + 还原 + 保存图片
- 饼图/地图：还原 + 保存图片

### 地图
- 地域维度 + 地图类型时，右侧显示 Top10 排行面板（190px），按当前指标降序，前三名圆圈用主色高亮
- 省份级别筛选到单一省份时，自动切换为对应省级地图（通过 adcode 从 `src/assets/maps/{adcode}_full.json` 加载）
- 全国地图文件：`src/assets/maps/china-map.json`；34 个省级地图文件均已下载至同目录

### 自定义分组
- 支持产品/渠道/地域三个维度的多层级自定义分组，保存在 localStorage（key: `shipping_product_groups`）
- 激活分组后，图表中该分组成员合并为单条，tooltip 底部蓝色显示成员列表
- 右击柱/饼扇区可下钻，自定义分组条目跳过下钻；面包屑显示在工具栏左侧
- **下钻 series 时必须限定品类搜索范围**：`drillDown` 函数在品类已选定时只在当前品类内查找 series，避免不同品类下相同 code（如 LX11 同时属于学习椅灵犀 V1.1 和学习桌理想 V1.1）导致误匹配；若未选品类则下钻同时自动设置父品类

### Bar 图（buildBarOption）行为
- items 按当前数据指标（发货量/销退量/净发货）**降序排列**后再绘制
- X 轴：`interval:0, hideOverlap:true` — 所有类目均纳入渲染，空间不足时自动隐藏重叠标签；dataZoom 放大后隐藏的标签自动恢复显示
- **选择「销退量」指标时**额外显示紫色「销退率」折线（销退量 ÷ 发货量，右侧 Y 轴百分比），tooltip 中同步展示；切换其他指标时折线消失
- 图表数据（`get_chart_options`、`get_chart_data`、`get_product_monthly`）均**排除 `type='aftersale'` 的操作人**对应记录（子查询过滤）

### 数据接口
- `GET /api/shipping/chart-options`：返回渠道列表、省份列表、有数据的产品 ID 集合
- `POST /api/shipping/chart-data`：body 含 `group_by`、`period`（时间维度专用）、日期范围、产品/渠道/地域筛选 ID；返回 `summary` + `items`
- 产品筛选复用 `GET /api/category/tree`
- 筛选变化（排除 chartType/comparisonMode 切换）→ 重新请求后端；chartType/comparisonMode 变化 → 仅重渲 ECharts
