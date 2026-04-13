# 售后数据前端组件说明

## page-aftersale.vue 说明
- 路由 `/aftersale`，`onMounted` 调用 `maximizeApp()`，返回按钮先 `unmaximizeApp()` 再 `router.back()`
- 3个 Tab：**待处理**（红色 badge 显示待处理数）/ **图表** / **数据**
- 挂载时调用 `GET /api/aftersale/pending/count` 初始化 badge，工单确认后更新

## AftersaleProcess.vue 说明
- 布局：左侧队列（280px）+ 右侧处理工作区（flex:1）
- 左侧：搜索 + 日期筛选 + 订单卡片列表（选中态主色左边框）
- 右侧工作区：信息栏 / 物料列表（直接展示原始物料，无组别简称合并）/ 备注区（seller_remark + buyer_remark 只读）/ 自动匹配建议 / 原因分配区 / 底部确认/忽略操作
- **自动匹配**：进入工单时自动调用 `POST /api/aftersale/auto-match`，传入 seller_remark；结果显示为芯片（名称+来源标签+置信度条），点击即填入原因行
- **产品候选**：文本匹配的候选排名列表，每行有「应用」按钮；展开后型号明细可逐条点击应用
- **原因分配行**：每行含原因下拉（从原因库选）/ 自定义原因输入 / 涉及产品多选 / 备注输入；支持添加多行（拆分多原因）
- 确认 → `POST /api/aftersale/cases`；忽略 → `POST /api/aftersale/cases/:order_no/ignore`
- 需要 `aftersale:edit` 权限才显示确认/忽略/添加原因按钮
- **关键词自动积累**：确认工单时，若原因行有 `reason_id`（原因库条目），自动从 seller_remark 提取 n-gram 写入 `aftersale_keyword_candidate`；同一词达到阈值（**2次**）后晋升到 `aftersale_reason.keywords`；自定义原因不参与
- **发货/售后物料简称内联新增**：两个简称 el-select 均支持直接输入新简称，输入内容不在列表中时显示「名称 + 橙色「新」tag」选项，选中后调 POST API 创建并自动回填 id（与具体原因 select 呈现一致）
- **发货简称匹配算法**：keywords 兼容存储物料名称/物料代码；候选计算与匹配按绝对命中数优先（主键），覆盖率（matched/len(kws)）仅作次级排序，避免单关键词简称因覆盖率虚高误胜
- **发货简称自动学习（两级 + 单 key）**：确认工单成功后，对每个 `shipping_alias_id` 仅新增 1 个关键词。①一级：简称名称匹配当前工单物料（code/name 任一 `includes`）；②一级无命中时，从已有 keywords 提取公共模式并过滤 ignore terms 后再匹配。学习写回优先物料 `name`（缺失回退 `code`）；新简称首次且两级均未命中时兜底绑定 1 个 key；多内容面板时优先使用该项勾选物料（`_selectedProducts`）

## AftersaleReasonLib.vue 说明
- 从 AftersaleProcess.vue 顶部「原因库」按钮打开（el-dialog）
- 3个 Tab：售后原因库 / 发货物料简称 / 售后物料简称（已移除物料组别简称 Tab）
- 发货简称/售后简称列表支持搜索（按简称名与关键词过滤，显示“过滤结果/总数”）
- 原因支持：新增 / 编辑 / 删除（删除时查询使用次数，usage>0 时二次确认）
- 关键词以 tag 形式编辑，回车添加，逗号分隔存储；关键词也会由系统自动积累（见上）
- 更新后 emit('updated') 触发 AftersaleProcess 刷新原因选项

## AftersaleDashboard.vue 说明
- 布局：左侧筛选面板（260px，style 参考 ShippingDashboard）+ 右侧图表区（待实现）
- 筛选面板：6个可折叠区块，每个区块联动更新候选选项
  - 时间选择：日期范围 + 快捷短语
  - 产品选择：品类 → 系列 → 型号（三级联动，品类/系列选中后下一级才可用）
  - 售后原因选择：原因分类（一级）→ 具体原因（二级）
  - 发货物料选择：发货物料简称 + 售后物料简称（两个独立 select）
  - 渠道选择：渠道名称多选
  - 地域选择：省份 → 城市（两级）
- **联动逻辑**：任一维度筛选变化 → debounce 300ms → POST /api/aftersale/chart-filter-options
  - 对每个维度，接口返回 "应用其他维度过滤后" 该维度的可用候选 id/名称
  - 前端 computed 将 available 集合与静态候选数据交叉，过滤不可用选项
- 静态数据（挂载时加载一次）：/api/category/tree、/api/aftersale/reasons、/api/aftersale/shipping-aliases、/api/aftersale/return-aliases

## AftersaleTable.vue 说明

### 数据加载（两阶段）
- 默认固定查询 `status=confirmed`，忽略项不在数据页显示
- **Phase 1**：`GET /api/aftersale/cases` 只返回基础字段（不含 reasons），表格立即渲染，`reasons: null`
- **Phase 2**：后台 `GET /api/aftersale/cases/reasons?ids=...`（selectinload，无N+1），返回后合并进 items
- `_loadSeq` 计数器：每次 `loadData()` 递增，异步回调检查 `seq === _loadSeq`，防止翻页/筛选后旧请求覆盖新数据

### 筛选选项（懒加载）
- 首次打开任意筛选下拉时触发 `GET /api/aftersale/filter-options`（raw SQL DISTINCT）
- 加载后缓存，不重复请求（`_filterOptLoaded` 标志）

### 列定义（COL_DEFS）
| 列 | key | 说明 |
|---|---|---|
| 订单号 | order_no | 固定左，sort按钮 |
| 产品 | product | model_code + model_name，可按 model_code 筛选 |
| 一级原因 | reason_category | 从 reasons[0] 取 |
| 二级原因 | reason_name | 从 reasons[0] 取；多条时显示 +N badge |
| 购买日期 | purchase_date | |
| 售后日期 | shipped_date | sort按钮 |
| 间隔天 | days_since_purchase | sort按钮 |
| 渠道 | channel_name | |
| 省份 | province | |
| 城市 | city | |
| 县区 | district | |
| 发货物料简称 | shipping_alias | 从 reasons[0] 取 |
| 售后物料简称 | return_alias | 从 reasons[0] 取 |

- 列宽由 Canvas `measureText` 动态计算（采样前100行 + 表头），夹在 min/max 之间
- 表格允许超出容器宽度，水平滚动

### 表头样式（参考 ProductTable）
- `.th-top`（标签 + sort按钮）/ `.th-filter-wrap`（筛选下拉）
- 筛选用 `el-select filterable allow-create @visible-change="onFilterDropdownOpen"`
- 表头不换行（`:deep(.el-table__header th) { white-space: nowrap }`）

### 展开行
- 商家备注 / 买家留言
- 发货物料（来自 `case.products`）
- 同一订单多条 reason 时，主行二级原因列显示 `+N` badge，展开后列出所有原因

### 服务端排序
- `sort_by` / `sort_order` 参数传给后端（白名单字段），前端无客户端排序
