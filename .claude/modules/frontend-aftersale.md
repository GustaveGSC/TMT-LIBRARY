# 售后数据前端组件说明

## page-aftersale.vue 说明
- 路由 `/aftersale`，`onMounted` 调用 `maximizeApp()`，返回按钮先 `unmaximizeApp()` 再 `router.back()`
- 3个 Tab：**待处理**（红色 badge 显示待处理数）/ **图表** / **数据**
- 挂载时调用 `GET /api/aftersale/pending/count` 初始化 badge，工单确认后更新

## AftersaleProcess.vue 说明
- 布局：左侧队列（280px）+ 右侧处理工作区（flex:1）
- 左侧：搜索 + 日期筛选 + 订单卡片列表（选中态主色左边框）
- 右侧工作区：信息栏 / 物料列表 / 备注区（seller_remark + buyer_remark 只读）/ 自动匹配建议 / 原因分配区 / 底部确认/忽略操作
- **自动匹配**：进入工单时自动调用 `POST /api/aftersale/auto-match`，传入 seller_remark；结果显示为芯片（名称+来源标签+置信度条），点击即填入原因行
- **原因分配行**：每行含原因下拉（从原因库选）/ 自定义原因输入 / 涉及产品多选 / 备注输入；支持添加多行（拆分多原因）
- 确认 → `POST /api/aftersale/cases`；忽略 → `POST /api/aftersale/cases/:order_no/ignore`
- 需要 `aftersale:edit` 权限才显示确认/忽略/添加原因按钮

## AftersaleReasonLib.vue 说明
- 从 AftersaleProcess.vue 顶部「原因库」按钮打开（el-dialog）
- 布局：左侧分类 Tab + 原因列表（260px）/ 分隔线 / 右侧编辑表单
- 原因支持：新增 / 编辑 / 删除（删除时查询使用次数，usage>0 时二次确认）
- 关键词以 tag 形式编辑，回车添加，逗号分隔存储；关键词用于自动匹配阶段一
- 更新后 emit('updated') 触发 AftersaleProcess 刷新原因选项

## AftersaleDashboard.vue 说明
- 布局：左侧筛选面板（210px）+ 右侧图表区
- 筛选：日期范围 / 渠道多选 / 省份多选 / 原因分类
- 左侧统计卡片：待处理 / 已处理 / 已忽略 + Top5 常见原因
- 4个维度 Tab：原因分布 / 渠道分布 / 地域分布 / 时间趋势
- 原因/渠道/地域 → 柱图或饼图可切换；时间趋势 → 面积折线图（按月）
- 底部数据明细表（前10条，含占比计算）

## AftersaleTable.vue 说明
- 展示所有已创建工单（confirmed + ignored），支持分页
- 筛选：订单号搜索 / 状态筛选 / 日期范围
- 展开行：显示 seller/buyer 备注 + 原因详情（含涉及产品）+ 物料列表
- 状态标签：confirmed=已确认（success），ignored=已忽略（info）
- 编辑按钮（需 `aftersale:edit`）：弹窗编辑 reasons
