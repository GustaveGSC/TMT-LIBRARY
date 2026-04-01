# 产品库前端组件说明

## Pinia Store 结构
```
src/stores/product/
├── index.js      # 产品库主store
├── finished.js   # 成品store（含FIELD_GETTER、filters含market、FILTER_FIELDS含market）
└── packaged.js   # 产成品store
```

## page-product.vue 说明
- `onMounted`：调用 `maximizeApp()`
- 返回按钮：先 `unmaximizeApp()` 再 `router.back()`
- 顶部导航：概览(SVG inline) / 表格(PNG) / 图片(PNG) / 图表(PNG)
- active 状态：文字加粗 + 主色 + 底部2px橙色指示线，无背景填充
- 数据管理区：导入数据 / 编码规则 / 分类管理 / 标签管理 / **参数管理**
- **数据管理区需要 `product:edit` 权限才显示**（`v-if="canEditProduct"`）
- **概览分类卡片**：每块显示该分类成品总数 + 待处理数量（`cat.unprocessed > 0` 时红色显示「X 个待处理」）；统计均排除 `ignored` 状态产品

## ProductTable.vue 说明
- 双表格布局：成品表（上）+ 产成品表（下）
- 成品表展开行：`<FinishedExpandRow :row="row" @saved="finishedStore.load()" />`
- `expandedCode = ref(null)`，`expandedKeys = computed(() => expandedCode.value ? [expandedCode.value] : [])`
- `:expand-row-keys="expandedKeys"`，`:row-key="r => r.code"`
- 动态列宽：canvas measureText，watch rawItems.length + onMounted 触发
- COL_DEFS 含 market 列（销售市场，排在上市年月前）
- FILTER_FIELDS 含 market
- MARKET_LABELS = `{ domestic: '内销', foreign: '外贸', both: '内外销' }`
- 排序：英文名称、系列名称、销售市场均有排序按钮；产成品清单、生命周期、状态不排序
- **产成品表**：`PK_COL_DEFS` + `pkColWidths`，watch `finishedStore.selectedPackaged` 触发动态列宽计算；`border` + `resizable` + `show-overflow-tooltip`

## FinishedExpandRow.vue 说明
- Props: `row`（Object）；Emits: `saved`
- **权限控制**：无 `product:edit` 权限时隐藏编辑/保存按钮，`···` 按钮始终显示（下载/复制/粘贴）
- **`···` 菜单**：复制（仅查看模式可用）/ 粘贴（仅编辑模式可用）；复制内容不含图片，含参数
- **composable 拆分**：
  - `useFinishedImage(props)` — 图片/裁剪逻辑（localCoverImage / savedCoverImage / cropperInst 等）
  - `useFinishedParams(props)` — 参数区逻辑（GROUP_DEFS 也从此导出）
- **布局**（宽度1000px）：
  ```
  ec-top（编码 + lc-badge + [编辑按钮] + ···按钮）
  ec-row（图片卡片238×238 | 信息卡片flex:1）
  ec-sections（折叠：参数/数据）
  ```
- **查看模式7行**：
  ```
  行1：中文名称（全宽）+ [内销tag if market=domestic/both]
  行2：英文名称（全宽）+ [外贸tag if market=foreign/both]
  行3：品类 / 系列编码 / 上市年月
  行4：型号编码 / 系列名称 / 退市年月
  行5：体积(m³) / 毛重(kg) / 净重(kg)
  行6：包装清单（全宽）
  行7：标签（全宽）
  ```
- **编辑模式7行**（行列结构与查看模式相同）：
  ```
  行1：el-autocomplete(中文名称) + 内销checkbox（最右）
  行2：el-autocomplete(英文名称) + 外贸checkbox（最右）
  行3：el-autocomplete(品类) / el-autocomplete(系列编码) / el-date-picker(上市年月)
  行4：el-autocomplete(型号编码[+?说明按钮]) / el-autocomplete(系列名称) / el-date-picker(退市年月)
  行5：体积/毛重/净重（只读）
  行6：包装清单（只读）
  行7：录入状态 select
  ```
- **型号简码说明按钮**：`?` 圆形按钮位于"型号简码"文字右侧，点击弹出 el-popover 显示 `src/assets/images/image_model_tip.png`
- **保存失败反馈**：`res.success` 为 false 或图片上传失败时 `ElMessage.error(res.message)`
- market checkbox → resolveMarket() → 'domestic'/'foreign'/'both'/''
- eg-lbl 宽80px，居中，背景#faf7f2，右边框分隔
- eg-row min-height:34px，不用固定height

## FinishedExpandRow 参数区说明
- **折叠区 ec-sections 包含两个子节**：参数 / 数据
- **参数节**：4个固定分组横排卡片（尺寸/配置/品牌/其他），由 `GROUP_DEFS` 定义
  - 分组定义（`useFinishedParams.js` 导出）：
    ```js
    { key: 'dimension', label: '尺寸', color: '#c4883a', bg: '#fff7ed' }
    { key: 'config',    label: '配置', color: '#3a7bc8', bg: '#edf4ff' }
    { key: 'brand',     label: '品牌', color: '#9c6fba', bg: '#f5eeff' }
    { key: 'other',     label: '其他', color: '#4a9a5a', bg: '#edf8ef' }
    ```
  - 参数项结构：`{ key_id, key_name, value, state: 'original'|'added'|'deleted' }`
  - `original` 项删除 → 标记红色+删除线+撤回按钮，保存时排除；`added` 项删除 → 直接移除
  - 支持拖动排序（SortableJS），sort_order = 保存时的数组下标
  - **独立编辑模式**：不进入主行编辑也可单独编辑参数（参数区右上角 ✎ 按钮）
  - 添加参数通过 el-dialog（el-select filterable allow-create + el-input），键名可选库中已有或自由输入
  - 键名库通过「参数管理」弹窗维护（page-product.vue 概览页数据管理区）
- **数据节**：占位，含两张卡片（发货数据 / 售后数据），待开发

## ProductChart.vue 说明
- 图表视图，从 `finishedStore.rawItems` 读取数据
- **始终排除 `status === 'ignored'` 的成品**（`activeItems` computed 预过滤，`filteredItems` 在此基础上按状态筛选）
- STATUS_TABS：全部 / 已录入 / 未录入（不含「无需录入」，ignored 已在基础集排除）
- 旭日图：品类（内环，tangential）→ 系列（中环，radial）→ 型号（外环5%，outside radial）
- 品类配色：`CAT_COLORS = ['#c4883a', '#4a8fc0', '#6ab47a', '#9c6fba', '#e07070', '#70aacc', '#e0a040', '#7abcaa']`
- 外环 r0:57% r:62%，中环 r0:36% r:57%，内环 r0:15% r:36%

## ProductImage.vue 说明
- 图片视图，从 `finishedStore.rawItems` 读取数据（复用表格视图已加载的数据，不重复请求）
- 始终过滤掉 `status === 'unrecorded'` 和 `status === 'ignored'` 的成品
- **工具栏**（单行）：搜索框 / 系列多选筛选（el-select filterable multiple） / 市场筛选 Tab / 排序按钮（品号/上市时间） / 数量统计
- **分组展示**：按 `category_name` 分组，每组有可点击标题行（展开=主色实心背景，合拢=普通卡片样式），标题行 sticky 吸顶
- **卡片**：固定高度图片区（180px） + 信息区（品号 + 中文名自动换行），点击弹出详情 dialog
- **详情 dialog**：无原生 header/close，`close-on-click-modal=true`，内嵌 `<FinishedExpandRow :plain="true" :on-close="..." />`，plain 模式下只读（无编辑/复制/粘贴）
- **滚动**：外层 `.grid-scroll`（`flex:1; min-height:0; overflow-y:auto`）负责滚动，内层 `.image-grid` 自然高度，缩小窗口宽度不压缩卡片高度

## ProductParam.vue 说明
- 概览页数据管理区的「参数管理」按钮打开，需要 `product:edit` 权限
- 弹窗固定高度 400px，内容不随 Tab 切换变化
- 布局：顶部4个分组 Tab（尺寸/配置/品牌/其他）+ 左侧键名列表 + 右侧编辑表单
- 支持新增/编辑/排序/删除，删除前调接口返回 usage_count 做二次确认

## ProductTag.vue 说明
- 弹窗内容：左侧标签列表（220px）+ 右侧编辑表单
- 支持新增/编辑/删除，颜色选择器（8预设色 + 自定义）
- 接口路径注意加尾斜杠：`/api/product/tags/`（GET/POST），`/api/product/tags/:id`（PUT/DELETE）

## ProductRules.vue 说明
- 顶部筛选tabs：全部/成品/产成品/半成品/物料
- 表头固定，表体最大高度220px可滚动
- 新增/编辑表单内嵌在弹窗下方（卡片形式）
- 类型颜色：finished=#c4883a，packaged=#4a8fc0，semi=#9c6fba，material=#6ab47a
