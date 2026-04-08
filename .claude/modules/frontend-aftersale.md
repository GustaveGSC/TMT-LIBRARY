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
- **关键词自动积累**：确认工单时，若原因行有 `reason_id`（原因库条目），自动从 seller_remark 提取 n-gram 写入 `aftersale_keyword_candidate`；同一词达到阈值（3次）后晋升到 `aftersale_reason.keywords`；自定义原因不参与

## AftersaleReasonLib.vue 说明
- 从 AftersaleProcess.vue 顶部「原因库」按钮打开（el-dialog）
- 3个 Tab：售后原因库 / 发货物料简称 / 售后物料简称（已移除物料组别简称 Tab）
- 原因支持：新增 / 编辑 / 删除（删除时查询使用次数，usage>0 时二次确认）
- 关键词以 tag 形式编辑，回车添加，逗号分隔存储；关键词也会由系统自动积累（见上）
- 更新后 emit('updated') 触发 AftersaleProcess 刷新原因选项

## AftersaleDashboard.vue 说明
- 布局：左侧筛选面板（210px）+ 右侧图表区
- 筛选：日期范围 / 渠道多选 / 省份多选 / 原因分类
- 左侧统计卡片：待处理 / 已处理 / 已忽略 + Top5 常见原因
- 4个维度 Tab：原因分布 / 渠道分布 / 地域分布 / 时间趋势
- 原因/渠道/地域 → 柱图或饼图可切换；时间趋势 → 面积折线图（按月）
- 底部数据明细表（前10条，含占比计算）

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
