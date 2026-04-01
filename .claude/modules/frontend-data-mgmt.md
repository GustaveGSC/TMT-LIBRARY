# 数据管理 & 发货图表前端组件说明

## page-data-mgmt.vue 说明
- 路由 `/data-mgmt`，`onMounted` 调用 `maximizeApp()`，返回按钮先 `unmaximizeApp()` 再 `router.back()`
- 顶部导航两个 Tab：**导入数据**（DataImport + ReturnImport 左右并排）/ **数据配置**（OperatorConfig + WarehouseConfig 左右并排）
- 右上角「刷新全局数据」按钮：点击先弹二次确认框，确认后调 `POST /api/shipping/resolve-all` → 订阅 SSE 进度（复用 `import/progress/:task_id`），实时显示"xxx / xxx 个订单"；刷新时同时计算发货数量、销退数量、实际数量

## DataImport.vue 说明
- 导入发货清单（xlsx/xls/csv），固定 100px 文件拖放区，选中后显示 Excel SVG 图标
- 导入流程：上传文件获取 task_id → 订阅 SSE → 展示进度条（parsing→parsed→inserting→inserted→resolving→done）
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

## ReturnImport.vue 说明
- 导入销退清单（xlsx/xls/csv），同 DataImport.vue 文件选择区风格
- 导入流程与 DataImport.vue 相同（上传→ task_id → SSE → 进度条）
- **仅处理数量 < 0 的行**，其余行忽略
- **不在导入时过滤仓库**，全量保存至 return_record；仓库过滤在计算 shipping_order_finished 时动态应用
- **订单匹配**：仅保留 ecommerce_order_no 存在于 shipping_record 的行，其余入 `unmatched_rows`
- **DB 去重**：检查 return_record 表 UNIQUE(ecommerce_order_no, product_code, shipped_date)
- **导入后触发重算**：对受影响的订单删除旧成品组合结果并重算（含 return_quantity / actual_quantity）
- **结果卡片**（3列网格）：文件总行数 / 销退行数 / 无匹配订单（可点击）/ 新增记录（accent）/ 跳过重复（可点击）/ 文件内合并（>0时可点击）
- **弹窗列**：5列（平台订单/交易日期/品号/数量/仓库）
- 无日历模块

## OperatorConfig.vue 说明
- 展示所有「最近操作人」列出现过的人员，可设置类型：发货 / 售后 / 未分类
- 类型颜色：shipping=#c4883a，aftersale=#4a8fc0，unknown=#8a7a6a
- 右上角「刷新成品组合」按钮（`stale_count > 0` 时显示），调 `POST /api/shipping/resolve`

## WarehouseConfig.vue 说明
- 展示所有在 return_record 中出现过的仓库名，可配置 is_excluded（排除/正常导入）
- 排除状态：橙红标签 + 橙红边框背景；正常状态：绿色标签
- 调 `GET /api/shipping/warehouses` 加载，`POST /api/shipping/warehouses/filter` 保存

## page-shipping.vue 说明
- 路由 `/shipping`，`onMounted` 调用 `maximizeApp()`，返回按钮先 `unmaximizeApp()`
- 内嵌 ShippingDashboard（左右两栏布局：筛选面板 + 图表区）

## ShippingDashboard.vue 说明
- 左侧筛选面板（230px）：日期范围 + 时间粒度 segmented（月/季度/半年/年）、品类/系列/型号级联选择、渠道多选、省份多选、重置按钮
- 右侧顶部工具栏：图表类型图标（柱/折/饼/地图）+ 分隔线 + 同比/环比按钮；最左显示下钻面包屑，最右显示数据指标选择
- 右侧内容区：ECharts 图表（占满）+ 底部聚合维度切换 chip（产品/渠道/地域/时间）

### 聚合维度与图表类型
| 维度 | 可用图表 | 默认 |
|------|---------|------|
| 产品（品类→系列→型号自动下钻） | bar、pie | bar |
| 渠道（渠道→渠道商自动下钻） | bar、pie | bar |
| 地域（省份→城市→县区自动下钻） | map、bar | map |
| 时间 | 同比（yoy）、环比（mom） | 同比 |

### 时间维度
- 切换到时间维度自动激活「同比」；可手动切换为「环比」
- 时间粒度（月/季度/半年/年）绑定左侧 segmented，切换后重新请求数据
- **同比（buildYoyOption）**：X 轴为完整一年期号（月 01-12 / Q1-Q4 / 上下半年），每年一个柱状系列；缺失期号显示 0
- **环比（buildMomOption）**：顺序柱状图 + 环比增长率折线（双 Y 轴）
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
