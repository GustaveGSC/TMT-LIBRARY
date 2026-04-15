# 售后数据前端组件说明

## page-aftersale.vue 说明
- 路由 `/aftersale`，`onMounted` 调用 `maximizeApp()`，返回按钮先 `unmaximizeApp()` 再 `router.back()`
- 3个 Tab：**待处理**（红色 badge 显示待处理数）/ **图表** / **数据**
- 挂载时调用 `GET /api/aftersale/pending/count` 初始化 badge，工单确认后更新

## AftersaleProcess.vue 说明
- 布局：左侧队列（280px）+ 右侧处理工作区（flex:1）
- 左侧：搜索 + 日期筛选 + 订单卡片列表（选中态主色左边框）
- 右侧工作区：信息栏 / 物料列表（直接展示原始物料，无组别简称合并）/ 备注区（seller_remark + buyer_remark 只读）/ 自动匹配建议 / 原因分配区 / 底部确认/忽略操作
- **自动匹配**：进入工单时自动调用 `POST /api/aftersale/auto-match`，传入 seller_remark；结果显示候选原因（名称+来源+评分条+命中关键词），点击即填入原因行
- **产品候选**：文本匹配的候选排名列表，每行有「应用」按钮；展开后型号明细可逐条点击应用
- **原因分配行**：每行含原因下拉（从原因库选）/ 自定义原因输入 / 涉及产品多选 / 备注输入；支持添加多行（拆分多原因）
- 待处理录入不再包含「售后物料简称」字段（已移除），`return_alias_id` 不随 `POST /api/aftersale/cases` 提交
- 确认 → `POST /api/aftersale/cases`；忽略 → `POST /api/aftersale/cases/:order_no/ignore`
- 需要 `aftersale:edit` 权限才显示确认/忽略/添加原因按钮
- **关键词自动积累**：确认工单时，若原因行有 `reason_id`（原因库条目），在去除 seller 中与 buyer留言重复的长片段得到有效备注后提取候选词写入 `aftersale_keyword_candidate`；须通过质量门禁（词典停用词、长度、日期数字噪声、`_keyword_quality_score` 等），且 **count ≥ 3** 且质量分 ≥ 仓库阈值后才晋升到 `aftersale_reason.keywords`；自定义原因不参与
- **候选词晋升抑制**：同一候选词若在多个原因候选池中高频出现（跨原因热点词），不自动晋升，避免“补偿/更换/问题”等泛词污染原因关键词库
- **原因匹配评分**：`auto-match` 使用加权评分（关键词命中分 + 条件触发的历史相似度分）。关键词阶段会结合词典中的故障核心词/部件词加权；仅当关键词命中候选过少时才拉取近期已确认工单做 `difflib` 比对（限量 + 文本截断 + `selectinload`，见仓库常量 `_AUTO_MATCH_*`）。返回字段含 `matched_keywords`、`keyword_score`、`history_score`、`total_score`、`confidence`、`source`
- **原因词典（标准档）**：停用词 / 故障核心词 / 部件词 / 同义词规则**只来自数据库表**，无硬编码兜底；新环境需运行 `backend/create_reason_keyword_rules.py` 或在「原因词典」Tab 保存一次以写入数据。读写接口 `GET/PUT /api/aftersale/reason-keyword-rules`（PUT 为**全量覆盖**）；后端对词典有短时内存缓存（约 60s），保存后会失效
- **词典自动建议**：工单确认时后端自动生成四类建议写入 `aftersale_dict_suggestion`：① `stopword`（跨原因高频候选词）② `ignore_term`（物料名通用前缀词）③ `promoted_keyword`（自动晋升的关键词）④ `synonym_candidate`（疑似同义词对）；在「原因词典」Tab 顶部显示可折叠的"待优化建议"区块，有 pending 建议时 Tab 按钮显示红点；接受/拒绝接口：`POST /api/aftersale/dictionary-suggestions/<id>/accept`（body: `{target_type?, canonical?}`）/ `reject`；已拒绝建议不再重复触发
- **同义词候选（synonym_candidate）**：两条触发路径：①跨原因中频词（spread 在 [2, global_hot_threshold) 区间）；②同原因内关键词存在子串包含关系；建议 UI 需用户手动填写「归一词」后才能接受，接受后自动写入 `aftersale_reason_synonym_rule`；`meta` 字段存 `reason_ids` / `longer` / `shorter` 供前端展示上下文
- **关键词学习性能**：`_auto_update_reason_keywords` 对候选词晋升与写回做批量处理，减少循环内的 flush/query
- **发货/售后物料简称内联新增**：两个简称 el-select 均支持直接输入新简称，输入内容不在列表中时显示「名称 + 橙色「新」tag」选项，选中后调 POST API 创建并自动回填 id（与具体原因 select 呈现一致）
- **发货简称匹配算法**：`keywords` 为 JSON 列表，存物料名称的有效 token（经 `_parse_product_tokens` 清洗后的词，不含"_"分隔的无效前缀）；候选计算与匹配按绝对命中数优先（主键），覆盖率（matched/len(kws)）仅作次级排序，避免单关键词简称因覆盖率虚高误胜；旧格式 keyword（含"_"）在迁移前兼容回退到 combined_name 包含匹配（迁移接口：`POST /api/aftersale/admin/migrate-alias-keywords`）
- **发货简称自动学习（两级 + 单 key）**：确认工单成功后，对每个 `shipping_alias_id` 仅新增 1 个关键词。①一级：简称名称匹配当前工单物料（code/name 任一 `includes`）；②一级无命中时，从已有 keywords 提取公共模式并过滤 ignore terms 后再匹配。学习写回优先使用 `cleanProductName(name)` 清洗后的有效 token（去掉"_"分隔的无效前缀和 ignore_term 子词，取最后一段），避免将"原材料_塑胶件_书包挂钩盖子"整体存入；新简称首次且两级均未命中时兜底绑定 1 个清洗后 token；多内容面板时优先使用该项勾选物料（`_selectedProducts`）
- **售后简称匹配与匹配依据**：库内匹配走 `match_return_alias`（简称名直命中加权 + 仅累计相似度 ≥ 0.5 的强关键词，总分需过阈值才采纳，降低误匹配）。待处理单 `suggest_product` 返回的 `suggestions` 含 `suggested_return_alias_id`、`suggested_return_alias_source`（`library`/`history`）、`suggested_return_alias_score`（**仅库匹配来源时有分**）；处理页「匹配依据」可展示该分数

## AftersaleReasonLib.vue 说明
- 从 AftersaleProcess.vue 顶部「原因库」按钮打开（`el-dialog`，可 **`draggable`** 拖动）
- Tab：**售后原因库** / **发货物料简称** / **词典**（已移除物料组别简称 Tab、过滤词独立 Tab）
- **词典**（原「原因词典」）：包含停用词/故障核心词/部件词/短词保留/同义词规则 + 物料过滤词卡片；加载 `GET /api/aftersale/reason-keyword-rules`；保存 `PUT` **整表替换**（前端提交五类词条列表 + 同义词，服务端清空对应表后按序插入）。交互为 **tag 区**：回车添加、点击 tag 就地编辑（停用词/核心词/部件词/**短词保留 short_keep_terms**）；**短词保留**用于配置「≤2 字但仍算业务词」的例外（默认其它 ≤2 字会当泛词）；同义词规则支持多个「别名」tag，保存时自动用 `|` 拼成 `pattern`，并可选字面/正则、`replacement`；列表区有统一 **max-height + 细滚动条**，卡片间距与售后主题一致
- 发货简称/售后简称列表支持搜索（按简称名与 `keywords` 过滤，展示「过滤结果/总数」）
- 原因支持：新增 / 编辑 / 删除（删除时查询使用次数，usage>0 时二次确认）
- 原因关键词以 tag 编辑，逗号分隔存储；亦由系统自动积累（见上）
- 更新后 `emit('updated')` 触发 AftersaleProcess 刷新原因选项

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
